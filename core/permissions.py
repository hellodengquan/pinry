from rest_framework import permissions

from core.visibility import BaseVisibilityPolicy


class IsOwnerOrReadOnly(permissions.IsAuthenticatedOrReadOnly):
    """
    对象级权限：仅允许对象所有者编辑它，其他用户只读。

    可通过构造参数传入 owner 字段名，默认为 "owner"。
    该权限类可被工厂化复用，无需为每个模型单独定义。
    """
    def __init__(self, owner_field_name="owner"):
        self._owner_field_name = owner_field_name

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, self._owner_field_name) == request.user


class VisibilityBasedPermission(permissions.BasePermission):
    """
    基于可见性策略的对象级权限。

    对于私有对象，仅允许所有者访问；公开对象对所有用户开放。
    通过注入不同的 visibility_policy，可以对任意模型复用该权限类。
    """
    def __init__(self, visibility_policy: type):
        if not issubclass(visibility_policy, BaseVisibilityPolicy):
            raise TypeError(
                "visibility_policy must be a subclass of BaseVisibilityPolicy"
            )
        self._visibility_policy = visibility_policy

    def __call__(self):
        return self

    def has_object_permission(self, request, view, obj):
        return self._visibility_policy.is_object_visible(obj, request.user)


class OwnerOnlyIfPrivate(VisibilityBasedPermission):
    """
    向后兼容的权限类：保持原有的接口签名，内部委托给 VisibilityBasedPermission。

    原实现依赖 "private" 字段和传入的 owner 字段名进行判断。
    这里通过构造一个匿名的 VisibilityPolicy 子类来保持等价行为，
    同时让外部调用者（如 views.py）无需立即修改代码。
    """
    def __init__(self, owner_field_name="owner"):
        class _AdHocPolicy(BaseVisibilityPolicy):
            pass

        _AdHocPolicy.owner_field_name = owner_field_name
        _AdHocPolicy.private_field_name = "private"
        super().__init__(_AdHocPolicy)


class OwnerOnly(permissions.IsAuthenticatedOrReadOnly):

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "owner", None) == request.user


class SuperUserOnly(permissions.BasePermission):
    """
    仅超级用户可访问的权限。
    """

    def has_permission(self, request, view):
        return request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser
