import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Type, Union

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class CacheNamespaceManager:
    _global_version_key = "preview:cache_version"
    _local_version: Optional[int] = None
    _local_version_ts: float = 0
    _version_ttl = 60
    _lock = Lock()

    @classmethod
    def get_version(cls) -> int:
        now = time.time()
        if cls._local_version is not None and (now - cls._local_version_ts) < cls._version_ttl:
            return cls._local_version

        with cls._lock:
            if cls._local_version is not None and (now - cls._local_version_ts) < cls._version_ttl:
                return cls._local_version

            try:
                version = cache.get(cls._global_version_key)
                if version is None:
                    version = 1
                    cache.set(cls._global_version_key, version, timeout=None)
                cls._local_version = int(version)
                cls._local_version_ts = now
            except Exception:
                logger.exception("Failed to get cache namespace version")
                cls._local_version = cls._local_version or 1
                cls._local_version_ts = now

            return cls._local_version

    @classmethod
    def bump_version(cls) -> int:
        try:
            try:
                new_version = cache.incr(cls._global_version_key)
            except ValueError:
                cache.add(cls._global_version_key, 1, timeout=None)
                new_version = 1
        except Exception:
            logger.exception("Failed to bump cache namespace version")
            new_version = int(time.time())

        with cls._lock:
            cls._local_version = new_version
            cls._local_version_ts = time.time()

        logger.info("Preview cache namespace bumped to version %d", new_version)
        return new_version

    @classmethod
    def reset_local_cache(cls) -> None:
        with cls._lock:
            cls._local_version = None
            cls._local_version_ts = 0


def get_cache_namespace_version() -> int:
    return CacheNamespaceManager.get_version()


def bump_cache_namespace() -> int:
    return CacheNamespaceManager.bump_version()


class PreviewErrorCode(str, Enum):
    INVALID_URL = "invalid_url"
    NETWORK_ERROR = "network_error"
    INVALID_CONTENT = "invalid_content"
    CONTENT_TOO_LARGE = "content_too_large"
    FORMAT_UNSUPPORTED = "format_unsupported"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNKNOWN_ERROR = "unknown_error"


class PreviewContentType(str, Enum):
    IMAGE = "image"
    WEBPAGE = "webpage"
    VIDEO = "video"
    UNKNOWN = "unknown"


