from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag
import logging

from core import serializers as api
from core.models import Image, Pin, Board
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import filter_private_pin, filter_private_board
from core.services import (
    PreviewError,
    PreviewContentType,
    get_preview_manager,
)

logger = logging.getLogger(__name__)


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
        preview_manager = get_preview_manager()
        url = request.data.get("url")
        referer = request.data.get("referer")
        if url:
            preview_manager.invalidate_cache_for_url(url, referer)
        return super(PinViewSet, self).create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        new_url = request.data.get("url")
        if new_url and new_url != instance.url:
            preview_manager = get_preview_manager()
            referer = request.data.get("referer", new_url)
            preview_manager.invalidate_cache_for_url(new_url, referer)
            preview_manager.invalidate_cache_for_url(instance.url, instance.referer)
        return super(PinViewSet, self).update(request, partial=partial, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='refetch')
    def refetch(self, request, pk=None):
        pin = self.get_object()
        if not pin.url:
            return Response(
                {"error": "Pin has no url to refetch"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        preview_manager = get_preview_manager()
        try:
            result = preview_manager.refresh(
                url=pin.url,
                referer=pin.referer,
                content_type_hint=PreviewContentType.IMAGE,
            )
        except PreviewError as e:
            return Response(
                {"error": e.to_dict()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if result.image_id and result.image_id != pin.image_id:
            try:
                from core.models import Image
                new_image = Image.objects.get(pk=result.image_id)
                pin.image = new_image
                pin.save()
            except Image.DoesNotExist:
                pass
        serializer = self.get_serializer(pin)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='inspect')
    def inspect(self, request, pk=None):
        pin = self.get_object()
        preview_manager = get_preview_manager()
        info = preview_manager.inspect(
            url=pin.url or "",
            referer=pin.referer,
            content_type_hint=PreviewContentType.IMAGE,
        )
        info.update({
            "pin_id": pin.pk,
            "pin_url": pin.url,
            "pin_referer": pin.referer,
            "image_id": pin.image_id,
        })
        return Response(info, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='export/json')
    def export_json(self, request):
        from django.http import JsonResponse
        import json

        queryset = self.filter_queryset(self.get_queryset())[:1000]
        preview_manager = get_preview_manager()

        items = []
        for pin in queryset:
            item = {
                "id": pin.pk,
                "url": pin.url,
                "referer": pin.referer,
                "description": pin.description,
                "private": pin.private,
                "published": pin.published.isoformat() if pin.published else None,
                "image_id": pin.image_id,
                "submitter": pin.submitter.username if pin.submitter else None,
                "tags": [t.name for t in pin.tags.all()],
            }
            if pin.url:
                try:
                    cache_info = preview_manager.inspect(
                        url=pin.url,
                        referer=pin.referer,
                        content_type_hint=PreviewContentType.IMAGE,
                    )
                    item["preview_cache_hit"] = cache_info.get("cache_hit", False)
                    item["preview_service"] = cache_info.get("detected_service")
                    cached = cache_info.get("cached_result") or {}
                    item["preview_content_type"] = cached.get("content_type")
                    item["preview_image_id"] = cached.get("image_id")
                    meta = cached.get("metadata") or {}
                    item["preview_width"] = meta.get("width")
                    item["preview_height"] = meta.get("height")
                    item["preview_title"] = meta.get("title")
                    item["preview_mime_type"] = meta.get("mime_type")
                except Exception:
                    item["preview_error"] = "inspection_failed"
            items.append(item)

        response = JsonResponse(
            items,
            safe=False,
            json_dumps_params={"indent": 2},
        )
        response["Content-Disposition"] = 'attachment; filename="pins_export.json"'
        return response

    @action(detail=False, methods=['get'], url_path='export/csv')
    def export_csv(self, request):
        from django.http import HttpResponse
        import csv
        import io

        queryset = self.filter_queryset(self.get_queryset())[:1000]
        preview_manager = get_preview_manager()

        headers = [
            "id", "url", "referer", "description", "private", "published",
            "image_id", "submitter", "tags",
            "preview_cache_hit", "preview_service", "preview_content_type",
            "preview_image_id", "preview_width", "preview_height",
            "preview_title", "preview_mime_type",
        ]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()

        for pin in queryset:
            row = {
                "id": pin.pk,
                "url": pin.url or "",
                "referer": pin.referer or "",
                "description": pin.description or "",
                "private": "yes" if pin.private else "no",
                "published": pin.published.isoformat() if pin.published else "",
                "image_id": pin.image_id or "",
                "submitter": pin.submitter.username if pin.submitter else "",
                "tags": ",".join(t.name for t in pin.tags.all()),
            }

            if pin.url:
                try:
                    cache_info = preview_manager.inspect(
                        url=pin.url,
                        referer=pin.referer,
                        content_type_hint=PreviewContentType.IMAGE,
                    )
                    row["preview_cache_hit"] = "yes" if cache_info.get("cache_hit") else "no"
                    row["preview_service"] = cache_info.get("detected_service") or ""
                    cached = cache_info.get("cached_result") or {}
                    row["preview_content_type"] = cached.get("content_type") or ""
                    row["preview_image_id"] = cached.get("image_id") or ""
                    meta = cached.get("metadata") or {}
                    row["preview_width"] = meta.get("width") or ""
                    row["preview_height"] = meta.get("height") or ""
                    row["preview_title"] = meta.get("title") or ""
                    row["preview_mime_type"] = meta.get("mime_type") or ""
                except Exception:
                    row["preview_cache_hit"] = "error"

            writer.writerow(row)

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="pins_export.csv"'
        return response


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
        invalidate_all = bool(request.data.get('all', False))
        preview_manager = get_preview_manager()

        if invalidate_all:
            bumped = preview_manager.invalidate_all()
            return Response(
                {"invalidated_all": True, "version_bumped": bumped},
                status=status.HTTP_200_OK,
            )

        if not url:
            return Response(
                {"url": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.data.get('referer')
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

    @action(detail=False, methods=['get'], url_path='cache-version')
    def cache_version(self, request):
        preview_manager = get_preview_manager()
        version = preview_manager.get_cache_version()
        return Response({
            "version": version,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='plugins/status')
    def plugins_status(self, request):
        from pinry_plugins.builder import (
            get_circuit_breaker_status,
            get_plugin_registry,
        )
        registry = get_plugin_registry()
        circuit_breakers = get_circuit_breaker_status()
        plugins = []
        for path, info in registry.items():
            plugin_key = f"{info.get('module')}.{info.get('class')}"
            cb_status = circuit_breakers.get(plugin_key, {})
            plugins.append({
                "path": path,
                "class_name": info.get("class"),
                "module": info.get("module"),
                "capabilities": info.get("capabilities", {}),
                "circuit_breaker": cb_status,
            })
        return Response({
            "count": len(plugins),
            "plugins": plugins,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='webhook')
    def webhook(self, request):
        from core.services.webhook_service import (
            WebhookError,
            is_webhook_enabled,
            process_webhook,
        )

        if not is_webhook_enabled():
            return Response(
                {"error": "webhook is disabled", "code": "webhook_disabled"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = process_webhook(request)
            return Response(result, status=status.HTTP_200_OK)
        except WebhookError as e:
            return Response(
                {"error": e.message, "code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error("Unexpected webhook error: %s", e)
            return Response(
                {"error": "internal server error", "code": "internal_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['get'], url_path='webhook/info')
    def webhook_info(self, request):
        from core.services.webhook_service import (
            WEBHOOK_ACTIONS,
            WEBHOOK_SIGNATURE_HEADER,
            is_webhook_enabled,
        )
        return Response({
            "enabled": is_webhook_enabled(),
            "signature_header": WEBHOOK_SIGNATURE_HEADER,
            "supported_actions": list(WEBHOOK_ACTIONS.keys()),
            "example_payload": {
                "action": "refresh",
                "url": "http://example.com/image.jpg",
                "referer": "http://example.com/",
                "content_type": "image",
                "force": True,
                "async": False,
            },
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='versions')
    def version_history(self, request):
        from core.services.versioning import get_version_history

        url = request.query_params.get("url")
        if not url:
            return Response(
                {"url": "This query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.query_params.get("referer")
        history = get_version_history(url, referer)
        return Response({
            "url": url,
            "referer": referer,
            "total_versions": len(history),
            "history": history,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='versions/rollback')
    def version_rollback(self, request):
        from core.services.versioning import rollback_to_version

        url = request.data.get("url")
        version = request.data.get("version")
        if not url or version is None:
            return Response(
                {"url": "url and version are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.data.get("referer")
        result = rollback_to_version(url, int(version), referer)
        if result is None:
            return Response(
                {"error": f"Version {version} not found for {url}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='versions/diff')
    def version_diff(self, request):
        from core.services.versioning import diff_versions

        url = request.query_params.get("url")
        version_a = request.query_params.get("version_a")
        version_b = request.query_params.get("version_b")
        if not url or not version_a or not version_b:
            return Response(
                {"error": "url, version_a, version_b are required query params."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referer = request.query_params.get("referer")
        result = diff_versions(url, int(version_a), int(version_b), referer)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='metrics')
    def metrics(self, request):
        from core.services.metrics import get_metrics_summary

        summary = get_metrics_summary()
        return Response(summary, status=status.HTTP_200_OK)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board-auto-complete")
drf_router.register(r'preview', PreviewViewSet, basename="preview")
