import logging
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import LinkCheck, LinkCheckTask, Pin

logger = logging.getLogger(__name__)


class ErrorType:
    CONNECTION_REFUSED = "connection_refused"
    DNS_ERROR = "dns_error"
    TIMEOUT = "timeout"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    SSL_ERROR = "ssl_error"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    UNKNOWN = "unknown"

    CHOICES = (
        (CONNECTION_REFUSED, "连接被拒绝"),
        (DNS_ERROR, "DNS 解析失败"),
        (TIMEOUT, "请求超时"),
        (TOO_MANY_REDIRECTS, "重定向过多"),
        (SSL_ERROR, "SSL 证书错误"),
        (HTTP_4XX, "HTTP 4xx 错误"),
        (HTTP_5XX, "HTTP 5xx 错误"),
        (UNKNOWN, "未知错误"),
    )


def _get_timeout():
    return getattr(settings, "LINK_CHECK_TIMEOUT", 15)


def _get_user_agent():
    return getattr(
        settings,
        "LINK_CHECK_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
    )


def _get_rate_limit():
    return getattr(settings, "LINK_CHECK_RATE_LIMIT_PER_MINUTE", 10)


def _get_rate_limit_prefix():
    return getattr(settings, "LINK_CHECK_RATE_LIMIT_PREFIX", "pinry:link_check:rate")


