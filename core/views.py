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
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate, SuperUserOnly
from core.serializers import filter_private_pin, filter_private_board
from core.models import MediaCheckAuditLog
from core.utils import (
    run_media_check,
    delete_orphan_files,
    fix_missing_files,
    save_report,
    MediaCheckRenderer,
    get_max_depth,
    get_exclude_dirs,
    get_audit_log_retention_days,
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


class MediaCheckViewSet(viewsets.GenericViewSet):
    permission_classes = [SuperUserOnly]
    serializer_class = api.MediaCheckSerializer

    def _get_scan_params(self, data):
        max_depth = data.get('max_depth')
        if max_depth is None:
            max_depth = get_max_depth()
        exclude_dirs = data.get('exclude_dirs')
        if exclude_dirs is not None:
            exclude_dirs = set(exclude_dirs)
        return max_depth, exclude_dirs

    def _save_report_if_needed(self, result, output_path):
        if output_path:
            saved_path = save_report(result, output_path)
            result['output_path'] = saved_path
        return result

    def _create_audit_log(self, report, action, user, orphan_result=None, missing_result=None):
        try:
            renderer = MediaCheckRenderer(
                report=report,
                orphan_result=orphan_result,
                missing_result=missing_result,
            )
            full_report = renderer.to_dict()
            return MediaCheckAuditLog.create_from_report(
                report=full_report,
                action=action,
                user=user,
                success=True,
            )
        except Exception:
            return None

    @action(detail=False, methods=['get'])
    def report(self, request):
        query_serializer = api.MediaCheckReportQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        max_depth, exclude_dirs = self._get_scan_params(params)
        output_path = params.get('output')

        result = run_media_check(max_depth=max_depth, exclude_dirs=exclude_dirs)
        result = self._save_report_if_needed(result, output_path)

        self._create_audit_log(
            report=result,
            action=MediaCheckAuditLog.ACTION_CHECK,
            user=request.user,
        )

        serializer = api.MediaCheckSerializer(result)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def fix(self, request):
        serializer = api.MediaCheckFixSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        action_param = data['action']
        max_depth, exclude_dirs = self._get_scan_params(data)
        output_path = data.get('output')

        results = {}
        orphan_result = None
        missing_result = None

        if action_param in ['delete_orphans', 'all']:
            orphan_result = delete_orphan_files(
                max_depth=max_depth,
                exclude_dirs=exclude_dirs,
            )
            results['delete_orphans'] = api.DeleteOrphanResultSerializer(orphan_result).data

        if action_param in ['fix_missing', 'all']:
            missing_result = fix_missing_files(
                max_depth=max_depth,
                exclude_dirs=exclude_dirs,
            )
            results['fix_missing'] = api.FixMissingResultSerializer(missing_result).data

        check_result = run_media_check(
            max_depth=max_depth,
            exclude_dirs=exclude_dirs,
        )
        check_result = self._save_report_if_needed(check_result, output_path)
        results['report'] = api.MediaCheckSerializer(check_result).data

        audit_action = action_param if action_param != 'all' else MediaCheckAuditLog.ACTION_ALL
        self._create_audit_log(
            report=check_result,
            action=audit_action,
            user=request.user,
            orphan_result=orphan_result,
            missing_result=missing_result,
        )

        return Response(results, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def audit_logs(self, request):
        logs = MediaCheckAuditLog.objects.all()
        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = api.MediaCheckAuditLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = api.MediaCheckAuditLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def audit_log_detail(self, request, pk=None):
        log = MediaCheckAuditLog.objects.get(pk=pk)
        serializer = api.MediaCheckAuditLogDetailSerializer(log)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def cleanup_audit_logs(self, request):
        serializer = api.MediaCheckAuditCleanupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        retention_days = serializer.validated_data.get('retention_days')

        count = MediaCheckAuditLog.cleanup_old_logs(retention_days)
        actual_days = retention_days if retention_days else get_audit_log_retention_days()

        return Response({
            'deleted_count': count,
            'retention_days': actual_days,
        })

    @action(detail=False, methods=['get'])
    def config(self, request):
        return Response({
            'max_depth': get_max_depth(),
            'exclude_dirs': sorted(list(get_exclude_dirs())),
            'audit_retention_days': get_audit_log_retention_days(),
        })


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-auto-complete")
drf_router.register(r'media-check', MediaCheckViewSet, basename="media-check")
