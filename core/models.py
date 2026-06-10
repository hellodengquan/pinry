import PIL.Image
import requests
from urllib.parse import urlparse, urlunparse

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.dispatch import receiver

from django_images.models import Image as BaseImage, Thumbnail
from django_images.settings import IMAGE_AUTO_DELETE
from taggit.managers import TaggableManager

from users.models import User


def normalize_url(url):
    if not url:
        return url
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() if parsed.scheme else 'https'
        netloc = parsed.netloc.lower() if parsed.netloc else ''
        path = parsed.path.rstrip('/') if parsed.path else ''
        if path and not path.startswith('/'):
            path = '/' + path
        normalized = urlunparse((
            scheme,
            netloc,
            path,
            parsed.params,
            parsed.query,
            '',
        ))
        return normalized
    except ValueError:
        return url


class ImageManager(models.Manager):
    _default_ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/48.0.2564.82 Safari/537.36',
    }

    @staticmethod
    def _is_valid_image(fp):
        fp.seek(0)
        try:
            PIL.Image.open(fp)
        except PIL.UnidentifiedImageError:
            fp.seek(0)
            return False
        else:
            fp.seek(0)
            return True

    def _fetch_image_content(self, url, referer=None):
        file_name = url.split("/")[-1].split('#')[0].split('?')[0]
        buf = BytesIO()
        headers = dict(self._default_ua)
        if referer is not None:
            headers["Referer"] = referer
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        buf.write(response.content)
        if not self._is_valid_image(buf):
            return None, None
        obj = InMemoryUploadedFile(buf, 'image', file_name,
                                   None, buf.tell(), None)
        return obj, buf

    # FIXME: Move this into an asynchronous task
    def create_for_url(self, url, referer=None):
        normalized_url = normalize_url(url)
        normalized_referer = normalize_url(referer) if referer else normalized_url
        try:
            obj, buf = self._fetch_image_content(normalized_url, normalized_referer)
        except requests.RequestException:
            return None
        if not obj:
            return None
        image = self.create(image=obj)
        Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
        return image

    def refresh_for_url(self, image_instance, url, referer=None):
        normalized_url = normalize_url(url)
        normalized_referer = normalize_url(referer) if referer else normalized_url
        try:
            obj, buf = self._fetch_image_content(normalized_url, normalized_referer)
        except requests.RequestException:
            return None, False
        if not obj:
            return None, False
        old_image_path = image_instance.image.name
        image_instance.image = obj
        image_instance.save()
        Thumbnail.objects.get_or_create_at_sizes(image_instance, settings.IMAGE_SIZES.keys())
        if IMAGE_AUTO_DELETE and old_image_path:
            try:
                storage = image_instance.image.storage
                if storage.exists(old_image_path):
                    storage.delete(old_image_path)
            except Exception:
                pass
        return image_instance, True


class Image(BaseImage):
    objects = ImageManager()

    class Sizes:
        standard = "standard"
        thumbnail = "thumbnail"
        square = "square"

    class Meta:
        proxy = True

    @property
    def standard(self):
        return Thumbnail.objects.get(
            original=self, size=self.Sizes.standard
        )

    @property
    def thumbnail(self):
        return Thumbnail.objects.get(
            original=self, size=self.Sizes.thumbnail
        )

    @property
    def square(self):
        return Thumbnail.objects.get(
            original=self, size=self.Sizes.square
        )


class Board(models.Model):
    class Meta:
        unique_together = ("submitter", "name")
        index_together = ("submitter", "name")

    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128, blank=False, null=False)
    private = models.BooleanField(default=False, blank=False)
    pins = models.ManyToManyField("Pin", related_name="pins", blank=True)

    published = models.DateTimeField(auto_now_add=True)


class Pin(models.Model):
    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    private = models.BooleanField(default=False, blank=False)
    url = models.CharField(null=True, blank=True, max_length=2048)
    referer = models.CharField(null=True, blank=True, max_length=2048)
    description = models.TextField(blank=True, null=True)
    image = models.ForeignKey(Image, related_name='pin', on_delete=models.CASCADE)
    published = models.DateTimeField(auto_now_add=True)
    tags = TaggableManager()

    def tag_list(self):
        return self.tags.all()

    def refresh_preview(self):
        if not self.url:
            return False, "URL is required"
        normalized_url = normalize_url(self.url)
        normalized_referer = normalize_url(self.referer) if self.referer else normalized_url
        image, success = Image.objects.refresh_for_url(
            self.image, normalized_url, normalized_referer
        )
        if success:
            self.url = normalized_url
            self.referer = normalized_referer if normalized_referer else normalized_url
            self.save(update_fields=['url', 'referer'])
            return True, "Preview refreshed successfully"
        return False, "Failed to refresh preview"

    def __unicode__(self):
        return '%s - %s' % (self.submitter, self.published)


@receiver(models.signals.post_delete, sender=Pin)
def delete_pin_images(sender, instance, **kwargs):
    try:
        instance.image.delete()
    except Image.DoesNotExist:
        pass
