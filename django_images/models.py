import hashlib
import os.path
from io import BytesIO

from django.db import models
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.dispatch import receiver
from PIL import Image as PILImage

from importlib import import_module

from django.urls import reverse

from . import utils
from .settings import IMAGE_SIZES, IMAGE_PATH, IMAGE_AUTO_DELETE


def calculate_md5(file_obj):
    hasher = hashlib.md5()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(8192), b''):
        hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()


def calculate_phash(file_obj):
    try:
        file_obj.seek(0)
        img = PILImage.open(file_obj)
        img = img.convert('L').resize((8, 8), PILImage.Resampling.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / 64
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        file_obj.seek(0)
        return '%016x' % int(bits, 2)
    except Exception:
        file_obj.seek(0)
        return None


def hamming_distance(hash1, hash2):
    if hash1 is None or hash2 is None:
        return 999
    return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')


def hashed_upload_to(instance, filename, **kwargs):
    image_type = 'original' if isinstance(instance, Image) else 'thumbnail'
    prefix = 'image/%s/by-md5/' % (image_type,)
    hasher = hashlib.md5()
    for chunk in instance.image.chunks():
        hasher.update(chunk)
    hash_ = hasher.hexdigest()
    base, ext = os.path.splitext(filename)
    return '%(prefix)s%(first)s/%(second)s/%(hash)s/%(base)s%(ext)s' % {
        'prefix': prefix,
        'first': hash_[0],
        'second': hash_[1],
        'hash': hash_,
        'base': base,
        'ext': ext,
    }


if IMAGE_PATH is None:
    upload_to = hashed_upload_to
else:
    if callable(IMAGE_PATH):
        upload_to = IMAGE_PATH
    else:
        parts = IMAGE_PATH.split('.')
        module_name = '.'.join(parts[:-1])
        module = import_module(module_name)
        upload_to = getattr(module, parts[-1])


class Image(models.Model):
    image = models.ImageField(upload_to=upload_to,
                              height_field='height', width_field='width',
                              max_length=255)
    height = models.PositiveIntegerField(default=0, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)
    hash = models.CharField(max_length=32, blank=True, null=True, db_index=True, editable=False)
    phash = models.CharField(max_length=16, blank=True, null=True, db_index=True, editable=False)

    def save(self, *args, **kwargs):
        if self.image:
            if not self.hash:
                self.hash = calculate_md5(self.image)
            if not self.phash:
                self.phash = calculate_phash(self.image)
        super(Image, self).save(*args, **kwargs)

    def find_similar(self, max_distance=5):
        if not self.phash:
            return Image.objects.none()
        similar = []
        for img in Image.objects.exclude(id=self.id).filter(phash__isnull=False):
            if hamming_distance(self.phash, img.phash) <= max_distance:
                similar.append(img)
        return similar

    def get_by_size(self, size):
        return self.thumbnail_set.get(size=size)

    def get_absolute_url(self, size=None):
        if not size:
            return self.image.url
        try:
            return self.get_by_size(size).image.url
        except Thumbnail.DoesNotExist:
            return reverse('image-thumbnail', args=(self.id, size))


class ThumbnailManager(models.Manager):
    def get_or_create_at_sizes(self, image, sizes):
        sizes_to_create = list(sizes)
        sized = {}
        for size in sizes:
            if size not in IMAGE_SIZES:
                raise ValueError("Received unknown size: %s" % size)

            try:
                sized[size] = image.get_by_size(size)
            except Thumbnail.DoesNotExist:
                pass
            else:
                sizes_to_create.remove(size)

        if sizes_to_create:
            bufs = [
                utils.write_image_in_memory(img)
                for img in utils.scale_and_crop_iter(
                    image.image,
                    [IMAGE_SIZES[size] for size in sizes_to_create])
            ]
            for size, buf in zip(sizes_to_create, bufs):
                # and save to storage
                original_dir, original_file = os.path.split(image.image.name)
                thumb_file = InMemoryUploadedFile(buf, "image", original_file,
                                                  None, buf.tell(), None)
                sized[size], created = image.thumbnail_set.get_or_create(
                    size=size, defaults={'image': thumb_file})

        # Make sure this is in the correct order
        return [sized[size] for size in sizes]


class Thumbnail(models.Model):
    original = models.ForeignKey(Image, on_delete=models.CASCADE)
    image = models.ImageField(upload_to=upload_to,
                              height_field='height', width_field='width',
                              max_length=255)
    size = models.CharField(max_length=100)
    height = models.PositiveIntegerField(default=0, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)

    objects = ThumbnailManager()

    class Meta:
        unique_together = ('original', 'size')

    def get_absolute_url(self):
        return self.image.url


@receiver(models.signals.post_save)
def original_changed(sender, instance, created, **kwargs):
    if isinstance(instance, Image):
        instance.thumbnail_set.all().delete()


@receiver(models.signals.post_delete)
def delete_image_files(sender, instance, **kwargs):
    if isinstance(instance, (Image, Thumbnail)) and IMAGE_AUTO_DELETE:
        if instance.image.storage.exists(instance.image.name):
            instance.image.delete(save=False)
