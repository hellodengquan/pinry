import mock
from django.test import TestCase

from pinry_plugins.events import (
    Event,
    EventType,
    EventBus,
    get_event_bus,
    dispatch_event,
    on,
    event_context,
    set_event_context,
    clear_event_context,
)
from pinry_plugins.builder._loader import (
    LEGACY_METHOD_MAP,
    _wrap_legacy_method,
    _register_plugin_events,
)

from core.tests.helpers import create_user, create_image, create_pin
from core.models import Pin, Image, Board


class TestEventBusSubscribeAndUnsubscribe(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.received = []

    def tearDown(self):
        self.bus._listeners = {}

    def test_subscribe_single_listener(self):
        def listener(event):
            self.received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)
        self.assertIn(listener, self.bus._listeners[EventType.PIN_PRE_CREATE])

    def test_subscribe_multiple_listeners_same_event(self):
        def l1(event):
            self.received.append("l1")

        def l2(event):
            self.received.append("l2")

        self.bus.subscribe(EventType.PIN_PRE_CREATE, l1)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, l2)
        self.assertEqual(len(self.bus._listeners[EventType.PIN_PRE_CREATE]), 2)

    def test_subscribe_different_events(self):
        def l1(event):
            pass

        def l2(event):
            pass

        self.bus.subscribe(EventType.PIN_PRE_CREATE, l1)
        self.bus.subscribe(EventType.BOARD_PRE_CREATE, l2)
        self.assertIn(EventType.PIN_PRE_CREATE, self.bus._listeners)
        self.assertIn(EventType.BOARD_PRE_CREATE, self.bus._listeners)

    def test_unsubscribe_existing_listener(self):
        def listener(event):
            self.received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)
        self.bus.unsubscribe(EventType.PIN_PRE_CREATE, listener)
        self.assertNotIn(listener, self.bus._listeners.get(EventType.PIN_PRE_CREATE, []))

    def test_unsubscribe_nonexistent_listener_no_error(self):
        def listener(event):
            pass

        self.bus.unsubscribe(EventType.PIN_PRE_CREATE, listener)

    def test_unsubscribe_from_empty_event_type(self):
        def listener(event):
            pass

        self.bus.unsubscribe(EventType.PIN_POST_CREATE, listener)

    def test_on_decorator_subscribes(self):
        received = []

        @on(EventType.PIN_PRE_DELETE)
        def my_listener(event):
            received.append(event)

        dispatch_event(EventType.PIN_PRE_DELETE, payload={"x": 1})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["x"], 1)
        self.bus.unsubscribe(EventType.PIN_PRE_DELETE, my_listener)


class TestEventBusDispatchOrder(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.order = []

    def tearDown(self):
        self.bus._listeners = {}

    def test_dispatch_order_matches_subscribe_order(self):
        def first(event):
            self.order.append("first")

        def second(event):
            self.order.append("second")

        def third(event):
            self.order.append("third")

        self.bus.subscribe(EventType.PIN_PRE_CREATE, first)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, second)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, third)

        dispatch_event(EventType.PIN_PRE_CREATE)
        self.assertEqual(self.order, ["first", "second", "third"])

    def test_dispatch_no_listeners_no_error(self):
        result = dispatch_event(EventType.IMAGE_PRE_DELETE)
        self.assertIsInstance(result, Event)

    def test_dispatch_returns_event_object(self):
        def listener(event):
            pass

        self.bus.subscribe(EventType.BOARD_PRE_CREATE, listener)
        evt = dispatch_event(
            EventType.BOARD_PRE_CREATE,
            payload={"board_instance": "b1"},
            context={"source": "test"},
        )
        self.assertEqual(evt.type, EventType.BOARD_PRE_CREATE)
        self.assertEqual(evt.payload["board_instance"], "b1")
        self.assertEqual(evt.context["source"], "test")

    def test_dispatch_pre_then_post_order(self):
        order = []

        def pre(event):
            order.append("pre")

        def post(event):
            order.append("post")

        self.bus.subscribe(EventType.PIN_PRE_CREATE, pre)
        self.bus.subscribe(EventType.PIN_POST_CREATE, post)

        dispatch_event(EventType.PIN_PRE_CREATE)
        dispatch_event(EventType.PIN_POST_CREATE)
        self.assertEqual(order, ["pre", "post"])


