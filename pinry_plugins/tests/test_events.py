import os
import django
from io import BytesIO
from unittest import mock

from django.test import TestCase
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile

from pinry_plugins.events import (
    EventType,
    Event,
    EventBus,
    get_event_bus,
    dispatch_event,
    on,
    event_context,
    set_event_context,
    clear_event_context,
    _get_current_context,
)
from pinry_plugins.builder._loader import LEGACY_METHOD_MAP, _wrap_legacy_method
from core.models import Image, Pin
from django_images.models import Thumbnail


TEST_IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'docs/src/imgs/logo-dark.png'
)


def _make_test_image():
    image = Image.objects.create(image=open(TEST_IMAGE_PATH, 'rb'))
    Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
    return image


class EventTypeEnumTests(TestCase):
    def test_event_type_values_are_unique(self):
        values = [e.value for e in EventType]
        self.assertEqual(len(values), len(set(values)))

    def test_event_type_is_string_subclass(self):
        self.assertTrue(isinstance(EventType.PIN_PRE_CREATE, str))

    def test_all_pin_events_have_expected_prefix(self):
        pin_events = [e for e in EventType if e.value.startswith("pin.")]
        expected = {"pin.pre_create", "pin.post_create", "pin.pre_update",
                    "pin.post_update", "pin.pre_delete", "pin.post_delete", "pin.sync"}
        self.assertEqual({e.value for e in pin_events}, expected)

    def test_fetch_events_have_expected_states(self):
        fetch_events = [e for e in EventType if e.value.startswith("fetch.")]
        expected = {"fetch.preview.start", "fetch.preview.success", "fetch.preview.failure"}
        self.assertEqual({e.value for e in fetch_events}, expected)


class EventDataClassTests(TestCase):
    def test_event_creation_defaults(self):
        event = Event(type=EventType.PIN_PRE_CREATE)
        self.assertEqual(event.type, EventType.PIN_PRE_CREATE)
        self.assertEqual(event.payload, {})
        self.assertEqual(event.context, {})
        self.assertIsNotNone(event.timestamp)

    def test_event_creation_with_payload_and_context(self):
        payload = {"pin_instance": "test", "extra": "data"}
        context = {"user": "admin", "source": "test"}
        event = Event(type=EventType.PIN_POST_CREATE, payload=payload, context=context)
        self.assertEqual(event.payload, payload)
        self.assertEqual(event.context, context)

    def test_event_clone_is_deep_copy(self):
        original = Event(
            type=EventType.PIN_PRE_CREATE,
            payload={"list": [1, 2, 3], "nested": {"key": "value"}},
            context={"ctx_list": [4, 5, 6]},
        )
        cloned = original.clone()
        original.payload["list"].append(4)
        original.payload["nested"]["key"] = "modified"
        original.context["ctx_list"].append(7)
        self.assertEqual(cloned.payload["list"], [1, 2, 3])
        self.assertEqual(cloned.payload["nested"]["key"], "value")
        self.assertEqual(cloned.context["ctx_list"], [4, 5, 6])

    def test_event_clone_with_overrides(self):
        original = Event(type=EventType.PIN_PRE_CREATE, payload={"a": 1})
        cloned = original.clone(type=EventType.PIN_POST_CREATE, payload={"b": 2})
        self.assertEqual(cloned.type, EventType.PIN_POST_CREATE)
        self.assertEqual(cloned.payload, {"b": 2})


class EventBusSubscribeTests(TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.bus._listeners = {}

    def test_subscribe_adds_listener(self):
        def handler(event):
            pass
        self.bus.subscribe(EventType.PIN_PRE_CREATE, handler)
        self.assertIn(handler, self.bus._listeners[EventType.PIN_PRE_CREATE])

    def test_subscribe_multiple_listeners_same_event(self):
        def h1(event): pass
        def h2(event): pass
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h1)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h2)
        self.assertEqual(len(self.bus._listeners[EventType.PIN_PRE_CREATE]), 2)

    def test_unsubscribe_removes_listener(self):
        def handler(event): pass
        self.bus.subscribe(EventType.PIN_PRE_CREATE, handler)
        self.bus.unsubscribe(EventType.PIN_PRE_CREATE, handler)
        self.assertNotIn(handler, self.bus._listeners[EventType.PIN_PRE_CREATE])

    def test_unsubscribe_nonexistent_listener_no_error(self):
        def handler(event): pass
        self.bus.unsubscribe(EventType.PIN_PRE_CREATE, handler)

    def test_unsubscribe_nonexistent_event_no_error(self):
        def handler(event): pass
        self.bus.unsubscribe(EventType.PIN_POST_DELETE, handler)


