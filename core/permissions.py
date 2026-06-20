from rest_framework import permissions

from core.models import BoardCollaborator


class IsOwnerOrReadOnly(permissions.IsAuthenticatedOrReadOnly):
    def __init__(self, owner_field_name="owner"):
        self.__owner_field_name = owner_field_name

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if getattr(obj, self.__owner_field_name) == request.user:
            return True

        if hasattr(obj, 'collaborators'):
            return BoardCollaborator.has_permission_for_method(
                request.user, obj, request.method
            )

        return False


class OwnerOnlyIfPrivate(permissions.BasePermission):
    def __init__(self, owner_field_name="owner"):
        self.__owner_field_name = owner_field_name

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        if not getattr(obj, "private"):
            return True
        if request.user == getattr(obj, self.__owner_field_name):
            return True
        if hasattr(obj, 'collaborators'):
            perm = BoardCollaborator.get_permission_level(request.user, obj)
            return perm is not None
        return False


class OwnerOnly(permissions.IsAuthenticatedOrReadOnly):

    def has_permission(self, request, view):
        return request.user.is_authenticated()

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user


class SuperUserOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        return request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser
