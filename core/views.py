from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.models import Image, Pin, Board
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import filter_private_pin, filter_private_board
from core.services import (
    PreviewError,
    PreviewContentType,
    get_preview_manager,
)


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


class PreviewViewSet(viewsets.ViewSet):
    permission_classes = []

    def _parse_content_type(self, value):
        if not value:
            return None
        try:
            return PreviewContentType(value)
        except ValueError:
            return None

    @action(detail=False, methods=['post'], url_path='fetch')
    def fetch(self, request):
        url = request.data.get('url')
        if not url:
            return Response(
                {"url": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        referer = request.data.get('referer')
        content_type_hint = self._parse_content_type(
            request.data.get('content_type')
        )
        force_refresh = bool(request.data.get('force_refresh', False))

        preview_manager = get_preview_manager()
        try:
            result = preview_manager.preview(
                url=url,
                referer=referer,
                content_type_hint=content_type_hint,
                force_refresh=force_refresh,
            )
            return Response(result.to_dict(), status=status.HTTP_200_OK)
        except PreviewError as e:
            return Response(
                {"error": e.to_dict()},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=['post'], url_path='refresh')
    def refresh(self, request):
        url = request.data.get('url')
        if not url:
            return Response(
                {"url": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        referer = request.data.get('referer')
        content_type_hint = self._parse_content_type(
            request.data.get('content_type')
        )

        preview_manager = get_preview_manager()
        try:
            result = preview_manager.refresh(
                url=url,
                referer=referer,
                content_type_hint=content_type_hint,
            )
            return Response(result.to_dict(), status=status.HTTP_200_OK)
        except PreviewError as e:
            return Response(
                {"error": e.to_dict()},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=['post'], url_path='invalidate-cache')
    def invalidate_cache(self, request):
        url = request.data.get('url')
        if not url:
            return Response(
                {"url": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.data.get('referer')
        preview_manager = get_preview_manager()
        count = preview_manager.invalidate_cache_for_url(url, referer)
        return Response(
            {"invalidated": count},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='inspect')
    def inspect(self, request):
        url = request.data.get('url')
        if not url:
            return Response(
                {"url": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.data.get('referer')
        content_type_hint = self._parse_content_type(
            request.data.get('content_type')
        )
        preview_manager = get_preview_manager()
        info = preview_manager.inspect(
            url=url,
            referer=referer,
            content_type_hint=content_type_hint,
        )
        return Response(info, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='types')
    def types(self, request):
        supported = [
            {"type": t.value, "name": t.name}
            for t in PreviewContentType
        ]
        return Response({"supported": supported}, status=status.HTTP_200_OK)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-auto-complete")
drf_router.register(r'preview', PreviewViewSet, basename="preview")
