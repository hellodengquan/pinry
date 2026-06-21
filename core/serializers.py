from django.conf import settings
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from taggit.models import Tag

from core.models import Image, Board
from core.models import Pin
from django_images.models import Thumbnail
from users.serializers import UserSerializer
from users.models import User


def filter_private_pin(request, query):
    if request.user.is_authenticated:
        query = query.exclude(~Q(submitter=request.user), private=True)
    else:
        query = query.exclude(private=True)
    return query.select_related('image', 'submitter')


def filter_private_board(request, query):
    if request.user.is_authenticated:
        query = query.exclude(~Q(submitter=request.user), private=True)
    else:
        query = query.exclude(private=True)
    return query


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

    def create(self, validated_data):
        if 'url' not in validated_data and\
                'image_by_id' not in validated_data:
            raise ValidationError(
                detail={
                    "url-or-image": "Either url or image_by_id is required."
                },
            )

        submitter = self.context['request'].user
        if 'url' in validated_data and validated_data['url']:
            url = validated_data['url']
            image = Image.objects.create_for_url(
                url,
                validated_data.get('referer', url),
            )
            if not image:
                raise ValidationError({"url": "invalid image content"})
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
        # change for image-id or image is not allowed
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

    def get_total_pins(self, instance):
        query = instance.pins.all()
        request = self.context['request']
        query = filter_private_pin(request, query)
        return query.count()

    def get_cover(self, instance: Board) -> dict or None:
        pin = instance.pins.first()
        if pin is None:
            return None
        return PinSerializer(pin, context=self.context).data

    @staticmethod
    def _get_list(pins_id, submitter: User):
        pins = Pin.objects.filter(id__in=pins_id)
        valid_pins = []
        for pin in pins:
            if pin.private and pin.submitter != submitter:
                continue
            valid_pins.append(pin)
        return valid_pins

    def update(self, instance: Board, validated_data):
        pins_to_add = validated_data.pop("pins_to_add", [])
        pins_to_remove = validated_data.pop("pins_to_remove", [])
        board = Board.objects.filter(
            submitter=instance.submitter,
            name=validated_data.get('name', None)
        ).first()
        if board and board.id != instance.id:
            raise ValidationError(
                detail={'name': "Board with this name already exists"}
            )
        instance = super(BoardSerializer, self).update(instance, validated_data)
        changed = False
        if pins_to_add:
            changed = True
            for pin in self._get_list(pins_to_add, instance.submitter):
                instance.pins.add(pin)
        if pins_to_remove:
            changed = True
            for pin in self._get_list(pins_to_remove, instance.submitter):
                instance.pins.remove(pin)
        if changed:
            instance.save()
        return instance

    def create(self, validated_data):
        validated_data.pop('pins_to_remove', None)
        validated_data.pop('pins_to_add', None)
        user = self.context['request'].user
        if Board.objects.filter(name=validated_data['name'], submitter=user).exists():
            raise ValidationError(
                detail={"name": "board with this name already exists."}
            )
        validated_data['submitter'] = user
        return super(BoardSerializer, self).create(validated_data)


class TagAutoCompleteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag
        fields = ('name', )


class BatchFingerprintPolicySerializer(serializers.Serializer):
    """
    指纹匹配策略配置

    【pHash 阈值选择依据（阈值 5 的默认值论证）】
    ┌──────────┬─────────────────────────────────────────────────────────────┐
    │ 阈值  0   │ 命中: PNG→JPG 转格式 / 文件重命名 / 仅改 EXIF              │
    │          │ 漏报: 任何像素修改        FP: ≈0%      用途: 取证级严格去重  │
    ├──────────┼─────────────────────────────────────────────────────────────┤
    │ 阈值  2   │ 命中: JPG 95→50 压缩 / 去隐形水印 / 色彩空间转换           │
    │          │ 漏报: 可见水印 / ±10% 亮度   FP: <0.01%  用途: 素材库管理    │
    ├──────────┼─────────────────────────────────────────────────────────────┤
    │★阈值  5 ★│ 命中: 缩放 2000→800 / 居中裁剪 80%+ / 常规滤镜 / ±20% 亮度 │
    │(默认推荐) │ 漏报: 镜像 / 旋转>45° / 裁切 >50%  FP:≈0.1% 用途: Pinry 默认│
    ├──────────┼─────────────────────────────────────────────────────────────┤
    │ 阈值  7   │ 命中: 加文字 meme 图 / 手机 vs 桌面截图 / 黑白 vs 彩色      │
    │          │ 漏报: 白天 vs 黑夜同场景     FP: ≈2-3%   用途: 相似推荐辅助  │
    ├──────────┼─────────────────────────────────────────────────────────────┤
    │ 阈值 10+  │ 命中: 同色系 / 同构图分类                                   │
    │          │ 漏报: 多数跨类别图片         FP: >10%    用途: 粗粒度分类     │
    └──────────┴─────────────────────────────────────────────────────────────┘
    注: 命中样本对照详见 django_images.models.PHASH_THRESHOLD_SAMPLES 常量
    """
    enable_exact_match = serializers.BooleanField(
        default=True,
        help_text="MD5 精确匹配（exact match）- 完全相同的图片，命中后阻止导入（精确去重）"
    )
    enable_phash_match = serializers.BooleanField(
        default=True,
        help_text="感知哈希匹配（pHash / perceptual）- 检测相似/变体图片，命中后仅警告（相似提醒）"
    )
    phash_threshold = serializers.IntegerField(
        default=5,
        min_value=0,
        max_value=32,
        help_text=(
            "pHash 汉明距离阈值（建议值）："
            "0=完全相同，2=极相似(FP<0.01%)，"
            "5=平衡推荐(默认, FP≈0.1%)，7=宽松(FP≈2-3%)，10+=粗分类"
        )
    )


