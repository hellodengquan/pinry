import hashlib
import re
from urllib.parse import urlparse

import PIL.Image
import requests

from io import BytesIO

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import InMemoryUploadedFile

from core.models import Image
from django_images.models import Thumbnail


class MediaPreviewService:
    _default_ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/48.0.2564.82 Safari/537.36',
    }

    ALLOWED_SCHEMES = {'http', 'https'}
    MAX_REDIRECTS = 5
    REQUEST_TIMEOUT = 15
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    MAX_IMAGE_CONTENT_LENGTH = 20 * 1024 * 1024

    AUDIO_EXTENSIONS = {
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.oga', '.m4a',
        '.wma', '.opus', '.aiff', '.amr',
    }
    EXECUTABLE_EXTENSIONS = {
        '.exe', '.msi', '.bat', '.cmd', '.sh', '.com', '.scr',
        '.pif', '.app', '.dmg', '.pkg', '.deb', '.rpm', '.apk',
        '.iso', '.jar', '.wsf', '.vbs', '.ps1', '.so', '.dll',
        '.svg',
    }

    BLOCKED_MIME_PREFIXES = (
        'audio/',
        'application/x-msdownload',
        'application/x-dosexec',
        'application/x-executable',
        'application/x-sharedlib',
        'application/vnd.android.package-archive',
        'application/x-apple-diskimage',
        'application/x-iso9660-image',
        'application/java-archive',
        'application/x-sh',
        'application/x-bat',
    )
    BLOCKED_MIME_EXACTS = {
        'application/octet-stream',
        'application/pdf',
        'image/svg+xml',
    }

    OEMBED_CACHE_KEY_PREFIX = 'pinry:oembed:'
    DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX = 'pinry:detect:'

    OEMBED_CACHE_TIMEOUT = getattr(
        settings, 'OEMBED_CACHE_TIMEOUT', 60 * 60 * 24,
    )
    DETECT_MEDIA_TYPE_CACHE_TIMEOUT = getattr(
        settings, 'DETECT_MEDIA_TYPE_CACHE_TIMEOUT', 60 * 60,
    )

    YOUTUBE_PATTERN = re.compile(
        r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)(?P<id>[A-Za-z0-9_-]{11})',
        re.IGNORECASE,
    )
    VIMEO_PATTERN = re.compile(
        r'^(https?://)?(www\.)?vimeo\.com/(?P<id>\d+)',
        re.IGNORECASE,
    )

    OEMBED_PROVIDERS = {
        'youtube': {
            'endpoint': 'https://www.youtube.com/oembed',
            'params': {'format': 'json'},
        },
        'vimeo': {
            'endpoint': 'https://vimeo.com/api/oembed.json',
            'params': {},
        },
    }

    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
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

    class SecurityError(Exception):
        pass

    class BlockedContentTypeError(SecurityError):
        pass

    @classmethod
    def _cache_key(cls, prefix, *parts):
        raw = ':'.join(str(p) for p in parts)
        digest = hashlib.md5(raw.encode('utf-8')).hexdigest()
        return '%s%s' % (prefix, digest)

    @classmethod
    def invalidate_cache_for_url(cls, url, referer=None):
        if not url:
            return
        provider = cls._detect_video_provider(url)
        if provider:
            oembed_key = cls._cache_key(
                cls.OEMBED_CACHE_KEY_PREFIX, provider, url,
            )
            cache.delete(oembed_key)
        detect_key = cls._cache_key(
            cls.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX, url, '',
        )
        cache.delete(detect_key)
        if referer:
            detect_key_with_ref = cls._cache_key(
                cls.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX,
                url, referer,
            )
            cache.delete(detect_key_with_ref)

    @classmethod
    def _validate_url_scheme(cls, url):
        parsed = urlparse(url)
        if parsed.scheme not in cls.ALLOWED_SCHEMES:
            raise cls.SecurityError(
                'URL scheme %s is not allowed' % parsed.scheme,
            )
        return parsed

    @classmethod
    def _check_extension_blacklist(cls, url):
        lower_url = url.lower().split('?')[0].split('#')[0]
        for ext in cls.AUDIO_EXTENSIONS:
            if lower_url.endswith(ext):
                raise cls.BlockedContentTypeError(
                    'Audio file extension %s is not allowed' % ext,
                )
        for ext in cls.EXECUTABLE_EXTENSIONS:
            if lower_url.endswith(ext):
                raise cls.BlockedContentTypeError(
                    'Executable file extension %s is not allowed' % ext,
                )
        return None

    @classmethod
    def _check_mime_blacklist(cls, content_type):
        if not content_type:
            return None
        ct = content_type.lower().split(';')[0].strip()
        if ct in cls.BLOCKED_MIME_EXACTS:
            raise cls.BlockedContentTypeError(
                'Content type %s is not allowed' % ct,
            )
        for prefix in cls.BLOCKED_MIME_PREFIXES:
            if ct.startswith(prefix):
                raise cls.BlockedContentTypeError(
                    'Content type %s is not allowed' % ct,
                )
        return None

    @classmethod
    def _detect_video_provider(cls, url):
        if cls.YOUTUBE_PATTERN.match(url):
            return 'youtube'
        if cls.VIMEO_PATTERN.match(url):
            return 'vimeo'
        return None

    @classmethod
    def _fetch_oembed(cls, url, provider):
        cache_key = cls._cache_key(cls.OEMBED_CACHE_KEY_PREFIX, provider, url)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached if cached else None
        try:
            provider_config = cls.OEMBED_PROVIDERS.get(provider)
            if not provider_config:
                return None
            params = dict(provider_config.get('params', {}))
            params['url'] = url
            response = requests.get(
                provider_config['endpoint'],
                params=params,
                timeout=cls.REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
            result = {}
            if 'title' in data:
                result['title'] = data['title']
            if 'thumbnail_url' in data:
                result['thumbnail_url'] = data['thumbnail_url']
            if 'thumbnail_width' in data:
                result['thumbnail_width'] = data['thumbnail_width']
            if 'thumbnail_height' in data:
                result['thumbnail_height'] = data['thumbnail_height']
            if 'duration' in data:
                result['duration'] = data['duration']
            if 'author_name' in data:
                result['author_name'] = data['author_name']
            if 'provider_name' in data:
                result['provider_name'] = data['provider_name']
            if 'html' in data:
                result['embed_html'] = data['html']
            cache.set(cache_key, result or False, cls.OEMBED_CACHE_TIMEOUT)
            return result
        except (requests.RequestException, ValueError, KeyError):
            cache.set(cache_key, False, 60)
            return None

    @classmethod
    def detect_media_type(cls, url, content_type=None, use_cache=True):
        if not url:
            return 'unknown'

        if use_cache:
            cache_key = cls._cache_key(
                cls.DETECT_MEDIA_TYPE_CACHE_KEY_PREFIX,
                url,
                content_type or '',
            )
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            cls._check_extension_blacklist(url)
        except cls.BlockedContentTypeError:
            if use_cache:
                cache.set(
                    cache_key, 'blocked',
                    cls.DETECT_MEDIA_TYPE_CACHE_TIMEOUT,
                )
            return 'blocked'

        if content_type:
            try:
                cls._check_mime_blacklist(content_type)
            except cls.BlockedContentTypeError:
                if use_cache:
                    cache.set(
                        cache_key, 'blocked',
                        cls.DETECT_MEDIA_TYPE_CACHE_TIMEOUT,
                    )
                return 'blocked'

        result = 'unknown'

        if cls._detect_video_provider(url):
            result = 'video'
        else:
            lower_url = url.lower().split('?')[0].split('#')[0]
            ext = None
            for e in list(cls.IMAGE_EXTENSIONS) + list(cls.VIDEO_EXTENSIONS):
                if lower_url.endswith(e):
                    ext = e
                    break

            if ext:
                if ext in cls.VIDEO_EXTENSIONS:
                    result = 'video'
                elif ext in cls.IMAGE_EXTENSIONS:
                    result = 'image'
            elif content_type:
                if content_type.startswith(cls.VIDEO_MIME_PREFIXES):
                    result = 'video'
                elif content_type.startswith(cls.IMAGE_MIME_PREFIXES):
                    result = 'image'
                elif cls.URL_PATTERN.match(url):
                    result = 'web_link'
            elif cls.URL_PATTERN.match(url):
                result = 'web_link'

        if use_cache and result != 'unknown':
            cache.set(cache_key, result, cls.DETECT_MEDIA_TYPE_CACHE_TIMEOUT)
        return result

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
    def _fetch_url(cls, url, referer=None, max_content_length=None):
        cls._validate_url_scheme(url)
        cls._check_extension_blacklist(url)

        if max_content_length is None:
            max_content_length = cls.MAX_CONTENT_LENGTH

        headers = dict(cls._default_ua)
        if referer is not None:
            cls._validate_url_scheme(referer)
            headers["Referer"] = referer

        response = requests.get(
            url,
            headers=headers,
            timeout=cls.REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if len(response.history) > cls.MAX_REDIRECTS:
            response.close()
            raise cls.SecurityError(
                'Too many redirects: %s' % len(response.history),
            )

        content_length_header = response.headers.get('Content-Length')
        if content_length_header:
            try:
                content_length = int(content_length_header)
                if content_length > max_content_length:
                    response.close()
                    raise cls.SecurityError(
                        'Content-Length %s exceeds maximum allowed %s' % (
                            content_length, max_content_length,
                        ),
                    )
            except (ValueError, TypeError):
                pass

        content_type = response.headers.get('Content-Type', '')
        cls._check_mime_blacklist(content_type)

        response.raise_for_status()

        content = BytesIO()
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                total_bytes += len(chunk)
                if total_bytes > max_content_length:
                    response.close()
                    raise cls.SecurityError(
                        'Content exceeds maximum allowed size: %s' % max_content_length,
                    )
                content.write(chunk)

        content.seek(0)
        response.close()

        wrapped_response = type('Response', (), {})()
        wrapped_response.content = content.getvalue()
        wrapped_response.headers = response.headers
        wrapped_response.status_code = response.status_code
        return wrapped_response

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
    def _enrich_metadata_with_oembed(cls, url, metadata):
        provider = cls._detect_video_provider(url)
        if provider:
            oembed_data = cls._fetch_oembed(url, provider)
            if oembed_data:
                metadata.update({
                    'oembed': oembed_data,
                    'title': oembed_data.get('title'),
                    'thumbnail_url': oembed_data.get('thumbnail_url'),
                    'duration': oembed_data.get('duration'),
                    'provider': provider,
                })
        return metadata

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
            cls._validate_url_scheme(url)
        except cls.SecurityError as e:
            result['media_type'] = 'unknown'
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'error': 'Invalid URL scheme: %s' % e,
            }
            return result

        pre_detected = cls.detect_media_type(url)
        if pre_detected == 'blocked':
            result['media_type'] = 'blocked'
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'error': 'Content blocked by extension or MIME type policy',
            }
            return result

        provider = cls._detect_video_provider(url)
        if provider:
            result['media_type'] = 'video'
            result['video_url'] = url
            result['metadata'] = cls._enrich_metadata_with_oembed(
                url,
                {
                    'url': url,
                    'referer': referer or url,
                    'provider': provider,
                },
            )
            return result

        response = None
        try:
            response = cls._fetch_url(
                url,
                referer,
                max_content_length=cls.MAX_IMAGE_CONTENT_LENGTH,
            )
        except cls.BlockedContentTypeError as e:
            result['media_type'] = 'blocked'
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'error': str(e),
            }
            return result
        except cls.SecurityError as e:
            result['media_type'] = cls.detect_media_type(url)
            if result['media_type'] == 'web_link':
                result['web_link_url'] = url
            elif result['media_type'] == 'video':
                result['video_url'] = url
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'error': str(e),
            }
            return result
        except requests.RequestException:
            result['media_type'] = cls.detect_media_type(url)
            if result['media_type'] == 'web_link':
                result['web_link_url'] = url
            elif result['media_type'] == 'video':
                result['video_url'] = url
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
            }
            return result

        content_type = response.headers.get('Content-Type', '')
        media_type = cls.detect_media_type(url, content_type)
        result['media_type'] = media_type

        if media_type == 'blocked':
            result['metadata'] = {
                'url': url,
                'referer': referer or url,
                'error': 'Content blocked by MIME type policy',
            }
            return result

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
            result['metadata'] = cls._enrich_metadata_with_oembed(
                url,
                {
                    'url': url,
                    'referer': referer or url,
                    'content_type': content_type,
                },
            )
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
