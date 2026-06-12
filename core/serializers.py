from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from taggit.models import Tag

from core.models import Image, Board
from core.models import Pin
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy
from django_images.models import Thumbnail
from users.serializers import UserSerializer
from users.models import User


def filter_private_pin(request, query):
    """
    向后兼容的包装函数：内部委托给 PinVisibilityPolicy。
    新代码请直接使用 PinVisibilityPolicy.filter_queryset。
    """
    return PinVisibilityPolicy.filter_queryset(query, request.user)


def filter_private_board(request, query):
    """
    向后兼容的包装函数：内部委托给 BoardVisibilityPolicy。
    新代码请直接使用 BoardVisibilityPolicy.filter_queryset。
    """
    return BoardVisibilityPolicy.filter_queryset(query, request.user)


class ThumbnailSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Thumbnail
        fields = (
            "image",
            "width",
            "height",
        )


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = (
            "id",
            "image",
            "width",
            "height",
            "standard",
            "thumbnail",
            "square",
        )
        extra_kwargs = {
            "width": {"read_only": True},
            "height": {"read_only": True},
        }

    standard = ThumbnailSerializer(read_only=True)
    thumbnail = ThumbnailSerializer(read_only=True)
    square = ThumbnailSerializer(read_only=True)

    def create(self, validated_data):
        image = super(ImageSerializer, self).create(validated_data)
        Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
        return image


class TagSerializer(serializers.SlugRelatedField):
    class Meta:
        model = Tag
        fields = ("name",)

    queryset = Tag.objects.all()

    def __init__(self, **kwargs):
        super(TagSerializer, self).__init__(
            slug_field="name",
            **kwargs
        )

    def to_internal_value(self, data):
        obj, _ = self.get_queryset().get_or_create(
            defaults={self.slug_field: data, "slug": data},
            **{self.slug_field: data}
        )
        return obj


class PinSerializer(serializers.HyperlinkedModelSerializer):
    """
    Pin 的序列化器。

    职责拆分：
    - 字段定义/序列化：由 ModelSerializer 和字段声明处理
    - 数据校验/创建/更新：由 create / update 方法处理
    - 可见性判断：统一由 PinVisibilityPolicy 处理，不在此处混入
    """

    class Meta:
        model = Pin
        fields = (
            settings.DRF_URL_FIELD_NAME,
            "private",
            "id",
            "submitter",
            "url",
            "description",
            "referer",
            "image",
            "image_by_id",
            "tags",
        )

    submitter = UserSerializer(read_only=True)
    tags = TagSerializer(
        many=True,
        source="tag_list",
        required=False,
    )
    image = ImageSerializer(required=False, read_only=True)
    image_by_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        write_only=True,
        required=False,
    )

    def _validate_image_source(self, validated_data):
        """校验：必须提供 url 或 image_by_id 中的至少一个。"""
        if 'url' not in validated_data and 'image_by_id' not in validated_data:
            raise ValidationError(
                detail={
                    "url-or-image": "Either url or image_by_id is required."
                },
            )

    def _create_image_from_url(self, url, referer):
        """从 URL 下载并创建 Image 对象，失败则抛出校验错误。"""
        image = Image.objects.create_for_url(url, referer)
        if not image:
            raise ValidationError({"url": "invalid image content"})
        return image

    def create(self, validated_data):
        self._validate_image_source(validated_data)
        submitter = self.context['request'].user

        if 'url' in validated_data and validated_data['url']:
            url = validated_data['url']
            image = self._create_image_from_url(
                url,
                validated_data.get('referer', url),
            )
        else:
            image = validated_data.pop("image_by_id")

        tags = validated_data.pop('tag_list', [])
        pin = Pin.objects.create(submitter=submitter, image=image, **validated_data)
        if tags:
            pin.tags.set(*tags)
        return pin

    def update(self, instance, validated_data):
        tags = validated_data.pop('tag_list', None)
        if tags:
            instance.tags.set(*tags)
        else:
            instance.tags.set()
        validated_data.pop('image_by_id', None)
        return super(PinSerializer, self).update(instance, validated_data)


