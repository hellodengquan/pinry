import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from core.link_checker import (
    ErrorType,
    classify_error,
    check_single_url,
    get_domain,
    is_valid_url,
    wait_for_rate_limit,
    create_link_check_records,
    run_link_check_task,
    check_single_pin,
)
from core.models import LinkCheck, LinkCheckTask, Pin

User = get_user_model()


def _make_pin_mock(pin_id, url, user_id=1):
    pin = MagicMock(spec=Pin)
    pin.id = pin_id
    pin.pk = pin_id
    pin.url = url
    pin.submitter_id = user_id
    pin._state = MagicMock(db="default")
    return pin


@pytest.fixture
def user(db):
    return User.objects.create_user(username="checker", password="pw")


@pytest.fixture
def transactional_user(transactional_db):
    return User.objects.create_user(username="checker_tx", password="pw")


@pytest.fixture
def task(user):
    return LinkCheckTask.objects.create(submitter=user)


# ============================================================
# classify_error
# ============================================================

class TestClassifyError:
    def test_http_4xx(self):
        assert classify_error(http_status_code=404) == ErrorType.HTTP_4XX

    def test_http_403(self):
        assert classify_error(http_status_code=403) == ErrorType.HTTP_4XX

    def test_http_5xx(self):
        assert classify_error(http_status_code=500) == ErrorType.HTTP_5XX

    def test_http_502(self):
        assert classify_error(http_status_code=502) == ErrorType.HTTP_5XX

    def test_http_3xx_not_classified_as_error(self):
        result = classify_error(http_status_code=301)
        assert result == ErrorType.UNKNOWN

    def test_timeout_exception(self):
        import requests
        exc = requests.exceptions.Timeout("timed out")
        assert classify_error(exception=exc) == ErrorType.TIMEOUT

    def test_connection_error_refused(self):
        import requests
        exc = requests.exceptions.ConnectionError("Connection refused")
        assert classify_error(exception=exc) == ErrorType.CONNECTION_REFUSED

    def test_connection_error_generic(self):
        import requests
        exc = requests.exceptions.ConnectionError("Some other connection issue")
        assert classify_error(exception=exc) == ErrorType.CONNECTION_REFUSED

    def test_dns_error_gaierror(self):
        exc = Exception("gaierror: nodename nor servname provided")
        assert classify_error(exception=exc) == ErrorType.DNS_ERROR

    def test_ssl_error(self):
        exc = Exception("SSLError: certificate verify failed")
        assert classify_error(exception=exc) == ErrorType.SSL_ERROR

    def test_too_many_redirects(self):
        import requests
        exc = requests.exceptions.TooManyRedirects("too many redirects")
        assert classify_error(exception=exc) == ErrorType.TOO_MANY_REDIRECTS

    def test_unknown_exception(self):
        exc = RuntimeError("something unexpected")
        assert classify_error(exception=exc) == ErrorType.UNKNOWN

    def test_no_args(self):
        assert classify_error() == ErrorType.UNKNOWN

    def test_http_status_takes_priority(self):
        import requests
        exc = requests.exceptions.Timeout("timed out")
        assert classify_error(http_status_code=404, exception=exc) == ErrorType.HTTP_4XX


# ============================================================
# is_valid_url
# ============================================================

class TestIsValidUrl:
    def test_valid_https(self):
        assert is_valid_url("https://example.com") is True

    def test_valid_http(self):
        assert is_valid_url("http://example.com/path?q=1") is True

    def test_empty_string(self):
        assert is_valid_url("") is False

    def test_none(self):
        assert is_valid_url(None) is False

    def test_ftp_scheme(self):
        assert is_valid_url("ftp://files.example.com") is False

    def test_no_scheme(self):
        assert is_valid_url("example.com/page") is False

    def test_javascript_scheme(self):
        assert is_valid_url("javascript:alert(1)") is False


# ============================================================
# get_domain
# ============================================================

