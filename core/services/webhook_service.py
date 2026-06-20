import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = getattr(settings, "PREVIEW_WEBHOOK_SECRET", "")
WEBHOOK_ENABLED = getattr(settings, "PREVIEW_WEBHOOK_ENABLED", False)
WEBHOOK_ALLOWED_IPS = getattr(settings, "PREVIEW_WEBHOOK_ALLOWED_IPS", None)
WEBHOOK_SIGNATURE_HEADER = getattr(
    settings, "PREVIEW_WEBHOOK_SIGNATURE_HEADER", "X-Pinry-Signature"
)


class WebhookError(Exception):
    def __init__(self, message: str, code: str = "webhook_error"):
        self.message = message
        self.code = code
        super().__init__(message)


def is_webhook_enabled() -> bool:
    return WEBHOOK_ENABLED and bool(WEBHOOK_SECRET)


def compute_signature(payload: bytes, secret: str) -> str:
    mac = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False

    expected = compute_signature(payload, secret)

    try:
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip


def validate_ip(ip: str, allowed_ips: Optional[List[str]] = None) -> bool:
    if allowed_ips is None or "*" in allowed_ips:
        return True
    return ip in allowed_ips


def validate_webhook_request(request, secret: Optional[str] = None) -> Tuple[bool, str]:
    if not is_webhook_enabled():
        return False, "webhook_disabled"

    if WEBHOOK_ALLOWED_IPS:
        client_ip = get_client_ip(request)
        if not validate_ip(client_ip, WEBHOOK_ALLOWED_IPS):
            logger.warning("Webhook request from blocked IP: %s", client_ip)
            return False, "ip_not_allowed"

    secret = secret or WEBHOOK_SECRET
    signature = request.META.get(f"HTTP_{WEBHOOK_SIGNATURE_HEADER.upper().replace('-', '_')}", "")

    body = getattr(request, "body", b"")
    if not verify_signature(body, signature, secret):
        logger.warning("Webhook signature verification failed")
        return False, "invalid_signature"

    return True, "ok"


def parse_webhook_payload(body: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise WebhookError(f"Invalid JSON payload: {e}", code="invalid_payload")

    if not isinstance(data, dict):
        raise WebhookError("Payload must be a JSON object", code="invalid_payload")

    return data


def handle_refresh_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    from core.services import get_preview_manager
    from core.tasks import dispatch_refresh

    url = payload.get("url")
    if not url:
        raise WebhookError("Missing 'url' field in payload", code="missing_url")

    referer = payload.get("referer")
    content_type = payload.get("content_type")
    force = bool(payload.get("force", True))
    async_mode = payload.get("async", None)

    manager = get_preview_manager()

    if async_mode is None:
        from core.tasks import _HAS_CELERY
        async_mode = _HAS_CELERY

    if async_mode:
        task_result = dispatch_refresh(
            url=url,
            referer=referer,
            content_type=content_type,
            async_mode=True,
        )
        task_id = getattr(task_result, "id", None)
        return {
            "status": "queued",
            "url": url,
            "task_id": task_id,
        }

    try:
        result = manager.refresh(
            url=url,
            referer=referer,
            content_type_hint=(
                __import__("core.services", fromlist=["PreviewContentType"])
                .PreviewContentType(content_type)
                if content_type
                else None
            ),
        )
        return {
            "status": "success",
            "url": url,
            "content_type": result.content_type.value,
            "image_id": result.image_id,
            "from_cache": result.from_cache,
        }
    except Exception as e:
        return {
            "status": "error",
            "url": url,
            "error": str(e),
        }


def handle_batch_refresh_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    from core.tasks import batch_refresh_preview_task, _HAS_CELERY

    items = payload.get("items") or payload.get("urls")
    if not items:
        raise WebhookError("Missing 'items' field in payload", code="missing_items")

    if isinstance(items, list) and items and isinstance(items[0], str):
        items = [{"url": u} for u in items]

    async_mode = payload.get("async", None)
    if async_mode is None:
        async_mode = _HAS_CELERY

    if async_mode:
        task_result = batch_refresh_preview_task.delay(items=items)
        return {
            "status": "queued",
            "task_id": getattr(task_result, "id", None),
            "total": len(items),
        }

    result = batch_refresh_preview_task(items=items)
    return result


def handle_invalidate_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    from core.services import get_preview_manager

    invalidate_all = bool(payload.get("all", False))
    manager = get_preview_manager()

    if invalidate_all:
        bumped = manager.invalidate_all()
        return {
            "status": "success",
            "invalidated_all": True,
            "version_bumped": bumped,
        }

    url = payload.get("url")
    if not url:
        raise WebhookError(
            "Missing 'url' field (or set 'all': true)",
            code="missing_url",
        )

    referer = payload.get("referer")
    count = manager.invalidate_cache_for_url(url, referer)
    return {
        "status": "success",
        "url": url,
        "invalidated": count,
    }


WEBHOOK_ACTIONS = {
    "refresh": handle_refresh_webhook,
    "batch_refresh": handle_batch_refresh_webhook,
    "invalidate": handle_invalidate_webhook,
}


def process_webhook(request) -> Dict[str, Any]:
    valid, reason = validate_webhook_request(request)
    if not valid:
        raise WebhookError(f"Webhook validation failed: {reason}", code=reason)

    body = getattr(request, "body", b"")
    payload = parse_webhook_payload(body)

    action = payload.get("action", "refresh")
    handler = WEBHOOK_ACTIONS.get(action)

    if not handler:
        raise WebhookError(
            f"Unknown action: {action}. "
            f"Supported actions: {', '.join(WEBHOOK_ACTIONS.keys())}",
            code="unknown_action",
        )

    result = handler(payload)
    result.setdefault("action", action)
    result.setdefault("processed_at", timezone.now().isoformat())
    return result