class PinIdListField(serializers.ListField):
    child = serializers.IntegerField(
        min_value=1
    )


class BoardAutoCompleteSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Board
        fields = (
            settings.DRF_URL_FIELD_NAME,
            'id',
            'name',
        )


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    """
    Board 的序列化器。

    职责拆分：
    - 字段定义/序列化：由 ModelSerializer 和字段声明处理
    - 数据校验/创建/更新：由 create / update 方法处理
    - Pin 可见性过滤：统一由 PinVisibilityPolicy 处理
    - Board 自身可见性：统一由 BoardVisibilityPolicy 处理
    """

    class Meta:
        model = Board
        fields = (
            settings.DRF_URL_FIELD_NAME,
            "id",
            "name",
            "private",
            "total_pins",
            "cover",
            "published",
            "submitter",
            "pins_to_add",
            "pins_to_remove",
        )
        read_only_fields = ('submitter', 'published')
        extra_kwargs = {
            'submitter': {"view_name": "users:user-detail"},
        }

    submitter = UserSerializer(read_only=True)
    total_pins = serializers.SerializerMethodField(
        read_only=True,
    )
    cover = serializers.SerializerMethodField(
        read_only=True,
    )
    pins_to_add = PinIdListField(
        max_length=10,
        write_only=True,
        required=False,
        allow_empty=False,
        help_text="only patch method works for this field",
    )
    pins_to_remove = PinIdListField(
        max_length=10,
        write_only=True,
        required=False,
        allow_empty=False,
        help_text="only patch method works for this field"
    )

    def _get_current_user(self):
        """从序列化上下文中获取当前请求用户。"""
        request = self.context.get('request')
        return request.user if request is not None else None

    def get_total_pins(self, instance):
        """返回 Board 中对当前用户可见的 Pin 数量。"""
        query = instance.pins.all()
        user = self._get_current_user()
        visible_pins = PinVisibilityPolicy.filter_queryset(query, user)
        return visible_pins.count()

    def get_cover(self, instance: Board) -> dict or None:
        """返回 Board 中第一个 Pin 的序列化结果作为封面。"""
        pin = instance.pins.first()
        if pin is None:
            return None
        return PinSerializer(pin, context=self.context).data

    def _validate_board_name_unique(self, submitter: User, name: str, exclude_id: int = None):
        """校验 Board 名称对同一用户的唯一性。"""
        query = Board.objects.filter(submitter=submitter, name=name)
        if exclude_id is not None:
            query = query.exclude(id=exclude_id)
        if query.exists():
            raise ValidationError(
                detail={'name': "Board with this name already exists"}
            )

    @staticmethod
    def _filter_visible_pins(pins_id, submitter: User):
        """
        根据 Pin 可见性策略过滤 pin id 列表。

        仅保留 submitter 可见的 Pin（即：公开的 Pin，或 submitter 自己的私有 Pin）。
        """
        pins = Pin.objects.filter(id__in=pins_id)
        return PinVisibilityPolicy.filter_visible_objects(pins, submitter)

    def update(self, instance: Board, validated_data):
        pins_to_add = validated_data.pop("pins_to_add", [])
        pins_to_remove = validated_data.pop("pins_to_remove", [])

        new_name = validated_data.get('name', None)
        if new_name is not None:
            self._validate_board_name_unique(
                instance.submitter, new_name, exclude_id=instance.id
            )

        instance = super(BoardSerializer, self).update(instance, validated_data)

        changed = False
        if pins_to_add:
            changed = True
            for pin in self._filter_visible_pins(pins_to_add, instance.submitter):
                instance.pins.add(pin)
        if pins_to_remove:
            changed = True
            for pin in self._filter_visible_pins(pins_to_remove, instance.submitter):
                instance.pins.remove(pin)
        if changed:
            instance.save()
        return instance

    def create(self, validated_data):
        validated_data.pop('pins_to_remove', None)
        validated_data.pop('pins_to_add', None)
        user = self.context['request'].user

        self._validate_board_name_unique(user, validated_data['name'])
        validated_data['submitter'] = user
        return super(BoardSerializer, self).create(validated_data)


class TagAutoCompleteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag
        fields = ('name', )
