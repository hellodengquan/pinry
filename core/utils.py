import hashlib
import os

from django.core.exceptions import ObjectDoesNotExist


def upload_path(instance, filename, **kwargs):
    hasher = hashlib.md5()
    for chunk in instance.image.chunks():
        hasher.update(chunk)
    hash = hasher.hexdigest()
    base, ext = os.path.splitext(filename)
    return '%(first)s/%(second)s/%(hash)s/%(base)s%(ext)s' % {
        'first': hash[0],
        'second': hash[1],
        'hash': hash,
        'base': base,
        'ext': ext,
    }


def generate_pin_cursor_token(request, queryset, filter_params=None):
    """
    Generate a lightweight cursor token representing the current state
    of the visible pin collection. This token is used to detect when
    the collection has changed (e.g., visibility toggled) between page requests.
    """
    if filter_params is None:
        filter_params = {}

    hasher = hashlib.sha256()

    user_id = request.user.id if request.user.is_authenticated else 'anonymous'
    hasher.update(f"user:{user_id}".encode('utf-8'))

    for key in sorted(filter_params.keys()):
        hasher.update(f"filter:{key}={filter_params[key]}".encode('utf-8'))

    count = queryset.count()
    hasher.update(f"count:{count}".encode('utf-8'))

    if count > 0:
        try:
            first_item = queryset.order_by('-id').first()
            last_item = queryset.order_by('id').first()
            if first_item:
                hasher.update(f"first_id:{first_item.id}".encode('utf-8'))
            if last_item:
                hasher.update(f"last_id:{last_item.id}".encode('utf-8'))
        except ObjectDoesNotExist:
            pass

    return hasher.hexdigest()
