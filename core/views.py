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
    PIN_ALREADY_IN_BOARD = "pin_already_in_board"


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
        BatchOperationResultCodes.PIN_ALREADY_IN_BOARD: "Pin already exists in the target board",
    }

    # ------------------------------------------------------------------
    # 公共工具方法
    # ------------------------------------------------------------------
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

    def _build_response(self, operation, results):
        any_success = any(r["success"] for r in results)
        any_failed = any(not r["success"] for r in results)
        if any_success:
            code = status.HTTP_200_OK
        elif not results:
            code = status.HTTP_400_BAD_REQUEST
        else:
            code = status.HTTP_400_BAD_REQUEST
            first_code = results[0].get("code")
            if first_code in (
                BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND,
            ):
                code = status.HTTP_404_NOT_FOUND
            elif first_code in (
                BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
                BatchOperationResultCodes.SOURCE_BOARD_NO_PERMISSION,
            ):
                code = status.HTTP_403_FORBIDDEN
        return Response(self._build_result(operation, results), status=code)

    # ------------------------------------------------------------------
    # 可复用执行框架
    #  操作 = preflight(ctx) -> None (失败时填充 results)
    #       + for_each(ctx, pin) -> (success_code, error_code, extra_msg | None)
    #       + finally build_response
    #  权限检查分两级：
    #    - ACCESS 级：仅验证是否可见（_can_access_pin）
    #    - OWNER 级：验证是否是 Pin 所有者（submitter == user）
    # ------------------------------------------------------------------
    def _run_batch_operation(
        self,
        request,
        serializer_cls,
        operation_name,
        preflight_fn,
        per_pin_fn,
        permission_level="ACCESS",
    ):
        """模板方法：执行批量操作的公共流程

        Args:
            request: Django request 对象
            serializer_cls: 请求参数序列化器
            operation_name: 操作标识（写入结果结构的 operation 字段）
            preflight_fn(ctx) -> None:
                执行前检查（如 Board 权限校验）。
                遇到需要立刻终止的错误时，向 ctx["results"] 写入结果，
                ctx["abort"] = True，然后 return。
            per_pin_fn(ctx, pin) -> (success_code, error_code, extra_msg) | None:
                Pin 存在且通过权限检查后，被调用执行具体操作。
                返回 tuple(success_code, operation_failed_code, None/extra_msg)
                操作成功返回 (success_code, None, None)
                有特殊业务错误返回 (None, special_code, extra_msg)
                返回 None 表示跳过（上层自行处理）
            permission_level: "ACCESS" | "OWNER" | None
                - "ACCESS": 使用 _can_access_pin (私有Pin仅所有者可见)
                - "OWNER": 验证 submitter == user
                - None: 不做 Pin 级权限检查
        """
        ctx = {
            "request": request,
            "user": request.user,
            "serializer": serializer_cls(data=request.data),
            "results": [],
            "abort": False,
            "data": None,
            "pin_ids": [],
            "pin_map": {},
            "extra": {},
        }

        if not ctx["serializer"].is_valid():
            return Response(
                ctx["serializer"].errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        ctx["data"] = ctx["serializer"].validated_data
        ctx["pin_ids"] = ctx["data"]["pin_ids"]

        # --- 1) 前置检查（Board 相关校验） -----------------------------
        preflight_fn(ctx)
        if ctx["abort"]:
            any_success = any(r["success"] for r in ctx["results"])
            if any_success:
                resp_status = status.HTTP_200_OK
            elif ctx["results"]:
                first_code = ctx["results"][0].get("code")
                if first_code in (
                    BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                    BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND,
                ):
                    resp_status = status.HTTP_404_NOT_FOUND
                else:
                    resp_status = status.HTTP_403_FORBIDDEN
            else:
                resp_status = status.HTTP_400_BAD_REQUEST
            return Response(
                self._build_result(operation_name, ctx["results"]),
                status=resp_status,
            )

        # --- 2) 批量加载 Pin ------------------------------------------
        pins = Pin.objects.filter(id__in=ctx["pin_ids"])
        ctx["pin_map"] = {p.id: p for p in pins}

        # --- 3) 逐项执行循环 ------------------------------------------
        for pin_id in ctx["pin_ids"]:
            pin = ctx["pin_map"].get(pin_id)

            # 3a) Pin 不存在
            if pin is None:
                ctx["results"].append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.PIN_NOT_FOUND,
                    )
                )
                continue

            # 3b) Pin 级权限检查
            if permission_level == "ACCESS":
                if not self._can_access_pin(ctx["user"], pin):
                    ctx["results"].append(
                        self._make_result(
                            pin_id, False,
                            BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS,
                        )
                    )
                    continue
            elif permission_level == "OWNER":
                if pin.submitter != ctx["user"]:
                    ctx["results"].append(
                        self._make_result(
                            pin_id, False,
                            BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
                        )
                    )
                    continue

            # 3c) 业务钩子
            try:
                outcome = per_pin_fn(ctx, pin)
                if outcome is None:
                    continue

                success_code, error_code, extra_msg = outcome
                if success_code is not None:
                    ctx["results"].append(
                        self._make_result(
                            pin_id, True, success_code, extra_msg,
                        )
                    )
                else:
                    ctx["results"].append(
                        self._make_result(
                            pin_id, False, error_code, extra_msg,
                        )
                    )
            except Exception as exc:
                ctx["results"].append(
                    self._make_result(
                        pin_id, False,
                        BatchOperationResultCodes.OPERATION_FAILED,
                        str(exc),
                    )
                )

        # --- 4) 组装响应 ---------------------------------------------
        return self._build_response(operation_name, ctx["results"])

    # ------------------------------------------------------------------
    # 具体操作: Move
    # ------------------------------------------------------------------
    @staticmethod
    def _move_preflight(ctx, view):
        data = ctx["data"]
        user = ctx["user"]
        pin_ids = ctx["pin_ids"]
        source_board_id = data.get("source_board_id")
        target_board_id = data["target_board_id"]

        try:
            target_board = Board.objects.get(id=target_board_id)
        except Board.DoesNotExist:
            for pid in pin_ids:
                ctx["results"].append(
                    view._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                    )
                )
            ctx["abort"] = True
            return

        if not view._is_board_owner(user, target_board):
            for pid in pin_ids:
                ctx["results"].append(
                    view._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
                    )
                )
            ctx["abort"] = True
            return

        ctx["extra"]["target_board"] = target_board
        source_board = None
        if source_board_id:
            try:
                source_board = Board.objects.get(id=source_board_id)
                if not view._is_board_owner(user, source_board):
                    for pid in pin_ids:
                        ctx["results"].append(
                            view._make_result(
                                pid, False,
                                BatchOperationResultCodes.SOURCE_BOARD_NO_PERMISSION,
                            )
                        )
                    ctx["abort"] = True
                    return
            except Board.DoesNotExist:
                for pid in pin_ids:
                    ctx["results"].append(
                        view._make_result(
                            pid, False,
                            BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND,
                        )
                    )
                ctx["abort"] = True
                return
        ctx["extra"]["source_board"] = source_board

    @staticmethod
    def _move_per_pin(view, ctx, pin):
        target_board = ctx["extra"]["target_board"]
        source_board = ctx["extra"].get("source_board")

        with transaction.atomic():
            if source_board:
                source_board.pins.remove(pin)
            target_board.pins.add(pin)
        return BatchOperationResultCodes.SUCCESS_MOVE, None, None

    @action(detail=False, methods=["post"], url_path="move-pins")
    def move_pins(self, request):
        return self._run_batch_operation(
            request=request,
            serializer_cls=api.BatchMovePinsSerializer,
            operation_name="move",
            preflight_fn=lambda ctx: self._move_preflight(ctx, self),
            per_pin_fn=lambda ctx, pin: self._move_per_pin(self, ctx, pin),
            permission_level="ACCESS",
        )

    # ------------------------------------------------------------------
    # 具体操作: Copy (含已存在检测)
    # ------------------------------------------------------------------
    @staticmethod
    def _copy_preflight(ctx, view):
        data = ctx["data"]
        user = ctx["user"]
        pin_ids = ctx["pin_ids"]
        target_board_id = data["target_board_id"]

        try:
            target_board = Board.objects.get(id=target_board_id)
        except Board.DoesNotExist:
            for pid in pin_ids:
                ctx["results"].append(
                    view._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
                    )
                )
            ctx["abort"] = True
            return

        if not view._is_board_owner(user, target_board):
            for pid in pin_ids:
                ctx["results"].append(
                    view._make_result(
                        pid, False,
                        BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
                    )
                )
            ctx["abort"] = True
            return

        ctx["extra"]["target_board"] = target_board
        ctx["extra"]["existing_pin_ids"] = set(
            target_board.pins.values_list("id", flat=True),
        )

    @staticmethod
    def _copy_per_pin(view, ctx, pin):
        target_board = ctx["extra"]["target_board"]
        existing = ctx["extra"]["existing_pin_ids"]

        if pin.id in existing:
            return None, BatchOperationResultCodes.PIN_ALREADY_IN_BOARD, None

        with transaction.atomic():
            target_board.pins.add(pin)
        return BatchOperationResultCodes.SUCCESS_COPY, None, None

    @action(detail=False, methods=["post"], url_path="copy-pins")
    def copy_pins(self, request):
        return self._run_batch_operation(
            request=request,
            serializer_cls=api.BatchCopyPinsSerializer,
            operation_name="copy",
            preflight_fn=lambda ctx: self._copy_preflight(ctx, self),
            per_pin_fn=lambda ctx, pin: self._copy_per_pin(self, ctx, pin),
            permission_level="ACCESS",
        )

    # ------------------------------------------------------------------
    # 具体操作: Delete
    # ------------------------------------------------------------------
    @staticmethod
    def _delete_preflight(ctx, view):
        pass

    @staticmethod
    def _delete_per_pin(view, ctx, pin):
        with transaction.atomic():
            pin.delete()
        return BatchOperationResultCodes.SUCCESS_DELETE, None, None

    @action(detail=False, methods=["post"], url_path="delete-pins")
    def delete_pins(self, request):
        return self._run_batch_operation(
            request=request,
            serializer_cls=api.BatchDeletePinsSerializer,
            operation_name="delete",
            preflight_fn=lambda ctx: self._delete_preflight(ctx, self),
            per_pin_fn=lambda ctx, pin: self._delete_per_pin(self, ctx, pin),
            permission_level="OWNER",
        )

    # ------------------------------------------------------------------
    # 具体操作: Update Privacy
    # ------------------------------------------------------------------
    @staticmethod
    def _privacy_preflight(ctx, view):
        private = ctx["data"]["private"]
        ctx["extra"]["success_code"] = (
            BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE
            if private
            else BatchOperationResultCodes.SUCCESS_PRIVACY_PUBLIC
        )

    @staticmethod
    def _privacy_per_pin(view, ctx, pin):
        private = ctx["data"]["private"]
        with transaction.atomic():
            pin.private = private
            pin.save(update_fields=["private"])
        return ctx["extra"]["success_code"], None, None

    @action(detail=False, methods=["post"], url_path="update-privacy")
    def update_privacy(self, request):
        return self._run_batch_operation(
            request=request,
            serializer_cls=api.BatchUpdatePrivacySerializer,
            operation_name="privacy",
            preflight_fn=lambda ctx: self._privacy_preflight(ctx, self),
            per_pin_fn=lambda ctx, pin: self._privacy_per_pin(self, ctx, pin),
            permission_level="OWNER",
        )


drf_router = routers.DefaultRouter()
drf_router.register(r'pins', PinViewSet, basename="pin")
drf_router.register(r'images', ImageViewSet)
drf_router.register(r'boards', BoardViewSet, basename="board")
drf_router.register(r'tags-auto-complete', TagAutoCompleteViewSet)
drf_router.register(r'boards-auto-complete', BoardAutoCompleteViewSet, basename="board")
drf_router.register(r'batch-operations', BatchOperationViewSet, basename="batch-operation")
