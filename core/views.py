from django.core.cache import cache
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag, TaggedItem

from core import serializers as api
from core.models import Image, Pin, Board
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import filter_private_pin, filter_private_board

TAGS_CACHE_TIMEOUT = 60 * 5
TAGS_CACHE_KEY_PREFIX = 'tags_auto_complete_list'


def _invalidate_tags_cache():
    cache.delete_pattern(f'*{TAGS_CACHE_KEY_PREFIX}*')


class ImageViewSet(mixins.CreateModelMixin, GenericViewSet):
    queryset = Image.objects.all()
    serializer_class = api.ImageSerializer

    def create(self, request, *args, **kwargs):
        return super(ImageViewSet, self).create(request, *args, **kwargs)


class PinViewSet(viewsets.ModelViewSet):
    serializer_class = api.PinSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filter_fields = ("submitter__username", 'tags__name', "pins__id")
    ordering_fields = ('-id', )
    ordering = ('-id', )
    permission_classes = [IsOwnerOrReadOnly("submitter"), OwnerOnlyIfPrivate("submitter")]

    def get_queryset(self):
        query = Pin.objects.all()
        request = self.request
        return filter_private_pin(request, query)


class BoardViewSet(viewsets.ModelViewSet):
    serializer_class = api.BoardSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    search_fields = ("name", )
    filter_fields = ("submitter__username", )
    ordering_fields = ('-id', )
    ordering = ('-id', )
    permission_classes = [IsOwnerOrReadOnly("submitter"), OwnerOnlyIfPrivate("submitter")]

    def get_queryset(self):
        return filter_private_board(self.request, Board.objects.all())


class BoardAutoCompleteViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = api.BoardAutoCompleteSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_fields = ("submitter__username", )
    ordering_fields = ('-id', )
    ordering = ('-id', )
    pagination_class = None
    permission_classes = [OwnerOnlyIfPrivate("submitter"), ]

    def get_queryset(self):
        return filter_private_board(self.request, Board.objects.all())


class TagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Tag.objects.all()
    serializer_class = api.TagAutoCompleteSerializer
    pagination_class = None
    filter_backends = (SearchFilter,)
    search_fields = ('name',)

    @method_decorator(cache_page(TAGS_CACHE_TIMEOUT, key_prefix=TAGS_CACHE_KEY_PREFIX))
    def list(self, request, *args, **kwargs):
        return super(TagViewSet, self).list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        response = super(TagViewSet, self).create(request, *args, **kwargs)
        _invalidate_tags_cache()
        return response

    def update(self, request, *args, **kwargs):
        response = super(TagViewSet, self).update(request, *args, **kwargs)
        _invalidate_tags_cache()
        return response

    def destroy(self, request, *args, **kwargs):
        response = super(TagViewSet, self).destroy(request, *args, **kwargs)
        _invalidate_tags_cache()
        return response

    @action(detail=False, methods=['post'], url_path='merge')
    def merge_tags(self, request):
        source_tag_name = request.data.get('source_tag')
        target_tag_name = request.data.get('target_tag')

        if not source_tag_name or not target_tag_name:
            return Response(
                {'error': 'source_tag and target_tag are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source_tag_name == target_tag_name:
            return Response(
                {'error': 'source_tag and target_tag must be different'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                source_tag = Tag.objects.select_for_update().get(name=source_tag_name)
            except Tag.DoesNotExist:
                return Response(
                    {'error': f'Source tag "{source_tag_name}" does not exist'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                target_tag = Tag.objects.select_for_update().get(name=target_tag_name)
            except Tag.DoesNotExist:
                source_tag.name = target_tag_name
                source_tag.slug = target_tag_name
                source_tag.save()
                _invalidate_tags_cache()
                return Response(
                    {
                        'success': True,
                        'message': f'Tag renamed from "{source_tag_name}" to "{target_tag_name}"',
                        'merged_into': target_tag_name,
                        'tag_map': {source_tag_name: target_tag_name},
                    },
                    status=status.HTTP_200_OK,
                )

            source_tagged_items = TaggedItem.objects.select_for_update().filter(tag=source_tag)
            migrated_count = 0
            for tagged_item in source_tagged_items:
                existing = TaggedItem.objects.filter(
                    tag=target_tag,
                    content_type=tagged_item.content_type,
                    object_id=tagged_item.object_id,
                ).first()
                if existing is None:
                    tagged_item.tag = target_tag
                    tagged_item.save()
                    migrated_count += 1
                else:
                    tagged_item.delete()

            source_tag.delete()
            _invalidate_tags_cache()

        return Response(
            {
                'success': True,
                'message': f'Merged tag "{source_tag_name}" into "{target_tag_name}"',
                'merged_into': target_tag_name,
                'migrated_count': migrated_count,
                'tag_map': {source_tag_name: target_tag_name},
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path='verify')
    def verify_tags(self, request):
        tag_names = request.query_params.getlist('tag_names')
        result = {
            'valid_tags': [],
            'invalid_tags': [],
        }

        for tag_name in tag_names:
            if Tag.objects.filter(name=tag_name).exists():
                result['valid_tags'].append(tag_name)
            else:
                result['invalid_tags'].append(tag_name)

        return Response(result, status=status.HTTP_200_OK)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags', TagViewSet, basename="tag")
drf_router.register(r'tags-auto-complete', TagViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
