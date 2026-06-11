from django.test import TestCase, override_settings
from django.utils import translation
from rest_framework import status

from core.exceptions import (
    APIException,
    ErrorCode,
    ERROR_MESSAGE_MAP,
    HTTP_STATUS_TO_ERROR_CODE,
    MAX_DETAIL_LENGTH,
    NotFound,
    PermissionDenied,
    ValidationError,
    AuthenticationFailed,
    Conflict,
    MethodNotAllowed,
    TooManyRequests,
    ServiceUnavailable,
    ParseError,
    UnsupportedMediaType,
    format_error_response,
    get_error_message,
    get_http_status_from_error_code,
    truncate_detail,
)


class ErrorCodeStructureTests(TestCase):
    def test_error_code_values_follow_convention(self):
        self.assertEqual(ErrorCode.SUCCESS, 0)
        self.assertTrue(40000 <= ErrorCode.BAD_REQUEST < 40100)
        self.assertTrue(40100 <= ErrorCode.UNAUTHORIZED < 40200)
        self.assertTrue(40300 <= ErrorCode.FORBIDDEN < 40400)
        self.assertTrue(40400 <= ErrorCode.NOT_FOUND < 40500)
        self.assertTrue(50000 <= ErrorCode.INTERNAL_SERVER_ERROR < 50100)

    def test_error_message_map_covers_all_codes(self):
        code_attributes = {
            k: v for k, v in vars(ErrorCode).items()
            if not k.startswith('_') and isinstance(v, int)
        }
        for name, code in code_attributes.items():
            self.assertIn(
                code, ERROR_MESSAGE_MAP,
                f"ErrorCode.{name} ({code}) missing from ERROR_MESSAGE_MAP"
            )

    def test_http_status_mapping_exists_for_common_codes(self):
        self.assertIn(status.HTTP_400_BAD_REQUEST, HTTP_STATUS_TO_ERROR_CODE)
        self.assertIn(status.HTTP_401_UNAUTHORIZED, HTTP_STATUS_TO_ERROR_CODE)
        self.assertIn(status.HTTP_403_FORBIDDEN, HTTP_STATUS_TO_ERROR_CODE)
        self.assertIn(status.HTTP_404_NOT_FOUND, HTTP_STATUS_TO_ERROR_CODE)
        self.assertIn(status.HTTP_500_INTERNAL_SERVER_ERROR, HTTP_STATUS_TO_ERROR_CODE)


class TruncateDetailTests(TestCase):
    def test_string_within_limit_unchanged(self):
        text = "a" * 100
        result = truncate_detail(text)
        self.assertEqual(result, text)

    def test_string_exceeding_limit_truncated(self):
        text = "a" * 2000
        result = truncate_detail(text)
        self.assertEqual(len(result), MAX_DETAIL_LENGTH + 3)
        self.assertTrue(result.endswith("..."))

    def test_dict_values_truncated(self):
        data = {
            "short": "ok",
            "long": "a" * 2000,
            "nested": {"deep": "b" * 2000},
        }
        result = truncate_detail(data)
        self.assertEqual(result["short"], "ok")
        self.assertTrue(result["long"].endswith("..."))
        self.assertEqual(len(result["long"]), MAX_DETAIL_LENGTH + 3)
        self.assertTrue(result["nested"]["deep"].endswith("..."))

    def test_list_items_truncated(self):
        data = ["ok", "a" * 2000, {"key": "b" * 2000}]
        result = truncate_detail(data)
        self.assertEqual(result[0], "ok")
        self.assertTrue(result[1].endswith("..."))
        self.assertTrue(result[2]["key"].endswith("..."))

    def test_custom_max_length(self):
        text = "a" * 500
        result = truncate_detail(text, max_length=100)
        self.assertEqual(len(result), 103)
        self.assertTrue(result.endswith("..."))

    def test_non_string_non_container_preserved(self):
        self.assertEqual(truncate_detail(123), 123)
        self.assertEqual(truncate_detail(None), None)
        self.assertEqual(truncate_detail(True), True)


