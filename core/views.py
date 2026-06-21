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
from django_images.models import calculate_md5, calculate_phash, hamming_distance


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

    @staticmethod
    def _get_headers(referer=None):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/48.0.2564.82 Safari/537.36',
        }
        if referer:
            headers['Referer'] = referer
        return headers

    def _check_url_404(self, url, referer=None, timeout=10):
        try:
            resp = requests.head(
                url,
                headers=self._get_headers(referer),
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code == 404:
                return '404'
            if resp.status_code >= 400:
                return f'error_{resp.status_code}'
            return None
        except requests.exceptions.RequestException:
            return 'unreachable'

    def _check_boards(self, board_ids, user_board_ids, board_policy):
        """
        校验并处理多 Board 归属，按优先级规则返回最终 board_ids 列表

        处理顺序（按优先级）：
          1. 若用户未传 board_ids，则使用默认 default_board_ids
          2. 按传入顺序保留优先级（靠前 = 优先级高）
          3. 去重（保留首次出现，即优先级最高的）
          4. 过滤无效 board（不存在或无权限），并用后续有效 board 补位
          5. 若禁止多 board，则只保留优先级最高的一个
          6. 若设置 max_boards_per_pin，则截断保留前 N 个

        Returns:
            (issues, warnings, processed_ids)
        """
        issues = []
        warnings = []

        input_ids = list(board_ids)
        if not input_ids:
            default_ids = board_policy.get('default_board_ids', []) or []
            if default_ids:
                input_ids = list(default_ids)
                warnings.append('used_default_board')
            else:
                warnings.append('missing_board')
                return issues, warnings, []

        seen = set()
        deduped_ids = []
        has_duplicates = False
        for bid in input_ids:
            if bid in seen:
                has_duplicates = True
            else:
                seen.add(bid)
                deduped_ids.append(bid)
        if has_duplicates:
            warnings.append('duplicate_boards')
            if not board_policy.get('dedupe_board_ids', True):
                return issues + ['duplicate_boards_not_allowed'], warnings, []

        valid_ids = []
        invalid_ids = []
        for bid in deduped_ids:
            if bid in user_board_ids:
                valid_ids.append(bid)
            else:
                invalid_ids.append(bid)
        if invalid_ids:
            warnings.append('invalid_board_skipped')

        if not board_policy.get('allow_multiple_boards', True) and len(valid_ids) > 1:
            warnings.append('multiple_boards_trimmed')
            valid_ids = valid_ids[:1]

        max_boards = board_policy.get('max_boards_per_pin', 0)
        if max_boards and max_boards > 0 and len(valid_ids) > max_boards:
            warnings.append('max_boards_exceeded')
            valid_ids = valid_ids[:max_boards]

        if not valid_ids and (deduped_ids or board_policy.get('default_board_ids')):
            warnings.append('no_valid_board_left')
            warnings.append('missing_board')

        return issues, warnings, valid_ids

    def _check_fingerprints(self, img_content, url, user, md5_seen, phash_seen,
                           fp_policy):
        issues = []
        warnings = []
        hashes = {'md5': None, 'phash': None}

        from io import BytesIO
        img_buf = BytesIO(img_content)

        if fp_policy.get('enable_exact_match', True):
            md5 = calculate_md5(img_buf)
            hashes['md5'] = md5
            if md5 in md5_seen:
                issues.append('duplicate_fingerprint')
            elif Image.objects.filter(hash=md5, pin__submitter=user).exists():
                issues.append('duplicate_fingerprint')
            md5_seen.add(md5)

        if fp_policy.get('enable_phash_match', True):
            phash = calculate_phash(img_buf)
            hashes['phash'] = phash
            if phash:
                threshold = fp_policy.get('phash_threshold', 5)
                for existing_phash in phash_seen:
                    if hamming_distance(phash, existing_phash) <= threshold:
                        warnings.append('similar_in_batch')
                        break
                for existing_img in Image.objects.filter(
                    phash__isnull=False,
                    pin__submitter=user
                ):
                    if hamming_distance(phash, existing_img.phash) <= threshold:
                        warnings.append('similar_fingerprint')
                        break
                phash_seen.add(phash)

        return issues, warnings, hashes

    @action(detail=False, methods=['post'], url_path='batch-precheck')
    def batch_precheck(self, request):
        serializer = api.BatchPrecheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pins_data = serializer.validated_data['pins']
        fp_policy = serializer.validated_data.get('fingerprint_policy', {})
        board_policy = serializer.validated_data.get('board_policy', {})
        url_policy = serializer.validated_data.get('url_policy', {})

        user = request.user
        user_boards = Board.objects.filter(submitter=user)
        user_board_ids = set(user_boards.values_list('id', flat=True))

        results = []
        md5_hashes_seen = set()
        phash_hashes_seen = set()

        check_404 = url_policy.get('check_404_on_precheck', True)
        timeout = url_policy.get('timeout', 10)

        for idx, pin_data in enumerate(pins_data):
            item_result = {
                'index': idx,
                'url': pin_data.get('url'),
                'description': pin_data.get('description'),
                'issues': [],
                'warnings': [],
                'can_import': True,
                'image_hashes': {},
                'board_ids': [],
            }

            if not pin_data.get('url'):
                item_result['issues'].append('missing_url')
                item_result['can_import'] = False

            board_ids = pin_data.get('board_ids', [])
            board_issues, board_warnings, processed_board_ids = self._check_boards(
                board_ids, user_board_ids, board_policy
            )
            item_result['issues'].extend(board_issues)
            item_result['warnings'].extend(board_warnings)
            item_result['board_ids'] = processed_board_ids
            if board_issues:
                item_result['can_import'] = False

            url = pin_data.get('url')
            if url:
                if check_404:
                    url_status = self._check_url_404(
                        url, pin_data.get('referer'), timeout
                    )
                    if url_status == '404':
                        item_result['issues'].append('url_404')
                        item_result['can_import'] = False
                    elif url_status and url_status.startswith('error_'):
                        item_result['warnings'].append(f'url_{url_status}')
                    elif url_status == 'unreachable':
                        item_result['warnings'].append('url_unreachable')

                try:
                    img_resp = requests.get(
                        url,
                        headers=self._get_headers(pin_data.get('referer')),
                        timeout=timeout + 5,
                    )
                    if img_resp.status_code == 200:
                        fp_issues, fp_warnings, hashes = self._check_fingerprints(
                            img_resp.content, url, user,
                            md5_hashes_seen, phash_hashes_seen,
                            fp_policy
                        )
                        item_result['issues'].extend(fp_issues)
                        item_result['warnings'].extend(fp_warnings)
                        item_result['image_hashes'] = hashes
                        if fp_issues:
                            item_result['can_import'] = False
                except requests.exceptions.RequestException:
                    item_result['warnings'].append('url_fetch_failed')

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
        """
        批量导入确认接口

        skipped_pins 的原因分类（三种跳过原因）：
        ---------------------------------------------------------------
        1. url_became_404
           触发时机：导入期二次校验
           条件    ：check_404_on_import=True 时，HEAD 请求返回 404
           说明    ：预检通过后，原链接被删除/失效，提前终止避免无效下载
                    （区别于 url_fetch_failed 归类在 failed_pins）

        2. duplicate_fingerprint
           触发时机：导入期下载图片后
           条件    ：enable_exact_match=True 时，MD5 与已有 Pin 或批次内重复
           说明    ：预检和导入之间可能新增了 Pin，做最终精确去重

        3. board_became_invalid
           触发时机：导入期 Board 校验
           条件    ：预检时有效的 board_id，在导入时不存在或用户无权限
           说明    ：预检后 Board 可能被删除/权限变更，拒绝导入到非法 Board
                    （本场景仅在该 Pin 的所有 Board 均失效时触发跳过；
                     若仍有有效 Board 则继续导入，仅记录 warning）
        ---------------------------------------------------------------

        返回字段:
            created: 成功创建的 Pin 列表
            failed : 出现异常或配置错误的条目（非跳过）
            skipped: 因上述三种规则主动跳过的条目
        """
        serializer = api.BatchImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pins_data = serializer.validated_data['pins']
        fp_policy = serializer.validated_data.get('fingerprint_policy', {})
        board_policy = serializer.validated_data.get('board_policy', {})
        url_policy = serializer.validated_data.get('url_policy', {})
        skip_prechecked = serializer.validated_data.get('skip_prechecked_valid', False)

        user = request.user
        user_boards = Board.objects.filter(submitter=user)
        user_board_ids = set(user_boards.values_list('id', flat=True))

        created_pins = []
        failed_pins = []
        skipped_pins = []
        md5_hashes_seen = set()
        phash_hashes_seen = set()

        quick_check_404 = url_policy.get('check_404_on_import', True)
        timeout = url_policy.get('timeout', 10)

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

                _, board_warnings, processed_board_ids = self._check_boards(
                    board_ids, user_board_ids, board_policy
                )

                if (board_ids or board_policy.get('default_board_ids')) \
                        and not processed_board_ids \
                        and 'no_valid_board_left' in board_warnings:
                    skipped_pins.append({
                        'index': idx,
                        'url': url,
                        'reason': 'board_became_invalid'
                    })
                    continue

                if quick_check_404 and not skip_prechecked:
                    url_status = self._check_url_404(url, referer, timeout)
                    if url_status == '404':
                        skipped_pins.append({
                            'index': idx,
                            'url': url,
                            'reason': 'url_became_404'
                        })
                        continue

                try:
                    img_resp = requests.get(
                        url,
                        headers=self._get_headers(referer),
                        timeout=timeout + 5,
                    )
                    if img_resp.status_code != 200:
                        failed_pins.append({
                            'index': idx,
                            'error': f'url_error_{img_resp.status_code}'
                        })
                        continue
                except requests.exceptions.RequestException as e:
                    failed_pins.append({
                        'index': idx,
                        'error': f'url_fetch_failed: {str(e)}'
                    })
                    continue

                from io import BytesIO
                img_buf = BytesIO(img_resp.content)

                if fp_policy.get('enable_exact_match', True):
                    md5 = calculate_md5(img_buf)
                    if md5 in md5_hashes_seen or Image.objects.filter(
                        hash=md5, pin__submitter=user
                    ).exists():
                        skipped_pins.append({
                            'index': idx,
                            'url': url,
                            'reason': 'duplicate_fingerprint'
                        })
                        continue
                    md5_hashes_seen.add(md5)

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

                boards_added = []
                for board_id in processed_board_ids:
                    try:
                        board = Board.objects.get(id=board_id, submitter=user)
                        if not board.pins.filter(id=pin.id).exists():
                            board.pins.add(pin)
                            boards_added.append(board_id)
                    except Board.DoesNotExist:
                        pass

                created_pins.append({
                    'index': idx,
                    'id': pin.id,
                    'url': pin.url,
                    'board_ids': boards_added,
                })
            except Exception as e:
                failed_pins.append({'index': idx, 'error': str(e)})

        return Response({
            'created': created_pins,
            'failed': failed_pins,
            'skipped': skipped_pins,
            'total_created': len(created_pins),
            'total_failed': len(failed_pins),
            'total_skipped': len(skipped_pins),
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
