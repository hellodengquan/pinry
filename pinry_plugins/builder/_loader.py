import logging

from django.conf import settings
from django.utils.module_loading import import_string

from pinry_plugins.events import (
    EventType,
    Event,
    get_event_bus,
)

_plugins = getattr(settings, "ENABLED_PLUGINS", [])
_plugin_instances = []

LEGACY_METHOD_MAP = {
    "process_image_pre_creation": EventType.IMAGE_PRE_CREATE,
    "process_image_post_create": EventType.IMAGE_POST_CREATE,
    "process_image_pre_delete": EventType.IMAGE_PRE_DELETE,
    "process_image_post_delete": EventType.IMAGE_POST_DELETE,
    "process_thumbnail_pre_creation": EventType.THUMBNAIL_PRE_CREATE,
    "process_thumbnail_post_create": EventType.THUMBNAIL_POST_CREATE,
    "process_pin_pre_create": EventType.PIN_PRE_CREATE,
    "process_pin_post_create": EventType.PIN_POST_CREATE,
    "process_pin_pre_update": EventType.PIN_PRE_UPDATE,
    "process_pin_post_update": EventType.PIN_POST_UPDATE,
    "process_pin_pre_delete": EventType.PIN_PRE_DELETE,
    "process_pin_post_delete": EventType.PIN_POST_DELETE,
    "process_pin_sync": EventType.PIN_SYNC,
    "process_board_pre_create": EventType.BOARD_PRE_CREATE,
    "process_board_post_create": EventType.BOARD_POST_CREATE,
    "process_board_pre_update": EventType.BOARD_PRE_UPDATE,
    "process_board_post_update": EventType.BOARD_POST_UPDATE,
    "process_board_pre_delete": EventType.BOARD_PRE_DELETE,
    "process_board_post_delete": EventType.BOARD_POST_DELETE,
    "process_fetch_preview_start": EventType.FETCH_PREVIEW_START,
    "process_fetch_preview_success": EventType.FETCH_PREVIEW_SUCCESS,
    "process_fetch_preview_failure": EventType.FETCH_PREVIEW_FAILURE,
}


def _wrap_legacy_method(plugin, method_name: str) -> callable:
    method = getattr(plugin, method_name)

    def _legacy_handler(event: Event):
        try:
            kwargs = {"django_settings": settings}
            if "image_instance" in event.payload:
                kwargs["image_instance"] = event.payload["image_instance"]
            if "thumbnail_instance" in event.payload:
                kwargs["thumbnail_instance"] = event.payload["thumbnail_instance"]
            if "pin_instance" in event.payload:
                kwargs["pin_instance"] = event.payload["pin_instance"]
            if "board_instance" in event.payload:
                kwargs["board_instance"] = event.payload["board_instance"]
            if "instance" in event.payload:
                kwargs["instance"] = event.payload["instance"]
            for k, v in event.payload.items():
                if k not in kwargs:
                    kwargs[k] = v
            kwargs["event"] = event
            method(**kwargs)
        except Exception:
            logging.exception(
                "Error occurs while processing plugin method %s for plugin %s",
                method_name,
                plugin,
            )

    return _legacy_handler


def _register_plugin_events(plugin) -> None:
    bus = get_event_bus()
    for method_name, event_type in LEGACY_METHOD_MAP.items():
        if hasattr(plugin, method_name):
            bus.subscribe(event_type, _wrap_legacy_method(plugin, method_name))
    handle_event_method = getattr(plugin, "handle_event", None)
    if callable(handle_event_method):
        def _universal_handler(event: Event):
            try:
                handle_event_method(event)
            except Exception:
                logging.exception(
                    "Error occurs while calling handle_event for plugin %s",
                    plugin,
                )
        for event_type in EventType:
            bus.subscribe(event_type, _universal_handler)


def _load_plugins():
    for plugin_path in _plugins:
        plugin_cls = import_string(plugin_path)
        try:
            plugin_instance = plugin_cls()
            _plugin_instances.append(plugin_instance)
            _register_plugin_events(plugin_instance)
        except Exception:
            logging.exception(
                "Failed to load plugin %s", plugin_path
            )


def init():
    _load_plugins()
