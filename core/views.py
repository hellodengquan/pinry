import threading

from django.db.models import Subquery, OuterRef, Max
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
from core.link_checker import check_single_pin, run_link_check_task
from core.models import Image, Pin, Board, LinkCheck, LinkCheckTask
from core.permissions import IsOwnerOrReadOnly, OwnerOnlyIfPrivate
from core.serializers import (
    filter_private_pin,
    filter_private_board,
    LinkCheckActionSerializer,
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


class LinkCheckViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = api.LinkCheckSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_fields = ("status", "action_status", "pin")
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

        def run_in_background(task_id):
            run_link_check_task(task_id)

        thread = threading.Thread(target=run_in_background, args=(task.id,), daemon=True)
        thread.start()

        return Response(
            api.LinkCheckTaskSerializer(task).data,
            status=status.HTTP_201_CREATED,
        )


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
drf_router.register(r'link-checks', LinkCheckViewSet, basename="linkcheck")
drf_router.register(r'link-check-tasks', LinkCheckTaskViewSet, basename="linkchecktask")
