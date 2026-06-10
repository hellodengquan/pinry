from rest_framework import permissions

from core.visibility import VisibilityPolicy


class IsOwnerOrReadOnly(permissions.IsAuthenticatedOrReadOnly):
    def __init__(self, owner_field_name="submitter"):
        self._owner_field_name = owner_field_name

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return VisibilityPolicy.can_change(
            obj, request.user, owner_field=self._owner_field_name
        )


class OwnerOnlyIfPrivate(permissions.BasePermission):
    def __init__(self, owner_field_name="submitter"):
        self._owner_field_name = owner_field_name

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        return VisibilityPolicy.can_view(
            obj, request.user, owner_field=self._owner_field_name
        )


class OwnerOnly(permissions.IsAuthenticatedOrReadOnly):

    def has_permission(self, request, view):
        return request.user.is_authenticated()

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "owner") == request.user


class SuperUserOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        return request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser
