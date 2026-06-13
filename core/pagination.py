from django.db.models.sql.constants import LOUTER
from rest_framework.pagination import LimitOffsetPagination


def _has_m2m_or_multi_join(queryset):
    alias_map = queryset.query.alias_map
    if len(alias_map) <= 1:
        return False
    seen_count = 0
    for alias, join in alias_map.items():
        if alias in (queryset.query.get_meta().db_table,):
            continue
        join_type = getattr(join, 'join_type', None)
        table_name = getattr(join, 'table_name', None)
        if table_name and 'tag' in table_name.lower():
            return True
        if table_name and 'board' in table_name.lower() and 'pins' in table_name.lower():
            return True
        if join_type is not None:
            seen_count += 1
            if seen_count > 1:
                return True
    return queryset.query.distinct


class PermissionAwareLimitOffsetPagination(LimitOffsetPagination):

    def get_count(self, queryset):
        if queryset.query.distinct or _has_m2m_or_multi_join(queryset):
            queryset = queryset.distinct()
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)