class TestGetDomain:
    def test_simple(self):
        assert get_domain("https://example.com/path") == "example.com"

    def test_subdomain(self):
        assert get_domain("https://www.pinterest.com/pin/123") == "www.pinterest.com"

    def test_with_port(self):
        assert get_domain("http://localhost:8000/api") == "localhost:8000"

    def test_invalid(self):
        assert get_domain("not-a-url") == ""


# ============================================================
# check_single_url
# ============================================================

class TestCheckSingleUrl:
    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_success_200(self, mock_head, mock_rate):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_head.return_value = mock_resp

        result = check_single_url("https://example.com", timeout=5)
        assert result["success"] is True
        assert result["http_status_code"] == 200
        assert result["error_type"] is None

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_failure_404(self, mock_head, mock_rate):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.reason = "Not Found"
        mock_head.return_value = mock_resp

        result = check_single_url("https://example.com/missing", timeout=5)
        assert result["success"] is False
        assert result["http_status_code"] == 404
        assert result["error_type"] == ErrorType.HTTP_4XX

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_failure_500(self, mock_head, mock_rate):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.reason = "Internal Server Error"
        mock_head.return_value = mock_resp

        result = check_single_url("https://example.com/broken", timeout=5)
        assert result["success"] is False
        assert result["error_type"] == ErrorType.HTTP_5XX

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_timeout(self, mock_head, mock_rate):
        import requests
        mock_head.side_effect = requests.exceptions.Timeout("timed out")

        result = check_single_url("https://slow.example.com", timeout=1)
        assert result["success"] is False
        assert result["error_type"] == ErrorType.TIMEOUT

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_connection_error(self, mock_head, mock_rate):
        import requests
        mock_head.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = check_single_url("https://down.example.com", timeout=5)
        assert result["success"] is False
        assert result["error_type"] == ErrorType.CONNECTION_REFUSED

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_head_405_fallback_get_success(self, mock_head, mock_rate):
        mock_head_resp = MagicMock()
        mock_head_resp.status_code = 405
        mock_head_resp.reason = "Method Not Allowed"

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.reason = "OK"

        mock_head.return_value = mock_head_resp

        with patch("core.link_checker.requests.get", return_value=mock_get_resp):
            result = check_single_url("https://example.com/api", timeout=5)
        assert result["success"] is True

    @patch("core.link_checker.wait_for_rate_limit")
    @patch("core.link_checker.requests.head")
    def test_has_response_time(self, mock_head, mock_rate):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_head.return_value = mock_resp

        result = check_single_url("https://example.com", timeout=5)
        assert result["response_time_ms"] is not None
        assert result["response_time_ms"] >= 0


# ============================================================
# wait_for_rate_limit
# ============================================================

class TestWaitForRateLimit:
    @patch("core.link_checker.cache")
    def test_passes_when_under_limit(self, mock_cache):
        mock_cache.get.return_value = 3
        mock_cache.set.return_value = None
        with override_settings(LINK_CHECK_RATE_LIMIT_PER_MINUTE=10):
            wait_for_rate_limit("example.com")
        mock_cache.set.assert_called_once()

    @patch("core.link_checker.cache")
    def test_disabled_when_zero(self, mock_cache):
        with override_settings(LINK_CHECK_RATE_LIMIT_PER_MINUTE=0):
            wait_for_rate_limit("example.com")
        mock_cache.get.assert_not_called()

    @patch("core.link_checker.cache")
    def test_cache_error_does_not_block(self, mock_cache):
        mock_cache.get.side_effect = Exception("redis down")
        with override_settings(LINK_CHECK_RATE_LIMIT_PER_MINUTE=10):
            wait_for_rate_limit("example.com")


# ============================================================
# create_link_check_records
# ============================================================

