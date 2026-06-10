from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, routers, status, permissions
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


class BatchOperationResultCodes:
    SUCCESS_MOVE = "success_move"
    SUCCESS_COPY = "success_copy"
    SUCCESS_DELETE = "success_delete"
    SUCCESS_PRIVACY_PUBLIC = "success_privacy_public"
    SUCCESS_PRIVACY_PRIVATE = "success_privacy_private"
    PIN_NOT_FOUND = "pin_not_found"
    PIN_NO_PERMISSION_ACCESS = "pin_no_permission_access"
    PIN_NO_PERMISSION_OWNER = "pin_no_permission_owner"
    TARGET_BOARD_NOT_FOUND = "target_board_not_found"
    TARGET_BOARD_NO_PERMISSION = "target_board_no_permission"
    SOURCE_BOARD_NOT_FOUND = "source_board_not_found"
    SOURCE_BOARD_NO_PERMISSION = "source_board_no_permission"
    OPERATION_FAILED = "operation_failed"


class BatchOperationViewSet(GenericViewSet):
    permission_classes = [permissions.IsAuthenticated, ]
    serializer_class = api.BatchOperationSerializer
    queryset = Pin.objects.none()

    RESULT_MESSAGES = {
        BatchOperationResultCodes.SUCCESS_MOVE: "Moved successfully",
        BatchOperationResultCodes.SUCCESS_COPY: "Copied successfully",
        BatchOperationResultCodes.SUCCESS_DELETE: "Deleted successfully",
        BatchOperationResultCodes.SUCCESS_PRIVACY_PUBLIC: "Privacy set to public",
        BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE: "Privacy set to private",
        BatchOperationResultCodes.PIN_NOT_FOUND: "Pin does not exist",
        BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS: "No permission to access this pin",
        BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER: "No permission to modify this pin",
        BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND: "Target board does not exist",
        BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION: "No permission to modify target board",
        BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND: "Source board does not exist",
        BatchOperationResultCodes.SOURCE_BOARD_NO_PERMISSION: "No permission to modify source board",
        BatchOperationResultCodes.OPERATION_FAILED: "Operation failed",
    }

    def _make_result(self, pin_id, success, code, message=None):
        return {
            "pin_id": pin_id,
            "success": success,
            "code": code,
            "message": message or self.RESULT_MESSAGES.get(code, ""),
        }

    def _build_result(self, operation, results):
        total = len(results)
        success_count = sum(1 for r in results if r["success"])
        failed_count = total - success_count
        return {
            "operation": operation,
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    def _can_access_pin(self, user, pin):
        if pin.private and pin.submitter != user:
            return False
        return True

    def _is_board_owner(self, user, board):
        return board.submitter == user

    @action(detail=False, methods=["post"], url_path="move-pins")
    def move_pins(self, request):
        serializer = api.BatchMovePinsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        pin_ids = data["pin_ids"]
        source_board_id = data.get("source_board_id")
        target_board_id = data["target_board_id"]
        user = request.user

        results = []

        try:
            target_board = Board.objects.get(id=target_board_id)
        except Board.DoesNotExist:
            for pid in pin_ids:
                results.append(
                    self._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                    )
                )
            return Response(
                self._build_result("move", results),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not self._is_board_owner(user, target_board):
            for pid in pin_ids:
                results.append(
                    self._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
                    )
                )
            return Response(
                self._build_result("move", results),
                status=status.HTTP_403_FORBIDDEN,
            )

        source_board = None
        if source_board_id:
            try:
                source_board = Board.objects.get(id=source_board_id)
                if not self._is_board_owner(user, source_board):
                    for pid in pin_ids:
                        results.append(
                            self._make_result(
                                pid, False,
                                BatchOperationResultCodes.SOURCE_BOARD_NO_PERMISSION,
                            )
                        )
                    return Response(
                        self._build_result("move", results),
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Board.DoesNotExist:
                for pid in pin_ids:
                    results.append(
                        self._make_result(
                            pid, False,
                            BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND,
                        )
                    )
                return Response(
                    self._build_result("move", results),
                    status=status.HTTP_404_NOT_FOUND,
                )

        pins = Pin.objects.filter(id__in=pin_ids)
        pin_map = {p.id: p for p in pins}

        for pin_id in pin_ids:
            pin = pin_map.get(pin_id)
            if pin is None:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NOT_FOUND,
                    )
                )
                continue

            if not self._can_access_pin(user, pin):
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS,
                    )
                )
                continue

            try:
                with transaction.atomic():
                    if source_board:
                        source_board.pins.remove(pin)
                    target_board.pins.add(pin)
                    results.append(
                        self._make_result(
                            pin_id, True,
                            BatchOperationResultCodes.SUCCESS_MOVE,
                        )
                    )
            except Exception as e:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.OPERATION_FAILED,
                        f"Failed to move: {str(e)}",
                    )
                )

        response_status = status.HTTP_200_OK if any(
            r["success"] for r in results
        ) else status.HTTP_400_BAD_REQUEST
        return Response(self._build_result("move", results), status=response_status)

    @action(detail=False, methods=["post"], url_path="copy-pins")
    def copy_pins(self, request):
        serializer = api.BatchCopyPinsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        pin_ids = data["pin_ids"]
        target_board_id = data["target_board_id"]
        user = request.user

        results = []

        try:
            target_board = Board.objects.get(id=target_board_id)
        except Board.DoesNotExist:
            for pid in pin_ids:
                results.append(
                    self._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                    )
                )
            return Response(
                self._build_result("copy", results),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not self._is_board_owner(user, target_board):
            for pid in pin_ids:
                results.append(
                    self._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
                    )
                )
            return Response(
                self._build_result("copy", results),
                status=status.HTTP_403_FORBIDDEN,
            )

        pins = Pin.objects.filter(id__in=pin_ids)
        pin_map = {p.id: p for p in pins}

        for pin_id in pin_ids:
            pin = pin_map.get(pin_id)
            if pin is None:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NOT_FOUND,
                    )
                )
                continue

            if not self._can_access_pin(user, pin):
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS,
                    )
                )
                continue

            try:
                with transaction.atomic():
                    target_board.pins.add(pin)
                    results.append(
                        self._make_result(
                            pin_id, True,
                            BatchOperationResultCodes.SUCCESS_COPY,
                        )
                    )
            except Exception as e:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.OPERATION_FAILED,
                        f"Failed to copy: {str(e)}",
                    )
                )

        response_status = status.HTTP_200_OK if any(
            r["success"] for r in results
        ) else status.HTTP_400_BAD_REQUEST
        return Response(self._build_result("copy", results), status=response_status)

    @action(detail=False, methods=["post"], url_path="delete-pins")
    def delete_pins(self, request):
        serializer = api.BatchDeletePinsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        pin_ids = data["pin_ids"]
        user = request.user

        results = []
        pins = Pin.objects.filter(id__in=pin_ids)
        pin_map = {p.id: p for p in pins}

        for pin_id in pin_ids:
            pin = pin_map.get(pin_id)
            if pin is None:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NOT_FOUND,
                    )
                )
                continue

            if pin.submitter != user:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
                    )
                )
                continue

            try:
                with transaction.atomic():
                    pin.delete()
                    results.append(
                        self._make_result(
                            pin_id, True,
                            BatchOperationResultCodes.SUCCESS_DELETE,
                        )
                    )
            except Exception as e:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.OPERATION_FAILED,
                        f"Failed to delete: {str(e)}",
                    )
                )

        response_status = status.HTTP_200_OK if any(
            r["success"] for r in results
        ) else status.HTTP_400_BAD_REQUEST
        return Response(self._build_result("delete", results), status=response_status)

    @action(detail=False, methods=["post"], url_path="update-privacy")
    def update_privacy(self, request):
        serializer = api.BatchUpdatePrivacySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        pin_ids = data["pin_ids"]
        private = data["private"]
        user = request.user

        results = []
        pins = Pin.objects.filter(id__in=pin_ids)
        pin_map = {p.id: p for p in pins}

        success_code = (
            BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE
            if private
            else BatchOperationResultCodes.SUCCESS_PRIVACY_PUBLIC
        )

        for pin_id in pin_ids:
            pin = pin_map.get(pin_id)
            if pin is None:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NOT_FOUND,
                    )
                )
                continue

            if pin.submitter != user:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
                    )
                )
                continue

            try:
                with transaction.atomic():
                    pin.private = private
                    pin.save(update_fields=["private"])
                    results.append(
                        self._make_result(
                            pin_id, True,
                            success_code,
                        )
                    )
            except Exception as e:
                results.append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.OPERATION_FAILED,
                        f"Failed to update privacy: {str(e)}",
                    )
                )

        response_status = status.HTTP_200_OK if any(
            r["success"] for r in results
        ) else status.HTTP_400_BAD_REQUEST
        return Response(self._build_result("privacy", results), status=response_status)


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
drf_router.register(r'batch-operations', BatchOperationViewSet, basename="batch-operation")