class TestEventBusFaultIsolation(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.received = []

    def tearDown(self):
        self.bus._listeners = {}

    def test_exception_in_one_listener_does_not_stop_others(self):
        def bad(event):
            raise RuntimeError("boom")

        def good(event):
            self.received.append("good")

        self.bus.subscribe(EventType.PIN_PRE_CREATE, bad)
        self.bus.subscribe(EventType.PIN_PRE_CREATE, good)

        event = Event(type=EventType.PIN_PRE_CREATE, payload={})
        errors = self.bus.dispatch(event, fail_silently=True)

        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0], "good")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)

    def test_exception_in_first_listener_second_still_runs(self):
        def bad1(event):
            raise ValueError("first")

        def bad2(event):
            raise TypeError("second")

        def good(event):
            self.received.append("ok")

        self.bus.subscribe(EventType.PIN_POST_CREATE, bad1)
        self.bus.subscribe(EventType.PIN_POST_CREATE, bad2)
        self.bus.subscribe(EventType.PIN_POST_CREATE, good)

        event = Event(type=EventType.PIN_POST_CREATE, payload={})
        errors = self.bus.dispatch(event, fail_silently=True)

        self.assertEqual(len(self.received), 1)
        self.assertEqual(len(errors), 2)
        self.assertIsInstance(errors[0], ValueError)
        self.assertIsInstance(errors[1], TypeError)

    def test_fail_silently_false_raises(self):
        def bad(event):
            raise RuntimeError("fatal")

        self.bus.subscribe(EventType.BOARD_PRE_DELETE, bad)

        event = Event(type=EventType.BOARD_PRE_DELETE, payload={})
        with self.assertRaises(RuntimeError):
            self.bus.dispatch(event, fail_silently=False)

    def test_dispatch_event_default_fail_silently(self):
        def bad(event):
            raise RuntimeError("silent")

        self.bus.subscribe(EventType.PIN_SYNC, bad)
        evt = dispatch_event(EventType.PIN_SYNC, payload={})
        self.assertIsInstance(evt, Event)
        self.bus.unsubscribe(EventType.PIN_SYNC, bad)

    def test_all_errors_collected_when_fail_silently(self):
        def bad1(event):
            raise ValueError("e1")

        def bad2(event):
            raise KeyError("e2")

        self.bus.subscribe(EventType.PIN_SYNC, bad1)
        self.bus.subscribe(EventType.PIN_SYNC, bad2)

        event = Event(type=EventType.PIN_SYNC, payload={})
        errors = self.bus.dispatch(event, fail_silently=True)

        self.assertEqual(len(errors), 2)


class TestEventContextMerging(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        clear_event_context()

    def tearDown(self):
        self.bus._listeners = {}
        clear_event_context()

    def test_set_event_context_merged_into_dispatched_event(self):
        received = []

        def listener(event):
            received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)

        set_event_context(user="alice", source="api")
        dispatch_event(EventType.PIN_PRE_CREATE, payload={})

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].context["user"], "alice")
        self.assertEqual(received[0].context["source"], "api")

    def test_event_context_manager_restores_after_exit(self):
        received = []

        def listener(event):
            received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)

        with event_context(user="bob", request="req1"):
            dispatch_event(EventType.PIN_PRE_CREATE)

        dispatch_event(EventType.PIN_PRE_CREATE)

        self.assertEqual(len(received), 2)
        self.assertEqual(received[0].context["user"], "bob")
        self.assertNotIn("user", received[1].context)

    def test_event_context_nesting(self):
        received = []

        def listener(event):
            received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)

        with event_context(level=1):
            with event_context(level=2):
                dispatch_event(EventType.PIN_PRE_CREATE)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[1 - 1].context["level"], 2)

    def test_explicit_context_overrides_thread_context(self):
        received = []

        def listener(event):
            received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)

        set_event_context(source="thread")
        dispatch_event(EventType.PIN_PRE_CREATE, context={"source": "explicit"})

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].context["source"], "explicit")

    def test_clear_event_context(self):
        received = []

        def listener(event):
            received.append(event)

        self.bus.subscribe(EventType.PIN_PRE_CREATE, listener)

        set_event_context(user="charlie")
        clear_event_context()
        dispatch_event(EventType.PIN_PRE_CREATE)

        self.assertNotIn("user", received[0].context)