class TestCreateLinkCheckRecords:
    def test_returns_queryset_on_valid(self, db):
        pin = _make_pin_mock(1, "https://example.com/page1")
        with patch("core.link_checker.is_valid_url", return_value=True):
            with patch("core.link_checker.LinkCheck.objects.bulk_create", return_value=[]):
                with patch(
                    "core.link_checker.LinkCheck.objects.filter"
                ) as mock_filter:
                    mock_qs = MagicMock()
                    mock_qs.values_list.return_value = []
                    mock_filter.return_value = mock_qs

                    with patch.object(LinkCheck.objects, "filter") as m_f:
                        m_f.return_value.values_list.return_value = []
                        result = create_link_check_records([pin])
                        assert result is not None

    def test_skips_all_when_invalid(self, db):
        pin = _make_pin_mock(1, "")
        with patch("core.link_checker.is_valid_url", return_value=False):
            result = create_link_check_records([pin])
            assert result.count() == 0


# ============================================================
# run_link_check_task
# ============================================================

class TestRunLinkCheckTask:
    @pytest.mark.django_db
    def test_nonexistent_task(self):
        result = run_link_check_task(99999)
        assert result is None

    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.create_link_check_records")
    @patch("core.link_checker.get_pins_to_check")
    def test_full_run_success(self, mock_pins, mock_create, mock_check, transactional_user):
        mock_check.return_value = {
            "success": True,
            "http_status_code": 200,
            "error_message": None,
            "error_type": None,
            "response_time_ms": 100,
        }
        pin = _make_pin_mock(1, "https://example.com/ok")
        mock_pins.return_value = [pin]

        mock_check_obj = MagicMock()
        mock_check_obj.url = "https://example.com/ok"
        mock_check_obj.pin_id = 1
        mock_create.return_value = [mock_check_obj]

        task = LinkCheckTask.objects.create(submitter=transactional_user)
        result = run_link_check_task(task.id)

        task.refresh_from_db()
        assert task.status == LinkCheckTask.Status.COMPLETED
        assert result["success"] == 1
        assert result["failed"] == 0

    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.create_link_check_records")
    @patch("core.link_checker.get_pins_to_check")
    def test_full_run_with_failures(self, mock_pins, mock_create, mock_check, transactional_user):
        mock_check.return_value = {
            "success": False,
            "http_status_code": 500,
            "error_message": "Internal Server Error",
            "error_type": ErrorType.HTTP_5XX,
            "response_time_ms": 200,
        }
        pin = _make_pin_mock(1, "https://example.com/down")
        mock_pins.return_value = [pin]

        mock_check_obj = MagicMock()
        mock_check_obj.url = "https://example.com/down"
        mock_check_obj.pin_id = 1
        mock_create.return_value = [mock_check_obj]

        task = LinkCheckTask.objects.create(submitter=transactional_user)
        result = run_link_check_task(task.id)

        task.refresh_from_db()
        assert task.status == LinkCheckTask.Status.COMPLETED
        assert result["failed"] == 1
        assert result["error_counts"][ErrorType.HTTP_5XX] == 1

    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.create_link_check_records")
    @patch("core.link_checker.get_pins_to_check")
    def test_cancel_returns_early(self, mock_pins, mock_create, mock_check, transactional_user):
        mock_check.return_value = {
            "success": False,
            "http_status_code": 500,
            "error_message": "err",
            "error_type": ErrorType.HTTP_5XX,
            "response_time_ms": 100,
        }
        pin = _make_pin_mock(1, "https://example.com/x")
        mock_pins.return_value = [pin]

        mock_check_obj = MagicMock()
        mock_check_obj.url = "https://example.com/x"
        mock_check_obj.pin_id = 1
        mock_check_obj.save = MagicMock()
        mock_create.return_value = [mock_check_obj]

        task = LinkCheckTask.objects.create(submitter=transactional_user)

        original_get = LinkCheckTask.objects.get

        def patched_get(*args, **kwargs):
            obj = original_get(*args, **kwargs)
            original_refresh = obj.refresh_from_db

            def fake_refresh(fields=None):
                original_refresh(fields=fields)
                obj.status = LinkCheckTask.Status.CANCELLED

            obj.refresh_from_db = fake_refresh
            return obj

        with patch.object(LinkCheckTask.objects, "get", patched_get):
            result = run_link_check_task(task.id)

        assert result is not None
        assert result.get("cancelled") is True

    @patch("core.link_checker.get_pins_to_check")
    def test_skips_already_completed(self, mock_pins, transactional_user):
        task = LinkCheckTask.objects.create(
            submitter=transactional_user,
            status=LinkCheckTask.Status.COMPLETED,
        )
        result = run_link_check_task(task.id)
        assert result is None
        mock_pins.assert_not_called()

    @patch("core.link_checker.get_pins_to_check")
    def test_skips_already_cancelled(self, mock_pins, transactional_user):
        task = LinkCheckTask.objects.create(
            submitter=transactional_user,
            status=LinkCheckTask.Status.CANCELLED,
        )
        result = run_link_check_task(task.id)
        assert result is None
        mock_pins.assert_not_called()

    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.create_link_check_records")
    @patch("core.link_checker.get_pins_to_check")
    def test_exception_marks_task_failed(self, mock_pins, mock_create, mock_check, transactional_user):
        mock_check.side_effect = RuntimeError("unexpected crash")
        pin = _make_pin_mock(1, "https://example.com/crash")
        mock_pins.return_value = [pin]

        mock_check_obj = MagicMock()
        mock_check_obj.url = "https://example.com/crash"
        mock_check_obj.pin_id = 1
        mock_create.return_value = [mock_check_obj]

        task = LinkCheckTask.objects.create(submitter=transactional_user)
        with pytest.raises(RuntimeError):
            run_link_check_task(task.id)

        task.refresh_from_db()
        assert task.status == LinkCheckTask.Status.FAILED
        assert "unexpected crash" in task.error_message


