from abc import ABC, abstractmethod

from django.db.models import Q, QuerySet


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

    @classmethod
    @abstractmethod
    def infer_privacy(cls, obj) -> bool:
        """
        根据关联关系推断对象的隐私状态应该是什么。

        用于回填审计：将推断结果与实际 private 字段对比，
        发现因旧规则遗留导致的可见性不一致。
        """
        ...

    @classmethod
    def get_owner(cls, obj):
        return getattr(obj, cls.owner_field_name, None)


class PinVisibilityPolicy(BaseVisibilityPolicy):
    """
    Pin 的可见性策略。

    - 公开 Pin：对所有用户可见
    - 私有 Pin：仅对 submitter（所有者）可见

    推断规则：
    - 若 Pin 所属的任意 Board 为 private=True → 推断 Pin 应为 private
    - 若 Pin 当前为 private，但被至少一个 public Board 引用 → 推断 Pin 应为 public
      （private Pin 出现在 public Board 中是不一致配置，可能导致信息泄露）
    - 否则保持 Pin 自身的 private 值
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

    @classmethod
    def infer_privacy(cls, obj) -> bool:
        from core.models import Board

        in_private_board = Board.objects.filter(
            pins=obj, private=True
        ).exists()
        if in_private_board:
            return True

        in_public_board = Board.objects.filter(
            pins=obj, private=False
        ).exists()
        if cls.is_private(obj) and in_public_board:
            return False

        return cls.is_private(obj)


class BoardVisibilityPolicy(BaseVisibilityPolicy):
    """
    Board 的可见性策略。

    - 公开 Board：对所有用户可见
    - 私有 Board：仅对 submitter（所有者）可见

    推断规则：
    - 若 Board 中所有 Pin 都属于其他用户且均为 private → 推断 Board 应为 private
      （对非所有者无可见内容）
    - 若 Board 当前为 private，但包含至少一个 public Pin → 推断 Board 应为 public
      （private Board 中出现 public Pin 是不一致配置，public Pin 本身对所有人可见）
    - 否则保持 Board 自身的 private 值
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

    @classmethod
    def infer_privacy(cls, obj) -> bool:
        owner = cls.get_owner(obj)
        pins = obj.pins.all()

        if not pins.exists():
            return cls.is_private(obj)

        has_public_pin = any(
            not PinVisibilityPolicy.infer_privacy(pin) for pin in pins
        )
        if cls.is_private(obj) and has_public_pin:
            return False

        all_pins_invisible_to_others = True
        for pin in pins:
            if not PinVisibilityPolicy.infer_privacy(pin):
                all_pins_invisible_to_others = False
                break
            if PinVisibilityPolicy.get_owner(pin) == owner:
                all_pins_invisible_to_others = False
                break
        if all_pins_invisible_to_others:
            return True

        return cls.is_private(obj)