def _rate_limit_key(domain: str) -> str:
    prefix = _get_rate_limit_prefix()
    now_minute = int(time.time() // 60)
    return f"{prefix}:{domain}:{now_minute}"


def wait_for_rate_limit(domain: str) -> None:
    """Per-domain rate limiting using a per-minute counter in cache.

    Blocks (sleeps) until the current minute has remaining slots.
    Uses the Django cache backend (which can be memcached/redis).
    """
    rate = _get_rate_limit()
    if rate <= 0:
        return

    key = _rate_limit_key(domain)
    while True:
        try:
            current = cache.get(key, 0)
            if current < rate:
                cache.set(key, current + 1, timeout=120)
                return
            sleep_time = 60 - (time.time() % 60) + 0.1
            logger.debug("Rate limit hit for %s, sleeping %.1fs", domain, sleep_time)
            time.sleep(sleep_time)
        except Exception as e:
            logger.warning("Rate limit cache error for %s: %s", domain, e)
            return


def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def classify_error(http_status_code=None, exception=None) -> str:
    """Classify the failure reason into one of ErrorType categories."""
    if http_status_code is not None:
        if 400 <= http_status_code < 500:
            return ErrorType.HTTP_4XX
        if 500 <= http_status_code < 600:
            return ErrorType.HTTP_5XX

    if exception is not None:
        exc_name = type(exception).__name__.lower()
        exc_msg = str(exception).lower()

        if "timeout" in exc_name or "timeout" in exc_msg:
            return ErrorType.TIMEOUT
        if "connectionerror" in exc_name or "connection refused" in exc_msg:
            return ErrorType.CONNECTION_REFUSED
        if "gaierror" in exc_name or "nodename" in exc_msg or "dns" in exc_msg:
            return ErrorType.DNS_ERROR
        if "too many redirects" in exc_msg or "max retries exceeded with url" in exc_msg:
            return ErrorType.TOO_MANY_REDIRECTS
        if "ssl" in exc_name or "certificate" in exc_msg:
            return ErrorType.SSL_ERROR
        if "connect" in exc_name and "timeout" not in exc_msg:
            return ErrorType.CONNECTION_REFUSED

    return ErrorType.UNKNOWN


def is_valid_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def check_single_url(url: str, timeout: int | None = None) -> dict:
    """Check a single URL and return detailed result with error_type."""
    if timeout is None:
        timeout = _get_timeout()

    result = {
        "http_status_code": None,
        "error_message": None,
        "error_type": None,
        "response_time_ms": None,
        "success": False,
    }

    domain = get_domain(url)
    if domain:
        wait_for_rate_limit(domain)

    start_time = time.monotonic()
    exception = None

    try:
        headers = {"User-Agent": _get_user_agent()}
        response = requests.head(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result["http_status_code"] = response.status_code
        result["response_time_ms"] = elapsed_ms

        if 200 <= response.status_code < 400:
            result["success"] = True
        else:
            result["error_message"] = f"HTTP {response.status_code} {response.reason}"
            result["success"] = False

        if response.status_code == 405:
            try:
                response_get = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                    stream=True,
                )
                response_get.close()
                result["http_status_code"] = response_get.status_code
                if 200 <= response_get.status_code < 400:
                    result["success"] = True
                    result["error_message"] = None
                else:
                    result["error_message"] = (
                        f"HTTP {response_get.status_code} {response_get.reason}"
                    )
                    result["success"] = False
            except requests.RequestException as e:
                result["error_message"] = f"GET fallback failed: {str(e)}"
                result["success"] = False
                exception = e

    except requests.exceptions.Timeout as e:
        result["error_message"] = f"Request timed out after {timeout}s"
        result["success"] = False
        exception = e
    except requests.exceptions.ConnectionError as e:
        result["error_message"] = f"Connection error: {str(e)}"
        result["success"] = False
        exception = e
    except requests.exceptions.TooManyRedirects as e:
        result["error_message"] = "Too many redirects"
        result["success"] = False
        exception = e
    except requests.exceptions.RequestException as e:
        result["error_message"] = f"Request error: {str(e)}"
        result["success"] = False
        exception = e
    except Exception as e:
        result["error_message"] = f"Unexpected error: {str(e)}"
        result["success"] = False
        exception = e

    if result["response_time_ms"] is None:
        result["response_time_ms"] = int((time.monotonic() - start_time) * 1000)

    if not result["success"]:
        result["error_type"] = classify_error(
            http_status_code=result["http_status_code"],
            exception=exception,
        )

    return result


def get_pins_to_check(user=None, only_mine=True):
    query = Pin.objects.exclude(url__isnull=True).exclude(url="")
    if user is not None and only_mine:
        query = query.filter(submitter=user)
    return query.select_related("submitter", "image")


@transaction.atomic
def create_link_check_records(pins, task: LinkCheckTask | None = None):
    records = []
    for pin in pins:
        if not is_valid_url(pin.url):
            continue
        records.append(
            LinkCheck(
                pin=pin,
                url=pin.url,
                status=LinkCheck.Status.PENDING,
                action_status=LinkCheck.ActionStatus.UNHANDLED,
            )
        )
    created = LinkCheck.objects.bulk_create(records, batch_size=500)
    if task is not None:
        task.total_pins = len(created)
        task.save(update_fields=["total_pins"])
    return created


def run_link_check_task(task_id: int):
    """Run the entire link check task synchronously.

    Used by both the CLI management command and the Celery task.
    """
    try:
        task = LinkCheckTask.objects.get(id=task_id)
    except LinkCheckTask.DoesNotExist:
        logger.error("LinkCheckTask %s not found", task_id)
        return

    if task.status == LinkCheckTask.Status.COMPLETED:
        logger.warning("LinkCheckTask %s already completed, skipping", task_id)
        return

    task.status = LinkCheckTask.Status.RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])

    try:
        pins = get_pins_to_check(user=task.submitter, only_mine=False)
        checks = create_link_check_records(pins, task)

        failed = 0
        success = 0

        error_counts = defaultdict(int)

        for check in checks:
            check.status = LinkCheck.Status.RUNNING
            check.save(update_fields=["status"])

            result = check_single_url(check.url)
            check.http_status_code = result["http_status_code"]
            check.error_message = result["error_message"]
            check.error_type = result["error_type"]
            check.response_time_ms = result["response_time_ms"]
            check.checked_at = timezone.now()

            if result["success"]:
                check.status = LinkCheck.Status.SUCCESS
                check.action_status = LinkCheck.ActionStatus.HANDLED
                success += 1
            else:
                check.status = LinkCheck.Status.FAILED
                failed += 1
                if result["error_type"]:
                    error_counts[result["error_type"]] += 1

            check.save()

            task.checked_count += 1
            task.success_count = success
            task.failed_count = failed
            task.save(
                update_fields=["checked_count", "success_count", "failed_count"]
            )

        task.status = LinkCheckTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at"])

        logger.info(
            "LinkCheckTask %s done: total=%s success=%s failed=%s",
            task_id,
            task.total_pins,
            success,
            failed,
        )
        return {
            "task_id": task_id,
            "total": task.total_pins,
            "success": success,
            "failed": failed,
            "error_counts": dict(error_counts),
        }

    except Exception as e:
        logger.exception("LinkCheckTask %s failed", task_id)
        task.status = LinkCheckTask.Status.FAILED
        task.error_message = str(e)
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "error_message", "completed_at"])
        raise


def check_single_pin(pin_id: int) -> LinkCheck | None:
    try:
        pin = Pin.objects.get(id=pin_id)
    except Pin.DoesNotExist:
        return None

    if not is_valid_url(pin.url):
        return None

    check = LinkCheck.objects.create(
        pin=pin,
        url=pin.url,
        status=LinkCheck.Status.RUNNING,
    )

    result = check_single_url(check.url)
    check.http_status_code = result["http_status_code"]
    check.error_message = result["error_message"]
    check.error_type = result["error_type"]
    check.response_time_ms = result["response_time_ms"]
    check.checked_at = timezone.now()

    if result["success"]:
        check.status = LinkCheck.Status.SUCCESS
        check.action_status = LinkCheck.ActionStatus.HANDLED
    else:
        check.status = LinkCheck.Status.FAILED

    check.save()
    return check
