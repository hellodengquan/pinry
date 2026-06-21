import hashlib
import requests

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

    @action(detail=False, methods=['post'], url_path='batch-precheck')
    def batch_precheck(self, request):
        serializer = api.BatchPrecheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pins_data = serializer.validated_data['pins']

        user = request.user
        user_boards = Board.objects.filter(submitter=user)
        user_board_ids = set(user_boards.values_list('id', flat=True))

        results = []
        url_hashes_seen = set()

        for idx, pin_data in enumerate(pins_data):
            item_result = {
                'index': idx,
                'url': pin_data.get('url'),
                'description': pin_data.get('description'),
                'issues': [],
                'warnings': [],
                'can_import': True,
            }

            if not pin_data.get('url'):
                item_result['issues'].append('missing_url')
                item_result['can_import'] = False

            board_ids = pin_data.get('board_ids', [])
            if not board_ids:
                item_result['warnings'].append('missing_board')
            else:
                invalid_boards = [bid for bid in board_ids if bid not in user_board_ids]
                if invalid_boards:
                    item_result['issues'].append('invalid_board')
                    item_result['can_import'] = False

            if pin_data.get('url'):
                url = pin_data['url']
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                                      'Chrome/48.0.2564.82 Safari/537.36',
                    }
                    referer = pin_data.get('referer')
                    if referer:
                        headers['Referer'] = referer
                    resp = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
                    if resp.status_code == 404:
                        item_result['issues'].append('url_404')
                        item_result['can_import'] = False
                    elif resp.status_code >= 400:
                        item_result['warnings'].append(f'url_error_{resp.status_code}')
                except requests.exceptions.RequestException:
                    item_result['warnings'].append('url_unreachable')

                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                                      'Chrome/48.0.2564.82 Safari/537.36',
                    }
                    referer = pin_data.get('referer')
                    if referer:
                        headers['Referer'] = referer
                    img_resp = requests.get(url, headers=headers, timeout=15)
                    if img_resp.status_code == 200:
                        hasher = hashlib.md5()
                        hasher.update(img_resp.content)
                        img_hash = hasher.hexdigest()

                        if Image.objects.filter(hash=img_hash, pin__submitter=user).exists():
                            item_result['warnings'].append('duplicate_fingerprint')
                        if img_hash in url_hashes_seen:
                            item_result['warnings'].append('duplicate_in_batch')
                        url_hashes_seen.add(img_hash)
                        item_result['image_hash'] = img_hash
                except requests.exceptions.RequestException:
                    pass

            results.append(item_result)

        summary = {
            'total': len(results),
            'can_import': sum(1 for r in results if r['can_import']),
            'has_issues': sum(1 for r in results if r['issues']),
            'has_warnings': sum(1 for r in results if r['warnings']),
        }

        return Response({'results': results, 'summary': summary})

    @action(detail=False, methods=['post'], url_path='batch-import')
    def batch_import(self, request):
        serializer = api.BatchImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pins_data = serializer.validated_data['pins']

        user = request.user
        created_pins = []
        failed_pins = []

        for idx, pin_data in enumerate(pins_data):
            try:
                url = pin_data.get('url')
                referer = pin_data.get('referer') or url
                description = pin_data.get('description', '')
                tags = pin_data.get('tags', [])
                private = pin_data.get('private', False)
                board_ids = pin_data.get('board_ids', [])

                if not url:
                    failed_pins.append({'index': idx, 'error': 'missing_url'})
                    continue

                image = Image.objects.create_for_url(url, referer)
                if not image:
                    failed_pins.append({'index': idx, 'error': 'invalid_image'})
                    continue

                pin = Pin.objects.create(
                    submitter=user,
                    url=url,
                    referer=pin_data.get('referer'),
                    description=description,
                    private=private,
                    image=image,
                )
                if tags:
                    tag_objs = []
                    for tag_name in tags:
                        tag_obj, _ = Tag.objects.get_or_create(
                            defaults={'name': tag_name, 'slug': tag_name},
                            name=tag_name
                        )
                        tag_objs.append(tag_obj)
                    pin.tags.set(*tag_objs)

                for board_id in board_ids:
                    try:
                        board = Board.objects.get(id=board_id, submitter=user)
                        board.pins.add(pin)
                    except Board.DoesNotExist:
                        pass

                created_pins.append({
                    'index': idx,
                    'id': pin.id,
                    'url': pin.url,
                })
            except Exception as e:
                failed_pins.append({'index': idx, 'error': str(e)})

        return Response({
            'created': created_pins,
            'failed': failed_pins,
            'total_created': len(created_pins),
            'total_failed': len(failed_pins),
        }, status=status.HTTP_201_CREATED if created_pins else status.HTTP_400_BAD_REQUEST)


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
