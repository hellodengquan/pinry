import os
import unittest

from django.test import TestCase, LiveServerTestCase
from django.core.cache import cache
import mock

from core.media_preview import MediaPreviewService
from core.tests.api import _create_mock_response


class MediaTypeDetectionTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_image_url_jpg(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/photo.jpg'),
            'image',
        )

    def test_image_url_png(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/photo.png'),
            'image',
        )

    def test_image_url_with_query(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/photo.jpg?w=200'),
            'image',
        )

    def test_video_url_mp4(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/clip.mp4'),
            'video',
        )

    def test_video_url_webm(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/clip.webm'),
            'video',
        )

    def test_web_link_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/page.html'),
            'web_link',
        )

    def test_web_link_url_no_extension(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/some/path/'),
            'web_link',
        )

    def test_content_type_image(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/get', content_type='image/jpeg',
            ),
            'image',
        )

    def test_content_type_video(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/get', content_type='video/mp4',
            ),
            'video',
        )

    def test_none_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(None),
            'unknown',
        )

    def test_empty_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(''),
            'unknown',
        )

    def test_youtube_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
            'video',
        )

    def test_youtu_be_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('https://youtu.be/dQw4w9WgXcQ'),
            'video',
        )

    def test_vimeo_url(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('https://vimeo.com/123456789'),
            'video',
        )

    def test_mp3_extension_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/audio.mp3'),
            'blocked',
        )

    def test_wav_extension_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/audio.wav'),
            'blocked',
        )

    def test_exe_extension_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/installer.exe'),
            'blocked',
        )

    def test_apk_extension_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/app.apk'),
            'blocked',
        )

    def test_svg_extension_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type('http://example.com/icon.svg'),
            'blocked',
        )

    def test_svg_mime_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/icon',
                content_type='image/svg+xml',
            ),
            'blocked',
        )

    def test_audio_mime_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/stream',
                content_type='audio/mpeg',
            ),
            'blocked',
        )

    def test_octet_stream_mime_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/download',
                content_type='application/octet-stream',
            ),
            'blocked',
        )

    def test_pdf_mime_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/doc.pdf',
                content_type='application/pdf',
            ),
            'blocked',
        )

    def test_msdownload_mime_blocked(self):
        self.assertEqual(
            MediaPreviewService.detect_media_type(
                'http://example.com/file',
                content_type='application/x-msdownload',
            ),
            'blocked',
        )

    def test_detect_result_cached(self):
        url = 'http://example.com/unique-page-' + str(id(self)) + '.html'
        cache.clear()
        first = MediaPreviewService.detect_media_type(url)
        second = MediaPreviewService.detect_media_type(url)
        self.assertEqual(first, second)
        cache_key = MediaPreviewService._cache_key(
            MediaPreviewService.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX,
            url, '',
        )
        self.assertIsNotNone(cache.get(cache_key))


def _mock_image_response():
    return _create_mock_response(
        open('docs/src/imgs/logo-dark.png', 'rb').read(),
        'image/png',
    )


def _mock_non_image_response():
    return _create_mock_response(b'not an image', 'text/html')


def _mock_video_response():
    return _create_mock_response(b'fake video data', 'video/mp4')


def _mock_mp3_response():
    return _create_mock_response(b'fake mp3 data', 'audio/mpeg')


def _mock_svg_response():
    return _create_mock_response(
        b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
        b'<script>alert("xss")</script></svg>',
        'image/svg+xml',
    )


def _mock_octet_stream_response():
    return _create_mock_response(b'binary data', 'application/octet-stream')


class SecurityTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_file_scheme_rejected(self):
        with self.assertRaises(MediaPreviewService.SecurityError):
            MediaPreviewService._validate_url_scheme('file:///etc/passwd')

    def test_ftp_scheme_rejected(self):
        with self.assertRaises(MediaPreviewService.SecurityError):
            MediaPreviewService._validate_url_scheme('ftp://example.com/file')

    def test_http_scheme_allowed(self):
        parsed = MediaPreviewService._validate_url_scheme('http://example.com/')
        self.assertEqual(parsed.scheme, 'http')

    def test_https_scheme_allowed(self):
        parsed = MediaPreviewService._validate_url_scheme('https://example.com/')
        self.assertEqual(parsed.scheme, 'https')

    def test_too_many_redirects_rejected(self):
        mock_resp = _create_mock_response(b'data', 'image/png', history=['r1', 'r2', 'r3', 'r4', 'r5', 'r6'])
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.SecurityError) as ctx:
                MediaPreviewService._fetch_url('http://example.com/')
            self.assertIn('Too many redirects', str(ctx.exception))

    def test_large_content_length_rejected(self):
        mock_resp = _create_mock_response(b'x' * 1000, 'image/png')
        mock_resp.headers['Content-Length'] = str(100 * 1024 * 1024)
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.SecurityError) as ctx:
                MediaPreviewService._fetch_url('http://example.com/', max_content_length=50 * 1024 * 1024)
            self.assertIn('Content-Length', str(ctx.exception))

    def test_mp3_extension_rejected_in_fetch(self):
        mock_resp = _mock_mp3_response()
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.BlockedContentTypeError):
                MediaPreviewService._fetch_url('http://example.com/audio.mp3')

    def test_audio_mime_rejected_in_fetch(self):
        mock_resp = _mock_mp3_response()
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.BlockedContentTypeError):
                MediaPreviewService._fetch_url('http://example.com/stream')

    def test_svg_extension_rejected_in_fetch(self):
        mock_resp = _mock_svg_response()
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.BlockedContentTypeError):
                MediaPreviewService._fetch_url('http://example.com/icon.svg')

    def test_svg_mime_rejected_in_fetch(self):
        mock_resp = _mock_svg_response()
        with mock.patch('requests.get', return_value=mock_resp):
            with self.assertRaises(MediaPreviewService.BlockedContentTypeError):
                MediaPreviewService._fetch_url('http://example.com/icon')


class CacheInvalidationTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_invalidate_oembed_cache(self):
        url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        provider = 'youtube'
        cache_key = MediaPreviewService._cache_key(
            MediaPreviewService.OEMBED_CACHE_KEY_PREFIX, provider, url,
        )
        cache.set(cache_key, {'title': 'Old Title'}, 3600)
        self.assertIsNotNone(cache.get(cache_key))

        MediaPreviewService.invalidate_cache_for_url(url)

        self.assertIsNone(cache.get(cache_key))

    def test_invalidate_detect_cache(self):
        url = 'http://example.com/photo.jpg'
        cache_key = MediaPreviewService._cache_key(
            MediaPreviewService.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX, url, '',
        )
        cache.set(cache_key, 'image', 3600)
        self.assertIsNotNone(cache.get(cache_key))

        MediaPreviewService.invalidate_cache_for_url(url)

        self.assertIsNone(cache.get(cache_key))

    def test_invalidate_old_url_on_change(self):
        old_url = 'https://www.youtube.com/watch?v=OLD_VIDEO_ID'
        new_url = 'https://www.youtube.com/watch?v=NEW_VIDEO_ID'
        old_key = MediaPreviewService._cache_key(
            MediaPreviewService.OEMBED_CACHE_KEY_PREFIX, 'youtube', old_url,
        )
        new_key = MediaPreviewService._cache_key(
            MediaPreviewService.OEMBED_CACHE_KEY_PREFIX, 'youtube', new_url,
        )
        cache.set(old_key, {'title': 'Old Video'}, 3600)
        cache.set(new_key, {'title': 'New Video'}, 3600)

        MediaPreviewService.invalidate_cache_for_url(new_url)
        if old_url != new_url:
            MediaPreviewService.invalidate_cache_for_url(old_url)

        self.assertIsNone(cache.get(old_key))
        self.assertIsNone(cache.get(new_key))

    def test_invalidate_non_video_url_only_deletes_detect(self):
        url = 'http://example.com/page.html'
        detect_key = MediaPreviewService._cache_key(
            MediaPreviewService.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX, url, '',
        )
        cache.set(detect_key, 'web_link', 3600)

        MediaPreviewService.invalidate_cache_for_url(url)

        self.assertIsNone(cache.get(detect_key))


class BuildPreviewFromUrlTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    @mock.patch('requests.get', return_value=_mock_image_response())
    def test_image_url_returns_image_type(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/photo.jpg',
        )
        self.assertEqual(result['media_type'], 'image')
        self.assertIsNotNone(result['image'])
        self.assertIn('width', result['metadata'])
        self.assertIn('height', result['metadata'])

    @mock.patch('requests.get', return_value=_mock_non_image_response())
    def test_non_image_url_falls_back_to_web_link(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/photo.jpg',
        )
        self.assertEqual(result['media_type'], 'web_link')
        self.assertIsNone(result['image'])
        self.assertEqual(result['web_link_url'], 'http://example.com/photo.jpg')

    @mock.patch('requests.get', return_value=_mock_video_response())
    def test_video_url_returns_video_type(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/clip.mp4',
        )
        self.assertEqual(result['media_type'], 'video')
        self.assertEqual(result['video_url'], 'http://example.com/clip.mp4')

    @mock.patch('requests.get', side_effect=Exception('network error'))
    def test_network_error_falls_back_gracefully(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/page.html',
        )
        self.assertEqual(result['media_type'], 'web_link')
        self.assertEqual(result['web_link_url'], 'http://example.com/page.html')

    @mock.patch('requests.get')
    def test_file_url_rejected(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'file:///etc/passwd',
        )
        self.assertEqual(result['media_type'], 'unknown')
        self.assertIn('error', result['metadata'])
        self.assertEqual(mock_get.call_count, 0)

    @mock.patch('requests.get')
    def test_youtube_url_uses_oembed(self, mock_get):
        def mock_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            if 'youtube.com/oembed' in url:
                oembed_resp = _create_mock_response(b'{}', 'application/json')
                oembed_resp.json = lambda: {
                    'title': 'Test Video',
                    'thumbnail_url': 'https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg',
                    'duration': 120,
                }
                return oembed_resp
            return _mock_video_response()

        mock_get.side_effect = mock_side_effect
        result = MediaPreviewService.build_preview_from_url(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        )
        self.assertEqual(result['media_type'], 'video')
        self.assertIn('oembed', result['metadata'])
        self.assertEqual(result['metadata']['title'], 'Test Video')
        self.assertEqual(result['metadata']['duration'], 120)

    @mock.patch('requests.get')
    def test_oembed_result_cached(self, mock_get):
        cache.clear()
        call_counter = [0]

        def mock_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            if 'youtube.com/oembed' in url:
                call_counter[0] += 1
                oembed_resp = _create_mock_response(b'{}', 'application/json')
                oembed_resp.json = lambda: {'title': 'Cached Video'}
                return oembed_resp
            return _mock_video_response()

        mock_get.side_effect = mock_side_effect

        url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        result1 = MediaPreviewService.build_preview_from_url(url)
        result2 = MediaPreviewService.build_preview_from_url(url)

        self.assertEqual(result1['metadata']['title'], 'Cached Video')
        self.assertEqual(result2['metadata']['title'], 'Cached Video')
        self.assertEqual(
            call_counter[0], 1,
            'oembed endpoint should be called only once due to caching',
        )

    @mock.patch('requests.get')
    def test_youtube_url_oembed_failure_survives(self, mock_get):
        def mock_side_effect(*args, **kwargs):
            raise Exception('oembed failed')

        mock_get.side_effect = mock_side_effect
        result = MediaPreviewService.build_preview_from_url(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        )
        self.assertEqual(result['media_type'], 'video')
        self.assertEqual(result['metadata']['provider'], 'youtube')

    @mock.patch('requests.get', return_value=_mock_mp3_response())
    def test_mp3_url_blocked(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/song.mp3',
        )
        self.assertEqual(result['media_type'], 'blocked')
        self.assertIn('error', result['metadata'])

    @mock.patch('requests.get', return_value=_mock_octet_stream_response())
    def test_octet_stream_blocked(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/download',
        )
        self.assertEqual(result['media_type'], 'blocked')
        self.assertIn('error', result['metadata'])

    @mock.patch('requests.get', return_value=_mock_svg_response())
    def test_svg_url_blocked(self, mock_get):
        result = MediaPreviewService.build_preview_from_url(
            'http://example.com/icon.svg',
        )
        self.assertEqual(result['media_type'], 'blocked')
        self.assertIn('error', result['metadata'])