class TestEventClone(TestCase):
    def test_clone_deep_copies_payload(self):
        original = Event(
            type=EventType.PIN_PRE_CREATE,
            payload={"items": [1, 2, 3]},
        )
        cloned = original.clone()
        original.payload["items"].append(4)
        self.assertEqual(len(cloned.payload["items"]), 3)

    def test_clone_deep_copies_context(self):
        original = Event(
            type=EventType.PIN_PRE_CREATE,
            context={"meta": {"a": 1}},
        )
        cloned = original.clone()
        original.context["meta"]["a"] = 999
        self.assertEqual(cloned.context["meta"]["a"], 1)

    def test_clone_overrides(self):
        original = Event(
            type=EventType.PIN_PRE_CREATE,
            payload={"x": 1},
        )
        cloned = original.clone(payload={"x": 2})
        self.assertEqual(cloned.payload["x"], 2)
        self.assertEqual(original.payload["x"], 1)


class TestPreviewFetchEventChain(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.event_log = []

        def recorder(event):
            self.event_log.append((event.type, dict(event.payload)))

        for et in (
            EventType.FETCH_PREVIEW_START,
            EventType.FETCH_PREVIEW_SUCCESS,
            EventType.FETCH_PREVIEW_FAILURE,
            EventType.IMAGE_PRE_CREATE,
            EventType.IMAGE_POST_CREATE,
            EventType.THUMBNAIL_PRE_CREATE,
            EventType.THUMBNAIL_POST_CREATE,
        ):
            self.bus.subscribe(et, recorder)

    def tearDown(self):
        self.bus._listeners = {}

    @mock.patch('requests.get')
    def test_successful_fetch_emits_start_then_success(self, mock_get):
        mock_get.return_value = mock.Mock(
            content=open('docs/src/imgs/logo-dark.png', 'rb').read()
        )
        Image.objects.create_for_url(
            "http://example.com/test.png",
            referer="http://example.com/",
        )
        types = [e[0] for e in self.event_log]
        self.assertIn(EventType.FETCH_PREVIEW_START, types)
        self.assertIn(EventType.FETCH_PREVIEW_SUCCESS, types)
        start_idx = types.index(EventType.FETCH_PREVIEW_START)
        success_idx = types.index(EventType.FETCH_PREVIEW_SUCCESS)
        self.assertLess(start_idx, success_idx)

    @mock.patch('requests.get')
    def test_successful_fetch_start_carries_url_and_referer(self, mock_get):
        mock_get.return_value = mock.Mock(
            content=open('docs/src/imgs/logo-dark.png', 'rb').read()
        )
        Image.objects.create_for_url(
            "http://example.com/img.png",
            referer="http://example.com/ref",
        )
        start_events = [e for e in self.event_log if e[0] == EventType.FETCH_PREVIEW_START]
        self.assertEqual(len(start_events), 1)
        self.assertEqual(start_events[0][1]["url"], "http://example.com/img.png")
        self.assertEqual(start_events[0][1]["referer"], "http://example.com/ref")

    @mock.patch('requests.get')
    def test_successful_fetch_success_carries_image_instance(self, mock_get):
        mock_get.return_value = mock.Mock(
            content=open('docs/src/imgs/logo-dark.png', 'rb').read()
        )
        Image.objects.create_for_url("http://example.com/img.png")
        success_events = [e for e in self.event_log if e[0] == EventType.FETCH_PREVIEW_SUCCESS]
        self.assertEqual(len(success_events), 1)
        self.assertIn("image_instance", success_events[0][1])

    @mock.patch('requests.get')
    def test_failed_fetch_invalid_image_emits_start_then_failure(self, mock_get):
        mock_get.return_value = mock.Mock(content=b"not-an-image")
        Image.objects.create_for_url("http://example.com/bad.png")
        types = [e[0] for e in self.event_log]
        self.assertIn(EventType.FETCH_PREVIEW_START, types)
        self.assertIn(EventType.FETCH_PREVIEW_FAILURE, types)
        self.assertNotIn(EventType.FETCH_PREVIEW_SUCCESS, types)
        start_idx = types.index(EventType.FETCH_PREVIEW_START)
        failure_idx = types.index(EventType.FETCH_PREVIEW_FAILURE)
        self.assertLess(start_idx, failure_idx)

    @mock.patch('requests.get')
    def test_failed_fetch_carries_reason(self, mock_get):
        mock_get.return_value = mock.Mock(content=b"not-an-image")
        Image.objects.create_for_url("http://example.com/bad.png")
        failure_events = [e for e in self.event_log if e[0] == EventType.FETCH_PREVIEW_FAILURE]
        self.assertEqual(len(failure_events), 1)
        self.assertIn("reason", failure_events[0][1])

    @mock.patch('requests.get', side_effect=Exception("network error"))
    def test_fetch_exception_emits_start_then_failure(self, mock_get):
        Image.objects.create_for_url("http://example.com/down.png")
        types = [e[0] for e in self.event_log]
        self.assertIn(EventType.FETCH_PREVIEW_START, types)
        self.assertIn(EventType.FETCH_PREVIEW_FAILURE, types)
        self.assertNotIn(EventType.FETCH_PREVIEW_SUCCESS, types)
        failure_events = [e for e in self.event_log if e[0] == EventType.FETCH_PREVIEW_FAILURE]
        self.assertEqual(failure_events[0][1]["reason"], "exception")
        self.assertIn("exception", failure_events[0][1])

    @mock.patch('requests.get')
    def test_full_create_for_url_event_chain_order(self, mock_get):
        mock_get.return_value = mock.Mock(
            content=open('docs/src/imgs/logo-dark.png', 'rb').read()
        )
        Image.objects.create_for_url("http://example.com/chain.png")
        types = [e[0] for e in self.event_log]
        expected_order = [
            EventType.FETCH_PREVIEW_START,
            EventType.IMAGE_PRE_CREATE,
            EventType.IMAGE_POST_CREATE,
            EventType.FETCH_PREVIEW_SUCCESS,
        ]
        for expected in expected_order:
            self.assertIn(expected, types, f"{expected} missing from event chain")
        actual_ordered = [t for t in types if t in expected_order]
        self.assertEqual(actual_ordered, expected_order)


class TestLegacyPluginHookCompatibility(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.legacy_calls = []

    def tearDown(self):
        self.bus._listeners = {}

    def _make_legacy_plugin(self, method_name):
        plugin = type("FakeLegacyPlugin", (), {method_name: lambda self, **kw: self._record(method_name, kw)})()
        plugin._record = lambda name, kw: self.legacy_calls.append((name, kw))
        return plugin

    def test_process_image_pre_creation_is_called(self):
        plugin = self._make_legacy_plugin("process_image_pre_creation")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.IMAGE_PRE_CREATE,
            payload={"image_instance": "img", "instance": "img"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_image_pre_creation")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["image_instance"], "img")
        self.assertEqual(kwargs["django_settings"].__class__.__name__, "Settings")
        self.assertIn("event", kwargs)

    def test_process_thumbnail_pre_creation_is_called(self):
        plugin = self._make_legacy_plugin("process_thumbnail_pre_creation")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.THUMBNAIL_PRE_CREATE,
            payload={"thumbnail_instance": "thumb", "instance": "thumb"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_thumbnail_pre_creation")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["thumbnail_instance"], "thumb")
        self.assertIn("event", kwargs)

    def test_process_image_post_create_is_called(self):
        plugin = self._make_legacy_plugin("process_image_post_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.IMAGE_POST_CREATE,
            payload={"image_instance": "img2", "instance": "img2"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_image_post_create")

    def test_process_image_pre_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_image_pre_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.IMAGE_PRE_DELETE,
            payload={"image_instance": "img3", "instance": "img3"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_image_pre_delete")

    def test_process_image_post_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_image_post_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.IMAGE_POST_DELETE,
            payload={"image_instance": "img4", "instance": "img4"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_image_post_delete")

    def test_process_thumbnail_post_create_is_called(self):
        plugin = self._make_legacy_plugin("process_thumbnail_post_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.THUMBNAIL_POST_CREATE,
            payload={"thumbnail_instance": "th2", "instance": "th2"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_thumbnail_post_create")

    def test_process_pin_pre_create_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_pre_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_PRE_CREATE,
            payload={"pin_instance": "p1", "instance": "p1"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_pre_create")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["pin_instance"], "p1")
        self.assertIn("event", kwargs)

    def test_process_pin_post_create_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_post_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_POST_CREATE,
            payload={"pin_instance": "p2", "instance": "p2"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_post_create")

    def test_process_pin_pre_update_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_pre_update")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_PRE_UPDATE,
            payload={"pin_instance": "p3", "instance": "p3"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_pre_update")

    def test_process_pin_post_update_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_post_update")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_POST_UPDATE,
            payload={"pin_instance": "p4", "instance": "p4"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_post_update")

    def test_process_pin_pre_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_pre_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_PRE_DELETE,
            payload={"pin_instance": "p5", "instance": "p5"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_pre_delete")

    def test_process_pin_post_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_post_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_POST_DELETE,
            payload={"pin_instance": "p6", "instance": "p6"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_post_delete")

    def test_process_pin_sync_is_called(self):
        plugin = self._make_legacy_plugin("process_pin_sync")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_SYNC,
            payload={"pin_instance": "p7", "instance": "p7", "extra_data": {}},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_pin_sync")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["pin_instance"], "p7")
        self.assertIn("extra_data", kwargs)

    def test_process_board_pre_create_is_called(self):
        plugin = self._make_legacy_plugin("process_board_pre_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_PRE_CREATE,
            payload={"board_instance": "b1", "instance": "b1"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_pre_create")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["board_instance"], "b1")
        self.assertIn("event", kwargs)

    def test_process_board_post_create_is_called(self):
        plugin = self._make_legacy_plugin("process_board_post_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_POST_CREATE,
            payload={"board_instance": "b2", "instance": "b2"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_post_create")

    def test_process_board_pre_update_is_called(self):
        plugin = self._make_legacy_plugin("process_board_pre_update")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_PRE_UPDATE,
            payload={"board_instance": "b3", "instance": "b3"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_pre_update")

    def test_process_board_post_update_is_called(self):
        plugin = self._make_legacy_plugin("process_board_post_update")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_POST_UPDATE,
            payload={"board_instance": "b4", "instance": "b4"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_post_update")

    def test_process_board_pre_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_board_pre_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_PRE_DELETE,
            payload={"board_instance": "b5", "instance": "b5"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_pre_delete")

    def test_process_board_post_delete_is_called(self):
        plugin = self._make_legacy_plugin("process_board_post_delete")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.BOARD_POST_DELETE,
            payload={"board_instance": "b6", "instance": "b6"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_board_post_delete")

    def test_process_fetch_preview_start_is_called(self):
        plugin = self._make_legacy_plugin("process_fetch_preview_start")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.FETCH_PREVIEW_START,
            payload={"url": "http://ex.com/a.png", "referer": "http://ex.com/"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_fetch_preview_start")
        kwargs = self.legacy_calls[0][1]
        self.assertEqual(kwargs["url"], "http://ex.com/a.png")
        self.assertEqual(kwargs["referer"], "http://ex.com/")

    def test_process_fetch_preview_success_is_called(self):
        plugin = self._make_legacy_plugin("process_fetch_preview_success")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.FETCH_PREVIEW_SUCCESS,
            payload={"url": "http://ex.com/a.png", "image_instance": "img"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_fetch_preview_success")
        kwargs = self.legacy_calls[0][1]
        self.assertIn("image_instance", kwargs)
        self.assertIn("url", kwargs)

    def test_process_fetch_preview_failure_is_called(self):
        plugin = self._make_legacy_plugin("process_fetch_preview_failure")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.FETCH_PREVIEW_FAILURE,
            payload={"url": "http://ex.com/bad.png", "reason": "invalid_image_content"},
        )
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.legacy_calls[0][0], "process_fetch_preview_failure")
        kwargs = self.legacy_calls[0][1]
        self.assertIn("reason", kwargs)

    def test_legacy_hook_not_subscribed_if_method_missing(self):
        plugin = type("MinimalPlugin", (), {
            "process_pin_pre_create": lambda self, **kw: None,
        })()
        _register_plugin_events(plugin)
        self.assertIn(EventType.PIN_PRE_CREATE, self.bus._listeners)
        self.assertNotIn(EventType.PIN_POST_CREATE, self.bus._listeners)
        self.assertNotIn(EventType.BOARD_PRE_CREATE, self.bus._listeners)

    def test_legacy_hook_django_settings_always_passed(self):
        plugin = self._make_legacy_plugin("process_pin_pre_create")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.PIN_PRE_CREATE,
            payload={"pin_instance": "p", "instance": "p"},
        )
        kwargs = self.legacy_calls[0][1]
        from django.conf import settings as django_settings
        self.assertIs(kwargs["django_settings"], django_settings)

    def test_legacy_hook_exception_does_not_propagate(self):
        def broken_method(self, **kw):
            raise RuntimeError("legacy plugin broke")

        plugin = type("BrokenPlugin", (), {
            "process_pin_pre_create": broken_method,
        })()
        _register_plugin_events(plugin)
        evt = dispatch_event(
            EventType.PIN_PRE_CREATE,
            payload={"pin_instance": "p", "instance": "p"},
        )
        self.assertIsInstance(evt, Event)

    def test_legacy_hook_event_object_always_passed(self):
        plugin = self._make_legacy_plugin("process_image_pre_creation")
        _register_plugin_events(plugin)
        dispatch_event(
            EventType.IMAGE_PRE_CREATE,
            payload={"image_instance": "img", "instance": "img"},
        )
        kwargs = self.legacy_calls[0][1]
        self.assertIn("event", kwargs)
        self.assertIsInstance(kwargs["event"], Event)
        self.assertEqual(kwargs["event"].type, EventType.IMAGE_PRE_CREATE)

    def test_handle_event_universal_handler(self):
        universal_calls = []

        class UniversalPlugin:
            def handle_event(self, event):
                universal_calls.append(event.type)

        plugin = UniversalPlugin()
        _register_plugin_events(plugin)
        dispatch_event(EventType.PIN_PRE_CREATE)
        dispatch_event(EventType.BOARD_POST_UPDATE)
        dispatch_event(EventType.FETCH_PREVIEW_START)
        self.assertIn(EventType.PIN_PRE_CREATE, universal_calls)
        self.assertIn(EventType.BOARD_POST_UPDATE, universal_calls)
        self.assertIn(EventType.FETCH_PREVIEW_START, universal_calls)


class TestLegacyMethodMapCompleteness(TestCase):
    def test_all_legacy_methods_map_to_valid_event_types(self):
        for method_name, event_type in LEGACY_METHOD_MAP.items():
            self.assertIsInstance(event_type, EventType)

    def test_all_event_types_covered_by_legacy_map(self):
        mapped_types = set(LEGACY_METHOD_MAP.values())
        for et in EventType:
            self.assertIn(et, mapped_types, f"EventType {et} not covered by LEGACY_METHOD_MAP")


class TestModelSaveDeleteEventChain(TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.bus._listeners = {}
        self.event_log = []

        def recorder(event):
            self.event_log.append(event.type)

        for et in EventType:
            self.bus.subscribe(et, recorder)

    def tearDown(self):
        self.bus._listeners = {}

    def test_pin_create_emits_pre_then_post(self):
        user = create_user("pin_create_test")
        image = create_image()
        self.event_log.clear()
        Pin.objects.create(submitter=user, image=image)
        self.assertIn(EventType.PIN_PRE_CREATE, self.event_log)
        self.assertIn(EventType.PIN_POST_CREATE, self.event_log)
        pre_idx = self.event_log.index(EventType.PIN_PRE_CREATE)
        post_idx = self.event_log.index(EventType.PIN_POST_CREATE)
        self.assertLess(pre_idx, post_idx)

    def test_pin_update_emits_pre_then_post(self):
        user = create_user("pin_update_test")
        image = create_image()
        pin = Pin.objects.create(submitter=user, image=image)
        self.event_log.clear()
        pin.description = "updated"
        pin.save()
        self.assertIn(EventType.PIN_PRE_UPDATE, self.event_log)
        self.assertIn(EventType.PIN_POST_UPDATE, self.event_log)
        self.assertNotIn(EventType.PIN_PRE_CREATE, self.event_log)
        pre_idx = self.event_log.index(EventType.PIN_PRE_UPDATE)
        post_idx = self.event_log.index(EventType.PIN_POST_UPDATE)
        self.assertLess(pre_idx, post_idx)

    def test_pin_delete_emits_pre_then_post(self):
        user = create_user("pin_delete_test")
        image = create_image()
        pin = Pin.objects.create(submitter=user, image=image)
        self.event_log.clear()
        pin.delete()
        self.assertIn(EventType.PIN_PRE_DELETE, self.event_log)
        self.assertIn(EventType.PIN_POST_DELETE, self.event_log)
        pre_idx = self.event_log.index(EventType.PIN_PRE_DELETE)
        post_idx = self.event_log.index(EventType.PIN_POST_DELETE)
        self.assertLess(pre_idx, post_idx)

    def test_board_create_emits_pre_then_post(self):
        user = create_user("board_create_test")
        self.event_log.clear()
        Board.objects.create(name="test_board", submitter=user)
        self.assertIn(EventType.BOARD_PRE_CREATE, self.event_log)
        self.assertIn(EventType.BOARD_POST_CREATE, self.event_log)
        pre_idx = self.event_log.index(EventType.BOARD_PRE_CREATE)
        post_idx = self.event_log.index(EventType.BOARD_POST_CREATE)
        self.assertLess(pre_idx, post_idx)

    def test_board_update_emits_pre_then_post(self):
        user = create_user("board_update_test")
        board = Board.objects.create(name="test_board2", submitter=user)
        self.event_log.clear()
        board.name = "renamed"
        board.save()
        self.assertIn(EventType.BOARD_PRE_UPDATE, self.event_log)
        self.assertIn(EventType.BOARD_POST_UPDATE, self.event_log)
        self.assertNotIn(EventType.BOARD_PRE_CREATE, self.event_log)
        pre_idx = self.event_log.index(EventType.BOARD_PRE_UPDATE)
        post_idx = self.event_log.index(EventType.BOARD_POST_UPDATE)
        self.assertLess(pre_idx, post_idx)

    def test_board_delete_emits_pre_then_post(self):
        user = create_user("board_delete_test")
        board = Board.objects.create(name="test_board3", submitter=user)
        self.event_log.clear()
        board.delete()
        self.assertIn(EventType.BOARD_PRE_DELETE, self.event_log)
        self.assertIn(EventType.BOARD_POST_DELETE, self.event_log)
        pre_idx = self.event_log.index(EventType.BOARD_PRE_DELETE)
        post_idx = self.event_log.index(EventType.BOARD_POST_DELETE)
        self.assertLess(pre_idx, post_idx)

    def test_pin_sync_emits_sync_event(self):
        user = create_user("pin_sync_test")
        image = create_image()
        pin = Pin.objects.create(submitter=user, image=image)
        self.event_log.clear()
        pin.sync(force=True)
        self.assertIn(EventType.PIN_SYNC, self.event_log)
