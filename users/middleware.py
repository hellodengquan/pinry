from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorCode, format_error_response, truncate_detail


def _middleware_error_response(code, message=None, detail=None, status_code=403):
    error_data = format_error_response(
        code=code,
        message=message,
        detail=detail,
    )
    error_data["detail"] = truncate_detail(error_data["detail"])
    return JsonResponse(error_data, status=status_code)


class Public(MiddlewareMixin):

    acceptable_paths = (
        "/api/v2/profile/",
    )

    def process_request(self, request):
        if settings.PUBLIC is False and not request.user.is_authenticated:
            for path in self.acceptable_paths:
                if not request.path.startswith(path):
                    return _middleware_error_response(
                        code=ErrorCode.FORBIDDEN,
                        message=_("Access denied. Please log in."),
                        detail={"non_field_errors": _("Access denied. Please log in.")},
                        status_code=403,
                    )
