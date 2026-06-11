from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.views.static import serve

from core import serializers as api
from core.models import Image, Pin, Board
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
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")


def find_image_for_path(path):
    from django_images.models import Thumbnail

    path_normalized = path.lstrip('/')

    image = None
    try:
        image = Image.objects.get(image=path_normalized)
    except Image.DoesNotExist:
        pass

    if image is None:
        try:
            thumbnail = Thumbnail.objects.get(image=path_normalized)
            image = thumbnail.original
        except Thumbnail.DoesNotExist:
            pass

    return image


def _can_access_image(user, image):
    pins = Pin.objects.filter(image=image)
    if not pins.exists():
        return False

    if pins.filter(private=False).exists():
        return True

    if not user.is_authenticated:
        return False

    return pins.filter(private=True, submitter=user).exists()


def protected_media(request, path, document_root=None, show_indexes=False):
    image = find_image_for_path(path)

    if image is None:
        raise Http404('Image not found')

    if not _can_access_image(request.user, image):
        if request.user.is_authenticated:
            return HttpResponseForbidden(
                'You do not have permission to access this content'
            )
        return HttpResponseForbidden(
            'Authentication required for private content'
        )

    if settings.DEBUG or settings.IS_TEST:
        return serve(request, path, document_root, show_indexes)

    response = HttpResponse()
    response['X-Accel-Redirect'] = '/internal-media/{}'.format(path.lstrip('/'))
    response['Content-Type'] = ''
    return response
