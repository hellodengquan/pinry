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
