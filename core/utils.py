import hashlib
import os

from django.conf import settings


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


def get_all_media_files():
    media_root = settings.MEDIA_ROOT
    all_files = set()
    if not os.path.exists(media_root):
        return all_files

    for root, dirs, files in os.walk(media_root):
        for file in files:
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, media_root)
            all_files.add(relative_path)
    return all_files


def get_all_db_images():
    from django_images.models import Image, Thumbnail

    db_files = set()
    for image in Image.objects.all():
        if image.image.name:
            db_files.add(image.image.name)
    for thumbnail in Thumbnail.objects.all():
        if thumbnail.image.name:
            db_files.add(thumbnail.image.name)
    return db_files


def check_pins_without_valid_image():
    from core.models import Pin

    pins_without_image = []
    for pin in Pin.objects.select_related('image'):
        if not pin.image or not pin.image.image.name:
            pins_without_image.append({
                'id': pin.id,
                'submitter': pin.submitter.username,
                'description': pin.description[:50] if pin.description else '',
            })
    return pins_without_image


def get_orphan_files():
    all_media_files = get_all_media_files()
    all_db_files = get_all_db_images()
    return all_media_files - all_db_files


def get_missing_files():
    all_media_files = get_all_media_files()
    all_db_files = get_all_db_images()
    return all_db_files - all_media_files


def run_media_check():
    media_root = settings.MEDIA_ROOT
    all_media_files = get_all_media_files()
    all_db_files = get_all_db_images()
    orphan_files = get_orphan_files()
    missing_files = get_missing_files()
    pins_without_image = check_pins_without_valid_image()

    orphan_files_with_size = []
    for file in sorted(orphan_files):
        full_path = os.path.join(media_root, file)
        size = os.path.getsize(full_path) if os.path.exists(full_path) else 0
        orphan_files_with_size.append({
            'path': file,
            'size': size,
        })

    return {
        'media_root': media_root,
        'total_files': len(all_media_files),
        'total_db_files': len(all_db_files),
        'orphan_count': len(orphan_files),
        'missing_count': len(missing_files),
        'orphan_files': orphan_files_with_size,
        'missing_files': sorted(list(missing_files)),
        'pins_without_image': pins_without_image,
    }


def delete_orphan_files():
    orphan_files = get_orphan_files()
    media_root = settings.MEDIA_ROOT
    deleted = []
    errors = []

    for file in orphan_files:
        full_path = os.path.join(media_root, file)
        try:
            os.remove(full_path)
            deleted.append(file)
        except OSError as e:
            errors.append({
                'path': file,
                'error': str(e),
            })

    return {
        'deleted_count': len(deleted),
        'deleted_files': deleted,
        'errors': errors,
    }


def fix_missing_files():
    from django_images.models import Image, Thumbnail
    from core.models import Pin

    missing_files = get_missing_files()
    fixed_images = 0
    fixed_thumbnails = 0
    fixed_pins = 0
    errors = []

    for file in missing_files:
        image = Image.objects.filter(image=file).first()
        if image:
            try:
                pins = Pin.objects.filter(image=image)
                fixed_pins += pins.count()
                pins.delete()
                image.delete()
                fixed_images += 1
            except Exception as e:
                errors.append({
                    'path': file,
                    'type': 'Image',
                    'error': str(e),
                })
            continue

        thumbnail = Thumbnail.objects.filter(image=file).first()
        if thumbnail:
            try:
                thumbnail.delete()
                fixed_thumbnails += 1
            except Exception as e:
                errors.append({
                    'path': file,
                    'type': 'Thumbnail',
                    'error': str(e),
                })

    return {
        'fixed_images': fixed_images,
        'fixed_thumbnails': fixed_thumbnails,
        'fixed_pins': fixed_pins,
        'errors': errors,
    }
