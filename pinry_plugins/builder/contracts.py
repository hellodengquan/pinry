from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.models import Image
from core.services.preview_service import (
    PreviewError,
    PreviewRequest,
    PreviewResult,
)
from django_images.models import Thumbnail


@runtime_checkable
class PreviewPluginProtocol(Protocol):
    def preview_pre_fetch(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
    ) -> None: ...

    def preview_post_fetch(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
        preview_result: PreviewResult,
    ) -> Optional[Dict[str, Any]]: ...

    def preview_on_error(
        self,
        django_settings: Any,
        preview_request: PreviewRequest,
        preview_error: PreviewError,
    ) -> None: ...


@runtime_checkable
class ImagePluginProtocol(Protocol):
    def process_image_pre_creation(
        self,
        django_settings: Any,
        image_instance: Image,
    ) -> None: ...

    def process_thumbnail_pre_creation(
        self,
        django_settings: Any,
        thumbnail_instance: Thumbnail,
    ) -> None: ...


@runtime_checkable
class PinryPluginProtocol(ImagePluginProtocol, PreviewPluginProtocol, Protocol):
    pass


class PluginContractViolationError(Exception):
    def __init__(self, plugin_class: str, missing_methods: list):
        self.plugin_class = plugin_class
        self.missing_methods = missing_methods
        message = (
            f"Plugin '{plugin_class}' does not implement required contract. "
            f"Missing methods: {', '.join(missing_methods)}"
        )
        super().__init__(message)


REQUIRED_IMAGE_PLUGIN_METHODS = [
    "process_image_pre_creation",
    "process_thumbnail_pre_creation",
]

REQUIRED_PREVIEW_PLUGIN_METHODS = [
    "preview_pre_fetch",
    "preview_post_fetch",
    "preview_on_error",
]

ALL_SUPPORTED_HOOKS = (
    REQUIRED_IMAGE_PLUGIN_METHODS + REQUIRED_PREVIEW_PLUGIN_METHODS
)


def validate_plugin_contract(plugin_instance: Any, strict: bool = False) -> list:
    missing_methods = []
    available_methods = [m for m in ALL_SUPPORTED_HOOKS if hasattr(plugin_instance, m)]

    if strict:
        for method in ALL_SUPPORTED_HOOKS:
            if not hasattr(plugin_instance, method):
                missing_methods.append(method)
    else:
        pass

    return missing_methods


def get_plugin_capabilities(plugin_instance: Any) -> Dict[str, bool]:
    return {
        method: callable(getattr(plugin_instance, method, None))
        for method in ALL_SUPPORTED_HOOKS
    }


def describe_plugin(plugin_instance: Any) -> Dict[str, Any]:
    return {
        "class": type(plugin_instance).__name__,
        "module": type(plugin_instance).__module__,
        "capabilities": get_plugin_capabilities(plugin_instance),
        "implements_image_protocol": isinstance(
            plugin_instance, ImagePluginProtocol
        ),
        "implements_preview_protocol": isinstance(
            plugin_instance, PreviewPluginProtocol
        ),
        "implements_full_protocol": isinstance(
            plugin_instance, PinryPluginProtocol
        ),
    }
