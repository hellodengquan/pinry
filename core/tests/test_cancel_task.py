import pytest
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import LinkCheck, LinkCheckTask, Pin, Image

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="canceltest", password="pw")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="canceltest_other", password="pw")


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin_cancel", password="pw", email="admin_cancel@example.com"
    )


def _make_pin(user, db):
    img = Image.objects.create(image="test.jpg")
    pin = Pin.objects.create(
        submitter=user,
        image=img,
        url="https://will-be-cancelled.example.com/x",
    )
    return pin


class TestCancelTaskRaceGuard:

    def test_cancel_running_task_marks_running_checks_as_cancelled(
        self, db, user, api_client
    ):
        """Worker正在跑某个链接时，cancel应该把该task关联的RUNNING LinkCheck标记为cancelled。
        同时不能影响其他task的RUNNING检查。"""
        api_client.force_authenticate(user=user)

        task_a = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.RUNNING,
        )
        pin_a = _make_pin(user, db)
        LinkCheck.objects.create(
            pin=pin_a,
            url=pin_a.url,
            task=task_a,
            status=LinkCheck.Status.RUNNING,
            action_status=LinkCheck.ActionStatus.UNHANDLED,
        )

        task_b = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.RUNNING,
        )
        pin_b = _make_pin(user, db)
        LinkCheck.objects.create(
            pin=pin_b,
            url=pin_b.url,
            task=task_b,
            status=LinkCheck.Status.RUNNING,
            action_status=LinkCheck.ActionStatus.UNHANDLED,
        )

        resp = api_client.post(f"/api/v2/link-check-tasks/{task_a.id}/cancel/")
        assert resp.status_code == 200, resp.data
        assert resp.data["status"] == LinkCheckTask.Status.CANCELLED

        task_a.refresh_from_db()
        assert task_a.status == LinkCheckTask.Status.CANCELLED

        check_a = LinkCheck.objects.get(task_id=task_a.id)
        assert check_a.status == LinkCheck.Status.FAILED
        assert check_a.error_type == "cancelled"
        assert check_a.checked_at is not None

        check_b = LinkCheck.objects.get(task_id=task_b.id)
        assert check_b.status == LinkCheck.Status.RUNNING, "other task's running check must NOT be touched"

    def test_cancel_pending_task_still_works(self, db, user, api_client):
        api_client.force_authenticate(user=user)
        task = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.PENDING,
        )
        resp = api_client.post(f"/api/v2/link-check-tasks/{task.id}/cancel/")
        assert resp.status_code == 200, resp.data
        task.refresh_from_db()
        assert task.status == LinkCheckTask.Status.CANCELLED

    def test_cancel_completed_task_returns_400(self, db, user, api_client):
        api_client.force_authenticate(user=user)
        task = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.COMPLETED,
        )
        resp = api_client.post(f"/api/v2/link-check-tasks/{task.id}/cancel/")
        assert resp.status_code == 400, resp.data

    def test_cancel_other_users_task_returns_403(self, db, user, other_user, api_client):
        api_client.force_authenticate(user=other_user)
        task = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.RUNNING,
        )
        resp = api_client.post(f"/api/v2/link-check-tasks/{task.id}/cancel/")
        assert resp.status_code == 403, resp.data

    def test_admin_can_cancel_any_task(self, db, user, admin_user, api_client):
        api_client.force_authenticate(user=admin_user)
        task = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.RUNNING,
        )
        resp = api_client.post(f"/api/v2/link-check-tasks/{task.id}/cancel/")
        assert resp.status_code == 200, resp.data
        task.refresh_from_db()
        assert task.status == LinkCheckTask.Status.CANCELLED

    def test_cancel_skips_non_running_linkchecks(self, db, user, api_client):
        """取消时只把RUNNING的改cancelled，PENDING/SUCCESS/FAILED保持原样。"""
        api_client.force_authenticate(user=user)
        task = LinkCheckTask.objects.create(
            submitter=user,
            status=LinkCheckTask.Status.RUNNING,
        )
        pin_running = _make_pin(user, db)
        pin_success = _make_pin(user, db)
        pin_failed = _make_pin(user, db)
        pin_pending = _make_pin(user, db)

        LinkCheck.objects.create(pin=pin_running, url=pin_running.url, task=task,
                                 status=LinkCheck.Status.RUNNING,
                                 action_status=LinkCheck.ActionStatus.UNHANDLED)
        LinkCheck.objects.create(pin=pin_success, url=pin_success.url, task=task,
                                 status=LinkCheck.Status.SUCCESS, http_status_code=200,
                                 action_status=LinkCheck.ActionStatus.UNHANDLED)
        LinkCheck.objects.create(pin=pin_failed, url=pin_failed.url, task=task,
                                 status=LinkCheck.Status.FAILED,
                                 error_type="http_4xx",
                                 action_status=LinkCheck.ActionStatus.UNHANDLED)
        LinkCheck.objects.create(pin=pin_pending, url=pin_pending.url, task=task,
                                 status=LinkCheck.Status.PENDING,
                                 action_status=LinkCheck.ActionStatus.UNHANDLED)

        resp = api_client.post(f"/api/v2/link-check-tasks/{task.id}/cancel/")
        assert resp.status_code == 200, resp.data

        qs = LinkCheck.objects.filter(task_id=task.id)
        running = qs.get(status=LinkCheck.Status.FAILED, error_type="cancelled")
        assert running.url == pin_running.url

        assert qs.filter(status=LinkCheck.Status.SUCCESS).exists()
        assert qs.filter(status=LinkCheck.Status.FAILED, error_type="http_4xx").exists()
        assert qs.filter(status=LinkCheck.Status.PENDING).exists()
