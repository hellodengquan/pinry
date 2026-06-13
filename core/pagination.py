from rest_framework.pagination import LimitOffsetPagination


class PermissionAwareLimitOffsetPagination(LimitOffsetPagination):

    def get_count(self, queryset):
        if queryset.query.distinct:
            queryset = queryset.distinct()
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)
