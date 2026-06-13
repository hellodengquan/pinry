from celery import shared_task

from .link_checker import check_single_pin as _check_single_pin
from .link_checker import run_link_check_task as _run_link_check_task


@shared_task(bind=True, name="core.run_link_check_task")
def run_link_check_task(self, task_id: int):
    """Celery task that runs the full link check for a given task ID."""
    return _run_link_check_task(task_id)


@shared_task(bind=True, name="core.check_single_pin_task")
def check_single_pin_task(self, pin_id: int):
    """Celery task to check a single Pin."""
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
