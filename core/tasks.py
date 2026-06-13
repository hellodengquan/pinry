from celery import shared_task
from celery.utils.log import get_task_logger

from .link_checker import check_single_pin as _check_single_pin
from .link_checker import run_link_check_task as _run_link_check_task

logger = get_task_logger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2
RETRY_BACKOFF_MAX = 60


def _calculate_backoff(retry_count: int) -> int:
    delay = RETRY_BACKOFF_BASE ** retry_count
    return min(delay, RETRY_BACKOFF_MAX)


@shared_task(
    bind=True,
    name="core.run_link_check_task",
    max_retries=MAX_RETRIES,
    default_retry_delay=5,
    acks_late=True,
)
def run_link_check_task(self, task_id: int):
    """Celery task that runs the full link check for a given task ID.

    Retries up to MAX_RETRIES times with exponential backoff on transient errors.
    """
    try:
        return _run_link_check_task(task_id)
    except Exception as exc:
        retry_count = self.request.retries
        if retry_count < MAX_RETRIES:
            backoff = _calculate_backoff(retry_count)
            logger.warning(
                "run_link_check_task(task_id=%s) failed (attempt %d/%d), "
                "retrying in %ds: %s",
                task_id,
                retry_count + 1,
                MAX_RETRIES + 1,
                backoff,
                exc,
            )
            raise self.retry(exc=exc, countdown=backoff)
        logger.error(
            "run_link_check_task(task_id=%s) exhausted all %d retries: %s",
            task_id,
            MAX_RETRIES,
            exc,
        )
        raise


@shared_task(
    bind=True,
    name="core.check_single_pin_task",
    max_retries=MAX_RETRIES,
    default_retry_delay=3,
    acks_late=True,
)
def check_single_pin_task(self, pin_id: int):
    """Celery task to check a single Pin with retry support."""
    try:
        result = _check_single_pin(pin_id)
        if result is None:
            return {"error": "pin not found or invalid url"}
        return {
            "id": result.id,
            "pin_id": result.pin_id,
            "status": result.status,
            "error_type": result.error_type,
            "http_status_code": result.http_status_code,
        }
    except Exception as exc:
        retry_count = self.request.retries
        if retry_count < MAX_RETRIES:
            backoff = _calculate_backoff(retry_count)
            logger.warning(
                "check_single_pin_task(pin_id=%s) failed (attempt %d/%d), "
                "retrying in %ds: %s",
                pin_id,
                retry_count + 1,
                MAX_RETRIES + 1,
                backoff,
                exc,
            )
            raise self.retry(exc=exc, countdown=backoff)
        logger.error(
            "check_single_pin_task(pin_id=%s) exhausted all %d retries: %s",
            pin_id,
            MAX_RETRIES,
            exc,
        )
        raise
