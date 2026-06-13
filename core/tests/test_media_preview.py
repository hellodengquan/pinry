from django.test import TestCase
import mock

from core.media_preview import MediaPreviewService
from core.tests.api import _create_mock_response


class MediaTypeDetectionTests(TestCase):
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


def _mock_image_response():
    return _create_mock_response(
        open('docs/src/imgs/logo-dark.png', 'rb').read(),
        'image/png',
    )


def _mock_non_image_response():
    return _create_mock_response(b'not an image', 'text/html')


def _mock_video_response():
    return _create_mock_response(b'fake video data', 'video/mp4')


class SecurityTests(TestCase):
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


class BuildPreviewFromUrlTests(TestCase):
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
    def test_youtube_url_oembed_failure_survives(self, mock_get):
        def mock_side_effect(*args, **kwargs):
            raise Exception('oembed failed')

        mock_get.side_effect = mock_side_effect
        result = MediaPreviewService.build_preview_from_url(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        )
        self.assertEqual(result['media_type'], 'video')
        self.assertEqual(result['metadata']['provider'], 'youtube')


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

        display = MediaPreviewService.buildDisplayItem(pin)
        self.assertEqual(display['id'], 1)
        self.assertEqual(display['mediaType'], 'image')
        self.assertEqual(display['author'], 'testuser')
        self.assertEqual(display['avatar'], '//gravatar.com/avatar/abc123')
        self.assertIn('width', display['style'])
        self.assertIn('height', display['style'])
