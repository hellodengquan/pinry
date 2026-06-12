from abc import ABC, abstractmethod

from django.db.models import Q, QuerySet

from users.models import User


class BaseVisibilityPolicy(ABC):
    """
    可见性策略基类，定义统一的可见性判断接口。

    所有需要做私有/公开可见性控制的模型都应该实现对应的子类策略，
    以便在 queryset 过滤、对象级权限判断、序列化字段截取等场景中复用。
    """

    owner_field_name: str = "submitter"
    private_field_name: str = "private"

    @classmethod
    def _is_authenticated(cls, user) -> bool:
        return user.is_authenticated if user is not None else False

    @classmethod
    def _is_owner(cls, obj, user) -> bool:
        if not cls._is_authenticated(user):
            return False
        return getattr(obj, cls.owner_field_name, None) == user

    @classmethod
    def is_private(cls, obj) -> bool:
        return getattr(obj, cls.private_field_name, False)

    @classmethod
    @abstractmethod
    def filter_queryset(cls, queryset: QuerySet, user) -> QuerySet:
        """根据用户身份过滤 queryset，只保留可见的对象。"""
        ...

    @classmethod
    def is_object_visible(cls, obj, user) -> bool:
        """判断单个对象对指定用户是否可见。"""
        if not cls.is_private(obj):
            return True
        return cls._is_owner(obj, user)

    @classmethod
    def filter_visible_objects(cls, objects, user):
        """从对象列表（非 QuerySet）中过滤出对用户可见的对象。"""
        return [obj for obj in objects if cls.is_object_visible(obj, user)]


class PinVisibilityPolicy(BaseVisibilityPolicy):
    """
    Pin 的可见性策略。

    - 公开 Pin：对所有用户可见
    - 私有 Pin：仅对 submitter（所有者）可见
    """

    owner_field_name = "submitter"
    private_field_name = "private"

    @classmethod
    def filter_queryset(cls, queryset: QuerySet, user) -> QuerySet:
        if cls._is_authenticated(user):
            queryset = queryset.exclude(~Q(submitter=user), private=True)
        else:
            queryset = queryset.exclude(private=True)
        return queryset.select_related("image", "submitter")


class BoardVisibilityPolicy(BaseVisibilityPolicy):
    """
    Board 的可见性策略。

    - 公开 Board：对所有用户可见
    - 私有 Board：仅对 submitter（所有者）可见
    """

    owner_field_name = "submitter"
    private_field_name = "private"

    @classmethod
    def filter_queryset(cls, queryset: QuerySet, user) -> QuerySet:
        if cls._is_authenticated(user):
            queryset = queryset.exclude(~Q(submitter=user), private=True)
        else:
            queryset = queryset.exclude(private=True)
        return queryset
