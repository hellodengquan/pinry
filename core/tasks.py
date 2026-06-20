import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
    _HAS_CELERY = True
except ImportError:
    _HAS_CELERY = False

    class _SyncTaskResult:
        def __init__(self, result=None, successful=True, failed=False, error=None):
            self._result = result
            self._successful = successful
            self._failed = failed
            self._error = error
            self.id = "sync-task"

        def get(self, timeout=None):
            if self._failed and self._error:
                raise self._error
            return self._result

        def ready(self):
            return True

        def successful(self):
            return self._successful

        def failed(self):
            return self._failed

        @property
        def state(self):
            return "SUCCESS" if self._successful else "FAILURE"

    def _make_sync_task(func: Callable, task_name: str) -> Callable:
        def delay(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return _SyncTaskResult(result=result, successful=True)
            except Exception as e:
                return _SyncTaskResult(failed=True, error=e)

        def apply_async(args=None, kwargs=None, **options):
            args = args or ()
            kwargs = kwargs or {}
            return delay(*args, **kwargs)

        def apply(args=None, kwargs=None, **options):
            args = args or ()
            kwargs = kwargs or {}
            return delay(*args, **kwargs)

        func.delay = delay
        func.apply_async = apply_async
        func.apply = apply
        func.name = task_name
        return func

    def shared_task(func=None, **kwargs):
        task_name = kwargs.get("name", None)

        def decorator(f):
            name = task_name or f"{f.__module__}.{f.__name__}"
            return _make_sync_task(f, name)

        if func:
            return decorator(func)
        return decorator


def has_celery() -> bool:
    return _HAS_CELERY


def _get_preview_manager():
    from core.services import get_preview_manager
    return get_preview_manager()


@shared_task(name="core.tasks.refresh_preview_task", max_retries=3)
def refresh_preview_task(
    url: str,
    referer: Optional[str] = None,
    content_type: Optional[str] = None,
    force: bool = True,
) -> Dict[str, Any]:
    from core.services import PreviewContentType, PreviewError

    content_type_hint = None
    if content_type:
        try:
            content_type_hint = PreviewContentType(content_type)
        except ValueError:
            content_type_hint = None

    manager = _get_preview_manager()
    try:
        result = manager.refresh(
            url=url,
            referer=referer,
            content_type_hint=content_type_hint,
        )
        return {
            "status": "success",
            "url": url,
            "content_type": result.content_type.value,
            "image_id": result.image_id,
            "from_cache": result.from_cache,
        }
    except PreviewError as e:
        return {
            "status": "error",
            "url": url,
            "error_code": e.code.value,
            "error_message": e.message,
        }
    except Exception as e:
        logger.exception("Unexpected error in refresh_preview_task for %s", url)
        return {
            "status": "error",
            "url": url,
            "error_code": "unknown_error",
            "error_message": str(e),
        }


@shared_task(name="core.tasks.batch_refresh_preview_task")
def batch_refresh_preview_task(
    items: List[Dict[str, Any]],
    force: bool = True,
) -> Dict[str, Any]:
    results = {"success": [], "failed": [], "total": len(items)}
    for item in items:
        url = item.get("url")
        if not url:
            continue
        try:
            result = refresh_preview_task.apply(
                kwargs={
                    "url": url,
                    "referer": item.get("referer"),
                    "content_type": item.get("content_type"),
                    "force": force,
                }
            )
            task_result = result.get() if hasattr(result, "get") else result
            if task_result.get("status") == "success":
                results["success"].append(url)
            else:
                results["failed"].append({
                    "url": url,
                    "error": task_result.get("error_message"),
                })
        except Exception as e:
            results["failed"].append({"url": url, "error": str(e)})
    return results


@shared_task(name="core.tasks.invalidate_preview_cache_task")
def invalidate_preview_cache_task(
    url: str,
    referer: Optional[str] = None,
) -> Dict[str, Any]:
    manager = _get_preview_manager()
    count = manager.invalidate_cache_for_url(url, referer)
    return {
        "url": url,
        "referer": referer,
        "invalidated": count,
        "status": "success",
    }


@shared_task(name="core.tasks.inspect_preview_task")
def inspect_preview_task(
    url: str,
    referer: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    from core.services import PreviewContentType

    content_type_hint = None
    if content_type:
        try:
            content_type_hint = PreviewContentType(content_type)
        except ValueError:
            content_type_hint = None

    manager = _get_preview_manager()
    info = manager.inspect(
        url=url,
        referer=referer,
        content_type_hint=content_type_hint,
    )
    return info


@shared_task(name="core.tasks.inspect_and_repair_task")
def inspect_and_repair_task(
    url: str,
    referer: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    from core.services import PreviewContentType, PreviewError

    content_type_hint = None
    if content_type:
        try:
            content_type_hint = PreviewContentType(content_type)
        except ValueError:
            content_type_hint = None

    manager = _get_preview_manager()
    info = manager.inspect(
        url=url,
        referer=referer,
        content_type_hint=content_type_hint,
    )

    result = {"url": url, "inspected": info, "repaired": False, "action": None}

    cache_hit = info.get("cache_hit", False)
    cached_result = info.get("cached_result")
    image_id = cached_result.get("image_id") if cached_result else None

    needs_repair = False
    if cache_hit and cached_result:
        from core.models import Image
        if image_id and not Image.objects.filter(pk=image_id).exists():
            needs_repair = True
            result["reason"] = "cached image_id does not exist"

    if not cache_hit:
        needs_repair = True
        result["reason"] = "no cache entry"

    if needs_repair:
        try:
            refresh_result = manager.refresh(
                url=url,
                referer=referer,
                content_type_hint=content_type_hint,
            )
            result["repaired"] = True
            result["action"] = "refreshed"
            result["new_image_id"] = refresh_result.image_id
        except PreviewError as e:
            result["repaired"] = False
            result["action"] = "failed"
            result["error"] = e.code.value
        except Exception as e:
            logger.exception("Repair failed for %s", url)
            result["repaired"] = False
            result["action"] = "error"
            result["error"] = str(e)

    return result


@shared_task(name="core.tasks.pin_refetch_task")
def pin_refresh_task(pin_id: int) -> Dict[str, Any]:
    from core.models import Pin

    try:
        pin = Pin.objects.get(pk=pin_id)
    except Pin.DoesNotExist:
        return {"status": "error", "pin_id": pin_id, "error": "pin not found"}

    if not pin.url:
        return {"status": "skipped", "pin_id": pin_id, "reason": "no url"}

    result = refresh_preview_task.apply(
        kwargs={
            "url": pin.url,
            "referer": pin.referer,
            "content_type": "image",
            "force": True,
        }
    )
    task_result = result.get() if hasattr(result, "get") else result

    if task_result.get("status") == "success" and task_result.get("image_id"):
        new_image_id = task_result["image_id"]
        if new_image_id != pin.image_id:
            from core.models import Image
            try:
                new_image = Image.objects.get(pk=new_image_id)
                pin.image = new_image
                pin.save()
                task_result["pin_updated"] = True
            except Image.DoesNotExist:
                task_result["pin_updated"] = False
                task_result["pin_update_error"] = "image not found"

    task_result["pin_id"] = pin_id
    return task_result


def dispatch_refresh(
    url: str,
    referer: Optional[str] = None,
    content_type: Optional[str] = None,
    async_mode: Optional[bool] = None,
) -> Any:
    use_async = async_mode if async_mode is not None else _HAS_CELERY
    if use_async:
        return refresh_preview_task.delay(
            url=url,
            referer=referer,
            content_type=content_type,
        )
    else:
        return refresh_preview_task(
            url=url,
            referer=referer,
            content_type=content_type,
        )


def dispatch_invalidate(
    url: str,
    referer: Optional[str] = None,
    async_mode: Optional[bool] = None,
) -> Any:
    use_async = async_mode if async_mode is not None else _HAS_CELERY
    if use_async:
        return invalidate_preview_cache_task.delay(url=url, referer=referer)
    else:
        return invalidate_preview_cache_task(url=url, referer=referer)


def dispatch_pin_refresh(
    pin_id: int,
    async_mode: Optional[bool] = None,
) -> Any:
    use_async = async_mode if async_mode is not None else _HAS_CELERY
    if use_async:
        return pin_refresh_task.delay(pin_id=pin_id)
    else:
        return pin_refresh_task(pin_id=pin_id)
