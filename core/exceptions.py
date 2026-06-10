from django.utils.translation import gettext_lazy as _
from rest_framework import status


class ErrorCode:
    SUCCESS = 0

    BAD_REQUEST = 40000
    VALIDATION_ERROR = 40001
    INVALID_PARAMS = 40002
    PARSE_ERROR = 40003

    UNAUTHORIZED = 40100
    AUTHENTICATION_FAILED = 40101
    INVALID_TOKEN = 40102
    TOKEN_EXPIRED = 40103

    FORBIDDEN = 40300
    PERMISSION_DENIED = 40301
    NOT_ALLOWED = 40302

    NOT_FOUND = 40404
    RESOURCE_NOT_FOUND = 40401

    METHOD_NOT_ALLOWED = 40500

    CONFLICT = 40900
    DUPLICATE_ENTRY = 40901

    UNSUPPORTED_MEDIA_TYPE = 41500

    TOO_MANY_REQUESTS = 42900

    INTERNAL_SERVER_ERROR = 50000
    SERVICE_UNAVAILABLE = 50300


ERROR_MESSAGE_MAP = {
    ErrorCode.SUCCESS: _("Success"),

    ErrorCode.BAD_REQUEST: _("Bad request"),
    ErrorCode.VALIDATION_ERROR: _("Validation error"),
    ErrorCode.INVALID_PARAMS: _("Invalid parameters"),
    ErrorCode.PARSE_ERROR: _("Parse error"),

    ErrorCode.UNAUTHORIZED: _("Unauthorized"),
    ErrorCode.AUTHENTICATION_FAILED: _("Authentication failed"),
    ErrorCode.INVALID_TOKEN: _("Invalid token"),
    ErrorCode.TOKEN_EXPIRED: _("Token expired"),

    ErrorCode.FORBIDDEN: _("Forbidden"),
    ErrorCode.PERMISSION_DENIED: _("Permission denied"),
    ErrorCode.NOT_ALLOWED: _("Not allowed"),

    ErrorCode.NOT_FOUND: _("Not found"),
    ErrorCode.RESOURCE_NOT_FOUND: _("Resource not found"),

    ErrorCode.METHOD_NOT_ALLOWED: _("Method not allowed"),

    ErrorCode.CONFLICT: _("Conflict"),
    ErrorCode.DUPLICATE_ENTRY: _("Duplicate entry"),

    ErrorCode.UNSUPPORTED_MEDIA_TYPE: _("Unsupported media type"),

    ErrorCode.TOO_MANY_REQUESTS: _("Too many requests"),

    ErrorCode.INTERNAL_SERVER_ERROR: _("Internal server error"),
    ErrorCode.SERVICE_UNAVAILABLE: _("Service unavailable"),
}


HTTP_STATUS_TO_ERROR_CODE = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.TOO_MANY_REQUESTS,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_SERVER_ERROR,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


MAX_DETAIL_LENGTH = 1000


def truncate_detail(detail, max_length=MAX_DETAIL_LENGTH):
    if isinstance(detail, str):
        if len(detail) > max_length:
            return detail[:max_length] + "..."
        return detail
    if isinstance(detail, dict):
        result = {}
        for key, value in detail.items():
            result[key] = truncate_detail(value, max_length)
        return result
    if isinstance(detail, list):
        return [truncate_detail(item, max_length) for item in detail]
    return detail


def get_error_message(code):
    return str(ERROR_MESSAGE_MAP.get(code, ERROR_MESSAGE_MAP[ErrorCode.INTERNAL_SERVER_ERROR]))


def format_error_response(code, message=None, detail=None, extra_fields=None):
    response_data = {
        "code": code,
        "message": message if message is not None else get_error_message(code),
        "detail": detail if detail is not None else {},
    }

    if extra_fields and isinstance(extra_fields, dict):
        response_data.update(extra_fields)

    response_data["detail"] = truncate_detail(response_data["detail"])

    return response_data


def get_http_status_from_error_code(code):
    for http_status, error_code in HTTP_STATUS_TO_ERROR_CODE.items():
        if code >= error_code and code < error_code + 100:
            return http_status
    return status.HTTP_500_INTERNAL_SERVER_ERROR


class APIException(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = ErrorCode.INTERNAL_SERVER_ERROR
    default_message = None

    def __init__(self, detail=None, code=None, message=None, status_code=None):
        self.code = code if code is not None else self.default_code
        self.message = message if message is not None else self.default_message
        self.detail = detail if detail is not None else {}
        if status_code is not None:
            self.status_code = status_code

    def __str__(self):
        return f"{self.code}: {self.message}"


class ValidationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCode.VALIDATION_ERROR


class AuthenticationFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = ErrorCode.AUTHENTICATION_FAILED


class PermissionDenied(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = ErrorCode.PERMISSION_DENIED


class NotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = ErrorCode.NOT_FOUND


class MethodNotAllowed(APIException):
    status_code = status.HTTP_405_METHOD_NOT_ALLOWED
    default_code = ErrorCode.METHOD_NOT_ALLOWED


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCode.CONFLICT


class UnsupportedMediaType(APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = ErrorCode.UNSUPPORTED_MEDIA_TYPE


class TooManyRequests(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = ErrorCode.TOO_MANY_REQUESTS


class ParseError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCode.PARSE_ERROR


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = ErrorCode.SERVICE_UNAVAILABLE
