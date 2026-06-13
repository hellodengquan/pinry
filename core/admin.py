from django.contrib import admin

from .models import Pin, Board


class PinAdmin(admin.ModelAdmin):
    pass


class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'submitter', 'private', 'is_archived', 'published', 'archived_at')
    list_filter = ('is_archived', 'private')
    search_fields = ('name', 'submitter__username')
    readonly_fields = ('published', 'archived_at')


admin.site.register(Pin, PinAdmin)
admin.site.register(Board, BoardAdmin)
