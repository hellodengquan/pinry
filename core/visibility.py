from django.db.models import Q


class VisibilityPolicy:
    DEFAULT_OWNER_FIELD = "submitter"

    @classmethod
    def filter_visible(cls, queryset, user, owner_field=None):
        owner_field = owner_field or cls.DEFAULT_OWNER_FIELD
        if user.is_authenticated:
            return queryset.exclude(~Q(**{owner_field: user}), private=True)
        return queryset.exclude(private=True)

    @classmethod
    def can_view(cls, obj, user, owner_field=None):
        owner_field = owner_field or cls.DEFAULT_OWNER_FIELD
        if not getattr(obj, "private", False):
            return True
        if not user.is_authenticated:
            return False
        return getattr(obj, owner_field) == user

    @classmethod
    def can_change(cls, obj, user, owner_field=None):
        owner_field = owner_field or cls.DEFAULT_OWNER_FIELD
        if not user.is_authenticated:
            return False
        return getattr(obj, owner_field) == user
