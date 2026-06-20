from django.utils.translation import gettext_lazy as _

PREVIEW_ERROR_MESSAGES = {
    "invalid_url": _("invalid url"),
    "network_error": _("network error"),
    "invalid_content": _("invalid image content"),
    "content_too_large": _("content too large"),
    "format_unsupported": _("unsupported format"),
    "timeout": _("request timeout"),
    "auth_required": _("authentication required"),
    "forbidden": _("access forbidden"),
    "not_found": _("resource not found"),
    "unknown_error": _("unknown error"),
}

ADMIN_LABELS = {
    "dashboard_title": _("Preview Service Dashboard"),
    "cache_management_title": _("Preview Cache Management"),
    "plugins_title": _("Preview Plugins"),
    "quick_stats": _("Quick Stats"),
    "total_pins": _("Total Pins"),
    "pins_with_url": _("Pins with URL"),
    "cache_version": _("Cache Version"),
    "content_types": _("Content Types"),
    "registered_services": _("Registered Preview Services"),
    "content_type": _("Content Type"),
    "status": _("Status"),
    "service_class": _("Service Class"),
    "available": _("Available"),
    "not_available": _("Not available"),
    "quick_actions": _("Quick Actions"),
    "cache_management": _("Cache Management"),
    "plugin_status": _("Plugin Status"),
    "global_cache": _("Global Cache"),
    "current_cache_version": _("Current cache version"),
    "invalidate_all_cache": _("Invalidate All Cache"),
    "url_cache_operations": _("URL Cache Operations"),
    "invalidate_url": _("Invalidate URL"),
    "inspect_url": _("Inspect URL"),
    "inspect_result": _("Inspect Result"),
    "all_cache_invalidated": _("All preview cache invalidated. Cache version bumped to %(version)s."),
    "invalidated_count": _("Invalidated %(count)s cache entries for: %(url)s"),
    "url_required": _("URL is required."),
    "plugin_overview": _("Plugin Overview"),
    "total_plugins_loaded": _("Total plugins loaded"),
    "reset_all_circuit_breakers": _("Reset All Circuit Breakers"),
    "plugin_col": _("Plugin"),
    "circuit_state_col": _("Circuit State"),
    "errors_window_col": _("Errors (window)"),
    "total_errors_col": _("Total Errors"),
    "trips_col": _("Trips"),
    "capabilities_col": _("Capabilities"),
    "no_plugins_enabled": _("No plugins enabled."),
    "all_breakers_reset": _("All circuit breakers reset."),
    "closed": _("closed"),
    "open": _("open"),
    "half_open": _("half open"),
    "none": _("none"),
    "preview_dashboard": _("Preview Dashboard"),
    "preview_cache": _("Preview Cache"),
    "preview_plugins": _("Preview Plugins"),
}

WEBHOOK_MESSAGES = {
    "webhook_disabled": _("webhook is disabled"),
    "ip_not_allowed": _("IP address not allowed"),
    "invalid_signature": _("Invalid webhook signature"),
    "invalid_payload": _("Invalid JSON payload"),
    "missing_url": _("Missing 'url' field in payload"),
    "missing_items": _("Missing 'items' field in payload"),
    "unknown_action": _("Unknown action: %(action)s. Supported: %(supported)s"),
}


def get_error_message(error_code: str, language: str = None) -> str:
    from django.utils.translation import activate, get_language

    saved = None
    if language:
        saved = get_language()
        activate(language)

    msg = str(PREVIEW_ERROR_MESSAGES.get(error_code, error_code))

    if saved:
        activate(saved)

    return msg


def get_admin_label(key: str, **kwargs) -> str:
    template = ADMIN_LABELS.get(key, key)
    if kwargs:
        return str(template) % kwargs
    return str(template)


def get_webhook_message(key: str, **kwargs) -> str:
    template = WEBHOOK_MESSAGES.get(key, key)
    if kwargs:
        return str(template) % kwargs
    return str(template)
