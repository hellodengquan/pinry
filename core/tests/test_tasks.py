import pytest
from unittest.mock import patch, MagicMock

try:
    from core.tasks import (
        run_link_check_task,
        check_single_pin_task,
        _calculate_backoff,
        MAX_RETRIES,
        RETRY_BACKOFF_BASE,
        RETRY_BACKOFF_MAX,
    )
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False

pytestmark = pytest.mark.skipif(
    not HAS_CELERY,
    reason="celery not installed",
)


class TestCalculateBackoff:
    def test_first_retry(self):
        assert _calculate_backoff(0) == 1

    def test_second_retry(self):
        assert _calculate_backoff(1) == 2

    def test_third_retry(self):
        assert _calculate_backoff(2) == 4

    def test_capped_at_max(self):
        result = _calculate_backoff(10)
        assert result == RETRY_BACKOFF_MAX

    def test_respects_base(self):
        assert _calculate_backoff(3) == RETRY_BACKOFF_BASE ** 3


class FakeRequest:
    def __init__(self, retries=0):
        self.retries = retries


class FakeTask:
    def __init__(self):
        self.request = FakeRequest(retries=0)
        self._retried = False
        self._retry_exc = None
        self._retry_countdown = None

    def retry(self, exc=None, countdown=None):
        self._retried = True
        self._retry_exc = exc
        self._retry_countdown = countdown
        raise exc or Exception("retry")


class TestRunLinkCheckTask:
    @patch("core.tasks._run_link_check_task")
    def test_success(self, mock_run):
        mock_run.return_value = {"task_id": 1, "total": 5, "success": 5, "failed": 0}
        fake = FakeTask()
        result = run_link_check_task(fake, task_id=1)
        assert result["success"] == 5

    @patch("core.tasks._run_link_check_task")
    def test_retries_on_exception(self, mock_run):
        mock_run.side_effect = ConnectionError("redis down")
        fake = FakeTask()
        fake.request = FakeRequest(retries=0)

        with pytest.raises(ConnectionError):
            run_link_check_task(fake, task_id=1)

        assert fake._retried is True
        assert fake._retry_countdown == _calculate_backoff(0)

    @patch("core.tasks._run_link_check_task")
    def test_raises_after_max_retries(self, mock_run):
        mock_run.side_effect = ConnectionError("redis down")
        fake = FakeTask()
        fake.request = FakeRequest(retries=MAX_RETRIES)

        with pytest.raises(ConnectionError):
            run_link_check_task(fake, task_id=1)

        assert fake._retried is False

    @patch("core.tasks._run_link_check_task")
    def test_backoff_increases(self, mock_run):
        mock_run.side_effect = ConnectionError("fail")
        fake = FakeTask()
        fake.request = FakeRequest(retries=2)

        with pytest.raises(ConnectionError):
            run_link_check_task(fake, task_id=1)

        assert fake._retry_countdown == _calculate_backoff(2)


class TestCheckSinglePinTask:
    @patch("core.tasks._check_single_pin")
    def test_success(self, mock_check):
        mock_result = MagicMock()
        mock_result.id = 1
        mock_result.pin_id = 10
        mock_result.status = "success"
        mock_result.error_type = None
        mock_result.http_status_code = 200
        mock_check.return_value = mock_result

        fake = FakeTask()
        result = check_single_pin_task(fake, pin_id=10)
        assert result["status"] == "success"
        assert result["pin_id"] == 10

    @patch("core.tasks._check_single_pin")
    def test_returns_error_dict_when_none(self, mock_check):
        mock_check.return_value = None
        fake = FakeTask()
        result = check_single_pin_task(fake, pin_id=999)
        assert result["error"] == "pin not found or invalid url"

    @patch("core.tasks._check_single_pin")
    def test_retries_on_exception(self, mock_check):
        mock_check.side_effect = ConnectionError("timeout")
        fake = FakeTask()
        fake.request = FakeRequest(retries=1)

        with pytest.raises(ConnectionError):
            check_single_pin_task(fake, pin_id=10)

        assert fake._retried is True
        assert fake._retry_countdown == _calculate_backoff(1)

    @patch("core.tasks._check_single_pin")
    def test_exhausts_retries(self, mock_check):
        mock_check.side_effect = RuntimeError("fatal")
        fake = FakeTask()
        fake.request = FakeRequest(retries=MAX_RETRIES)

        with pytest.raises(RuntimeError):
            check_single_pin_task(fake, pin_id=10)

        assert fake._retried is False
