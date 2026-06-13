from django.contrib import admin

from .models import Pin, Board, LinkCheck, LinkCheckTask


class PinAdmin(admin.ModelAdmin):
    pass


class LinkCheckAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "pin",
        "status",
        "error_type",
        "action_status",
        "http_status_code",
        "response_time_ms",
        "checked_at",
    )
    list_filter = ("status", "action_status", "error_type")
    search_fields = ("url", "error_message")
    raw_id_fields = ("pin",)
    readonly_fields = ("checked_at", "action_at", "created_at")


class LinkCheckTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "submitter",
        "status",
        "total_pins",
        "checked_count",
        "success_count",
        "failed_count",
        "started_at",
        "completed_at",
    )
    list_filter = ("status",)
    readonly_fields = (
        "total_pins",
        "checked_count",
        "success_count",
        "failed_count",
        "started_at",
        "completed_at",
        "created_at",
    )


admin.site.register(Pin, PinAdmin)
admin.site.register(Board)
admin.site.register(LinkCheck, LinkCheckAdmin)
admin.site.register(LinkCheckTask, LinkCheckTaskAdmin)
