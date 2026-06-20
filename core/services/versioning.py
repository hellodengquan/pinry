import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_VERSION_HISTORY_PREFIX = "preview:history:"
_MAX_HISTORY_PER_URL = getattr(settings, "PREVIEW_MAX_HISTORY", 10)
_VERSION_HISTORY_TTL = getattr(settings, "PREVIEW_HISTORY_TTL", 60 * 60 * 24 * 30)


def _history_key(url: str, referer: Optional[str] = None) -> str:
    raw = f"{url}|{referer or ''}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"{_VERSION_HISTORY_PREFIX}{digest}"


def save_version(url: str, result_dict: Dict[str, Any], referer: Optional[str] = None) -> int:
    from django.utils import timezone

    key = _history_key(url, referer)
    history = _load_history(key)

    version_number = len(history) + 1
    entry = {
        "version": version_number,
        "result": result_dict,
        "saved_at": timezone.now().isoformat(),
        "url": url,
    }
    history.append(entry)

    while len(history) > _MAX_HISTORY_PER_URL:
        history.pop(0)

    cache.set(key, history, timeout=_VERSION_HISTORY_TTL)
    return version_number


def _load_history(key: str) -> List[Dict[str, Any]]:
    try:
        history = cache.get(key)
        if history and isinstance(history, list):
            return history
    except Exception:
        logger.exception("Failed to load version history for key %s", key)
    return []


def get_version_history(url: str, referer: Optional[str] = None) -> List[Dict[str, Any]]:
    key = _history_key(url, referer)
    return _load_history(key)


def get_version(url: str, version: int, referer: Optional[str] = None) -> Optional[Dict[str, Any]]:
    history = get_version_history(url, referer)
    for entry in history:
        if entry.get("version") == version:
            return entry
    return None


def get_current_version_number(url: str, referer: Optional[str] = None) -> int:
    history = get_version_history(url, referer)
    if history:
        return history[-1].get("version", 0)
    return 0


def rollback_to_version(url: str, version: int, referer: Optional[str] = None) -> Optional[Dict[str, Any]]:
    from core.services.preview_service import PreviewRequest
    from core.services import get_preview_manager, PreviewContentType

    target = get_version(url, version, referer)
    if target is None:
        logger.warning("Rollback target version %d not found for %s", version, url)
        return None

    result_dict = target.get("result", {})
    preview_manager = get_preview_manager()

    request = PreviewRequest(
        url=url,
        referer=referer,
        content_type_hint=PreviewContentType.IMAGE,
    )

    cache_key = request.cache_key()
    cache.set(cache_key, result_dict, timeout=getattr(settings, "PREVIEW_CACHE_TIMEOUT", 86400))

    logger.info(
        "Rolled back preview cache for %s to version %d",
        url,
        version,
    )
    return target


def diff_versions(
    url: str,
    version_a: int,
    version_b: int,
    referer: Optional[str] = None,
) -> Dict[str, Any]:
    entry_a = get_version(url, version_a, referer)
    entry_b = get_version(url, version_b, referer)

    if not entry_a or not entry_b:
        missing = []
        if not entry_a:
            missing.append(version_a)
        if not entry_b:
            missing.append(version_b)
        return {
            "error": f"Version(s) not found: {missing}",
            "url": url,
        }

    result_a = entry_a.get("result", {})
    result_b = entry_b.get("result", {})

    diff = _compute_diff(result_a, result_b)
    return {
        "url": url,
        "version_a": version_a,
        "version_b": version_b,
        "saved_at_a": entry_a.get("saved_at"),
        "saved_at_b": entry_b.get("saved_at"),
        "diff": diff,
    }


def _compute_diff(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    changes = {}
    all_keys = set(list(a.keys()) + list(b.keys()))
    for key in all_keys:
        val_a = a.get(key)
        val_b = b.get(key)
        if val_a != val_b:
            changes[key] = {"from": val_a, "to": val_b}
    return changes


def clear_version_history(url: str, referer: Optional[str] = None) -> bool:
    key = _history_key(url, referer)
    try:
        cache.delete(key)
        return True
    except Exception:
        return False