class BatchBoardPolicySerializer(serializers.Serializer):
    """
    多 Board 归属策略

    【优先级 + Tiebreaker 判定规则（严格按顺序处理）】
    ┌─ 1. 优先级来源（由高到低）
    │   ├─ 用户显式指定的 board_ids（按传入顺序，index 越小优先级越高）
    │   └─ 配置的 default_board_ids（按传入顺序，优先级低于用户显式指定）
    │
    ├─ 2. Tiebreaker 决胜规则（相同优先级场景）
    │   ├─ (a) board_ids 内重复（如 [1, 2, 1]）
    │   │     → 保留首次出现的位置，丢弃后续重复（不影响其他项顺序）
    │   │     → 例: [1, 2, 1] → [1, 2]（1 仍为最高优先级）
    │   ├─ (b) 用户 board_ids ∩ default_board_ids 有交集
    │   │     → 以用户 board_ids 中的位置为准，default 中重复项不再追加
    │   │     → 例: user=[3, 1], default=[1, 2] → 合并后 [3, 1, 2]
    │   └─ (c) 用户 board_ids 为空且启用默认 → 使用 default_board_ids 的原顺序
    │
    └─ 3. 裁剪规则（仍按优先级保留高者）
        ├─ allow_multiple_boards=False → 仅保留 [0]（最高优先级 1 个）
        ├─ max_boards_per_pin=N      → 仅保留 [0:N]（最高优先级 N 个）
        └─ 无效 board 过滤后         → 同优先级下用下一个有效 board 依次补位
    """
    allow_multiple_boards = serializers.BooleanField(
        default=True,
        help_text="是否允许多画板归属：True=一个 Pin 分到多个画板，False=只保留优先级最高的一个"
    )
    dedupe_board_ids = serializers.BooleanField(
        default=True,
        help_text="是否自动去除重复的 board_id（按 tiebreaker 规则，保留首次出现即优先级最高的）"
    )
    default_board_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        help_text="默认画板 ID 列表（优先级低于用户显式 board_ids，按列表顺序决定内部优先级）"
    )
    max_boards_per_pin = serializers.IntegerField(
        default=0,
        min_value=0,
        help_text="单 Pin 最大归属画板数：0=不限制，>0 时按优先级仅保留最高的前 N 个"
    )


class BatchUrlPolicySerializer(serializers.Serializer):
    """
    URL 有效性检测策略

    两阶段检测：
    - 预检期：完整检测（HEAD + GET），向用户展示详细结果
    - 导入期：快速检测（仅 HEAD），防止预检后资源又被删除

    skipped 原因分类：
    - url_became_404    ：导入时二次检测发现 404（预检通过后失效）
    - duplicate_fingerprint：导入时二次校验发现 MD5 与已有/批次内重复
    - (更多可扩展)
    """
    check_404_on_precheck = serializers.BooleanField(
        default=True,
        help_text="预检期 404 检测：HEAD 请求 + 完整下载，生成详细预检报告"
    )
    check_404_on_import = serializers.BooleanField(
        default=True,
        help_text="导入期快速二次校验：仅 HEAD 请求，防止预检后链路失效导致 404"
    )
    timeout = serializers.IntegerField(
        default=10,
        min_value=1,
        max_value=60,
        help_text="网络请求超时时间（秒）"
    )


class BatchPinItemSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2048, required=False, allow_blank=True, allow_null=True)
    referer = serializers.CharField(max_length=2048, required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list
    )
    private = serializers.BooleanField(required=False, default=False)
    board_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list
    )

    def validate_board_ids(self, value):
        seen = set()
        duplicates = []
        for bid in value:
            if bid in seen:
                duplicates.append(bid)
            seen.add(bid)
        if duplicates:
            self.context['duplicate_boards'] = duplicates
        return list(seen)


class BatchPrecheckRequestSerializer(serializers.Serializer):
    pins = BatchPinItemSerializer(many=True, required=True)
    fingerprint_policy = BatchFingerprintPolicySerializer(required=False, default=dict)
    board_policy = BatchBoardPolicySerializer(required=False, default=dict)
    url_policy = BatchUrlPolicySerializer(required=False, default=dict)


class BatchImportRequestSerializer(serializers.Serializer):
    pins = BatchPinItemSerializer(many=True, required=True)
    fingerprint_policy = BatchFingerprintPolicySerializer(required=False, default=dict)
    board_policy = BatchBoardPolicySerializer(required=False, default=dict)
    url_policy = BatchUrlPolicySerializer(required=False, default=dict)
    skip_prechecked_valid = serializers.BooleanField(default=False, help_text="Skip revalidation if precheck already passed")
