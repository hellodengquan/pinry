from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import (
    APIException as DRFAPIException,
    ValidationError as DRFValidationError,
    AuthenticationFailed as DRFAuthenticationFailed,
    NotAuthenticated as DRFNotAuthenticated,
    PermissionDenied as DRFPermissionDenied,
    NotFound as DRFNotFound,
    MethodNotAllowed as DRFMethodNotAllowed,
    NotAcceptable as DRFNotAcceptable,
    UnsupportedMediaType as DRFUnsupportedMediaType,
    Throttled as DRFThrottled,
    ParseError as DRFParseError,
    ErrorDetail,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.exceptions import (
    APIException,
    ErrorCode,
    format_error_response,
    get_error_message,
    HTTP_STATUS_TO_ERROR_CODE,
    truncate_detail,
)


def _get_error_code_from_exception(exc, status_code):
    if isinstance(exc, APIException):
        return exc.code

    if isinstance(exc, DRFValidationError):
        return ErrorCode.VALIDATION_ERROR
    if isinstance(exc, DRFAuthenticationFailed):
        return ErrorCode.AUTHENTICATION_FAILED
    if isinstance(exc, DRFNotAuthenticated):
        return ErrorCode.UNAUTHORIZED
    if isinstance(exc, DRFPermissionDenied):
        return ErrorCode.PERMISSION_DENIED
    if isinstance(exc, DRFNotFound):
        return ErrorCode.NOT_FOUND
    if isinstance(exc, DRFMethodNotAllowed):
        return ErrorCode.METHOD_NOT_ALLOWED
    if isinstance(exc, DRFNotAcceptable):
        return ErrorCode.BAD_REQUEST
    if isinstance(exc, DRFUnsupportedMediaType):
        return ErrorCode.UNSUPPORTED_MEDIA_TYPE
    if isinstance(exc, DRFThrottled):
        return ErrorCode.TOO_MANY_REQUESTS
    if isinstance(exc, DRFParseError):
        return ErrorCode.PARSE_ERROR
    if isinstance(exc, DRFAPIException):
        return HTTP_STATUS_TO_ERROR_CODE.get(
            exc.status_code, ErrorCode.INTERNAL_SERVER_ERROR
        )

    return HTTP_STATUS_TO_ERROR_CODE.get(
        status_code, ErrorCode.INTERNAL_SERVER_ERROR
    )


def _get_message_from_exception(exc, code):
    if isinstance(exc, APIException) and exc.message:
        return str(exc.message)

    if isinstance(exc, DRFValidationError):
        return str(_("Validation error"))
    if isinstance(exc, DRFAuthenticationFailed):
        return str(_("Authentication failed"))
    if isinstance(exc, DRFNotAuthenticated):
        return str(_("Authentication credentials were not provided."))
    if isinstance(exc, DRFPermissionDenied):
        return str(_("You do not have permission to perform this action."))
    if isinstance(exc, DRFNotFound):
        return str(_("Not found."))
    if isinstance(exc, DRFMethodNotAllowed):
        return str(_("Method not allowed."))
    if isinstance(exc, DRFThrottled):
        return str(_("Request was throttled."))
    if isinstance(exc, DRFParseError):
        return str(_("Malformed request."))

    return get_error_message(code)


def _normalize_detail(detail):
    if isinstance(detail, ErrorDetail):
        return str(detail)
    if isinstance(detail, list):
        return [_normalize_detail(item) for item in detail]
    if isinstance(detail, dict):
        result = {}
        for key, value in detail.items():
            result[key] = _normalize_detail(value)
        return result
    if isinstance(detail, str):
        return detail
    return str(detail)


def _extract_field_errors(detail):
    if isinstance(detail, dict):
        result = {}
        for key, value in detail.items():
            if isinstance(value, list):
                result[key] = value[0] if value else ""
            elif isinstance(value, str):
                result[key] = value
            elif isinstance(value, dict):
                result[key] = _extract_field_errors(value)
            else:
                result[key] = str(value)
        return result
    if isinstance(detail, list):
        return {"non_field_errors": detail[0] if detail else ""}
    return {"non_field_errors": str(detail)}


def custom_exception_handler(exc, context):
    if isinstance(exc, APIException):
        status_code = exc.status_code
        error_code = exc.code
        message = exc.message if exc.message else get_error_message(error_code)
        detail = exc.detail
    else:
        response = drf_exception_handler(exc, context)
        if response is None:
            return None

        status_code = response.status_code
        error_code = _get_error_code_from_exception(exc, status_code)
        message = _get_message_from_exception(exc, error_code)

        if hasattr(exc, 'detail'):
            detail = _normalize_detail(exc.detail)
        else:
            detail = str(exc)

    detail = truncate_detail(detail)

    error_response = format_error_response(
        code=error_code,
        message=message,
        detail=detail,
    )

    field_errors = _extract_field_errors(detail)
    error_response.update(field_errors)

    if isinstance(exc, APIException):
        return Response(error_response, status=status_code)

    response.data = error_response
    return response


def handle_api_exception(exc):
    if isinstance(exc, APIException):
        error_code = exc.code
        message = exc.message if exc.message else get_error_message(error_code)
        detail = exc.detail
        status_code = exc.status_code
    else:
        error_code = ErrorCode.INTERNAL_SERVER_ERROR
        message = get_error_message(error_code)
        detail = str(exc)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    detail = truncate_detail(detail)

    error_response = format_error_response(
        code=error_code,
        message=message,
        detail=detail,
    )

    field_errors = _extract_field_errors(detail)
    error_response.update(field_errors)

    return Response(error_response, status=status_code)
