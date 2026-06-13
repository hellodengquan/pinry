from django.conf import settings
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from taggit.models import Tag

from core.media_preview import MediaPreviewService
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
            "media_type",
            "metadata",
            "description",
            "referer",
            "image",
            "image_by_id",
            "tags",
        )

    submitter = UserSerializer(read_only=True)
    media_type = serializers.SerializerMethodField(read_only=True)
    metadata = serializers.SerializerMethodField(read_only=True)
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

    def get_media_type(self, obj):
        return MediaPreviewService.detect_media_type(obj.url)

    def get_metadata(self, obj):
        return getattr(obj, '_media_preview_metadata', {})

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        cached_metadata = getattr(instance, '_media_preview_metadata', None)
        if cached_metadata is not None:
            ret['metadata'] = cached_metadata
        return ret

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
            referer = validated_data.get('referer', url)
            preview = MediaPreviewService.build_preview_from_url(url, referer)
            image = preview.get('image')
            if not image:
                raise ValidationError({"url": "invalid image content"})
            metadata = preview.get('metadata', {})
        else:
            image = validated_data.pop("image_by_id")
            metadata = {}
        tags = validated_data.pop('tag_list', [])
        pin = Pin.objects.create(submitter=submitter, image=image, **validated_data)
        if tags:
            pin.tags.set(*tags)
        pin._media_preview_metadata = metadata
        return pin

    def update(self, instance, validated_data):
        old_url = instance.url
        old_referer = instance.referer
        tags = validated_data.pop('tag_list', None)
        if tags:
            instance.tags.set(*tags)
        else:
            instance.tags.set()
        validated_data.pop('image_by_id', None)
        new_instance = super(PinSerializer, self).update(instance, validated_data)
        new_url = validated_data.get('url', old_url)
        new_referer = validated_data.get('referer', old_referer)
        if new_url != old_url or new_referer != old_referer:
            MediaPreviewService.invalidate_cache_for_url(new_url, new_referer)
            if old_url and old_url != new_url:
                MediaPreviewService.invalidate_cache_for_url(old_url, old_referer)
        return new_instance


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
