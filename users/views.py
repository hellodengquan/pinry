import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.utils import translation
from django.utils.functional import lazy
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, routers, status
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.serializers import UserSerializer
from users.models import User, UserSettings, LANGUAGE_CHOICES


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
    mixins.UpdateModelMixin,
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

    @action(detail=False, methods=["get"], url_path="available-languages")
    def available_languages(self, request):
        return Response({
            "default": settings.LANGUAGE_CODE,
            "current": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE),
            "results": [
                {"code": code, "label": label}
                for code, label in LANGUAGE_CHOICES
            ],
        })

    @action(detail=False, methods=["post"], url_path="set-language")
    def set_language(self, request):
        code = request.data.get("language") or request.data.get("lang")
        if code is None:
            return Response(
                {"detail": "`language` is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_codes = {c for c, _ in LANGUAGE_CHOICES}
        if code != "" and code not in valid_codes:
            return Response(
                {"detail": f"invalid language, must be one of {sorted(valid_codes)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        UserSettings.objects.update_or_create(
            user=request.user,
            defaults={"language": code if code else None},
        )
        if code:
            translation.activate(code)
        else:
            translation.deactivate()
        return Response(UserSerializer(request.user, context={"request": request}).data)


def login_user(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest()
    if 'username' not in data:
        return HttpResponseBadRequest(
            json.dumps({"username": "this field is required"})
        )
    if 'password' not in data:
        return HttpResponseBadRequest(
            json.dumps({"password": "this field is required"})
        )
    user = authenticate(
        request,
        username=data['username'],
        password=data['password']
    )
    if not user:
        return HttpResponseBadRequest(
            json.dumps({"password": "username and password doesn't match"})
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
