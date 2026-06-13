import logging
import time
from urllib.parse import urlparse

import requests
from django.db import transaction
from django.utils import timezone

from .models import LinkCheck, LinkCheckTask, Pin

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def is_valid_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def check_single_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    result = {
        "http_status_code": None,
        "error_message": None,
        "response_time_ms": None,
        "success": False,
    }

    start_time = time.monotonic()
    try:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
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

    except requests.exceptions.Timeout:
        result["error_message"] = f"Request timed out after {timeout}s"
        result["success"] = False
    except requests.exceptions.ConnectionError as e:
        result["error_message"] = f"Connection error: {str(e)}"
        result["success"] = False
    except requests.exceptions.TooManyRedirects:
        result["error_message"] = "Too many redirects"
        result["success"] = False
    except requests.exceptions.RequestException as e:
        result["error_message"] = f"Request error: {str(e)}"
        result["success"] = False
    except Exception as e:
        result["error_message"] = f"Unexpected error: {str(e)}"
        result["success"] = False

    if result["response_time_ms"] is None:
        result["response_time_ms"] = int((time.monotonic() - start_time) * 1000)

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
    try:
        task = LinkCheckTask.objects.get(id=task_id)
    except LinkCheckTask.DoesNotExist:
        logger.error("LinkCheckTask %s not found", task_id)
        return

    task.status = LinkCheckTask.Status.RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])

    try:
        pins = get_pins_to_check(user=task.submitter, only_mine=False)
        checks = create_link_check_records(pins, task)

        total = len(checks)
        failed = 0
        success = 0

        for check in checks:
            check.status = LinkCheck.Status.RUNNING
            check.save(update_fields=["status"])

            result = check_single_url(check.url)
            check.http_status_code = result["http_status_code"]
            check.error_message = result["error_message"]
            check.response_time_ms = result["response_time_ms"]
            check.checked_at = timezone.now()

            if result["success"]:
                check.status = LinkCheck.Status.SUCCESS
                check.action_status = LinkCheck.ActionStatus.HANDLED
                success += 1
            else:
                check.status = LinkCheck.Status.FAILED
                failed += 1

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

    except Exception as e:
        logger.exception("LinkCheckTask %s failed", task_id)
        task.status = LinkCheckTask.Status.FAILED
        task.error_message = str(e)
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "error_message", "completed_at"])


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
    check.response_time_ms = result["response_time_ms"]
    check.checked_at = timezone.now()

    if result["success"]:
        check.status = LinkCheck.Status.SUCCESS
        check.action_status = LinkCheck.ActionStatus.HANDLED
    else:
        check.status = LinkCheck.Status.FAILED

    check.save()
    return check
