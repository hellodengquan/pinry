import re

import PIL.Image
import requests

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile

from core.models import Image
from django_images.models import Thumbnail


class MediaPreviewService:
    _default_ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/48.0.2564.82 Safari/537.36',
    }

    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
        '.tiff', '.tif', '.ico',
    }

    VIDEO_EXTENSIONS = {
        '.mp4', '.webm', '.ogg', '.ogv', '.mov', '.avi',
    }

    VIDEO_MIME_PREFIXES = ('video/',)

    IMAGE_MIME_PREFIXES = ('image/',)

    URL_PATTERN = re.compile(
        r'^https?://[^\s<>]+$',
        re.IGNORECASE,
    )

    @classmethod
    def detect_media_type(cls, url, content_type=None):
        if not url:
            return 'unknown'

        lower_url = url.lower().split('?')[0].split('#')[0]
        ext = None
        for e in list(cls.IMAGE_EXTENSIONS) + list(cls.VIDEO_EXTENSIONS):
            if lower_url.endswith(e):
                ext = e
                break

        if ext:
            if ext in cls.VIDEO_EXTENSIONS:
                return 'video'
            if ext in cls.IMAGE_EXTENSIONS:
                return 'image'

        if content_type:
            if content_type.startswith(cls.VIDEO_MIME_PREFIXES):
                return 'video'
            if content_type.startswith(cls.IMAGE_MIME_PREFIXES):
                return 'image'

        if cls.URL_PATTERN.match(url):
            return 'web_link'

        return 'unknown'

    @classmethod
    def _is_valid_image(cls, fp):
        fp.seek(0)
        try:
            PIL.Image.open(fp)
        except PIL.UnidentifiedImageError:
            fp.seek(0)
            return False
        else:
            fp.seek(0)
            return True

    @classmethod
    def _fetch_url(cls, url, referer=None):
        headers = dict(cls._default_ua)
        if referer is not None:
            headers["Referer"] = referer
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response

    @classmethod
    def _create_image_from_response(cls, url, response):
        file_name = url.split("/")[-1].split('#')[0].split('?')[0]
        buf = BytesIO()
        buf.write(response.content)
        if not cls._is_valid_image(buf):
            return None
        obj = InMemoryUploadedFile(
            buf, 'image', file_name, None, buf.tell(), None,
        )
        image = Image.objects.create(image=obj)
        Thumbnail.objects.get_or_create_at_sizes(
            image, settings.IMAGE_SIZES.keys(),
        )
        return image

    @classmethod
    def build_preview_from_url(cls, url, referer=None):
        result = {
            'media_type': 'unknown',
            'image': None,
            'video_url': None,
            'web_link_url': None,
            'preview_image_url': None,
            'metadata': {},
        }

        try:
            response = cls._fetch_url(url, referer)
        except requests.RequestException:
            result['media_type'] = cls.detect_media_type(url)
            if result['media_type'] == 'web_link':
                result['web_link_url'] = url
                result['metadata'] = {
                    'url': url,
                    'referer': referer or url,
                }
            return result

        content_type = response.headers.get('Content-Type', '')
        media_type = cls.detect_media_type(url, content_type)
        result['media_type'] = media_type

        if media_type == 'image':
            image = cls._create_image_from_response(url, response)
            if image:
                result['image'] = image
                result['preview_image_url'] = image.image.url
                result['metadata'] = {
                    'width': image.width,
                    'height': image.height,
                    'url': url,
                    'referer': referer or url,
                }
            else:
                result['media_type'] = 'web_link'
                result['web_link_url'] = url
                result['metadata'] = {
                    'url': url,
                    'referer': referer or url,
                }
        elif media_type == 'video':
            result['video_url'] = url
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'content_type': content_type,
            }
        else:
            result['web_link_url'] = url
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'content_type': content_type,
            }

        return result

    @classmethod
    def build_preview_from_upload(cls, uploaded_file):
        image = Image.objects.create(image=uploaded_file)
        Thumbnail.objects.get_or_create_at_sizes(
            image, settings.IMAGE_SIZES.keys(),
        )
        return {
            'media_type': 'image',
            'image': image,
            'video_url': None,
            'web_link_url': None,
            'preview_image_url': image.image.url,
            'metadata': {
                'width': image.width,
                'height': image.height,
            },
        }

    @classmethod
    def build_preview_from_pin(cls, pin):
        result = {
            'id': pin.id,
            'media_type': 'image',
            'description': pin.description or '',
            'referer': pin.referer,
            'url': pin.url,
            'tags': list(pin.tags.names()),
            'private': pin.private,
            'submitter': {
                'id': pin.submitter.id,
                'username': pin.submitter.username,
                'gravatar': pin.submitter.gravatar,
            },
            'published': pin.published.isoformat() if pin.published else None,
        }

        if pin.image:
            try:
                thumbnail = pin.image.thumbnail
                standard = pin.image.standard
                square = pin.image.square
                result['image'] = {
                    'id': pin.image.id,
                    'original': pin.image.image.url,
                    'original_width': pin.image.width,
                    'original_height': pin.image.height,
                    'thumbnail': {
                        'url': thumbnail.image.url,
                        'width': thumbnail.width,
                        'height': thumbnail.height,
                    },
                    'standard': {
                        'url': standard.image.url,
                        'width': standard.width,
                        'height': standard.height,
                    },
                    'square': {
                        'url': square.image.url,
                        'width': square.width,
                        'height': square.height,
                    },
                }
            except Thumbnail.DoesNotExist:
                result['image'] = {
                    'id': pin.image.id,
                    'original': pin.image.image.url,
                    'original_width': pin.image.width,
                    'original_height': pin.image.height,
                }

            if pin.url:
                media_type = cls.detect_media_type(pin.url)
                if media_type == 'video':
                    result['media_type'] = 'video'
                    result['video_url'] = pin.url
                elif media_type == 'web_link':
                    result['media_type'] = 'web_link'
                    result['web_link_url'] = pin.url

        return result

    @classmethod
    def build_display_item(cls, pin):
        preview = cls.build_preview_from_pin(pin)
        display = {
            'id': preview['id'],
            'media_type': preview['media_type'],
            'url': None,
            'large_image_url': None,
            'original_image_url': preview.get('url'),
            'referer': preview.get('referer'),
            'description': preview.get('description', ''),
            'tags': preview.get('tags', []),
            'private': preview.get('private', False),
            'author': preview['submitter']['username'],
            'avatar': '//gravatar.com/avatar/%s' % preview['submitter']['gravatar'],
            'owner_id': preview['submitter']['id'],
            'style': {},
            'class': {},
        }

        image_data = preview.get('image')
        if image_data:
            thumbnail = image_data.get('thumbnail', {})
            display['url'] = thumbnail.get('url', image_data.get('original'))
            display['large_image_url'] = image_data.get('original')
            display['original_width'] = image_data.get('original_width')
            if thumbnail:
                display['style'] = {
                    'width': '%spx' % thumbnail.get('width', 240),
                    'height': '%spx' % thumbnail.get('height', 0),
                }

        if preview['media_type'] == 'video':
            display['video_url'] = preview.get('video_url')

        if preview['media_type'] == 'web_link':
            display['web_link_url'] = preview.get('web_link_url')

        return display
