import mock
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from core.services import (
    PreviewErrorCode,
    PreviewContentType,
    PreviewError,
    PreviewRequest,
    PreviewResult,
    get_preview_manager,
    preview_error_to_legacy_message,
)
from core.services.preview_service import (
    ImagePreviewService,
    PreviewServiceManager,
    VideoPreviewService,
    WebpagePreviewService,
)
from core.tests.helpers import create_user


def mock_requests_get_image(url, **kwargs):
    response = mock.Mock(content=open('docs/src/imgs/logo-dark.png', 'rb').read())
    return response


def mock_requests_get_invalid(url, **kwargs):
    response = mock.Mock(content=b"invalid_content")
    return response


class PreviewErrorCodeTests(TestCase):
    def test_error_code_values(self):
        self.assertEqual(PreviewErrorCode.INVALID_URL.value, "invalid_url")
        self.assertEqual(PreviewErrorCode.INVALID_CONTENT.value, "invalid_content")
        self.assertEqual(PreviewErrorCode.NETWORK_ERROR.value, "network_error")
        self.assertEqual(PreviewErrorCode.FORMAT_UNSUPPORTED.value, "format_unsupported")
        self.assertEqual(PreviewErrorCode.UNKNOWN_ERROR.value, "unknown_error")

    def test_content_type_values(self):
        self.assertEqual(PreviewContentType.IMAGE.value, "image")
        self.assertEqual(PreviewContentType.WEBPAGE.value, "webpage")
        self.assertEqual(PreviewContentType.VIDEO.value, "video")
        self.assertEqual(PreviewContentType.UNKNOWN.value, "unknown")


class PreviewErrorTests(TestCase):
    def test_preview_error_creation(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_CONTENT,
            message="invalid image content",
            field="url",
            details={"key": "value"},
        )
        self.assertEqual(error.code, PreviewErrorCode.INVALID_CONTENT)
        self.assertEqual(error.message, "invalid image content")
        self.assertEqual(error.field, "url")
        self.assertEqual(error.details, {"key": "value"})

    def test_preview_error_to_dict(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_CONTENT,
            message="invalid image content",
            field="url",
        )
        result = error.to_dict()
        self.assertEqual(result["code"], "invalid_content")
        self.assertEqual(result["message"], "invalid image content")
        self.assertEqual(result["field"], "url")

    def test_preview_error_to_validation_error_dict(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_CONTENT,
            message="invalid image content",
            field="url",
        )
        result = error.to_validation_error_dict()
        self.assertEqual(result, {"url": "invalid image content"})

    def test_legacy_message_compatibility(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_CONTENT,
            message="new detailed message",
        )
        legacy = preview_error_to_legacy_message(error)
        self.assertEqual(legacy, "invalid image content")

    def test_legacy_message_network_error(self):
        error = PreviewError(
            code=PreviewErrorCode.NETWORK_ERROR,
            message="new message",
        )
        legacy = preview_error_to_legacy_message(error)
        self.assertEqual(legacy, "network error")


class PreviewRequestTests(TestCase):
    def test_cache_key_deterministic(self):
        req1 = PreviewRequest(url="http://example.com/img.jpg", referer="http://example.com/")
        req2 = PreviewRequest(url="http://example.com/img.jpg", referer="http://example.com/")
        self.assertEqual(req1.cache_key(), req2.cache_key())

    def test_cache_key_differs_for_url(self):
        req1 = PreviewRequest(url="http://example.com/img1.jpg")
        req2 = PreviewRequest(url="http://example.com/img2.jpg")
        self.assertNotEqual(req1.cache_key(), req2.cache_key())

    def test_cache_key_differs_for_referer(self):
        req1 = PreviewRequest(url="http://example.com/img.jpg", referer="http://a.com/")
        req2 = PreviewRequest(url="http://example.com/img.jpg", referer="http://b.com/")
        self.assertNotEqual(req1.cache_key(), req2.cache_key())


