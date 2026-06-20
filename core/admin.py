from django.contrib import admin
from django.db.models import Case, When, IntegerField, Value

from .models import Pin, Board, BoardCollaborator


class PinAdmin(admin.ModelAdmin):
    pass


class BoardCollaboratorAdmin(admin.ModelAdmin):
    list_display = ('board_name', 'user_username', 'permission_label', 'permission_level', 'board_submitter')
    list_filter = ('permission',)
    search_fields = ('board__name', 'user__username')
    raw_id_fields = ('board', 'user')

    def _annotated_queryset(self, request):
        qs = super().get_queryset(request).select_related('board', 'board__submitter', 'user')
        order_cases = [
            When(permission=perm, then=Value(level))
            for perm, level in BoardCollaborator._PERMISSION_HIERARCHY.items()
        ]
        return qs.annotate(
            _permission_level=Case(
                *order_cases,
                default=Value(0),
                output_field=IntegerField(),
            )
        )

    def get_queryset(self, request):
        return self._annotated_queryset(request)

    def get_ordering(self, request):
        return ['board__name', '-_permission_level']

    def board_name(self, obj):
        return obj.board.name if obj.board else 'N/A'
    board_name.short_description = 'Board'
    board_name.admin_order_field = 'board__name'

    def user_username(self, obj):
        return obj.user.username if obj.user else 'N/A'
    user_username.short_description = 'User'
    user_username.admin_order_field = 'user__username'

    def permission_label(self, obj):
        return obj.get_permission_display()
    permission_label.short_description = 'Permission'

    def permission_level(self, obj):
        return getattr(obj, '_permission_level', 0)
    permission_level.short_description = 'Level'
    permission_level.admin_order_field = '_permission_level'

    def board_submitter(self, obj):
        if obj.board and obj.board.submitter:
            return obj.board.submitter.username
        return 'N/A'
    board_submitter.short_description = 'Board Owner'


admin.site.register(Pin, PinAdmin)
admin.site.register(Board)
admin.site.register(BoardCollaborator, BoardCollaboratorAdmin)