class EventBusDispatchTests(TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.bus._listeners = {}

    def test_dispatch_calls_listeners_in_order(self):
        call_order = []
        def h1(event): call_order.append("h1")
        def h2(event): call_order.append("h2")
        def h3(event): call_order.append("h3")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h1)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h2)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h3)
        event = Event(type=EventType.PIN_PRE_CREATE)
        self.bus.dispatch(event)
        self.assertEqual(call_order, ["h1", "h2", "h3"])

    def test_dispatch_passes_correct_event(self):
        received = []
        def handler(event):
            received.append(event)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, handler)
        event = Event(type=EventType.PIN_PRE_CREATE, payload={"key": "value"})
        self.bus.dispatch(event)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].type, EventType.PIN_PRE_CREATE)
        self.assertEqual(received[0].payload["key"], "value")

    def test_dispatch_only_calls_listeners_for_matching_event_type(self):
        pin_calls = []
        image_calls = []
        def pin_handler(event): pin_calls.append(event)
        def image_handler(event): image_calls.append(event)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, pin_handler)
        self.bus.subscribe(EventType.IMAGE_PRE_CREATE, image_handler)
        self.bus.dispatch(Event(type=EventType.PIN_PRE_CREATE))
        self.assertEqual(len(pin_calls), 1)
        self.assertEqual(len(image_calls), 0)

    def test_dispatch_returns_error_list(self):
        def good_handler(event): pass
        def bad_handler(event): raise RuntimeError("boom")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, good_handler)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, bad_handler)
        errors = self.bus.dispatch(Event(type=EventType.PIN_PRE_CREATE))
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(str(errors[0]), "boom")

    def test_dispatch_fail_silently_false_raises(self):
        def bad_handler(event): raise RuntimeError("boom")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, bad_handler)
        with self.assertRaises(RuntimeError):
            self.bus.dispatch(Event(type=EventType.PIN_PRE_CREATE), fail_silently=False)


class PluginFaultIsolationTests(TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.bus._listeners = {}

    def test_single_plugin_failure_does_not_affect_others(self):
        results = []
        def good1(event): results.append("good1")
        def bad(event): raise RuntimeError("bad plugin")
        def good2(event): results.append("good2")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, good1)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, bad)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, good2)
        errors = self.bus.dispatch(Event(type=EventType.PIN_PRE_CREATE))
        self.assertEqual(results, ["good1", "good2"])
        self.assertEqual(len(errors), 1)

    def test_all_plugins_fail_returns_all_errors(self):
        def h1(event): raise ValueError("err1")
        def h2(event): raise TypeError("err2")
        def h3(event): raise RuntimeError("err3")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h1)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h2)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, h3)
        errors = self.bus.dispatch(Event(type=EventType.PIN_PRE_CREATE))
        self.assertEqual(len(errors), 3)
        error_types = [type(e).__name__ for e in errors]
        self.assertIn("ValueError", error_types)
        self.assertIn("TypeError", error_types)
        self.assertIn("RuntimeError", error_types)

    def test_event_payload_not_modified_by_plugin(self):
        original_payload = {"data": [1, 2, 3]}
        event = Event(type=EventType.PIN_PRE_CREATE, payload=original_payload)
        def bad_plugin(event):
            event.payload["data"].append(999)
            raise RuntimeError("fail")
        self.bus.subscribe(EventType.PIN_PRE_CREATE, bad_plugin)
        self.bus.dispatch(event)
        self.assertEqual(event.payload["data"], [1, 2, 3, 999])