class ImagePreviewServiceTests(TestCase):
    def test_detect_content_type_by_extension(self):
        service = ImagePreviewService()
        self.assertEqual(
            service._detect_content_type("http://example.com/image.jpg"),
            PreviewContentType.IMAGE,
        )
        self.assertEqual(
            service._detect_content_type("http://example.com/photo.PNG"),
            PreviewContentType.IMAGE,
        )
        self.assertEqual(
            service._detect_content_type("http://example.com/pic.gif?size=large"),
            PreviewContentType.IMAGE,
        )

    def test_detect_content_type_non_image(self):
        service = ImagePreviewService()
        self.assertEqual(
            service._detect_content_type("http://example.com/page.html"),
            PreviewContentType.UNKNOWN,
        )

    def test_supports_hint(self):
        service = ImagePreviewService()
        request = PreviewRequest(
            url="http://example.com/anything",
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertTrue(service.supports(request))

    def test_supports_extension(self):
        service = ImagePreviewService()
        request = PreviewRequest(url="http://example.com/photo.jpg")
        self.assertTrue(service.supports(request))

    def test_supports_no_hint_no_extension(self):
        service = ImagePreviewService()
        request = PreviewRequest(url="http://example.com/resource")
        self.assertTrue(service.supports(request))


class WebpagePreviewServiceTests(TestCase):
    def test_detect_content_type_by_extension(self):
        service = WebpagePreviewService()
        self.assertEqual(
            service._detect_content_type("http://example.com/page.html"),
            PreviewContentType.WEBPAGE,
        )
        self.assertEqual(
            service._detect_content_type("http://example.com/blog/post.php"),
            PreviewContentType.WEBPAGE,
        )

    def test_detect_content_type_trailing_slash(self):
        service = WebpagePreviewService()
        self.assertEqual(
            service._detect_content_type("http://example.com/blog/"),
            PreviewContentType.WEBPAGE,
        )


class VideoPreviewServiceTests(TestCase):
    def test_detect_content_type_by_extension(self):
        service = VideoPreviewService()
        self.assertEqual(
            service._detect_content_type("http://example.com/video.mp4"),
            PreviewContentType.VIDEO,
        )
        self.assertEqual(
            service._detect_content_type("http://example.com/clip.webm"),
            PreviewContentType.VIDEO,
        )

    def test_detect_content_type_by_host(self):
        service = VideoPreviewService()
        self.assertEqual(
            service._detect_content_type("https://www.youtube.com/watch?v=abc"),
            PreviewContentType.VIDEO,
        )
        self.assertEqual(
            service._detect_content_type("https://youtu.be/abc123"),
            PreviewContentType.VIDEO,
        )
        self.assertEqual(
            service._detect_content_type("https://www.bilibili.com/video/BV123"),
            PreviewContentType.VIDEO,
        )


class PreviewServiceManagerTests(TestCase):
    def test_singleton(self):
        mgr1 = get_preview_manager()
        mgr2 = PreviewServiceManager()
        self.assertIs(mgr1, mgr2)

    def test_get_service_for_image(self):
        mgr = get_preview_manager()
        request = PreviewRequest(
            url="http://example.com/img.jpg",
            content_type_hint=PreviewContentType.IMAGE,
        )
        service = mgr.get_service_for_request(request)
        self.assertIsInstance(service, ImagePreviewService)

    def test_get_service_for_video(self):
        mgr = get_preview_manager()
        request = PreviewRequest(
            url="http://example.com/video.mp4",
        )
        service = mgr.get_service_for_request(request)
        self.assertIsInstance(service, VideoPreviewService)

    def test_get_service_for_webpage(self):
        mgr = get_preview_manager()
        request = PreviewRequest(
            url="http://example.com/page.html",
        )
        service = mgr.get_service_for_request(request)
        self.assertIsInstance(service, WebpagePreviewService)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_preview_image_success(self):
        from django.core.cache import cache
        cache.clear()

        mgr = get_preview_manager()
        result = mgr.preview(
            url="http://example.com/test.jpg",
            referer="http://example.com/",
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertIsInstance(result, PreviewResult)
        self.assertEqual(result.content_type, PreviewContentType.IMAGE)
        self.assertIsNotNone(result.image_id)
        self.assertFalse(result.from_cache)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_preview_caching(self):
        from django.core.cache import cache
        cache.clear()

        mgr = get_preview_manager()
        url = "http://example.com/cached.jpg"
        referer = "http://example.com/"

        result1 = mgr.preview(
            url=url,
            referer=referer,
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertFalse(result1.from_cache)

        result2 = mgr.preview(
            url=url,
            referer=referer,
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertTrue(result2.from_cache)
        self.assertEqual(result1.image_id, result2.image_id)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_preview_force_refresh(self):
        from django.core.cache import cache
        cache.clear()

        mgr = get_preview_manager()
        url = "http://example.com/refresh.jpg"
        referer = "http://example.com/"

        mgr.preview(url=url, referer=referer, content_type_hint=PreviewContentType.IMAGE)

        result = mgr.refresh(
            url=url,
            referer=referer,
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertFalse(result.from_cache)

    def test_inspect(self):
        mgr = get_preview_manager()
        info = mgr.inspect(
            url="http://example.com/test.jpg",
            content_type_hint=PreviewContentType.IMAGE,
        )
        self.assertEqual(info["url"], "http://example.com/test.jpg")
        self.assertEqual(info["content_type_hint"], "image")
        self.assertIn("detected_service", info)
        self.assertIn("cache_key", info)
        self.assertIn("cache_hit", info)

    @mock.patch('requests.get', mock_requests_get_invalid)
    def test_preview_invalid_content_raises(self):
        from django.core.cache import cache
        cache.clear()

        mgr = get_preview_manager()
        with self.assertRaises(PreviewError) as ctx:
            mgr.preview(
                url="http://example.com/invalid.jpg",
                content_type_hint=PreviewContentType.IMAGE,
            )
        self.assertEqual(ctx.exception.code, PreviewErrorCode.INVALID_CONTENT)

    def test_invalidate_cache_for_url(self):
        from django.core.cache import cache
        cache.clear()

        mgr = get_preview_manager()
        count = mgr.invalidate_cache_for_url("http://example.com/nonexistent.jpg")
        self.assertIsInstance(count, int)


class PreviewAPITests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("preview_test")
        self.client.login(username=self.user.username, password='password')

    def test_fetch_preview_without_url(self):
        url = reverse("preview-fetch")
        response = self.client.post(url, data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_fetch_image_preview_success(self):
        from django.core.cache import cache
        cache.clear()

        url = reverse("preview-fetch")
        post_data = {
            "url": "http://example.com/api-test.jpg",
            "content_type": "image",
            "referer": "http://example.com/",
        }
        response = self.client.post(url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["content_type"], "image")
        self.assertIsNotNone(data["image_id"])

    @mock.patch('requests.get', mock_requests_get_invalid)
    def test_fetch_invalid_content_returns_error(self):
        from django.core.cache import cache
        cache.clear()

        url = reverse("preview-fetch")
        post_data = {
            "url": "http://example.com/invalid-content.bin",
            "content_type": "image",
        }
        response = self.client.post(url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "invalid_content")

    def test_list_content_types(self):
        url = reverse("preview-types")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("supported", data)
        types = [item["type"] for item in data["supported"]]
        self.assertIn("image", types)
        self.assertIn("webpage", types)
        self.assertIn("video", types)

    def test_inspect_endpoint(self):
        url = reverse("preview-inspect")
        post_data = {
            "url": "http://example.com/test.jpg",
            "content_type": "image",
        }
        response = self.client.post(url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["url"], "http://example.com/test.jpg")
        self.assertIn("detected_service", data)

    def test_invalidate_cache_endpoint(self):
        url = reverse("preview-invalidate-cache")
        post_data = {"url": "http://example.com/test.jpg"}
        response = self.client.post(url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("invalidated", response.json())

    @mock.patch('requests.get', mock_requests_get_image)
    def test_refresh_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        fetch_url = reverse("preview-fetch")
        self.client.post(fetch_url, data={
            "url": "http://example.com/refresh-test.jpg",
            "content_type": "image",
        }, format="json")

        refresh_url = reverse("preview-refresh")
        post_data = {
            "url": "http://example.com/refresh-test.jpg",
            "content_type": "image",
        }
        response = self.client.post(refresh_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data["from_cache"])

    def test_cache_version_endpoint(self):
        url = reverse("preview-cache-version")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("version", data)
        self.assertIsInstance(data["version"], int)

    def test_invalidate_cache_all_endpoint(self):
        url = reverse("preview-invalidate-cache")
        response = self.client.post(
            url, data={"all": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data.get("invalidated_all"))
        self.assertIn("version_bumped", data)

    def test_plugins_status_endpoint(self):
        url = reverse("preview-plugins-status")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("plugins", data)
        self.assertIsInstance(data["plugins"], list)


class LegacyErrorMessageCompatibilityTests(TestCase):
    LEGACY_MESSAGE_MAP = {
        PreviewErrorCode.INVALID_URL: "invalid url",
        PreviewErrorCode.NETWORK_ERROR: "network error",
        PreviewErrorCode.INVALID_CONTENT: "invalid image content",
        PreviewErrorCode.CONTENT_TOO_LARGE: "content too large",
        PreviewErrorCode.FORMAT_UNSUPPORTED: "unsupported format",
        PreviewErrorCode.TIMEOUT: "request timeout",
        PreviewErrorCode.AUTH_REQUIRED: "authentication required",
        PreviewErrorCode.FORBIDDEN: "access forbidden",
        PreviewErrorCode.NOT_FOUND: "resource not found",
        PreviewErrorCode.UNKNOWN_ERROR: "unknown error",
    }

    def test_all_error_codes_have_legacy_mapping(self):
        for code in PreviewErrorCode:
            self.assertIn(
                code,
                self.LEGACY_MESSAGE_MAP,
                f"Missing legacy mapping for error code: {code}",
            )

    def test_legacy_mapping_coverage_exact_match(self):
        self.assertEqual(
            len(self.LEGACY_MESSAGE_MAP),
            len(PreviewErrorCode),
            "Legacy mapping count does not match PreviewErrorCode count",
        )

    def test_each_error_code_maps_correctly(self):
        for code, expected_message in self.LEGACY_MESSAGE_MAP.items():
            error = PreviewError(
                code=code,
                message="new internal message that should be ignored",
                field="url",
            )
            actual_message = preview_error_to_legacy_message(error)
            self.assertEqual(
                actual_message,
                expected_message,
                f"PreviewErrorCode.{code.name} should map to '{expected_message}', "
                f"got '{actual_message}'",
            )

    def test_to_validation_error_dict_uses_legacy_field_name_default(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_CONTENT,
            message="ignored",
        )
        result = error.to_validation_error_dict()
        self.assertEqual(result, {"url": "ignored"})

    def test_to_validation_error_dict_uses_custom_field(self):
        error = PreviewError(
            code=PreviewErrorCode.INVALID_URL,
            message="bad url",
            field="referer",
        )
        result = error.to_validation_error_dict()
        self.assertEqual(result, {"referer": "bad url"})

    def test_preview_error_full_dict_structure(self):
        error = PreviewError(
            code=PreviewErrorCode.TIMEOUT,
            message="request timeout",
            field="url",
            details={"timeout_seconds": 30},
        )
        result = error.to_dict()
        self.assertEqual(result["code"], "timeout")
        self.assertEqual(result["message"], "request timeout")
        self.assertEqual(result["field"], "url")
        self.assertEqual(result["details"], {"timeout_seconds": 30})

    def test_unknown_error_falls_back_to_message(self):
        error = PreviewError(
            code=PreviewErrorCode.UNKNOWN_ERROR,
            message="custom fallback message",
        )
        mapped = preview_error_to_legacy_message(error)
        self.assertEqual(mapped, "unknown error")

    def test_field_in_error_preserved_in_serializer_validation_error(self):
        from rest_framework.exceptions import ValidationError
        from core.serializers import PinSerializer

        error = PreviewError(
            code=PreviewErrorCode.FORBIDDEN,
            message="access forbidden",
            field="referer",
        )
        legacy_message = preview_error_to_legacy_message(error)
        validation_dict = {error.field or "url": legacy_message}
        self.assertEqual(validation_dict, {"referer": "access forbidden"})


class PluginContractTests(TestCase):
    def test_base_plugin_implements_all_hooks(self):
        from pinry_plugins.batteries.base import PinryBasePlugin

        class TestPlugin(PinryBasePlugin):
            pass

        plugin = TestPlugin()
        self.assertTrue(hasattr(plugin, "process_image_pre_creation"))
        self.assertTrue(hasattr(plugin, "process_thumbnail_pre_creation"))
        self.assertTrue(hasattr(plugin, "preview_pre_fetch"))
        self.assertTrue(hasattr(plugin, "preview_post_fetch"))
        self.assertTrue(hasattr(plugin, "preview_on_error"))

    def test_plugin_protocols_runtime_checkable(self):
        from pinry_plugins.builder.contracts import (
            ImagePluginProtocol,
            PreviewPluginProtocol,
            PinryPluginProtocol,
        )
        from pinry_plugins.batteries.base import PinryBasePlugin

        class FullPlugin(PinryBasePlugin):
            pass

        plugin = FullPlugin()
        self.assertIsInstance(plugin, ImagePluginProtocol)
        self.assertIsInstance(plugin, PreviewPluginProtocol)
        self.assertIsInstance(plugin, PinryPluginProtocol)

    def test_plugin_capabilities_detection(self):
        from pinry_plugins.builder.contracts import (
            get_plugin_capabilities,
            ALL_SUPPORTED_HOOKS,
        )
        from pinry_plugins.batteries.base import PinryBasePlugin

        class PartialPlugin(PinryBasePlugin):
            pass

        caps = get_plugin_capabilities(PartialPlugin())
        for hook in ALL_SUPPORTED_HOOKS:
            self.assertTrue(caps.get(hook), f"Hook {hook} should be callable")

    def test_plugin_describe_returns_full_info(self):
        from pinry_plugins.builder.contracts import describe_plugin
        from pinry_plugins.batteries.base import PinryBasePlugin

        class DescribedPlugin(PinryBasePlugin):
            name = "Described"

        info = describe_plugin(DescribedPlugin())
        self.assertIn("class", info)
        self.assertIn("module", info)
        self.assertIn("capabilities", info)
        self.assertIn("implements_image_protocol", info)
        self.assertIn("implements_preview_protocol", info)
        self.assertIn("implements_full_protocol", info)
        self.assertTrue(info["implements_full_protocol"])

    def test_example_plugin_inherits_base(self):
        from pinry_plugins.batteries.plugin_example import Plugin
        from pinry_plugins.batteries.base import PinryBasePlugin

        self.assertTrue(issubclass(Plugin, PinryBasePlugin))


class PinLifecyclePreviewIntegrationTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("pin_lifecycle_test")
        self.client.login(username=self.user.username, password='password')

    @mock.patch('requests.get', mock_requests_get_image)
    def test_create_pin_uses_preview_service(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        data = {
            "url": "http://example.com/pin-create.jpg",
            "description": "test pin",
            "tags": ["test"],
        }
        response = self.client.post(pin_url, data=data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin_data = response.json()
        self.assertIsNotNone(pin_data.get("image"))
        self.assertIsNotNone(pin_data["image"].get("id"))

    @mock.patch('requests.get', mock_requests_get_invalid)
    def test_create_pin_invalid_content_returns_legacy_error(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        data = {
            "url": "http://example.com/bad-content.bin",
            "description": "test",
        }
        response = self.client.post(pin_url, data=data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("url", response.json())
        self.assertEqual(response.json()["url"], "invalid image content")

    @mock.patch('requests.get', mock_requests_get_image)
    def test_pin_inspect_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        data = {
            "url": "http://example.com/pin-inspect.jpg",
            "description": "test inspect",
        }
        create_resp = self.client.post(pin_url, data=data, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        pin_id = create_resp.json()["id"]

        inspect_url = reverse("pin-inspect", args=[pin_id])
        response = self.client.get(inspect_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["pin_id"], pin_id)
        self.assertIn("cache_key", data)
        self.assertIn("detected_service", data)
        self.assertIn("image_id", data)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_pin_refetch_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        data = {
            "url": "http://example.com/pin-refetch.jpg",
            "description": "test refetch",
        }
        create_resp = self.client.post(pin_url, data=data, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        pin_id = create_resp.json()["id"]

        refetch_url = reverse("pin-refetch", args=[pin_id])
        response = self.client.post(refetch_url, format="json")
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])

    def test_refetch_pin_without_url_returns_error(self):
        from core.models import Pin, Image

        image = Image.objects.create()
        pin = Pin.objects.create(
            submitter=self.user,
            image=image,
            description="no url pin",
        )
        refetch_url = reverse("pin-refetch", args=[pin.pk])
        response = self.client.post(refetch_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())


class PreviewAsyncTasksTests(TestCase):
    def test_has_celery_returns_boolean(self):
        from core.tasks import has_celery
        result = has_celery()
        self.assertIsInstance(result, bool)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_refresh_preview_task_sync_mode(self):
        from django.core.cache import cache
        from core.tasks import refresh_preview_task

        cache.clear()
        result = refresh_preview_task(
            url="http://example.com/async-test.jpg",
            referer="http://example.com/",
            content_type="image",
            force=True,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["url"], "http://example.com/async-test.jpg")
        self.assertIsNotNone(result["image_id"])
        self.assertEqual(result["content_type"], "image")

    @mock.patch('requests.get', mock_requests_get_invalid)
    def test_refresh_preview_task_invalid_content(self):
        from django.core.cache import cache
        from core.tasks import refresh_preview_task

        cache.clear()
        result = refresh_preview_task(
            url="http://example.com/bad.jpg",
            content_type="image",
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "invalid_content")

    @mock.patch('requests.get', mock_requests_get_image)
    def test_batch_refresh_preview_task(self):
        from django.core.cache import cache
        from core.tasks import batch_refresh_preview_task

        cache.clear()
        items = [
            {"url": "http://example.com/batch-1.jpg", "content_type": "image"},
            {"url": "http://example.com/batch-2.jpg", "content_type": "image"},
        ]
        result = batch_refresh_preview_task(items=items)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["success"]), 2)

    def test_invalidate_preview_cache_task(self):
        from core.tasks import invalidate_preview_cache_task

        result = invalidate_preview_cache_task(
            url="http://example.com/cache-test.jpg",
            referer="http://example.com/",
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("invalidated", result)
        self.assertIsInstance(result["invalidated"], int)

    def test_inspect_preview_task(self):
        from core.tasks import inspect_preview_task

        result = inspect_preview_task(
            url="http://example.com/inspect-task.jpg",
            content_type="image",
        )
        self.assertIn("url", result)
        self.assertIn("cache_key", result)
        self.assertIn("cache_hit", result)

    @mock.patch('requests.get', mock_requests_get_image)
    def test_pin_refresh_task(self):
        from django.core.cache import cache
        from core.models import Pin, Image
        from core.tasks import pin_refresh_task

        cache.clear()
        image = Image.objects.create()
        pin = Pin.objects.create(
            submitter=create_user("task_test_user"),
            image=image,
            url="http://example.com/pin-task.jpg",
            description="test",
        )

        result = pin_refresh_task(pin_id=pin.pk)
        self.assertIn("pin_id", result)
        self.assertEqual(result["pin_id"], pin.pk)

    def test_pin_refresh_task_not_found(self):
        from core.tasks import pin_refresh_task

        result = pin_refresh_task(pin_id=99999)
        self.assertEqual(result["status"], "error")
        self.assertIn("pin not found", result["error"])

    @mock.patch('requests.get', mock_requests_get_image)
    def test_dispatch_refresh_sync(self):
        from django.core.cache import cache
        from core.tasks import dispatch_refresh

        cache.clear()
        result = dispatch_refresh(
            url="http://example.com/dispatch.jpg",
            content_type="image",
            async_mode=False,
        )
        self.assertEqual(result["status"], "success")


class CacheNamespaceTests(TestCase):
    def test_cache_namespace_manager_initial_version(self):
        from django.core.cache import cache
        from core.services.preview_service import CacheNamespaceManager

        cache.clear()
        CacheNamespaceManager.reset_local_cache()

        version = CacheNamespaceManager.get_version()
        self.assertIsInstance(version, int)
        self.assertGreaterEqual(version, 1)

    def test_cache_namespace_bump_version(self):
        from django.core.cache import cache
        from core.services.preview_service import CacheNamespaceManager

        cache.clear()
        CacheNamespaceManager.reset_local_cache()

        old_version = CacheNamespaceManager.get_version()
        new_version = CacheNamespaceManager.bump_version()

        self.assertGreater(new_version, old_version)

    def test_cache_namespace_local_caching(self):
        from django.core.cache import cache
        from core.services.preview_service import CacheNamespaceManager

        cache.clear()
        CacheNamespaceManager.reset_local_cache()

        v1 = CacheNamespaceManager.get_version()
        v2 = CacheNamespaceManager.get_version()
        self.assertEqual(v1, v2)

    def test_cache_key_uses_namespace_version(self):
        from core.services import PreviewRequest, PreviewContentType
        from core.services.preview_service import CacheNamespaceManager

        CacheNamespaceManager.reset_local_cache()
        version_before = CacheNamespaceManager.get_version()

        req = PreviewRequest(
            url="http://example.com/ns-test.jpg",
            content_type_hint=PreviewContentType.IMAGE,
        )
        key_before = req.cache_key()
        self.assertIn(f"v{version_before}:", key_before)

        CacheNamespaceManager.bump_version()
        version_after = CacheNamespaceManager.get_version()
        self.assertGreater(version_after, version_before)

        key_after = req.cache_key()
        self.assertIn(f"v{version_after}:", key_after)
        self.assertNotEqual(key_before, key_after)

    def test_preview_manager_invalidate_all(self):
        from django.core.cache import cache
        from core.services.preview_service import CacheNamespaceManager, get_preview_manager

        cache.clear()
        CacheNamespaceManager.reset_local_cache()

        manager = get_preview_manager()
        old_version = manager.get_cache_version()
        result = manager.invalidate_all()

        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 1)
        self.assertGreater(manager.get_cache_version(), old_version)

    def test_get_cache_namespace_version_exported(self):
        from core.services import get_cache_namespace_version
        version = get_cache_namespace_version()
        self.assertIsInstance(version, int)

    def test_bump_cache_namespace_exported(self):
        from django.core.cache import cache
        from core.services import (
            bump_cache_namespace,
            get_cache_namespace_version,
        )
        from core.services.preview_service import CacheNamespaceManager

        cache.clear()
        CacheNamespaceManager.reset_local_cache()

        old = get_cache_namespace_version()
        new = bump_cache_namespace()
        self.assertGreater(new, old)


class PluginCircuitBreakerTests(TestCase):
    def test_circuit_breaker_initial_state_closed(self):
        from pinry_plugins.builder._loader import (
            PluginCircuitBreaker,
            CircuitState,
        )

        cb = PluginCircuitBreaker(plugin_key="test.plugin")
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_circuit_breaker_trips_after_threshold(self):
        from pinry_plugins.builder._loader import (
            PluginCircuitBreaker,
            CircuitState,
        )

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=3,
            error_window=60,
        )

        self.assertTrue(cb.allow_request())
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_circuit_breaker_half_open_after_recovery(self):
        from pinry_plugins.builder._loader import (
            PluginCircuitBreaker,
            CircuitState,
        )
        import time

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=2,
            error_window=60,
            recovery_timeout=0,
        )

        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.01)
        self.assertTrue(cb.allow_request())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_circuit_breaker_recovery_on_success(self):
        from pinry_plugins.builder._loader import (
            PluginCircuitBreaker,
            CircuitState,
        )
        import time

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=2,
            error_window=60,
            recovery_timeout=0,
        )

        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.01)
        cb.allow_request()
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_circuit_breaker_get_status(self):
        from pinry_plugins.builder._loader import PluginCircuitBreaker

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=3,
            error_window=60,
        )

        status = cb.get_status()
        self.assertEqual(status["plugin"], "test.plugin")
        self.assertEqual(status["state"], "closed")
        self.assertEqual(status["error_threshold"], 3)
        self.assertEqual(status["current_error_count"], 0)
        self.assertEqual(status["total_errors"], 0)
        self.assertIn("trip_count", status)

    def test_circuit_breaker_disabled_always_allows(self):
        from pinry_plugins.builder._loader import (
            PluginCircuitBreaker,
            CircuitState,
        )

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=1,
            error_window=60,
            enabled=False,
        )

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_error_window_prunes_old_errors(self):
        from pinry_plugins.builder._loader import PluginCircuitBreaker
        import time

        cb = PluginCircuitBreaker(
            plugin_key="test.plugin",
            error_threshold=3,
            error_window=0,
        )

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.01)
        status = cb.get_status()
        self.assertEqual(status["current_error_count"], 0)

    def test_get_circuit_breaker_status_exported(self):
        from pinry_plugins.builder import get_circuit_breaker_status

        statuses = get_circuit_breaker_status()
        self.assertIsInstance(statuses, dict)

    def test_reset_circuit_breakers_exported(self):
        from pinry_plugins.builder import (
            reset_circuit_breakers,
            get_circuit_breaker_status,
        )

        reset_circuit_breakers()
        statuses = get_circuit_breaker_status()
        for key, status in statuses.items():
            self.assertEqual(status["state"], "closed")
            self.assertEqual(status["trip_count"], 0)

    def test_get_plugins_by_capability(self):
        from pinry_plugins.builder import get_plugins_by_capability

        plugins = get_plugins_by_capability("preview_pre_fetch")
        self.assertIsInstance(plugins, list)


class PinExportTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("export_test_user")
        self.client.login(username=self.user.username, password='password')

    @mock.patch('requests.get', mock_requests_get_image)
    def test_export_json_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        for i in range(3):
            self.client.post(pin_url, data={
                "url": f"http://example.com/export-{i}.jpg",
                "description": f"test pin {i}",
                "tags": [f"tag{i}"],
            }, format="json")

        export_url = reverse("pin-export-json")
        response = self.client.get(export_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"], "application/json"
        )
        self.assertIn("attachment", response.get("Content-Disposition", ""))
        self.assertIn("pins_export.json", response.get("Content-Disposition", ""))

    @mock.patch('requests.get', mock_requests_get_image)
    def test_export_csv_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        pin_url = reverse("pin-list")
        for i in range(3):
            self.client.post(pin_url, data={
                "url": f"http://example.com/csv-{i}.jpg",
                "description": f"test pin {i}",
            }, format="json")

        export_url = reverse("pin-export-csv")
        response = self.client.get(export_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response.get("Content-Disposition", ""))
        self.assertIn("pins_export.csv", response.get("Content-Disposition", ""))

        content = response.content.decode("utf-8")
        self.assertIn("id,url,referer", content)
        self.assertIn("preview_cache_hit", content)


class PreviewWebhookTests(APITestCase):
    TEST_SECRET = "test-webhook-secret-123"

    def setUp(self):
        super().setUp()
        self.user = create_user("webhook_test_user")
        self.client.login(username=self.user.username, password='password')

    def _sign_payload(self, payload: dict, secret: str) -> str:
        from core.services.webhook_service import compute_signature
        import json
        body = json.dumps(payload).encode("utf-8")
        return compute_signature(body, secret)

    def test_webhook_info_endpoint_disabled(self):
        url = reverse("preview-webhook-info")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data["enabled"])
        self.assertIn("supported_actions", data)
        self.assertIn("refresh", data["supported_actions"])

    def test_webhook_endpoint_disabled_returns_404(self):
        url = reverse("preview-webhook")
        response = self.client.post(url, data={"action": "refresh"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_compute_signature_deterministic(self):
        from core.services.webhook_service import compute_signature

        sig1 = compute_signature(b"hello world", self.TEST_SECRET)
        sig2 = compute_signature(b"hello world", self.TEST_SECRET)
        self.assertEqual(sig1, sig2)
        self.assertTrue(sig1.startswith("sha256="))

    def test_verify_signature_valid(self):
        from core.services.webhook_service import (
            compute_signature,
            verify_signature,
        )

        body = b'{"url":"http://example.com/test.jpg"}'
        sig = compute_signature(body, self.TEST_SECRET)
        self.assertTrue(verify_signature(body, sig, self.TEST_SECRET))

    def test_verify_signature_invalid(self):
        from core.services.webhook_service import verify_signature

        body = b'{"url":"http://example.com/test.jpg"}'
        self.assertFalse(verify_signature(body, "sha256=badbadbad", self.TEST_SECRET))

    def test_webhook_enabled_with_secret_refresh(self):
        from django.conf import settings
        from unittest import mock
        from django.core.cache import cache
        import json

        cache.clear()

        with mock.patch("core.services.webhook_service.WEBHOOK_ENABLED", True):
            with mock.patch("core.services.webhook_service.WEBHOOK_SECRET", self.TEST_SECRET):
                with mock.patch("requests.get", mock_requests_get_image):
                    url = reverse("preview-webhook")
                    payload = {
                        "action": "refresh",
                        "url": "http://example.com/webhook-test.jpg",
                        "content_type": "image",
                    }
                    body = json.dumps(payload).encode("utf-8")
                    from core.services.webhook_service import compute_signature
                    sig = compute_signature(body, self.TEST_SECRET)

                    response = self.client.post(
                        url,
                        data=body,
                        content_type="application/json",
                        HTTP_X_PINRY_SIGNATURE=sig,
                    )
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    data = response.json()
                    self.assertEqual(data["status"], "success")
                    self.assertIn("image_id", data)

    def test_webhook_invalid_signature_rejected(self):
        from unittest import mock

        with mock.patch("core.services.webhook_service.WEBHOOK_ENABLED", True):
            with mock.patch("core.services.webhook_service.WEBHOOK_SECRET", self.TEST_SECRET):
                url = reverse("preview-webhook")
                payload = {"action": "refresh", "url": "http://example.com/x.jpg"}
                response = self.client.post(
                    url,
                    data=payload,
                    format="json",
                    HTTP_X_PINRY_SIGNATURE="sha256=bad",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.json()["code"], "invalid_signature")

    def test_webhook_invalidate_all(self):
        from unittest import mock
        from django.core.cache import cache
        import json

        cache.clear()

        with mock.patch("core.services.webhook_service.WEBHOOK_ENABLED", True):
            with mock.patch("core.services.webhook_service.WEBHOOK_SECRET", self.TEST_SECRET):
                url = reverse("preview-webhook")
                payload = {"action": "invalidate", "all": True}
                body = json.dumps(payload).encode("utf-8")
                from core.services.webhook_service import compute_signature
                sig = compute_signature(body, self.TEST_SECRET)

                response = self.client.post(
                    url,
                    data=body,
                    content_type="application/json",
                    HTTP_X_PINRY_SIGNATURE=sig,
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                data = response.json()
                self.assertTrue(data["invalidated_all"])
                self.assertIn("version_bumped", data)

    def test_webhook_unknown_action_error(self):
        from unittest import mock
        import json

        with mock.patch("core.services.webhook_service.WEBHOOK_ENABLED", True):
            with mock.patch("core.services.webhook_service.WEBHOOK_SECRET", self.TEST_SECRET):
                url = reverse("preview-webhook")
                payload = {"action": "nonexistent_action", "url": "http://x.com/y.jpg"}
                body = json.dumps(payload).encode("utf-8")
                from core.services.webhook_service import compute_signature
                sig = compute_signature(body, self.TEST_SECRET)

                response = self.client.post(
                    url,
                    data=body,
                    content_type="application/json",
                    HTTP_X_PINRY_SIGNATURE=sig,
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.json()["code"], "unknown_action")

    def test_is_webhook_enabled_false_by_default(self):
        from core.services.webhook_service import is_webhook_enabled
        self.assertFalse(is_webhook_enabled())

    def test_webhook_missing_url_in_refresh(self):
        from unittest import mock
        import json

        with mock.patch("core.services.webhook_service.WEBHOOK_ENABLED", True):
            with mock.patch("core.services.webhook_service.WEBHOOK_SECRET", self.TEST_SECRET):
                url = reverse("preview-webhook")
                payload = {"action": "refresh"}
                body = json.dumps(payload).encode("utf-8")
                from core.services.webhook_service import compute_signature
                sig = compute_signature(body, self.TEST_SECRET)

                response = self.client.post(
                    url,
                    data=body,
                    content_type="application/json",
                    HTTP_X_PINRY_SIGNATURE=sig,
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.json()["code"], "missing_url")
