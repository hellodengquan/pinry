from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import (
    APIException as DRFAPIException,
    AuthenticationFailed as DRFAuthenticationFailed,
    ErrorDetail,
    MethodNotAllowed as DRFMethodNotAllowed,
    NotAuthenticated as DRFNotAuthenticated,
    NotFound as DRFNotFound,
    ParseError as DRFParseError,
    PermissionDenied as DRFPermissionDenied,
    Throttled as DRFThrottled,
    UnsupportedMediaType as DRFUnsupportedMediaType,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response

from core.exceptions import (
    APIException,
    ErrorCode,
    NotFound,
    PermissionDenied as CustomPermissionDenied,
    ValidationError as CustomValidationError,
)
from core.exception_handler import (
    _extract_field_errors,
    _get_error_code_from_exception,
    _get_message_from_exception,
    _normalize_detail,
    custom_exception_handler,
    handle_api_exception,
)


class NormalizeDetailTests(TestCase):
    def test_error_detail_converted_to_string(self):
        ed = ErrorDetail("test error", code="invalid")
        result = _normalize_detail(ed)
        self.assertEqual(result, "test error")
        self.assertIsInstance(result, str)

    def test_list_of_error_details_normalized(self):
        data = [ErrorDetail("err1", "c1"), ErrorDetail("err2", "c2")]
        result = _normalize_detail(data)
        self.assertEqual(result, ["err1", "err2"])

    def test_dict_of_error_details_normalized(self):
        data = {"f1": ErrorDetail("e1", "c1"), "f2": [ErrorDetail("e2", "c2")]}
        result = _normalize_detail(data)
        self.assertEqual(result["f1"], "e1")
        self.assertEqual(result["f2"], ["e2"])

    def test_plain_string_preserved(self):
        self.assertEqual(_normalize_detail("plain"), "plain")

    def test_plain_number_converted_to_string(self):
        self.assertEqual(_normalize_detail(123), "123")


class ExtractFieldErrorsTests(TestCase):
    def test_dict_with_list_errors_extracts_first_item(self):
        detail = {"username": ["This field is required."], "password": ["Too short."]}
        result = _extract_field_errors(detail)
        self.assertEqual(result["username"], "This field is required.")
        self.assertEqual(result["password"], "Too short.")

    def test_dict_with_string_errors_preserved(self):
        detail = {"username": "Taken", "email": "Invalid"}
        result = _extract_field_errors(detail)
        self.assertEqual(result, detail)

    def test_nested_dict_handled(self):
        detail = {"profile": {"name": ["Required"]}}
        result = _extract_field_errors(detail)
        self.assertEqual(result["profile"], {"name": "Required"})

    def test_list_becomes_non_field_errors(self):
        detail = ["Something went wrong"]
        result = _extract_field_errors(detail)
        self.assertEqual(result, {"non_field_errors": "Something went wrong"})

    def test_empty_list_becomes_empty_non_field_errors(self):
        detail = []
        result = _extract_field_errors(detail)
        self.assertEqual(result, {"non_field_errors": ""})

    def test_string_becomes_non_field_errors(self):
        detail = "Something failed"
        result = _extract_field_errors(detail)
        self.assertEqual(result, {"non_field_errors": "Something failed"})

    def test_empty_list_in_dict_values_handled(self):
        detail = {"field": []}
        result = _extract_field_errors(detail)
        self.assertEqual(result["field"], "")


class GetErrorCodeFromExceptionTests(TestCase):
    def test_custom_api_exception_uses_its_code(self):
        exc = CustomValidationError(code=ErrorCode.INVALID_PARAMS)
        self.assertEqual(_get_error_code_from_exception(exc, 400), ErrorCode.INVALID_PARAMS)

    def test_drf_validation_error_maps_to_validation_code(self):
        exc = DRFValidationError("bad")
        self.assertEqual(_get_error_code_from_exception(exc, 400), ErrorCode.VALIDATION_ERROR)

    def test_drf_authentication_failed(self):
        exc = DRFAuthenticationFailed()
        self.assertEqual(_get_error_code_from_exception(exc, 401), ErrorCode.AUTHENTICATION_FAILED)

    def test_drf_not_authenticated(self):
        exc = DRFNotAuthenticated()
        self.assertEqual(_get_error_code_from_exception(exc, 401), ErrorCode.UNAUTHORIZED)

    def test_drf_permission_denied(self):
        exc = DRFPermissionDenied()
        self.assertEqual(_get_error_code_from_exception(exc, 403), ErrorCode.PERMISSION_DENIED)

    def test_drf_not_found(self):
        exc = DRFNotFound()
        self.assertEqual(_get_error_code_from_exception(exc, 404), ErrorCode.NOT_FOUND)

    def test_drf_method_not_allowed(self):
        exc = DRFMethodNotAllowed("GET")
        self.assertEqual(_get_error_code_from_exception(exc, 405), ErrorCode.METHOD_NOT_ALLOWED)

    def test_drf_parse_error(self):
        exc = DRFParseError()
        self.assertEqual(_get_error_code_from_exception(exc, 400), ErrorCode.PARSE_ERROR)

    def test_drf_unsupported_media_type(self):
        exc = DRFUnsupportedMediaType("text/xml")
        self.assertEqual(_get_error_code_from_exception(exc, 415), ErrorCode.UNSUPPORTED_MEDIA_TYPE)

    def test_drf_throttled(self):
        exc = DRFThrottled()
        self.assertEqual(_get_error_code_from_exception(exc, 429), ErrorCode.TOO_MANY_REQUESTS)

    def test_unknown_exception_uses_http_status_mapping(self):
        exc = Exception()
        self.assertEqual(_get_error_code_from_exception(exc, 404), ErrorCode.NOT_FOUND)
        self.assertEqual(_get_error_code_from_exception(exc, 500), ErrorCode.INTERNAL_SERVER_ERROR)


class GetMessageFromExceptionTests(TestCase):
    def test_custom_api_exception_uses_its_message(self):
        exc = APIException(message="Custom boom")
        self.assertEqual(_get_message_from_exception(exc, ErrorCode.BAD_REQUEST), "Custom boom")

    def test_custom_api_exception_no_message_falls_back(self):
        exc = APIException()
        self.assertEqual(
            _get_message_from_exception(exc, ErrorCode.BAD_REQUEST),
            "Bad request",
        )

    def test_drf_validation_error_default_message(self):
        exc = DRFValidationError("field error")
        self.assertIn("Validation error", _get_message_from_exception(exc, ErrorCode.VALIDATION_ERROR))

    def test_drf_authentication_failed_message(self):
        exc = DRFAuthenticationFailed()
        self.assertIn("Authentication failed", _get_message_from_exception(exc, ErrorCode.AUTHENTICATION_FAILED))

    def test_drf_not_authenticated_message(self):
        exc = DRFNotAuthenticated()
        self.assertIn("credentials", _get_message_from_exception(exc, ErrorCode.UNAUTHORIZED))

    def test_drf_permission_denied_message(self):
        exc = DRFPermissionDenied()
        self.assertIn("permission", _get_message_from_exception(exc, ErrorCode.PERMISSION_DENIED).lower())

    def test_drf_not_found_message(self):
        exc = DRFNotFound()
        self.assertIn("Not found", _get_message_from_exception(exc, ErrorCode.NOT_FOUND))

    def test_drf_method_not_allowed_message(self):
        exc = DRFMethodNotAllowed("GET")
        self.assertIn("Method not allowed", _get_message_from_exception(exc, ErrorCode.METHOD_NOT_ALLOWED))

    def test_fallback_to_error_code_message(self):
        exc = DRFAPIException("custom")
        exc.status_code = 418
        msg = _get_message_from_exception(exc, ErrorCode.INTERNAL_SERVER_ERROR)
        self.assertIsNotNone(msg)


class CustomExceptionHandlerTests(TestCase):
    def _make_context(self):
        return {"view": None, "args": (), "kwargs": {}}

    def test_non_api_exception_returns_none(self):
        exc = ValueError("regular error")
        result = custom_exception_handler(exc, self._make_context())
        self.assertIsNone(result)

    def test_response_is_response_object(self):
        exc = DRFValidationError({"field": "error"})
        result = custom_exception_handler(exc, self._make_context())
        self.assertIsInstance(result, Response)

    def test_validation_error_response_has_three_core_fields(self):
        exc = DRFValidationError({"username": ["Required"]})
        result = custom_exception_handler(exc, self._make_context())
        data = result.data
        self.assertIn("code", data)
        self.assertIn("message", data)
        self.assertIn("detail", data)

    def test_validation_error_response_has_field_error_at_top_level(self):
        exc = DRFValidationError({"username": ["Required field"]})
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.data["username"], "Required field")

    def test_validation_error_status_code_400(self):
        exc = DRFValidationError({"x": "y"})
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_error_code_matches(self):
        exc = DRFValidationError({"x": "y"})
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.data["code"], ErrorCode.VALIDATION_ERROR)

    def test_not_found_response(self):
        exc = DRFNotFound()
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(result.data["code"], ErrorCode.NOT_FOUND)
        self.assertIn("message", result.data)
        self.assertIn("detail", result.data)

    def test_permission_denied_response(self):
        exc = DRFPermissionDenied()
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(result.data["code"], ErrorCode.PERMISSION_DENIED)

    def test_not_authenticated_response(self):
        exc = DRFNotAuthenticated()
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(result.data["code"], ErrorCode.UNAUTHORIZED)

    def test_authentication_failed_response(self):
        exc = DRFAuthenticationFailed()
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(result.data["code"], ErrorCode.AUTHENTICATION_FAILED)

    def test_custom_api_exception_handled(self):
        exc = NotFound(detail={"id": "not found"}, message="Custom not found")
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(result.data["code"], ErrorCode.NOT_FOUND)
        self.assertEqual(result.data["message"], "Custom not found")
        self.assertEqual(result.data["detail"], {"id": "not found"})

    def test_detail_with_long_text_gets_truncated(self):
        long_msg = "x" * 2000
        exc = DRFValidationError({"field": [long_msg]})
        result = custom_exception_handler(exc, self._make_context())
        self.assertTrue(result.data["detail"]["field"][0].endswith("..."))

    def test_multiple_field_errors_all_at_top_level(self):
        exc = DRFValidationError({
            "username": ["Bad username"],
            "email": ["Bad email"],
            "password": ["Too short"],
        })
        result = custom_exception_handler(exc, self._make_context())
        self.assertEqual(result.data["username"], "Bad username")
        self.assertEqual(result.data["email"], "Bad email")
        self.assertEqual(result.data["password"], "Too short")


class HandleApiExceptionTests(TestCase):
    def test_custom_api_exception_response(self):
        exc = CustomValidationError(
            detail={"field": "msg"},
            message="Validation failed",
        )
        result = handle_api_exception(exc)
        self.assertIsInstance(result, Response)
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result.data["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(result.data["message"], "Validation failed")
        self.assertEqual(result.data["detail"], {"field": "msg"})
        self.assertEqual(result.data["field"], "msg")

    def test_custom_permission_denied_response(self):
        exc = CustomPermissionDenied(message="No access")
        result = handle_api_exception(exc)
        self.assertEqual(result.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(result.data["code"], ErrorCode.PERMISSION_DENIED)

    def test_regular_exception_becomes_500(self):
        exc = Exception("something broke")
        result = handle_api_exception(exc)
        self.assertEqual(result.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(result.data["code"], ErrorCode.INTERNAL_SERVER_ERROR)
        self.assertIn("detail", result.data)

    def test_regular_exception_includes_error_message_in_detail(self):
        exc = Exception("very specific failure")
        result = handle_api_exception(exc)
        self.assertIn("very specific failure", str(result.data["detail"]))
