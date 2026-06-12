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
from core.serializers import filter_private_pin, filter_private_board, PinSerializer


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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        try:
            image = serializer.get_image_for_creation(validated_data)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        duplicates = serializer.find_duplicates(serializer.validated_data, image=image)
        duplicates = filter_private_pin(request, duplicates)
        if duplicates.exists() and not request.data.get('force_create', False):
            duplicate_serializer = PinSerializer(
                duplicates,
                many=True,
                context={'request': request}
            )
            return Response(
                {
                    "duplicates_found": True,
                    "duplicates": duplicate_serializer.data,
                    "message": "Duplicate pins found. You can merge or force create."
                },
                status=status.HTTP_409_CONFLICT
            )
        submitter = request.user
        tags = validated_data.pop('tag_list', [])
        validated_data.pop('image_by_id', None)
        pin = Pin.objects.create(
            submitter=submitter,
            image=image,
            **validated_data
        )
        if tags:
            pin.tags.set(*tags)
        result_serializer = self.get_serializer(
            pin,
            context={'request': request}
        )
        headers = self.get_success_headers(result_serializer.data)
        return Response(
            result_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    @action(detail=False, methods=['post'], serializer_class=api.PinMergeSerializer)
    def merge(self, request):
        serializer = api.PinMergeSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        merged_pin = serializer.save()
        result_serializer = api.PinSerializer(
            merged_pin,
            context={'request': request}
        )
        return Response(
            {
                "merged": True,
                "target_pin": result_serializer.data,
                "message": "Pins merged successfully. Tags and boards are preserved."
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def check_duplicates(self, request):
        url = request.query_params.get('url')
        image_by_id = request.query_params.get('image_by_id')
        if not url and not image_by_id:
            return Response(
                {"detail": "Either url or image_by_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        image_hash = None
        if image_by_id:
            try:
                image = Image.objects.get(id=image_by_id)
                image_hash = image.image_hash
            except Image.DoesNotExist:
                return Response(
                    {"detail": "Image not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        duplicates = Pin.find_duplicates(
            url=url,
            image_hash=image_hash,
            submitter=request.user if request.user.is_authenticated else None,
        )
        duplicates = filter_private_pin(request, duplicates)
        serializer = self.get_serializer(
            duplicates,
            many=True,
            context={'request': request}
        )
        return Response({
            "duplicates_found": duplicates.exists(),
            "count": duplicates.count(),
            "duplicates": serializer.data,
        })


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


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-auto-complete")