class ContextManagementTests(TestCase):
    def setUp(self):
        clear_event_context()

    def tearDown(self):
        clear_event_context()

    def test_set_event_context_adds_key(self):
        set_event_context(user="test_user")
        self.assertEqual(_get_current_context()["user"], "test_user")

    def test_set_event_context_merges(self):
        set_event_context(a=1)
        set_event_context(b=2)
        ctx = _get_current_context()
        self.assertEqual(ctx["a"], 1)
        self.assertEqual(ctx["b"], 2)

    def test_clear_event_context(self):
        set_event_context(a=1, b=2)
        clear_event_context()
        self.assertEqual(_get_current_context(), {})

    def test_event_context_manager_restores_old(self):
        set_event_context(existing="keep")
        with event_context(new="temp"):
            ctx = _get_current_context()
            self.assertEqual(ctx["existing"], "keep")
            self.assertEqual(ctx["new"], "temp")
        after = _get_current_context()
        self.assertEqual(after["existing"], "keep")
        self.assertNotIn("new", after)

    def test_event_context_manager_restores_on_exception(self):
        set_event_context(existing="keep")
        try:
            with event_context(new="temp"):
                raise RuntimeError("test")
        except RuntimeError:
            pass
        after = _get_current_context()
        self.assertEqual(after["existing"], "keep")
        self.assertNotIn("new", after)

    def test_dispatch_event_merges_thread_context(self):
        set_event_context(user="thread_user", source="test")
        event = dispatch_event(
            EventType.PIN_PRE_CREATE,
            payload={"pin": "test"},
            context={"local": "value"}
        )
        self.assertEqual(event.context["user"], "thread_user")
        self.assertEqual(event.context["source"], "test")
        self.assertEqual(event.context["local"], "value")

    def test_dispatch_event_explicit_context_overrides_thread(self):
        set_event_context(source="thread")
        event = dispatch_event(
            EventType.PIN_PRE_CREATE,
            context={"source": "explicit"}
        )
        self.assertEqual(event.context["source"], "explicit")


class DispatchEventConvenienceTests(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self._old_listeners = self.bus._listeners.copy()
        self.bus._listeners = {}

    def tearDown(self):
        self.bus._listeners = self._old_listeners
        clear_event_context()

    def test_dispatch_event_returns_event_object(self):
        event = dispatch_event(EventType.PIN_PRE_CREATE)
        self.assertIsInstance(event, Event)
        self.assertEqual(event.type, EventType.PIN_PRE_CREATE)

    def test_dispatch_event_payload(self):
        event = dispatch_event(
            EventType.PIN_POST_CREATE,
            payload={"pin_instance": "test_pin"}
        )
        self.assertEqual(event.payload["pin_instance"], "test_pin")

    def test_on_decorator(self):
        received = []
        @on(EventType.PIN_PRE_CREATE)
        def handler(event):
            received.append(event)
        event = dispatch_event(EventType.PIN_PRE_CREATE)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0], event)
        self.bus.unsubscribe(EventType.PIN_PRE_CREATE, handler)


