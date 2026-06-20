from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe

from .models import Pin, Board
from core.services import get_preview_manager, PreviewContentType


def _render_admin_page(title, body_html, request, opts):
    css = """
    <style>
        .preview-dashboard { max-width: 1000px; margin: 20px; }
        .preview-card {
            background: #fff; border: 1px solid #ddd; border-radius: 4px;
            padding: 16px; margin-bottom: 16px;
        }
        .preview-card h2 { margin-top: 0; font-size: 16px; color: #417690; }
        .preview-stats { display: flex; gap: 20px; flex-wrap: wrap; }
        .preview-stat {
            background: #f5f5f5; padding: 12px 20px; border-radius: 4px;
            min-width: 140px;
        }
        .preview-stat .number { font-size: 24px; font-weight: bold; color: #417690; }
        .preview-stat .label { font-size: 12px; color: #666; }
        .preview-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .preview-table th, .preview-table td {
            padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee;
        }
        .preview-table th { background: #f5f5f5; font-weight: 600; }
        .status-badge {
            display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 11px; font-weight: 600;
        }
        .status-ok { background: #d4edda; color: #155724; }
        .status-warn { background: #fff3cd; color: #856404; }
        .status-error { background: #f8d7da; color: #721c24; }
        .status-info { background: #d1ecf1; color: #0c5460; }
        .preview-form { margin: 16px 0; }
        .preview-form input[type="text"] {
            padding: 6px 8px; width: 400px;
            border: 1px solid #ccc; border-radius: 4px;
        }
        .preview-form button {
            padding: 6px 16px; background: #417690; color: #fff;
            border: none; border-radius: 4px; cursor: pointer;
        }
        .preview-form button:hover { background: #375f72; }
        .code-block {
            background: #f5f5f5; padding: 12px; border-radius: 4px;
            font-family: monospace; font-size: 12px; overflow-x: auto;
            white-space: pre-wrap; word-break: break-all;
        }
        .breadcrumb { margin-bottom: 16px; font-size: 12px; }
        .breadcrumb a { color: #417690; text-decoration: none; }
    </style>
    """

    breadcrumb = mark_safe(
        f'<div class="breadcrumb">'
        f'<a href="/admin/">Home</a> &rsaquo; {escape(title)}'
        f"</div>"
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{escape(title)} | Preview Service Admin</title>
        {css}
    </head>
    <body>
        <div class="preview-dashboard">
            {breadcrumb}
            <h1>{escape(title)}</h1>
            {body_html}
        </div>
    </body>
    </html>
    """
    return HttpResponse(mark_safe(html))


@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = ("id", "submitter", "description", "url", "image", "private", "published")
    list_filter = ("private", "published")
    search_fields = ("url", "description", "submitter__username")
    raw_id_fields = ("submitter", "image")
    readonly_fields = ("published",)
    actions = ["refresh_preview_action", "inspect_preview_action"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "preview-dashboard/",
                self.admin_site.admin_view(self.preview_dashboard),
                name="core_pin_preview_dashboard",
            ),
            path(
                "preview-cache/",
                self.admin_site.admin_view(self.preview_cache_management),
                name="core_pin_preview_cache",
            ),
            path(
                "preview-plugins/",
                self.admin_site.admin_view(self.preview_plugins),
                name="core_pin_preview_plugins",
            ),
        ]
        return custom_urls + urls

    def preview_dashboard(self, request):
        pin_count = Pin.objects.count()
        image_pin_count = Pin.objects.exclude(url__isnull=True).exclude(url="").count()
        manager = get_preview_manager()

        services_html = ""
        for ct in PreviewContentType:
            svc = manager._services.get(ct)
            status_class = "status-ok" if svc else "status-error"
            status_text = "Available" if svc else "Not available"
            svc_class = type(svc).__name__ if svc else "N/A"
            services_html += f"""
            <tr>
                <td><code>{escape(ct.value)}</code></td>
                <td><span class="status-badge {status_class}">{status_text}</span></td>
                <td><code>{escape(svc_class)}</code></td>
            </tr>
            """

        body = f"""
        <div class="preview-card">
            <h2>Quick Stats</h2>
            <div class="preview-stats">
                <div class="preview-stat">
                    <div class="number">{pin_count}</div>
                    <div class="label">Total Pins</div>
                </div>
                <div class="preview-stat">
                    <div class="number">{image_pin_count}</div>
                    <div class="label">Pins with URL</div>
                </div>
                <div class="preview-stat">
                    <div class="number">{manager.get_cache_version()}</div>
                    <div class="label">Cache Version</div>
                </div>
                <div class="preview-stat">
                    <div class="number">{len(PreviewContentType)}</div>
                    <div class="label">Content Types</div>
                </div>
            </div>
        </div>

        <div class="preview-card">
            <h2>Registered Preview Services</h2>
            <table class="preview-table">
                <thead>
                    <tr><th>Content Type</th><th>Status</th><th>Service Class</th></tr>
                </thead>
                <tbody>
                    {services_html}
                </tbody>
            </table>
        </div>

        <div class="preview-card">
            <h2>Quick Actions</h2>
            <p>
                <a href="../preview-cache/" class="button">Cache Management</a> &nbsp;
                <a href="../preview-plugins/" class="button">Plugin Status</a>
            </p>
        </div>
        """
        return _render_admin_page(
            "Preview Dashboard",
            mark_safe(body),
            request,
            Pin._meta,
        )

    def preview_cache_management(self, request):
        manager = get_preview_manager()
        inspect_result = None
        message = None
        message_level = "info"

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "invalidate_all":
                bumped = manager.invalidate_all()
                message = f"All preview cache invalidated. Cache version bumped to {manager.get_cache_version()}."
                message_level = "success"
            elif action == "invalidate_url":
                url = request.POST.get("url", "").strip()
                if url:
                    count = manager.invalidate_cache_for_url(url)
                    message = f"Invalidated {count} cache entries for: {url}"
                    message_level = "success"
                else:
                    message = "URL is required."
                    message_level = "error"
            elif action == "inspect_url":
                url = request.POST.get("url", "").strip()
                if url:
                    inspect_result = manager.inspect(url=url)
                else:
                    message = "URL is required."
                    message_level = "error"

        import json
        inspect_html = ""
        if inspect_result:
            json_str = json.dumps(inspect_result, indent=2, default=str)
            inspect_html = f"""
            <div class="preview-card">
                <h3>Inspect Result</h3>
                <div class="code-block">{escape(json_str)}</div>
            </div>
            """

        message_html = ""
        if message:
            msg_class = f"status-{message_level}"
            message_html = f"""
            <p><span class="status-badge {msg_class}">{escape(message)}</span></p>
            """

        body = f"""
        {message_html}

        <div class="preview-card">
            <h2>Global Cache</h2>
            <p>Current cache version: <strong>{manager.get_cache_version()}</strong></p>
            <form class="preview-form" method="post">
                <input type="hidden" name="action" value="invalidate_all">
                <button type="submit" style="background:#dc3545;">Invalidate All Cache</button>
            </form>
        </div>

        <div class="preview-card">
            <h2>URL Cache Operations</h2>
            <form class="preview-form" method="post" style="margin-bottom:12px;">
                <input type="text" name="url" placeholder="http://example.com/image.jpg"
                       value="{escape(request.POST.get('url', ''))}">
                <input type="hidden" name="action" value="invalidate_url">
                <button type="submit">Invalidate URL</button>
            </form>
            <form class="preview-form" method="post">
                <input type="text" name="url" placeholder="http://example.com/image.jpg"
                       value="{escape(request.POST.get('url', ''))}">
                <input type="hidden" name="action" value="inspect_url">
                <button type="submit" style="background:#6c757d;">Inspect URL</button>
            </form>
        </div>

        {inspect_html}
        """
        return _render_admin_page(
            "Preview Cache Management",
            mark_safe(body),
            request,
            Pin._meta,
        )

    def preview_plugins(self, request):
        from pinry_plugins.builder import (
            get_plugin_registry,
            get_circuit_breaker_status,
            reset_circuit_breakers,
        )

        message = None
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "reset_breakers":
                reset_circuit_breakers()
                message = "All circuit breakers reset."

        registry = get_plugin_registry()
        breakers = get_circuit_breaker_status()

        plugins_html = ""
        for path, info in registry.items():
            key = f"{info.get('module')}.{info.get('class')}"
            cb = breakers.get(key, {})
            state = cb.get("state", "unknown")
            state_class = "status-ok" if state == "closed" else "status-warn" if state == "half_open" else "status-error"

            caps = info.get("capabilities", {})
            cap_list = [k for k, v in caps.items() if v]
            cap_html = ", ".join(f"<code>{c}</code>" for c in cap_list) or "none"

            plugins_html += f"""
            <tr>
                <td><strong>{escape(info.get('class', '?'))}</strong><br>
                    <small style="color:#999;">{escape(path)}</small></td>
                <td><span class="status-badge {state_class}">{escape(state)}</span></td>
                <td>{cb.get('current_error_count', 0)}</td>
                <td>{cb.get('total_errors', 0)}</td>
                <td>{cb.get('trip_count', 0)}</td>
                <td>{mark_safe(cap_html)}</td>
            </tr>
            """

        if not registry:
            plugins_html = """
            <tr><td colspan="6" style="text-align:center;color:#999;padding:24px;">
                No plugins enabled.
            </td></tr>
            """

        message_html = ""
        if message:
            message_html = f'<p><span class="status-badge status-info">{escape(message)}</span></p>'

        body = f"""
        {message_html}

        <div class="preview-card">
            <h2>Plugin Overview</h2>
            <p>Total plugins loaded: <strong>{len(registry)}</strong></p>
            <form class="preview-form" method="post">
                <input type="hidden" name="action" value="reset_breakers">
                <button type="submit" style="background:#ffc107;color:#000;">
                    Reset All Circuit Breakers
                </button>
            </form>
        </div>

        <div class="preview-card">
            <h2>Plugin Status</h2>
            <table class="preview-table">
                <thead>
                    <tr>
                        <th>Plugin</th>
                        <th>Circuit State</th>
                        <th>Errors (window)</th>
                        <th>Total Errors</th>
                        <th>Trips</th>
                        <th>Capabilities</th>
                    </tr>
                </thead>
                <tbody>
                    {plugins_html}
                </tbody>
            </table>
        </div>
        """
        return _render_admin_page(
            "Preview Plugins",
            mark_safe(body),
            request,
            Pin._meta,
        )

    def refresh_preview_action(self, request, queryset):
        from core.tasks import dispatch_refresh

        refreshed = 0
        for pin in queryset.exclude(url="").exclude(url__isnull=True):
            try:
                dispatch_refresh(
                    url=pin.url,
                    referer=pin.referer,
                    async_mode=False,
                )
                refreshed += 1
            except Exception:
                pass
        self.message_user(request, f"Refreshed preview for {refreshed} pins.")

    refresh_preview_action.short_description = "Refresh preview for selected pins"

    def inspect_preview_action(self, request, queryset):
        first = queryset.exclude(url="").exclude(url__isnull=True).first()
        if not first:
            self.message_user(request, "No pins with URL selected.", level="ERROR")
            return HttpResponseRedirect("../")
        return HttpResponseRedirect(f"../preview-cache/?url={first.url}")

    inspect_preview_action.short_description = "Inspect preview for first selected pin"


admin.site.register(Board)
