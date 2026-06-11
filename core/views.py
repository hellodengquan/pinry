from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.models import Image, Pin, Board, BoardShareToken
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
        return filter_private_board(self.request, Board.objects.all())

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[IsAuthenticated],
        url_path='share-tokens',
    )
    def list_share_tokens(self, request, pk=None):
        board = self.get_object()
        if board.submitter != request.user:
            raise PermissionDenied("You don't have permission to manage share tokens for this board.")
        tokens = board.share_tokens.all()
        serializer = api.BoardShareTokenSerializer(tokens, many=True, context={'request': request})
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated],
        url_path='share-tokens/create',
    )
    def create_share_token(self, request, pk=None):
        board = self.get_object()
        if board.submitter != request.user:
            raise PermissionDenied("You don't have permission to create share tokens for this board.")
        serializer = api.BoardShareTokenCreateSerializer(
            data=request.data,
            context={'request': request, 'board': board},
        )
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(
            api.BoardShareTokenSerializer(token, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated],
        url_path='share-tokens/(?P<token_id>[^/.]+)/revoke',
    )
    def revoke_share_token(self, request, pk=None, token_id=None):
        board = self.get_object()
        if board.submitter != request.user:
            raise PermissionDenied("You don't have permission to manage share tokens for this board.")
        try:
            token = board.share_tokens.get(id=token_id)
        except BoardShareToken.DoesNotExist:
            raise NotFound("Share token not found.")
        if token.is_revoked:
            raise ValidationError("This token has already been revoked.")
        token.revoke()
        return Response(
            api.BoardShareTokenSerializer(token, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated],
        url_path='share-tokens/(?P<token_id>[^/.]+)/regenerate',
    )
    def regenerate_share_token(self, request, pk=None, token_id=None):
        board = self.get_object()
        if board.submitter != request.user:
            raise PermissionDenied("You don't have permission to manage share tokens for this board.")
        try:
            token = board.share_tokens.get(id=token_id)
        except BoardShareToken.DoesNotExist:
            raise NotFound("Share token not found.")
        serializer = api.BoardShareTokenRegenerateSerializer(
            token,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(
            api.BoardShareTokenSerializer(token, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class BoardShareViewSet(
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    permission_classes = [AllowAny]
    lookup_field = 'token'
    lookup_url_kwarg = 'token'

    def get_queryset(self):
        return BoardShareToken.objects.filter(is_revoked=False)

    def retrieve(self, request, *args, **kwargs):
        token_str = kwargs.get('token')
        try:
            share_token = BoardShareToken.objects.select_related('board', 'board__submitter').get(
                token=token_str,
            )
        except BoardShareToken.DoesNotExist:
            raise NotFound("Share link is invalid or has been revoked.")

        if not share_token.is_valid:
            if share_token.is_revoked:
                raise NotFound("Share link has been revoked.")
            else:
                raise NotFound("Share link has expired.")

        share_token.record_access()
        board = share_token.board

        offset = int(request.query_params.get('offset', 0))
        limit = min(int(request.query_params.get('limit', 30)), 100)

        pins_query = board.pins.filter(private=False).select_related('image')
        total_pins = pins_query.count()
        pins = pins_query[offset:offset + limit]

        board_data = api.AnonymousBoardSerializer(board, context={'request': request}).data
        pins_data = api.AnonymousPinSerializer(pins, many=True, context={'request': request}).data

        has_next = (offset + limit) < total_pins
        next_url = None
        if has_next:
            next_offset = offset + limit
            next_url = request.build_absolute_uri(
                f'{request.path}?offset={next_offset}&limit={limit}'
            )

        return Response({
            'board': board_data,
            'pins': {
                'count': total_pins,
                'next': next_url,
                'results': pins_data,
            },
            'share_info': {
                'created_at': share_token.created_at,
                'expires_at': share_token.expires_at,
                'access_count': share_token.access_count,
            },
        })

    @action(
        detail=True,
        methods=['get'],
        url_path='pins',
    )
    def list_pins(self, request, *args, **kwargs):
        token_str = kwargs.get('token')
        try:
            share_token = BoardShareToken.objects.select_related('board').get(token=token_str)
        except BoardShareToken.DoesNotExist:
            raise NotFound("Share link is invalid or has been revoked.")

        if not share_token.is_valid:
            if share_token.is_revoked:
                raise NotFound("Share link has been revoked.")
            else:
                raise NotFound("Share link has expired.")

        board = share_token.board

        offset = int(request.query_params.get('offset', 0))
        limit = min(int(request.query_params.get('limit', 30)), 100)
        ordering = request.query_params.get('ordering', '-id')

        pins_query = board.pins.filter(private=False).select_related('image').order_by(ordering)
        total_pins = pins_query.count()
        pins = pins_query[offset:offset + limit]

        pins_data = api.AnonymousPinSerializer(pins, many=True, context={'request': request}).data

        has_next = (offset + limit) < total_pins
        next_url = None
        if has_next:
            next_offset = offset + limit
            next_url = request.build_absolute_uri(
                f'{request.path}?offset={next_offset}&limit={limit}&ordering={ordering}'
            )

        return Response({
            'count': total_pins,
            'next': next_url,
            'results': pins_data,
        })


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
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-autocomplete")
drf_router.register(r'board-share', BoardShareViewSet, basename="board-share")
