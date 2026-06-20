import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from django.dispatch import receiver
from django.utils.module_loading import import_string
from django.conf import settings
from django.db import models

from core.models import Image
from django_images.models import Thumbnail
from pinry_plugins.builder.contracts import (
    PluginContractViolationError,
    describe_plugin,
    get_plugin_capabilities,
    validate_plugin_contract,
)

_plugins = getattr(settings, "ENABLED_PLUGINS", [])
_plugin_strict_mode = getattr(settings, "PLUGIN_STRICT_CONTRACT", False)
_plugin_error_threshold = getattr(settings, "PLUGIN_ERROR_THRESHOLD", 5)
_plugin_error_window = getattr(settings, "PLUGIN_ERROR_WINDOW", 60)
_plugin_circuit_breaker_enabled = getattr(
    settings, "PLUGIN_CIRCUIT_BREAKER_ENABLED", True
)
_plugin_recovery_timeout = getattr(settings, "PLUGIN_RECOVERY_TIMEOUT", 300)

_plugin_instances: List[Any] = []
_plugin_registry: Dict[str, Dict[str, Any]] = {}
_circuit_breakers: Dict[str, "PluginCircuitBreaker"] = {}

logger = logging.getLogger(__name__)


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class PluginCircuitBreaker:
    def __init__(
        self,
        plugin_key: str,
        error_threshold: int = 5,
        error_window: int = 60,
        recovery_timeout: int = 300,
        enabled: bool = True,
    ):
        self.plugin_key = plugin_key
        self.error_threshold = error_threshold
        self.error_window = error_window
        self.recovery_timeout = recovery_timeout
        self.enabled = enabled

        self.state = CircuitState.CLOSED
        self.error_times: Deque[float] = deque()
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
        self.total_errors = 0
        self.total_successes = 0
        self.trip_count = 0

    def _prune_old_errors(self, now: float) -> None:
        cutoff = now - self.error_window
        while self.error_times and self.error_times[0] < cutoff:
            self.error_times.popleft()

    def _error_count(self, now: float) -> int:
        self._prune_old_errors(now)
        return len(self.error_times)

    def allow_request(self) -> bool:
        if not self.enabled:
            return True

        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if (
                self.last_failure_time
                and (now - self.last_failure_time) >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                logger.info(
                    "Plugin '%s' circuit breaker transitioning to HALF_OPEN",
                    self.plugin_key,
                )
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return True

    def record_success(self) -> None:
        now = time.time()
        self.last_success_time = now
        self.total_successes += 1

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.error_times.clear()
            logger.info(
                "Plugin '%s' circuit breaker recovered, state CLOSED",
                self.plugin_key,
            )

    def record_failure(self) -> None:
        now = time.time()
        self.last_failure_time = now
        self.total_errors += 1
        self.error_times.append(now)

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.trip_count += 1
            logger.warning(
                "Plugin '%s' circuit breaker tripped again (HALF_OPEN -> OPEN), "
                "trip #%d",
                self.plugin_key,
                self.trip_count,
            )
            return

        if self.state == CircuitState.CLOSED and self.enabled:
            error_count = self._error_count(now)
            if error_count >= self.error_threshold:
                self.state = CircuitState.OPEN
                self.trip_count += 1
                logger.warning(
                    "Plugin '%s' circuit breaker tripped (%d errors in %ds), "
                    "trip #%d",
                    self.plugin_key,
                    error_count,
                    self.error_window,
                    self.trip_count,
                )

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        self._prune_old_errors(now)
        return {
            "plugin": self.plugin_key,
            "state": self.state,
            "enabled": self.enabled,
            "error_threshold": self.error_threshold,
            "error_window_seconds": self.error_window,
            "recovery_timeout_seconds": self.recovery_timeout,
            "current_error_count": len(self.error_times),
            "total_errors": self.total_errors,
            "total_successes": self.total_successes,
            "trip_count": self.trip_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "seconds_since_last_failure": (
                now - self.last_failure_time if self.last_failure_time else None
            ),
        }


def get_plugin_instances() -> List[Any]:
    return list(_plugin_instances)


def get_plugin_registry() -> Dict[str, Dict[str, Any]]:
    return dict(_plugin_registry)


def get_plugins_by_capability(capability: str) -> List[Any]:
    result = []
    for plugin in _plugin_instances:
        key = _plugin_key(plugin)
        cb = _circuit_breakers.get(key)
        if cb and not cb.allow_request():
            continue
        caps = get_plugin_capabilities(plugin)
        if caps.get(capability, False):
            result.append(plugin)
    return result


def get_circuit_breaker_status() -> Dict[str, Dict[str, Any]]:
    return {key: cb.get_status() for key, cb in _circuit_breakers.items()}


def reset_circuit_breakers() -> None:
    for cb in _circuit_breakers.values():
        cb.state = CircuitState.CLOSED
        cb.error_times.clear()
        cb.last_failure_time = None
        cb.trip_count = 0
    logger.info("All plugin circuit breakers reset")


def _plugin_key(plugin_instance: Any) -> str:
    return f"{type(plugin_instance).__module__}.{type(plugin_instance).__name__}"


def _register_plugin(plugin_path: str, plugin_instance: Any) -> None:
    info = describe_plugin(plugin_instance)
    info["path"] = plugin_path
    _plugin_registry[plugin_path] = info

    key = _plugin_key(plugin_instance)
    if key not in _circuit_breakers:
        _circuit_breakers[key] = PluginCircuitBreaker(
            plugin_key=key,
            error_threshold=_plugin_error_threshold,
            error_window=_plugin_error_window,
            recovery_timeout=_plugin_recovery_timeout,
            enabled=_plugin_circuit_breaker_enabled,
        )


def _load_plugins():
    for plugin_path in _plugins:
        plugin_cls = import_string(plugin_path)
        plugin_instance = plugin_cls()

        missing = validate_plugin_contract(
            plugin_instance, strict=_plugin_strict_mode
        )
        if missing and _plugin_strict_mode:
            raise PluginContractViolationError(plugin_path, missing)

        _plugin_instances.append(plugin_instance)
        _register_plugin(plugin_path, plugin_instance)

        caps = get_plugin_capabilities(plugin_instance)
        enabled = [k for k, v in caps.items() if v]
        logger.info(
            "Loaded plugin '%s' with hooks: %s",
            plugin_path,
            ", ".join(enabled) if enabled else "(none)",
        )


def _dispatch_plugin_hook(hook_name: str, **kwargs) -> None:
    for plugin in _plugin_instances:
        key = _plugin_key(plugin)
        cb = _circuit_breakers.get(key)

        if cb and not cb.allow_request():
            continue

        hook_fn = getattr(plugin, hook_name, None)
        if hook_fn is None or not callable(hook_fn):
            continue

        try:
            hook_fn(**kwargs)
            if cb:
                cb.record_success()
        except Exception:
            logger.exception(
                "Error in plugin hook '%s' for plugin %s",
                hook_name,
                key,
            )
            if cb:
                cb.record_failure()


@receiver(models.signals.pre_save, sender=Image)
def process_image_pre_creation(sender, instance: Image, **kwargs):
    if instance.pk is not None:
        return
    _dispatch_plugin_hook(
        "process_image_pre_creation",
        django_settings=settings,
        image_instance=instance,
    )


@receiver(models.signals.pre_save, sender=Thumbnail)
def process_thumbnail_pre_creation(sender, instance: Thumbnail, **kwargs):
    if instance.pk is not None:
        return
    _dispatch_plugin_hook(
        "process_thumbnail_pre_creation",
        django_settings=settings,
        thumbnail_instance=instance,
    )


def dispatch_preview_pre_fetch(preview_request) -> None:
    _dispatch_plugin_hook(
        "preview_pre_fetch",
        django_settings=settings,
        preview_request=preview_request,
    )


def dispatch_preview_post_fetch(preview_request, preview_result) -> Dict[str, Any]:
    plugin_data: Dict[str, Any] = {}
    for plugin in _plugin_instances:
        key = _plugin_key(plugin)
        cb = _circuit_breakers.get(key)

        if cb and not cb.allow_request():
            continue

        hook_fn = getattr(plugin, "preview_post_fetch", None)
        if hook_fn is None or not callable(hook_fn):
            continue

        try:
            result = hook_fn(
                django_settings=settings,
                preview_request=preview_request,
                preview_result=preview_result,
            )
            if result and isinstance(result, dict):
                plugin_data[type(plugin).__name__] = result
            if cb:
                cb.record_success()
        except Exception:
            logger.exception(
                "Error in plugin hook 'preview_post_fetch' for plugin %s",
                key,
            )
            if cb:
                cb.record_failure()

    return plugin_data


def dispatch_preview_on_error(preview_request, preview_error) -> None:
    _dispatch_plugin_hook(
        "preview_on_error",
        django_settings=settings,
        preview_request=preview_request,
        preview_error=preview_error,
    )


def init():
    _load_plugins()
