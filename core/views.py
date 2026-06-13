from django.db import transaction
from django.db.models import Subquery, OuterRef, Count
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from taggit.models import Tag

from core import serializers as api
from core.link_checker import check_single_pin, bulk_recheck_check_ids, bulk_recheck_all_failed
from core.models import Image, Pin, Board, LinkCheck, LinkCheckTask
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import (
    filter_private_pin,
    filter_private_board,
    LinkCheckActionSerializer,
)

try:
    from core.tasks import run_link_check_task as celery_run_link_check_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


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


class LinkCheckViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = api.LinkCheckSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_fields = ("status", "action_status", "pin", "error_type")
    ordering_fields = ("-created_at", "-checked_at", "response_time_ms")
    ordering = ("-created_at",)
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        query = LinkCheck.objects.all()
        latest = self.request.query_params.get("latest", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if latest:
            latest_ids = (
                LinkCheck.objects.filter(pin=OuterRef("pin"))
                .order_by("-created_at")
                .values_list("id", flat=True)[:1]
            )
            query = query.filter(id__in=Subquery(latest_ids))
        if not self.request.user.is_superuser:
            query = query.filter(pin__submitter=self.request.user)
        return query.select_related("pin", "pin__image", "pin__submitter")

    @action(detail=False, methods=["get"], url_path="error-type-stats")
    def error_type_stats(self, request):
        query = self.get_queryset().filter(status=LinkCheck.Status.FAILED)
        latest = request.query_params.get("latest", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if latest:
            latest_ids = (
                LinkCheck.objects.filter(pin=OuterRef("pin"))
                .order_by("-created_at")
                .values_list("id", flat=True)[:1]
            )
            query = query.filter(id__in=Subquery(latest_ids))

        only_unhandled = request.query_params.get(
            "only_unhandled", ""
        ).lower() in ("1", "true", "yes")
        if only_unhandled:
            query = query.filter(action_status=LinkCheck.ActionStatus.UNHANDLED)

        stats = (
            query.values("error_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response({"results": list(stats)})

    @action(detail=True, methods=["post"], url_path="action")
    def handle_action(self, request, pk=None):
        check = self.get_object()
        if not request.user.is_superuser and check.pin.submitter != request.user:
            return Response(
                {"detail": "permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = LinkCheckActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action_ = serializer.validated_data["action"]
        note = serializer.validated_data.get("action_note", "")

        if action_ == "ignore":
            check.action_status = LinkCheck.ActionStatus.IGNORED
        elif action_ == "fixed":
            check.action_status = LinkCheck.ActionStatus.FIXED
        elif action_ == "handled":
            check.action_status = LinkCheck.ActionStatus.HANDLED
        elif action_ == "delete":
            check.pin.delete()
            return Response(
                {"detail": "pin deleted", "link_check_id": check.id},
                status=status.HTTP_200_OK,
            )

        check.action_note = note
        check.action_at = timezone.now()
        check.save()
        return Response(api.LinkCheckSerializer(check).data)

    @action(detail=True, methods=["post"], url_path="recheck")
    def recheck(self, request, pk=None):
        check = self.get_object()
        if not request.user.is_superuser and check.pin.submitter != request.user:
            return Response(
                {"detail": "permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        result = check_single_pin(check.pin_id)
        if result is None:
            return Response(
                {"detail": "invalid pin or url"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(api.LinkCheckSerializer(result).data)

    @action(detail=False, methods=["post"], url_path="bulk-recheck")
    def bulk_recheck(self, request):
        check_ids = request.data.get("ids") or request.data.get("check_ids")
        if not isinstance(check_ids, list) or len(check_ids) == 0:
            return Response(
                {"detail": "`ids` must be a non-empty list of LinkCheck ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(check_ids) > 5000:
            return Response(
                {"detail": "`ids` too large (max 5000 per request)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        summary = bulk_recheck_check_ids(check_ids, user=request.user)
        return Response(summary)

    @action(detail=False, methods=["post"], url_path="recheck-all-failed")
    def recheck_all_failed(self, request):
        summary = bulk_recheck_all_failed(user=request.user)
        return Response(summary)


class LinkCheckTaskViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = api.LinkCheckTaskSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_fields = ("status",)
    ordering_fields = ("-created_at", "-completed_at")
    ordering = ("-created_at",)
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        query = LinkCheckTask.objects.all()
        if not self.request.user.is_superuser:
            query = query.filter(submitter=self.request.user)
        return query.select_related("submitter")

    @action(detail=False, methods=["post"], url_path="start")
    def start_task(self, request):
        task = LinkCheckTask.objects.create(submitter=request.user)

        if CELERY_AVAILABLE:
            result = celery_run_link_check_task.delay(task.id)
            task.celery_task_id = result.id
            task.save(update_fields=["celery_task_id"])
        else:
            from .link_checker import run_link_check_task as sync_run_task
            import threading

            def run_in_background(task_id):
                sync_run_task(task_id)

            thread = threading.Thread(
                target=run_in_background, args=(task.id,), daemon=True
            )
            thread.start()

        return Response(
            api.LinkCheckTaskSerializer(task, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_task(self, request, pk=None):
        with transaction.atomic():
            task = LinkCheckTask.objects.select_for_update().get(pk=pk)

            if not request.user.is_superuser and task.submitter != request.user:
                return Response(
                    {"detail": "permission denied"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if task.status not in (
                LinkCheckTask.Status.PENDING,
                LinkCheckTask.Status.RUNNING,
            ):
                return Response(
                    {"detail": "task cannot be cancelled in current status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            task.status = LinkCheckTask.Status.CANCELLED
            task.completed_at = timezone.now()
            task.save(update_fields=["status", "completed_at"])

            LinkCheck.objects.filter(
                task_id=task.id,
                status=LinkCheck.Status.RUNNING,
            ).update(
                status=LinkCheck.Status.FAILED,
                error_type="cancelled",
                error_message="Task cancelled by user",
                checked_at=timezone.now(),
            )

        if CELERY_AVAILABLE and task.celery_task_id:
            try:
                from pinry.celery import app as celery_app

                celery_app.control.revoke(
                    task.celery_task_id,
                    terminate=True,
                    signal="SIGTERM",
                )
            except Exception:
                pass

        serializer = api.LinkCheckTaskSerializer(task, context={"request": request})
        return Response(serializer.data)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
drf_router.register(r'link-checks', LinkCheckViewSet, basename="linkcheck")
drf_router.register(r'link-check-tasks', LinkCheckTaskViewSet, basename="linkchecktask")
