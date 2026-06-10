from django.contrib import admin

from .models import Pin, Board, BoardShareToken


class PinAdmin(admin.ModelAdmin):
    pass


class BoardShareTokenAdmin(admin.ModelAdmin):
    list_display = (
        'token',
        'board',
        'created_by',
        'created_at',
        'expires_at',
        'is_revoked',
        'access_count',
        'last_accessed_at',
    )
    list_filter = (
        'is_revoked',
        'created_at',
        'expires_at',
    )
    search_fields = (
        'token',
        'board__name',
        'created_by__username',
    )
    readonly_fields = (
        'token',
        'created_at',
        'revoked_at',
        'last_accessed_at',
        'access_count',
    )
    raw_id_fields = ('board', 'created_by')


admin.site.register(Pin, PinAdmin)
admin.site.register(Board)
admin.site.register(BoardShareToken, BoardShareTokenAdmin)
