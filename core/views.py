from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import BasePermission
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.models import Image, Pin, Board, BoardCollaborator
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import filter_private_pin, filter_private_board


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
        return filter_private_board(
            self.request,
            Board.objects.all().prefetch_related('collaborators'),
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
    permission_classes = [OwnerOnlyIfPrivate("submitter"), ]

    def get_queryset(self):
        return filter_private_board(
            self.request,
            Board.objects.all().prefetch_related('collaborators'),
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


class BoardCollaboratorPermission(BasePermission):
    def has_permission(self, request, view):
        board_id = view.kwargs.get('board_pk')
        if not board_id:
            return False
        try:
            board = Board.objects.get(id=board_id)
        except Board.DoesNotExist:
            return False
        if request.method in ('POST',):
            return request.user == board.submitter
        return True

    def has_object_permission(self, request, view, obj):
        board = obj.board
        if request.user == board.submitter:
            return True
        if request.method in ('PATCH', 'PUT'):
            return obj.user == request.user
        return True


class BoardCollaboratorViewSet(viewsets.ModelViewSet):
    serializer_class = api.BoardCollaboratorSerializer
    permission_classes = [BoardCollaboratorPermission]

    def get_queryset(self):
        board_id = self.kwargs.get('board_pk')
        return BoardCollaborator.objects.filter(board_id=board_id)

    def get_serializer_context(self):
        context = super(BoardCollaboratorViewSet, self).get_serializer_context()
        board_id = self.kwargs.get('board_pk')
        if board_id:
            try:
                context['board'] = Board.objects.get(id=board_id)
            except Board.DoesNotExist:
                pass
        return context

    def perform_create(self, serializer):
        board_id = self.kwargs.get('board_pk')
        board = Board.objects.get(id=board_id)
        serializer.save(board=board)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
drf_router.register(
    r'boards/(?P<board_pk>\d+)/collaborators',
    BoardCollaboratorViewSet,
    basename="board-collaborator",
)