class PreviewError(Exception):
    def __init__(
        self,
        code: PreviewErrorCode,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.field:
            result["field"] = self.field
        if self.details:
            result["details"] = self.details
        return result

    def to_validation_error_dict(self) -> Dict[str, str]:
        field_name = self.field or "url"
        return {field_name: self.message}


_ERROR_CODE_TO_LEGACY_MESSAGE = {
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


def preview_error_to_legacy_message(error: PreviewError) -> str:
    return _ERROR_CODE_TO_LEGACY_MESSAGE.get(error.code, error.message)


@dataclass
class PreviewRequest:
    url: str
    referer: Optional[str] = None
    content_type_hint: Optional[PreviewContentType] = None
    options: Dict[str, Any] = field(default_factory=dict)
    force_refresh: bool = False

    def cache_key(self) -> str:
        key_parts = [
            self.url,
            self.referer or "",
            self.content_type_hint.value if self.content_type_hint else "",
        ]
        raw_key = "|".join(key_parts)
        hash_digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        version = CacheNamespaceManager.get_version()
        return f"preview:v{version}:{hash_digest}"


@dataclass
class PreviewMetadata:
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    site_name: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewResult:
    content_type: PreviewContentType
    source_url: str
    referer: Optional[str] = None
    image_id: Optional[int] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: PreviewMetadata = field(default_factory=PreviewMetadata)
    raw_response: Optional[Any] = None
    fetched_at: Optional[float] = None
    from_cache: bool = False
    plugin_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "source_url": self.source_url,
            "referer": self.referer,
            "image_id": self.image_id,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "metadata": {
                "title": self.metadata.title,
                "description": self.metadata.description,
                "author": self.metadata.author,
                "site_name": self.metadata.site_name,
                "mime_type": self.metadata.mime_type,
                "width": self.metadata.width,
                "height": self.metadata.height,
                "duration": self.metadata.duration,
                "extra": self.metadata.extra,
            },
            "fetched_at": self.fetched_at,
            "from_cache": self.from_cache,
            "plugin_data": self.plugin_data,
        }


class PreviewService(ABC):
    content_type: PreviewContentType = PreviewContentType.UNKNOWN
    _registry: Dict[PreviewContentType, Type["PreviewService"]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.content_type != PreviewContentType.UNKNOWN:
            cls._registry[cls.content_type] = cls

    @classmethod
    def get_service_class(cls, content_type: PreviewContentType) -> Optional[Type["PreviewService"]]:
        return cls._registry.get(content_type)

    @classmethod
    def get_supported_types(cls) -> List[PreviewContentType]:
        return list(cls._registry.keys())

    @abstractmethod
    def fetch(self, request: PreviewRequest) -> PreviewResult:
        raise NotImplementedError

    def supports(self, request: PreviewRequest) -> bool:
        if request.content_type_hint:
            return request.content_type_hint == self.content_type
        return self._detect_content_type(request.url) == self.content_type

    def _detect_content_type(self, url: str) -> PreviewContentType:
        return PreviewContentType.UNKNOWN

    def _apply_plugins_pre_fetch(self, request: PreviewRequest) -> None:
        try:
            from pinry_plugins.builder import dispatch_preview_pre_fetch
            dispatch_preview_pre_fetch(request)
        except Exception:
            logger.exception("Error dispatching preview_pre_fetch")

    def _apply_plugins_post_fetch(
        self, request: PreviewRequest, result: PreviewResult
    ) -> None:
        try:
            from pinry_plugins.builder import dispatch_preview_post_fetch
            plugin_data = dispatch_preview_post_fetch(request, result)
            if plugin_data:
                result.plugin_data.update(plugin_data)
        except Exception:
            logger.exception("Error dispatching preview_post_fetch")

    def _apply_plugins_on_error(
        self, request: PreviewRequest, error: PreviewError
    ) -> None:
        try:
            from pinry_plugins.builder import dispatch_preview_on_error
            dispatch_preview_on_error(request, error)
        except Exception:
            logger.exception("Error dispatching preview_on_error")


class ImagePreviewService(PreviewService):
    content_type = PreviewContentType.IMAGE

    _IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
        ".tiff", ".tif", ".svg", ".ico",
    }

    def _detect_content_type(self, url: str) -> PreviewContentType:
        url_lower = url.lower().split("?")[0].split("#")[0]
        for ext in self._IMAGE_EXTENSIONS:
            if url_lower.endswith(ext):
                return PreviewContentType.IMAGE
        return PreviewContentType.UNKNOWN

    def supports(self, request: PreviewRequest) -> bool:
        if request.content_type_hint == PreviewContentType.IMAGE:
            return True
        if self._detect_content_type(request.url) == PreviewContentType.IMAGE:
            return True
        if request.content_type_hint is None:
            return True
        return False

    def fetch(self, request: PreviewRequest) -> PreviewResult:
        import time

        self._apply_plugins_pre_fetch(request)

        try:
            from core.models import Image

            referer = request.referer or request.url
            image = Image.objects.create_for_url(request.url, referer)

            if image is None:
                error = PreviewError(
                    code=PreviewErrorCode.INVALID_CONTENT,
                    message=preview_error_to_legacy_message(
                        PreviewError(PreviewErrorCode.INVALID_CONTENT, "")
                    ),
                    field="url",
                )
                self._apply_plugins_on_error(request, error)
                raise error

            result = PreviewResult(
                content_type=PreviewContentType.IMAGE,
                source_url=request.url,
                referer=referer,
                image_id=image.pk,
                image_url=image.image.url if image.image else None,
                thumbnail_url=image.thumbnail.image.url if hasattr(image, "thumbnail") else None,
                metadata=PreviewMetadata(
                    width=image.width,
                    height=image.height,
                    extra={"image_pk": image.pk},
                ),
                raw_response=image,
                fetched_at=time.time(),
                from_cache=False,
            )
            self._apply_plugins_post_fetch(request, result)
            return result

        except PreviewError:
            raise
        except Exception as e:
            error = PreviewError(
                code=PreviewErrorCode.UNKNOWN_ERROR,
                message=str(e),
                field="url",
                details={"original_error": type(e).__name__},
            )
            self._apply_plugins_on_error(request, error)
            raise error


class WebpagePreviewService(PreviewService):
    content_type = PreviewContentType.WEBPAGE

    _WEBPAGE_EXTENSIONS = {
        ".html", ".htm", ".php", ".asp", ".aspx", ".jsp",
    }

    def _detect_content_type(self, url: str) -> PreviewContentType:
        url_lower = url.lower().split("?")[0].split("#")[0]
        for ext in self._WEBPAGE_EXTENSIONS:
            if url_lower.endswith(ext):
                return PreviewContentType.WEBPAGE
        if url_lower.endswith("/") or "." not in url_lower.split("/")[-1]:
            return PreviewContentType.WEBPAGE
        return PreviewContentType.UNKNOWN

    def fetch(self, request: PreviewRequest) -> PreviewResult:
        import time

        self._apply_plugins_pre_fetch(request)

        try:
            result = PreviewResult(
                content_type=PreviewContentType.WEBPAGE,
                source_url=request.url,
                referer=request.referer,
                metadata=PreviewMetadata(
                    title=None,
                    description=None,
                    site_name=None,
                ),
                fetched_at=time.time(),
                from_cache=False,
            )
            self._apply_plugins_post_fetch(request, result)
            return result
        except PreviewError:
            raise
        except Exception as e:
            error = PreviewError(
                code=PreviewErrorCode.UNKNOWN_ERROR,
                message=str(e),
                field="url",
            )
            self._apply_plugins_on_error(request, error)
            raise error


class VideoPreviewService(PreviewService):
    content_type = PreviewContentType.VIDEO

    _VIDEO_EXTENSIONS = {
        ".mp4", ".webm", ".ogg", ".avi", ".mov", ".wmv",
        ".flv", ".mkv", ".m4v", ".3gp",
    }

    _VIDEO_HOSTS = [
        "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
        "bilibili.com", "youku.com", "tudou.com",
    ]

    def _detect_content_type(self, url: str) -> PreviewContentType:
        url_lower = url.lower().split("?")[0].split("#")[0]
        for ext in self._VIDEO_EXTENSIONS:
            if url_lower.endswith(ext):
                return PreviewContentType.VIDEO
        for host in self._VIDEO_HOSTS:
            if host in url_lower:
                return PreviewContentType.VIDEO
        return PreviewContentType.UNKNOWN

    def fetch(self, request: PreviewRequest) -> PreviewResult:
        import time

        self._apply_plugins_pre_fetch(request)

        try:
            result = PreviewResult(
                content_type=PreviewContentType.VIDEO,
                source_url=request.url,
                referer=request.referer,
                metadata=PreviewMetadata(
                    duration=None,
                    width=None,
                    height=None,
                ),
                fetched_at=time.time(),
                from_cache=False,
            )
            self._apply_plugins_post_fetch(request, result)
            return result
        except PreviewError:
            raise
        except Exception as e:
            error = PreviewError(
                code=PreviewErrorCode.UNKNOWN_ERROR,
                message=str(e),
                field="url",
            )
            self._apply_plugins_on_error(request, error)
            raise error


class PreviewServiceManager:
    _instance: Optional["PreviewServiceManager"] = None
    _cache_timeout_default = 60 * 60 * 24

    def __new__(cls) -> "PreviewServiceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services: Dict[PreviewContentType, PreviewService] = {}
            cls._instance._init_services()
        return cls._instance

    def _init_services(self) -> None:
        for content_type, service_cls in PreviewService._registry.items():
            self._services[content_type] = service_cls()

    def get_service(self, content_type: PreviewContentType) -> Optional[PreviewService]:
        return self._services.get(content_type)

    def get_service_for_request(self, request: PreviewRequest) -> Optional[PreviewService]:
        priority_order = [
            PreviewContentType.VIDEO,
            PreviewContentType.WEBPAGE,
            PreviewContentType.IMAGE,
        ]
        for content_type in priority_order:
            service = self._services.get(content_type)
            if service and service.supports(request):
                return service
        fallback_service = self._services.get(PreviewContentType.IMAGE)
        if fallback_service and request.content_type_hint is None:
            return fallback_service
        return None

    def _get_cache(self, key: str) -> Optional[PreviewResult]:
        cached = cache.get(key)
        if cached is not None and isinstance(cached, dict):
            try:
                metadata = PreviewMetadata(**cached.get("metadata", {}))
                result = PreviewResult(
                    content_type=PreviewContentType(cached["content_type"]),
                    source_url=cached["source_url"],
                    referer=cached.get("referer"),
                    image_id=cached.get("image_id"),
                    image_url=cached.get("image_url"),
                    thumbnail_url=cached.get("thumbnail_url"),
                    metadata=metadata,
                    fetched_at=cached.get("fetched_at"),
                    from_cache=True,
                    plugin_data=cached.get("plugin_data", {}),
                )
                return result
            except (KeyError, ValueError):
                return None
        return None

    def _set_cache(self, key: str, result: PreviewResult, timeout: Optional[int] = None) -> None:
        cache_timeout = timeout or getattr(
            settings, "PREVIEW_CACHE_TIMEOUT", self._cache_timeout_default
        )
        cache.set(key, result.to_dict(), cache_timeout)

    def invalidate_cache(self, request: PreviewRequest) -> bool:
        key = request.cache_key()
        if cache.get(key) is not None:
            cache.delete(key)
            return True
        return False

    def invalidate_cache_for_url(self, url: str, referer: Optional[str] = None) -> int:
        count = 0
        for content_type in PreviewContentType:
            request = PreviewRequest(
                url=url,
                referer=referer,
                content_type_hint=content_type,
            )
            if self.invalidate_cache(request):
                count += 1
        return count

    def invalidate_all(self) -> int:
        old_version = CacheNamespaceManager.get_version()
        new_version = CacheNamespaceManager.bump_version()
        return new_version - old_version if new_version > old_version else 1

    def get_cache_version(self) -> int:
        return CacheNamespaceManager.get_version()

    def preview(
        self,
        url: str,
        referer: Optional[str] = None,
        content_type_hint: Optional[PreviewContentType] = None,
        options: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False,
        use_cache: bool = True,
    ) -> PreviewResult:
        request = PreviewRequest(
            url=url,
            referer=referer,
            content_type_hint=content_type_hint,
            options=options or {},
            force_refresh=force_refresh,
        )
        return self.preview_by_request(request, use_cache=use_cache)

    def preview_by_request(
        self,
        request: PreviewRequest,
        use_cache: bool = True,
    ) -> PreviewResult:
        if use_cache and not request.force_refresh:
            cached = self._get_cache(request.cache_key())
            if cached is not None:
                return cached

        service = self.get_service_for_request(request)
        if service is None:
            raise PreviewError(
                code=PreviewErrorCode.FORMAT_UNSUPPORTED,
                message="unsupported content type",
                field="url",
                details={"url": request.url},
            )

        result = service.fetch(request)
        if use_cache:
            self._set_cache(request.cache_key(), result)
        return result

    def refresh(
        self,
        url: str,
        referer: Optional[str] = None,
        content_type_hint: Optional[PreviewContentType] = None,
    ) -> PreviewResult:
        return self.preview(
            url=url,
            referer=referer,
            content_type_hint=content_type_hint,
            force_refresh=True,
            use_cache=True,
        )

    def inspect(
        self,
        url: str,
        referer: Optional[str] = None,
        content_type_hint: Optional[PreviewContentType] = None,
    ) -> Dict[str, Any]:
        request = PreviewRequest(
            url=url,
            referer=referer,
            content_type_hint=content_type_hint,
        )
        service = self.get_service_for_request(request)
        cache_key = request.cache_key()
        cached = self._get_cache(cache_key)

        return {
            "url": url,
            "referer": referer,
            "content_type_hint": content_type_hint.value if content_type_hint else None,
            "detected_service": type(service).__name__ if service else None,
            "supported_types": [t.value for t in PreviewService.get_supported_types()],
            "cache_key": cache_key,
            "cache_hit": cached is not None,
            "cached_result": cached.to_dict() if cached else None,
        }


def get_preview_manager() -> PreviewServiceManager:
    return PreviewServiceManager()