class FormatErrorResponseTests(TestCase):
    def test_response_has_required_fields(self):
        resp = format_error_response(ErrorCode.VALIDATION_ERROR)
        self.assertIn("code", resp)
        self.assertIn("message", resp)
        self.assertIn("detail", resp)

    def test_response_code_matches_input(self):
        resp = format_error_response(ErrorCode.NOT_FOUND)
        self.assertEqual(resp["code"], ErrorCode.NOT_FOUND)

    def test_custom_message_used_when_provided(self):
        custom_msg = "Something went wrong"
        resp = format_error_response(ErrorCode.BAD_REQUEST, message=custom_msg)
        self.assertEqual(resp["message"], custom_msg)

    def test_default_message_used_when_none(self):
        resp = format_error_response(ErrorCode.VALIDATION_ERROR)
        self.assertEqual(resp["message"], str(ERROR_MESSAGE_MAP[ErrorCode.VALIDATION_ERROR]))

    def test_custom_detail_included(self):
        detail = {"field": "error message"}
        resp = format_error_response(ErrorCode.VALIDATION_ERROR, detail=detail)
        self.assertEqual(resp["detail"], detail)

    def test_detail_defaults_to_empty_dict(self):
        resp = format_error_response(ErrorCode.BAD_REQUEST)
        self.assertEqual(resp["detail"], {})

    def test_detail_is_truncated(self):
        long_detail = {"msg": "x" * 2000}
        resp = format_error_response(ErrorCode.BAD_REQUEST, detail=long_detail)
        self.assertTrue(resp["detail"]["msg"].endswith("..."))

    def test_extra_fields_merged(self):
        extra = {"error_field": "error_value", "other": 123}
        resp = format_error_response(
            ErrorCode.VALIDATION_ERROR,
            extra_fields=extra,
        )
        self.assertEqual(resp["error_field"], "error_value")
        self.assertEqual(resp["other"], 123)

    def test_extra_fields_do_not_override_core_fields(self):
        extra = {"code": 99999, "message": "override", "detail": "override"}
        resp = format_error_response(
            ErrorCode.VALIDATION_ERROR,
            message="original",
            detail={"orig": "detail"},
            extra_fields=extra,
        )
        self.assertEqual(resp["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(resp["message"], "original")
        self.assertEqual(resp["detail"], {"orig": "detail"})


class ErrorMessageTranslationTests(TestCase):
    @override_settings(LANGUAGE_CODE='en')
    def test_error_message_in_english(self):
        with translation.override('en'):
            msg = get_error_message(ErrorCode.VALIDATION_ERROR)
            self.assertEqual(msg, "Validation error")

    @override_settings(LANGUAGE_CODE='zh-hans')
    def test_error_message_respects_language_override(self):
        with translation.override('en'):
            msg_en = get_error_message(ErrorCode.VALIDATION_ERROR)
        self.assertEqual(msg_en, "Validation error")

    def test_unknown_code_returns_internal_server_error_message(self):
        msg = get_error_message(99999)
        self.assertEqual(msg, str(ERROR_MESSAGE_MAP[ErrorCode.INTERNAL_SERVER_ERROR]))


class HttpStatusMappingTests(TestCase):
    def test_get_http_status_from_error_code_400_range(self):
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.BAD_REQUEST),
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.VALIDATION_ERROR),
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.UNAUTHORIZED),
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.AUTHENTICATION_FAILED),
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.FORBIDDEN),
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.PERMISSION_DENIED),
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.NOT_FOUND),
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.METHOD_NOT_ALLOWED),
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.CONFLICT),
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.UNSUPPORTED_MEDIA_TYPE),
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.TOO_MANY_REQUESTS),
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_get_http_status_from_error_code_500_range(self):
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.INTERNAL_SERVER_ERROR),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.assertEqual(
            get_http_status_from_error_code(ErrorCode.SERVICE_UNAVAILABLE),
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def test_unknown_code_defaults_to_500(self):
        self.assertEqual(
            get_http_status_from_error_code(99999),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class CustomExceptionClassTests(TestCase):
    def test_base_api_exception_defaults(self):
        exc = APIException()
        self.assertEqual(exc.code, ErrorCode.INTERNAL_SERVER_ERROR)
        self.assertEqual(exc.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(exc.detail, {})

    def test_api_exception_custom_values(self):
        exc = APIException(
            detail={"field": "error"},
            code=ErrorCode.BAD_REQUEST,
            message="Custom message",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(exc.code, ErrorCode.BAD_REQUEST)
        self.assertEqual(exc.message, "Custom message")
        self.assertEqual(exc.detail, {"field": "error"})
        self.assertEqual(exc.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_error_defaults(self):
        exc = ValidationError()
        self.assertEqual(exc.code, ErrorCode.VALIDATION_ERROR)
        self.assertEqual(exc.status_code, status.HTTP_400_BAD_REQUEST)

    def test_authentication_failed_defaults(self):
        exc = AuthenticationFailed()
        self.assertEqual(exc.code, ErrorCode.AUTHENTICATION_FAILED)
        self.assertEqual(exc.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_permission_denied_defaults(self):
        exc = PermissionDenied()
        self.assertEqual(exc.code, ErrorCode.PERMISSION_DENIED)
        self.assertEqual(exc.status_code, status.HTTP_403_FORBIDDEN)

    def test_not_found_defaults(self):
        exc = NotFound()
        self.assertEqual(exc.code, ErrorCode.NOT_FOUND)
        self.assertEqual(exc.status_code, status.HTTP_404_NOT_FOUND)

    def test_method_not_allowed_defaults(self):
        exc = MethodNotAllowed()
        self.assertEqual(exc.code, ErrorCode.METHOD_NOT_ALLOWED)
        self.assertEqual(exc.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_conflict_defaults(self):
        exc = Conflict()
        self.assertEqual(exc.code, ErrorCode.CONFLICT)
        self.assertEqual(exc.status_code, status.HTTP_409_CONFLICT)

    def test_unsupported_media_type_defaults(self):
        exc = UnsupportedMediaType()
        self.assertEqual(exc.code, ErrorCode.UNSUPPORTED_MEDIA_TYPE)
        self.assertEqual(exc.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    def test_too_many_requests_defaults(self):
        exc = TooManyRequests()
        self.assertEqual(exc.code, ErrorCode.TOO_MANY_REQUESTS)
        self.assertEqual(exc.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_parse_error_defaults(self):
        exc = ParseError()
        self.assertEqual(exc.code, ErrorCode.PARSE_ERROR)
        self.assertEqual(exc.status_code, status.HTTP_400_BAD_REQUEST)

    def test_service_unavailable_defaults(self):
        exc = ServiceUnavailable()
        self.assertEqual(exc.code, ErrorCode.SERVICE_UNAVAILABLE)
        self.assertEqual(exc.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_exception_str(self):
        exc = APIException(code=ErrorCode.NOT_FOUND, message="Resource missing")
        self.assertIn(str(ErrorCode.NOT_FOUND), str(exc))
        self.assertIn("Resource missing", str(exc))
