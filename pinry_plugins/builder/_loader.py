import logging
from typing import Any, Dict, List

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
_plugin_instances: List[Any] = []
_plugin_registry: Dict[str, Dict[str, Any]] = {}


def get_plugin_instances() -> List[Any]:
    return list(_plugin_instances)


def get_plugin_registry() -> Dict[str, Dict[str, Any]]:
    return dict(_plugin_registry)


def get_plugins_by_capability(capability: str) -> List[Any]:
    result = []
    for plugin in _plugin_instances:
        caps = get_plugin_capabilities(plugin)
        if caps.get(capability, False):
            result.append(plugin)
    return result


def _register_plugin(plugin_path: str, plugin_instance: Any) -> None:
    info = describe_plugin(plugin_instance)
    info["path"] = plugin_path
    _plugin_registry[plugin_path] = info


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
        logging.info(
            "Loaded plugin '%s' with hooks: %s",
            plugin_path,
            ", ".join(enabled) if enabled else "(none)",
        )


def _dispatch_plugin_hook(hook_name: str, **kwargs) -> None:
    for plugin in _plugin_instances:
        hook_fn = getattr(plugin, hook_name, None)
        if hook_fn is None or not callable(hook_fn):
            continue
        try:
            hook_fn(**kwargs)
        except Exception:
            logging.exception(
                "Error in plugin hook '%s' for plugin %s",
                hook_name,
                type(plugin).__name__,
            )


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
        except Exception:
            logging.exception(
                "Error in plugin hook 'preview_post_fetch' for plugin %s",
                type(plugin).__name__,
            )
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
