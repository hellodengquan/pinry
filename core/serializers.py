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


class TagNameListField(serializers.ListField):
    child = serializers.CharField(max_length=128)


class BatchTagAddSerializer(serializers.Serializer):
    pin_ids = PinIdListField(
        required=False,
        help_text="List of pin IDs to add tags to",
    )
    pin_tag_names = TagNameListField(
        required=False,
        help_text="List of tag names to select pins by",
    )
    tags = TagNameListField(
        help_text="List of tag names to add",
    )
    dry_run = serializers.BooleanField(
        default=False,
        write_only=True,
        help_text="If true, only preview the result without making changes",
    )

    def validate_tags(self, value):
        if not value:
            raise ValidationError("At least one tag is required")
        return value

    def validate_pin_ids(self, value):
        if not value:
            return value
        existing_ids = set(Pin.objects.filter(id__in=value).values_list("id", flat=True))
        invalid_ids = set(value) - existing_ids
        if invalid_ids:
            raise ValidationError("Invalid pin IDs: {}".format(sorted(invalid_ids)))
        return value

    def validate(self, attrs):
        has_pin_ids = bool(attrs.get("pin_ids"))
        has_tag_names = bool(attrs.get("pin_tag_names"))
        if not has_pin_ids and not has_tag_names:
            raise ValidationError(
                "Either pin_ids or pin_tag_names must be provided"
            )
        if has_pin_ids and has_tag_names:
            raise ValidationError(
                "pin_ids and pin_tag_names cannot be used together"
            )
        return attrs


class BatchTagRemoveSerializer(serializers.Serializer):
    pin_ids = PinIdListField(
        required=False,
        help_text="List of pin IDs to remove tags from",
    )
    pin_tag_names = TagNameListField(
        required=False,
        help_text="List of tag names to select pins by",
    )
    tags = TagNameListField(
        help_text="List of tag names to remove",
    )
    dry_run = serializers.BooleanField(
        default=False,
        write_only=True,
        help_text="If true, only preview the result without making changes",
    )

    def validate_tags(self, value):
        if not value:
            raise ValidationError("At least one tag is required")
        return value

    def validate_pin_ids(self, value):
        if not value:
            return value
        existing_ids = set(Pin.objects.filter(id__in=value).values_list("id", flat=True))
        invalid_ids = set(value) - existing_ids
        if invalid_ids:
            raise ValidationError("Invalid pin IDs: {}".format(sorted(invalid_ids)))
        return value

    def validate(self, attrs):
        has_pin_ids = bool(attrs.get("pin_ids"))
        has_tag_names = bool(attrs.get("pin_tag_names"))
        if not has_pin_ids and not has_tag_names:
            raise ValidationError(
                "Either pin_ids or pin_tag_names must be provided"
            )
        if has_pin_ids and has_tag_names:
            raise ValidationError(
                "pin_ids and pin_tag_names cannot be used together"
            )
        return attrs


class BatchTagMergeSerializer(serializers.Serializer):
    source_tags = TagNameListField(
        help_text="List of tag names to merge into the target tag",
    )
    target_tag = serializers.CharField(
        max_length=128,
        help_text="The tag name that all source tags will be merged into",
    )
    dry_run = serializers.BooleanField(
        default=False,
        write_only=True,
        help_text="If true, only preview the result without making changes",
    )

    def validate_source_tags(self, value):
        if not value:
            raise ValidationError("At least one source tag is required")
        return value

    def validate(self, attrs):
        from core.batch_tags import _normalize_tag_name
        source_tags = attrs.get("source_tags", [])
        target_tag = attrs.get("target_tag", "")
        normalized_target = _normalize_tag_name(target_tag)
        for source in source_tags:
            if _normalize_tag_name(source) == normalized_target:
                raise ValidationError(
                    "Source tag '{}' is the same as target tag '{}' (case-insensitive)".format(
                        source, target_tag
                    )
                )
        return attrs


class BatchTagPreviewSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(
        choices=["add", "remove", "merge"],
        help_text="The type of batch operation to preview",
    )
    pin_ids = PinIdListField(
        required=False,
        help_text="List of pin IDs (for add/remove operations, pin-by-id mode)",
    )
    pin_tag_names = TagNameListField(
        required=False,
        help_text="List of tag names to select pins by (for add/remove operations, tag-selection mode)",
    )
    tags = TagNameListField(
        required=False,
        help_text="List of tag names (for add/remove operations, the tags to add/remove)",
    )
    source_tags = TagNameListField(
        required=False,
        help_text="List of source tag names (for merge operation)",
    )
    target_tag = serializers.CharField(
        max_length=128,
        required=False,
        help_text="Target tag name (for merge operation)",
    )

    def validate(self, attrs):
        operation = attrs.get("operation")
        if operation in ("add", "remove"):
            has_pin_ids = bool(attrs.get("pin_ids"))
            has_tag_names = bool(attrs.get("pin_tag_names"))
            if not has_pin_ids and not has_tag_names:
                raise ValidationError(
                    "Either pin_ids or pin_tag_names is required for {} operation".format(operation)
                )
            if has_pin_ids and has_tag_names:
                raise ValidationError(
                    "pin_ids and pin_tag_names cannot be used together"
                )
            if not attrs.get("tags"):
                raise ValidationError("tags is required for {} operation".format(operation))
        elif operation == "merge":
            if not attrs.get("source_tags"):
                raise ValidationError("source_tags is required for merge operation")
            if not attrs.get("target_tag"):
                raise ValidationError("target_tag is required for merge operation")
        return attrs


class TagAutoCompleteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag
        fields = ('name', )