class PreviewFetchEventSequenceTests(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self._old_listeners = self.bus._listeners.copy()
        self.bus._listeners = {}
        self.events = []
        def capture(event):
            self.events.append(event)
        for et in [EventType.FETCH_PREVIEW_START,
                   EventType.FETCH_PREVIEW_SUCCESS,
                   EventType.FETCH_PREVIEW_FAILURE,
                   EventType.IMAGE_PRE_CREATE,
                   EventType.IMAGE_POST_CREATE]:
            self.bus.subscribe(et, capture)

    def tearDown(self):
        self.bus._listeners = self._old_listeners

    def test_successful_fetch_sequence(self):
        def mock_get(url, **kwargs):
            resp = mock.Mock()
            resp.content = open(TEST_IMAGE_PATH, 'rb').read()
            return resp
        with mock.patch('requests.get', mock_get):
            image = Image.objects.create_for_url("http://example.com/test.png")
        self.assertIsNotNone(image)
        event_types = [e.type for e in self.events]
        self.assertEqual(event_types[0], EventType.FETCH_PREVIEW_START)
        self.assertEqual(event_types[1], EventType.IMAGE_PRE_CREATE)
        self.assertEqual(event_types[2], EventType.IMAGE_POST_CREATE)
        self.assertEqual(event_types[3], EventType.FETCH_PREVIEW_SUCCESS)
        self.assertEqual(self.events[0].payload["url"], "http://example.com/test.png")
        self.assertEqual(self.events[-1].payload["image_instance"], image)

    def test_invalid_image_fetch_sequence(self):
        def mock_get(url, **kwargs):
            resp = mock.Mock()
            resp.content = b"not an image"
            return resp
        with mock.patch('requests.get', mock_get):
            image = Image.objects.create_for_url("http://example.com/bad.png")
        self.assertIsNone(image)
        event_types = [e.type for e in self.events]
        self.assertEqual(event_types[0], EventType.FETCH_PREVIEW_START)
        self.assertEqual(event_types[1], EventType.FETCH_PREVIEW_FAILURE)
        self.assertEqual(self.events[-1].payload["reason"], "invalid_image_content")

    def test_fetch_with_referer(self):
        def mock_get(url, **kwargs):
            resp = mock.Mock()
            resp.content = open(TEST_IMAGE_PATH, 'rb').read()
            return resp
        with mock.patch('requests.get', mock_get):
            Image.objects.create_for_url(
                "http://example.com/img.png",
                referer="http://example.com/page.html"
            )
        self.assertEqual(self.events[0].payload["referer"], "http://example.com/page.html")
        self.assertEqual(self.events[-1].payload["referer"], "http://example.com/page.html")


class ModelLifecycleEventTests(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self._old_listeners = self.bus._listeners.copy()
        self.bus._listeners = {}
        self.events = []
        def capture(event):
            self.events.append(event)
        for et in EventType:
            self.bus.subscribe(et, capture)
        from users.models import User
        self.user, _ = User.objects.get_or_create(username="test_event_user",
                                                  defaults={"email": "test@example.com"})
        self.user.set_password("password")
        self.user.save()

    def tearDown(self):
        self.bus._listeners = self._old_listeners
        Pin.objects.filter(submitter=self.user).delete()
        Image.objects.all().delete()

    def test_pin_create_sequence(self):
        with event_context(user=self.user, source="test"):
            image = _make_test_image()
            pin = Pin.objects.create(submitter=self.user, image=image)
        event_types = [e.type for e in self.events]
        self.assertIn(EventType.IMAGE_PRE_CREATE, event_types)
        self.assertIn(EventType.IMAGE_POST_CREATE, event_types)
        self.assertIn(EventType.PIN_PRE_CREATE, event_types)
        self.assertIn(EventType.PIN_POST_CREATE, event_types)
        pin_create_idx = event_types.index(EventType.PIN_PRE_CREATE)
        pin_post_idx = event_types.index(EventType.PIN_POST_CREATE)
        self.assertLess(pin_create_idx, pin_post_idx)
        pin_pre_event = [e for e in self.events if e.type == EventType.PIN_PRE_CREATE][0]
        self.assertEqual(pin_pre_event.payload["pin_instance"], pin)
        self.assertEqual(pin_pre_event.context.get("user"), self.user)

    def test_pin_update_sequence(self):
        image = _make_test_image()
        pin = Pin.objects.create(submitter=self.user, image=image)
        self.events.clear()
        pin.description = "updated description"
        pin.save()
        event_types = [e.type for e in self.events]
        self.assertIn(EventType.PIN_PRE_UPDATE, event_types)
        self.assertIn(EventType.PIN_POST_UPDATE, event_types)
        self.assertNotIn(EventType.PIN_PRE_CREATE, event_types)
        update_pre_idx = event_types.index(EventType.PIN_PRE_UPDATE)
        update_post_idx = event_types.index(EventType.PIN_POST_UPDATE)
        self.assertLess(update_pre_idx, update_post_idx)
        post_event = [e for e in self.events if e.type == EventType.PIN_POST_UPDATE][0]
        self.assertEqual(post_event.payload["pin_instance"].description, "updated description")

    def test_pin_delete_sequence(self):
        image = _make_test_image()
        pin = Pin.objects.create(submitter=self.user, image=image)
        self.events.clear()
        pin_id = pin.id
        pin.delete()
        event_types = [e.type for e in self.events]
        self.assertIn(EventType.PIN_PRE_DELETE, event_types)
        self.assertIn(EventType.PIN_POST_DELETE, event_types)
        self.assertIn(EventType.IMAGE_PRE_DELETE, event_types)
        self.assertIn(EventType.IMAGE_POST_DELETE, event_types)
        pre_idx = event_types.index(EventType.PIN_PRE_DELETE)
        post_idx = event_types.index(EventType.PIN_POST_DELETE)
        img_pre_idx = event_types.index(EventType.IMAGE_PRE_DELETE)
        self.assertLess(pre_idx, img_pre_idx)
        self.assertLess(img_pre_idx, post_idx)
        pre_event = [e for e in self.events if e.type == EventType.PIN_PRE_DELETE][0]
        self.assertEqual(pre_event.payload["pin_instance"].id, pin_id)

    def test_pin_sync_event(self):
        image = _make_test_image()
        pin = Pin.objects.create(submitter=self.user, image=image)
        self.events.clear()
        pin.sync(external_id=123, sync_source="remote")
        event_types = [e.type for e in self.events]
        self.assertEqual(len(event_types), 1)
        self.assertEqual(event_types[0], EventType.PIN_SYNC)
        sync_event = self.events[0]
        self.assertEqual(sync_event.payload["pin_instance"], pin)
        self.assertEqual(sync_event.payload["extra_data"]["external_id"], 123)
        self.assertEqual(sync_event.payload["extra_data"]["sync_source"], "remote")


class LegacyPluginCompatibilityTests(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self._old_listeners = self.bus._listeners.copy()
        self.bus._listeners = {}
        from users.models import User
        self.user, _ = User.objects.get_or_create(username="test_legacy_user",
                                                  defaults={"email": "legacy@example.com"})
        self.user.set_password("password")
        self.user.save()

    def tearDown(self):
        self.bus._listeners = self._old_listeners
        Pin.objects.filter(submitter=self.user).delete()
        Image.objects.all().delete()

    def test_legacy_method_map_has_expected_entries(self):
        expected_methods = {
            "process_image_pre_creation",
            "process_thumbnail_pre_creation",
            "process_image_post_create",
            "process_thumbnail_post_create",
            "process_pin_pre_create",
            "process_pin_post_create",
            "process_pin_pre_update",
            "process_pin_post_update",
            "process_pin_pre_delete",
            "process_pin_post_delete",
            "process_pin_sync",
            "process_board_pre_create",
            "process_board_post_create",
            "process_board_pre_update",
            "process_board_post_update",
            "process_board_pre_delete",
            "process_board_post_delete",
            "process_fetch_preview_start",
            "process_fetch_preview_success",
            "process_fetch_preview_failure",
        }
        self.assertEqual(set(LEGACY_METHOD_MAP.keys()), expected_methods)

    def test_legacy_image_pre_creation_hook(self):
        calls = []
        class LegacyPlugin:
            def process_image_pre_creation(self, django_settings, image_instance, **kwargs):
                calls.append(("image_pre", image_instance, django_settings))
        plugin = LegacyPlugin()
        from pinry_plugins.builder._loader import _register_plugin_events
        _register_plugin_events(plugin)
        image = Image(image="test")
        dispatch_event(
            EventType.IMAGE_PRE_CREATE,
            payload={"image_instance": image, "instance": image}
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "image_pre")
        self.assertEqual(calls[0][1], image)
        self.assertIs(calls[0][2], settings)

    def test_legacy_thumbnail_pre_creation_hook(self):
        calls = []
        class LegacyPlugin:
            def process_thumbnail_pre_creation(self, django_settings, thumbnail_instance, **kwargs):
                calls.append(("thumb_pre", thumbnail_instance))
        plugin = LegacyPlugin()
        from pinry_plugins.builder._loader import _register_plugin_events
        _register_plugin_events(plugin)
        thumb = mock.Mock()
        dispatch_event(
            EventType.THUMBNAIL_PRE_CREATE,
            payload={"thumbnail_instance": thumb, "instance": thumb}
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], thumb)

    def test_legacy_pin_hooks(self):
        hook_calls = {}
        class LegacyPlugin:
            def process_pin_pre_create(self, **kwargs):
                hook_calls["pre_create"] = kwargs
            def process_pin_post_create(self, **kwargs):
                hook_calls["post_create"] = kwargs
            def process_pin_pre_update(self, **kwargs):
                hook_calls["pre_update"] = kwargs
            def process_pin_post_update(self, **kwargs):
                hook_calls["post_update"] = kwargs
            def process_pin_pre_delete(self, **kwargs):
                hook_calls["pre_delete"] = kwargs
            def process_pin_post_delete(self, **kwargs):
                hook_calls["post_delete"] = kwargs
            def process_pin_sync(self, **kwargs):
                hook_calls["sync"] = kwargs
        plugin = LegacyPlugin()
        from pinry_plugins.builder._loader import _register_plugin_events
        _register_plugin_events(plugin)
        image = _make_test_image()
        pin = Pin.objects.create(submitter=self.user, image=image)
        self.assertIn("pre_create", hook_calls)
        self.assertIn("post_create", hook_calls)
        self.assertEqual(hook_calls["pre_create"]["pin_instance"], pin)
        self.assertEqual(hook_calls["post_create"]["pin_instance"], pin)
        self.assertIn("event", hook_calls["pre_create"])
        self.assertIsInstance(hook_calls["pre_create"]["event"], Event)
        self.events = []
        hook_calls.clear()
        pin.description = "updated"
        pin.save()
        self.assertIn("pre_update", hook_c