# ============================================================
# check_single_pin
# ============================================================

class TestCheckSinglePin:
    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.Pin.objects.get")
    def test_success(self, mock_get, mock_check, db):
        pin = _make_pin_mock(1, "https://example.com/ok")
        mock_get.return_value = pin
        mock_check.return_value = {
            "success": True,
            "http_status_code": 200,
            "error_message": None,
            "error_type": None,
            "response_time_ms": 50,
        }
        result = check_single_pin(1)
        assert result is not None
        assert result.status == LinkCheck.Status.SUCCESS
        LinkCheck.objects.filter(id=result.id).delete()

    @patch("core.link_checker.check_single_url")
    @patch("core.link_checker.Pin.objects.get")
    def test_failure(self, mock_get, mock_check, db):
        pin = _make_pin_mock(1, "https://example.com/missing")
        mock_get.return_value = pin
        mock_check.return_value = {
            "success": False,
            "http_status_code": 404,
            "error_message": "Not Found",
            "error_type": ErrorType.HTTP_4XX,
            "response_time_ms": 30,
        }
        result = check_single_pin(1)
        assert result is not None
        assert result.status == LinkCheck.Status.FAILED
        assert result.error_type == ErrorType.HTTP_4XX
        LinkCheck.objects.filter(id=result.id).delete()

    @patch("core.link_checker.Pin.objects.get")
    def test_nonexistent_pin(self, mock_get):
        mock_get.side_effect = Pin.DoesNotExist
        assert check_single_pin(99999) is None

    @patch("core.link_checker.Pin.objects.get")
    def test_pin_without_url(self, mock_get):
        pin = _make_pin_mock(1, "")
        mock_get.return_value = pin
        assert check_single_pin(1) is None

    @patch("core.link_checker.Pin.objects.get")
    def test_pin_with_bad_url(self, mock_get):
        pin = _make_pin_mock(1, "ftp://invalid-scheme.com")
        mock_get.return_value = pin
        assert check_single_pin(1) is None
