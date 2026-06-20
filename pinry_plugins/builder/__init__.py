from . import _loader
from .contracts import (
    ALL_SUPPORTED_HOOKS,
    ImagePluginProtocol,
    PinryPluginProtocol,
    PluginContractViolationError,
    PreviewPluginProtocol,
    REQUIRED_IMAGE_PLUGIN_METHODS,
    REQUIRED_PREVIEW_PLUGIN_METHODS,
    describe_plugin,
    get_plugin_capabilities,
    validate_plugin_contract,
)
from ._loader import (
    CircuitState,
    PluginCircuitBreaker,
    dispatch_preview_on_error,
    dispatch_preview_post_fetch,
    dispatch_preview_pre_fetch,
    get_circuit_breaker_status,
    get_plugin_instances,
    get_plugin_registry,
    get_plugins_by_capability,
    reset_circuit_breakers,
)

__all__ = [
    "init",
    "ALL_SUPPORTED_HOOKS",
    "ImagePluginProtocol",
    "PinryPluginProtocol",
    "PluginContractViolationError",
    "PreviewPluginProtocol",
    "REQUIRED_IMAGE_PLUGIN_METHODS",
    "REQUIRED_PREVIEW_PLUGIN_METHODS",
    "describe_plugin",
    "get_plugin_capabilities",
    "validate_plugin_contract",
    "CircuitState",
    "PluginCircuitBreaker",
    "dispatch_preview_on_error",
    "dispatch_preview_post_fetch",
    "dispatch_preview_pre_fetch",
    "get_circuit_breaker_status",
    "get_plugin_instances",
    "get_plugin_registry",
    "get_plugins_by_capability",
    "reset_circuit_breakers",
]


def init():
    _loader.init()
