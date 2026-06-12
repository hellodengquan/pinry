from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.models import Image, Pin, Board
from core.permissions import (
    IsOwnerOrReadOnly,
    VisibilityBasedPermission,
)
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy


class ImageViewSet(mixins.CreateModelMixin, GenericViewSet):
    queryset = Image.objects.all()
    serializer_class = api.ImageSerializer

    def create(self, request, *args, **kwargs):
        return super(ImageViewSet, self).create(request, *args, **kwargs)


class PinViewSet(viewsets.ModelViewSet):
    """
    Pin 视图集。

    职责拆分：
    - queryset 过滤（字段截取/可见性）：PinVisibilityPolicy
    - 对象级权限：IsOwnerOrReadOnly（编辑权限） + VisibilityBasedPermission（查看权限）
    - 序列化/反序列化：PinSerializer
    """
    serializer_class = api.PinSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filter_fields = ("submitter__username", 'tags__name', "pins__id")
    ordering_fields = ('-id', )
    ordering = ('-id', )
    permission_classes = [
        IsOwnerOrReadOnly("submitter"),
        VisibilityBasedPermission(PinVisibilityPolicy),
    ]

    def get_queryset(self):
        return PinVisibilityPolicy.filter_queryset(
            Pin.objects.all(), self.request.user
        )


class BoardViewSet(viewsets.ModelViewSet):
    """
    Board 视图集。

    职责拆分：
    - queryset 过滤（字段截取/可见性）：BoardVisibilityPolicy
    - 对象级权限：IsOwnerOrReadOnly（编辑权限） + VisibilityBasedPermission（查看权限）
    - 序列化/反序列化：BoardSerializer
    """
    serializer_class = api.BoardSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    search_fields = ("name", )
    filter_fields = ("submitter__username", )
    ordering_fields = ('-id', )
    ordering = ('-id', )
    permission_classes = [
        IsOwnerOrReadOnly("submitter"),
        VisibilityBasedPermission(BoardVisibilityPolicy),
    ]

    def get_queryset(self):
        return BoardVisibilityPolicy.filter_queryset(
            Board.objects.all(), self.request.user
        )


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
    permission_classes = [
        VisibilityBasedPermission(BoardVisibilityPolicy),
    ]

    def get_queryset(self):
        return BoardVisibilityPolicy.filter_queryset(
            Board.objects.all(), self.request.user
        )


class TagAutoCompleteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    serializer_class = api.TagAutoCompleteSerializer
    pagination_class = None

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        return super(TagAutoCompleteViewSet, self).list(
            request,
            *args,
            **kwargs
        )


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