class VideoProviderDetectionTests(TestCase):
    def test_youtube_watch_url(self):
        self.assertEqual(
            MediaPreviewService._detect_video_provider('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
            'youtube',
        )

    def test_youtu_be_short_url(self):
        self.assertEqual(
            MediaPreviewService._detect_video_provider('https://youtu.be/dQw4w9WgXcQ'),
            'youtube',
        )

    def test_youtube_embed_url(self):
        self.assertEqual(
            MediaPreviewService._detect_video_provider('https://www.youtube.com/embed/dQw4w9WgXcQ'),
            'youtube',
        )

    def test_vimeo_url(self):
        self.assertEqual(
            MediaPreviewService._detect_video_provider('https://vimeo.com/123456789'),
            'vimeo',
        )

    def test_regular_image_url_not_detected(self):
        self.assertIsNone(
            MediaPreviewService._detect_video_provider('https://example.com/photo.jpg'),
        )

    def test_none_url_not_detected(self):
        self.assertIsNone(
            MediaPreviewService._detect_video_provider(None),
        )


class BuildDisplayItemTests(TestCase):
    def test_build_display_item_from_raw_pin_data(self):
        pin = {
            'id': 1,
            'url': 'http://example.com/photo.jpg',
            'referer': 'http://example.com/',
            'description': 'A nice photo',
            'tags': ['nature'],
            'private': False,
            'submitter': {
                'id': 10,
                'username': 'testuser',
                'gravatar': 'abc123',
            },
            'image': {
                'id': 5,
                'image': '/media/image/original/photo.jpg',
                'width': 800,
                'height': 600,
                'thumbnail': {
                    'image': '/media/image/thumbnail/photo.jpg',
                    'width': 240,
                    'height': 180,
                },
                'standard': {
                    'image': '/media/image/standard/photo.jpg',
                    'width': 600,
                    'height': 450,
                },
                'square': {
                    'image': '/media/image/square/photo.jpg',
                    'width': 125,
                    'height': 125,
                },
            },
        }

        display = MediaPreviewService.build_display_item(pin)
        self.assertEqual(display['id'], 1)
        self.assertEqual(display['media_type'], 'image')
        self.assertEqual(display['author'], 'testuser')
        self.assertEqual(display['avatar'], '//gravatar.com/avatar/abc123')
        self.assertIn('width', display['style'])
        self.assertIn('height', display['style'])


YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
VIMEO_VIDEO_URL = 'https://vimeo.com/22439234'


@unittest.skipUnless(
    os.environ.get('PINRY_LIVE_OEMBED_TESTS'),
    'Set PINRY_LIVE_OEMBED_TESTS=1 to run live oembed integration tests '
    'against real YouTube / Vimeo endpoints',
)
class OEmbedLiveIntegrationTests(LiveServerTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_live_youtube_oembed_returns_required_fields(self):
        result = MediaPreviewService._fetch_oembed(YOUTUBE_VIDEO_URL, 'youtube')
        self.assertIsNotNone(
            result,
            'YouTube oembed returned None; check network or endpoint change',
        )
        self.assertIn('title', result, 'YouTube oembed missing "title" field')
        self.assertIn('thumbnail_url', result, 'YouTube oembed missing "thumbnail_url" field')
        self.assertIn('provider_name', result, 'YouTube oembed missing "provider_name" field')
        self.assertEqual(result['provider_name'], 'YouTube')
        self.assertTrue(
            result['thumbnail_url'].startswith('https://'),
            'YouTube thumbnail_url should be https: %s' % result['thumbnail_url'],
        )

    def test_live_vimeo_oembed_returns_required_fields(self):
        result = MediaPreviewService._fetch_oembed(VIMEO_VIDEO_URL, 'vimeo')
        self.assertIsNotNone(
            result,
            'Vimeo oembed returned None; check network or endpoint change',
        )
        self.assertIn('title', result, 'Vimeo oembed missing "title" field')
        self.assertIn('thumbnail_url', result, 'Vimeo oembed missing "thumbnail_url" field')
        self.assertIn('provider_name', result, 'Vimeo oembed missing "provider_name" field')
        self.assertEqual(result['provider_name'], 'Vimeo')
        self.assertTrue(
            result['thumbnail_url'].startswith('https://'),
            'Vimeo thumbnail_url should be https: %s' % result['thumbnail_url'],
        )

    def test_live_youtube_build_preview_full_flow(self):
        result = MediaPreviewService.build_preview_from_url(YOUTUBE_VIDEO_URL)
        self.assertEqual(result['media_type'], 'video')
        self.assertEqual(result['video_url'], YOUTUBE_VIDEO_URL)
        self.assertIn('oembed', result['metadata'])
        oembed = result['metadata']['oembed']
        self.assertIn('title', oembed)
        self.assertIn('thumbnail_url', oembed)
        self.assertEqual(oembed['provider_name'], 'YouTube')

    def test_live_youtube_schema_fields_type_validation(self):
        result = MediaPreviewService._fetch_oembed(YOUTUBE_VIDEO_URL, 'youtube')
        self.assertIsNotNone(result)
        self.assertIsInstance(result['title'], str)
        self.assertIsInstance(result['thumbnail_url'], str)
        if 'thumbnail_width' in result:
            self.assertIsInstance(result['thumbnail_width'], int)
        if 'thumbnail_height' in result:
            self.assertIsInstance(result['thumbnail_height'], int)

    def test_live_vimeo_schema_fields_type_validation(self):
        result = MediaPreviewService._fetch_oembed(VIMEO_VIDEO_URL, 'vimeo')
        self.assertIsNotNone(result)
        self.assertIsInstance(result['title'], str)
        self.assertIsInstance(result['thumbnail_url'], str)
        if 'duration' in result:
            self.assertIsInstance(result['duration'], int)

    def test_live_oembed_cache_then_invalidate(self):
        url = YOUTUBE_VIDEO_URL
        r1 = MediaPreviewService._fetch_oembed(url, 'youtube')
        self.assertIsNotNone(r1)
        cache_key = MediaPreviewService._cache_key(
            MediaPreviewService.OEMBED_CACHE_KEY_PREFIX, 'youtube', url,
        )
        self.assertIsNotNone(cache.get(cache_key))

        MediaPreviewService.invalidate_cache_for_url(url)
        self.assertIsNone(cache.get(cache_key))

        r2 = MediaPreviewService._fetch_oembed(url, 'youtube')
        self.assertIsNotNone(r2)
        self.assertEqual(r1['title'], r2['title'])

