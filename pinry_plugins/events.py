import logging
import copy
import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

_event_context = threading.local()


def _get_current_context() -> Dict[str, Any]:
    return getattr(_event_context, "data", {})


def set_event_context(**kwargs) -> None:
    if not hasattr(_event_context, "data"):
        _event_context.data = {}
    _event_context.data.update(kwargs)


def clear_event_context() -> None:
    if hasattr(_event_context, "data"):
        _event_context.data = {}


@contextmanager
def event_context(**kwargs):
    old = _get_current_context().copy()
    set_event_context(**kwargs)
    try:
        yield
    finally:
        _event_context.data = old


class EventType(str, Enum):
    PIN_PRE_CREATE = "pin.pre_create"
    PIN_POST_CREATE = "pin.post_create"
    PIN_PRE_UPDATE = "pin.pre_update"
    PIN_POST_UPDATE = "pin.post_update"
    PIN_PRE_DELETE = "pin.pre_delete"
    PIN_POST_DELETE = "pin.post_delete"
    PIN_SYNC = "pin.sync"

    IMAGE_PRE_CREATE = "image.pre_create"
    IMAGE_POST_CREATE = "image.post_create"
    IMAGE_PRE_DELETE = "image.pre_delete"
    IMAGE_POST_DELETE = "image.post_delete"

    THUMBNAIL_PRE_CREATE = "thumbnail.pre_create"
    THUMBNAIL_POST_CREATE = "thumbnail.post_create"

    BOARD_PRE_CREATE = "board.pre_create"
    BOARD_POST_CREATE = "board.post_create"
    BOARD_PRE_UPDATE = "board.pre_update"
    BOARD_POST_UPDATE = "board.post_update"
    BOARD_PRE_DELETE = "board.pre_delete"
    BOARD_POST_DELETE = "board.post_delete"

    FETCH_PREVIEW_START = "fetch.preview.start"
    FETCH_PREVIEW_SUCCESS = "fetch.preview.success"
    FETCH_PREVIEW_FAILURE = "fetch.preview.failure"


@dataclass
class Event:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    def clone(self, **overrides) -> "Event":
        data = {
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": copy.deepcopy(self.payload),
            "context": copy.deepcopy(self.context),
        }
        data.update(overrides)
        return Event(**data)


class EventBus:
    _instance: Optional["EventBus"] = None
    _listeners: Dict[EventType, List[Callable[[Event], None]]]

    def __new__(cls: Type["EventBus"]) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._listeners = {}
        return cls._instance

    def subscribe(self, event_type: EventType, listener: Callable[[Event], None]) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: EventType, listener: Callable[[Event], None]) -> None:
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(listener)
            except ValueError:
                pass

    def dispatch(self, event: Event, fail_silently: bool = True) -> List[Exception]:
        errors: List[Exception] = []
        listeners = self._listeners.get(event.type, [])
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                errors.append(exc)
                logger.exception(
                    "Error occurred while dispatching event %s to listener %s: %s",
                    event.type.value,
                    getattr(listener, "__name__", repr(listener)),
                    exc,
                )
                if not fail_silently:
                    raise
        return errors


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus


def dispatch_event(event_type: EventType, payload: Dict[str, Any] = None, context: Dict[str, Any] = None, fail_silently: bool = True) -> Event:
    merged_context = _get_current_context().copy()
    if context:
        merged_context.update(context)
    event = Event(
        type=event_type,
        payload=payload or {},
        context=merged_context,
    )
    get_event_bus().dispatch(event, fail_silently=fail_silently)
    return event


def on(event_type: EventType) -> Callable:
    def decorator(func: Callable[[Event], None]) -> Callable[[Event], None]:
        get_event_bus().subscribe(event_type, func)
        return func
    return decorator
