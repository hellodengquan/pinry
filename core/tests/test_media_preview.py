from django.test import TestCase
import mock

from core.media_preview import MediaPreviewService


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


def _mock_image_response():
    response = mock.Mock(
        content=open('docs/src/imgs/logo-dark.png', 'rb').read(),
        headers={'Content-Type': 'image/png'},
    )
    response.raise_for_status.return_value = None
    return response


def _mock_non_image_response():
    response = mock.Mock(
        content=b'not an image',
        headers={'Content-Type': 'text/html'},
    )
    response.raise_for_status.return_value = None
    return response


def _mock_video_response():
    response = mock.Mock(
        content=b'fake video data',
        headers={'Content-Type': 'video/mp4'},
    )
    response.raise_for_status.return_value = None
    return response


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
