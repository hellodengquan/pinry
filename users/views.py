import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, routers, status
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.viewsets import GenericViewSet

from core.exceptions import ErrorCode, format_error_response, truncate_detail
from core.serializers import UserSerializer
from users.models import User


def _error_response(code, message=None, detail=None, status_code=None):
    if status_code is None:
        from core.exceptions import get_http_status_from_error_code
        status_code = get_http_status_from_error_code(code)

    error_data = format_error_response(
        code=code,
        message=message,
        detail=detail,
    )

    if isinstance(detail, dict):
        for key, value in detail.items():
            if key not in error_data:
                if isinstance(value, list):
                    error_data[key] = value[0] if value else ""
                else:
                    error_data[key] = value
    elif isinstance(detail, str):
        error_data["non_field_errors"] = detail

    error_data["detail"] = truncate_detail(error_data["detail"])

    return JsonResponse(error_data, status=status_code)


def reverse_lazy(name=None, *args):
    return lazy(reverse, str)(name, args=args)


class PublicUserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = UserSerializer
    filter_backends = (DjangoFilterBackend, )
    filter_fields = ("username", )
    pagination_class = None

    def get_queryset(self):
        username = self.request.GET.get("username", "")
        return User.objects.filter(username=username)


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    GenericViewSet,
):
    class Permission(BasePermission):
        def has_permission(self, request, view):
            if not request.method == "POST":
                return True
            return settings.ALLOW_NEW_REGISTRATIONS

        def has_object_permission(self, request, view, obj):
            return request.user == obj

    permission_classes = [Permission, ]
    serializer_class = UserSerializer
    pagination_class = None

    def get_queryset(self):
        if self.request.user.is_anonymous:
            return User.objects.none()
        return User.objects.filter(id=self.request.user.id)


def login_user(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _error_response(
            code=ErrorCode.PARSE_ERROR,
            message=_("Invalid JSON format"),
            detail={"non_field_errors": _("Invalid JSON format")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    errors = {}
    if 'username' not in data:
        errors["username"] = _("This field is required.")
    if 'password' not in data:
        errors["password"] = _("This field is required.")

    if errors:
        return _error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message=_("Validation error"),
            detail=errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(
        request,
        username=data['username'],
        password=data['password']
    )
    if not user:
        return _error_response(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message=_("Username and password doesn't match."),
            detail={"password": _("Username and password doesn't match.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    login(request, user)
    data = UserSerializer(
        user,
        context={'request': request},
    ).data
    return HttpResponse(
        JSONRenderer().render(data),
        content_type="application/json"
    )


@login_required
def logout_user(request):
    logout(request)
    messages.success(request, 'You have successfully logged out.')
    return HttpResponseRedirect('/')


drf_router = routers.DefaultRouter()
drf_router.register(r'users', UserViewSet, basename="user")
drf_router.register(r'public-users', PublicUserViewSet, basename="public-user")
