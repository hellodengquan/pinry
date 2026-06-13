from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.models import Image, Pin, Board
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import filter_private_pin, filter_private_board


class ArchivedBoardCursorPagination(CursorPagination):
    ordering = ('-archived_at', '-id')
    page_size = 50
    cursor_query_param = 'cursor'


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
        if self.action == 'list':
            return filter_private_board(self.request, Board.objects.all())
        return filter_private_board(self.request, Board.objects.all(), include_archived=True)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrReadOnly("submitter")])
    def archive(self, request, pk=None):
        board = self.get_object()
        board.is_archived = True
        board.archived_at = timezone.now()
        board.save()
        serializer = self.get_serializer(board)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrReadOnly("submitter")])
    def unarchive(self, request, pk=None):
        board = self.get_object()
        board.is_archived = False
        board.archived_at = None
        board.save()
        serializer = self.get_serializer(board)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='bulk-archive', url_name='bulk-archive')
    def bulk_archive(self, request):
        return self._bulk_toggle_archive(request, archive=True)

    @action(detail=False, methods=['post'], url_path='bulk-unarchive', url_name='bulk-unarchive')
    def bulk_unarchive(self, request):
        return self._bulk_toggle_archive(request, archive=False)

    def _bulk_toggle_archive(self, request, archive=True):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required"},
                status=401,
            )
        raw_ids = request.data.get("board_ids", []) if isinstance(request.data, dict) else []
        max_size = api.BoardBulkArchiveSerializer.MAX_BULK_SIZE
        if isinstance(raw_ids, list) and len(raw_ids) > max_size:
            return Response(
                {
                    "detail": f"Too many boards requested. Maximum allowed is {max_size}",
                    "max_size": max_size,
                    "requested": len(raw_ids),
                },
                status=413,
            )
        serializer = api.BoardBulkArchiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        board_ids = serializer.validated_data['board_ids']
        now = timezone.now()
        queryset = Board.objects.filter(id__in=board_ids, submitter=request.user)
        if archive:
            updated = queryset.filter(is_archived=False).update(is_archived=True, archived_at=now)
        else:
            updated = queryset.filter(is_archived=True).update(is_archived=False, archived_at=None)
        changed_ids = list(queryset.values_list('id', flat=True))
        return Response({
            "updated_count": updated,
            "board_ids": changed_ids,
        })


class ArchivedBoardViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = api.BoardSerializer
    pagination_class = ArchivedBoardCursorPagination
    filter_backends = (DjangoFilterBackend, SearchFilter)
    search_fields = ("name", )
    filter_fields = ("submitter__username", )
    permission_classes = [IsOwnerOrReadOnly("submitter"), OwnerOnlyIfPrivate("submitter")]

    def get_queryset(self):
        return filter_private_board(self.request, Board.objects.filter(is_archived=True), include_archived=True)


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


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'archived-boards', ArchivedBoardViewSet, basename="archived-board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-auto-complete")
