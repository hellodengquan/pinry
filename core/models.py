import PIL.Image
import logging
import requests

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models

from django_images.models import Image as BaseImage, Thumbnail
from taggit.managers import TaggableManager

from users.models import User
from pinry_plugins.events import dispatch_event, EventType

logger = logging.getLogger(__name__)


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

    def create_for_url(self, url, referer=None):
        dispatch_event(
            EventType.FETCH_PREVIEW_START,
            payload={
                "url": url,
                "referer": referer,
            },
        )
        try:
            file_name = url.split("/")[-1].split('#')[0].split('?')[0]
            buf = BytesIO()
            headers = dict(self._default_ua)
            if referer is not None:
                headers["Referer"] = referer
            response = requests.get(url, headers=headers)
            buf.write(response.content)
            if not self._is_valid_image(buf):
                dispatch_event(
                    EventType.FETCH_PREVIEW_FAILURE,
                    payload={
                        "url": url,
                        "referer": referer,
                        "reason": "invalid_image_content",
                    },
                )
                return None
            obj = InMemoryUploadedFile(buf, 'image', file_name,
                                       None, buf.tell(), None)
            image = self.create(image=obj)
            Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
            dispatch_event(
                EventType.FETCH_PREVIEW_SUCCESS,
                payload={
                    "url": url,
                    "referer": referer,
                    "image_instance": image,
                },
            )
            return image
        except Exception as exc:
            logger.exception("Failed to fetch preview image from %s", url)
            dispatch_event(
                EventType.FETCH_PREVIEW_FAILURE,
                payload={
                    "url": url,
                    "referer": referer,
                    "reason": "exception",
                    "exception": str(exc),
                },
            )
            return None


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

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            dispatch_event(
                EventType.IMAGE_PRE_CREATE,
                payload={"image_instance": self, "instance": self},
            )
        result = super().save(*args, **kwargs)
        if is_new:
            dispatch_event(
                EventType.IMAGE_POST_CREATE,
                payload={"image_instance": self, "instance": self},
            )
        return result

    def delete(self, *args, **kwargs):
        dispatch_event(
            EventType.IMAGE_PRE_DELETE,
            payload={"image_instance": self, "instance": self},
        )
        result = super().delete(*args, **kwargs)
        dispatch_event(
            EventType.IMAGE_POST_DELETE,
            payload={"image_instance": self, "instance": self},
        )
        return result


class Board(models.Model):
    class Meta:
        unique_together = ("submitter", "name")
        index_together = ("submitter", "name")

    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128, blank=False, null=False)
    private = models.BooleanField(default=False, blank=False)
    pins = models.ManyToManyField("Pin", related_name="pins", blank=True)

    published = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            dispatch_event(
                EventType.BOARD_PRE_CREATE,
                payload={"board_instance": self, "instance": self},
            )
        else:
            dispatch_event(
                EventType.BOARD_PRE_UPDATE,
                payload={"board_instance": self, "instance": self},
            )
        result = super().save(*args, **kwargs)
        if is_new:
            dispatch_event(
                EventType.BOARD_POST_CREATE,
                payload={"board_instance": self, "instance": self},
            )
        else:
            dispatch_event(
                EventType.BOARD_POST_UPDATE,
                payload={"board_instance": self, "instance": self},
            )
        return result

    def delete(self, *args, **kwargs):
        dispatch_event(
            EventType.BOARD_PRE_DELETE,
            payload={"board_instance": self, "instance": self},
        )
        result = super().delete(*args, **kwargs)
        dispatch_event(
            EventType.BOARD_POST_DELETE,
            payload={"board_instance": self, "instance": self},
        )
        return result


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

    def __unicode__(self):
        return '%s - %s' % (self.submitter, self.published)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            dispatch_event(
                EventType.PIN_PRE_CREATE,
                payload={"pin_instance": self, "instance": self},
            )
        else:
            dispatch_event(
                EventType.PIN_PRE_UPDATE,
                payload={"pin_instance": self, "instance": self},
            )
        result = super().save(*args, **kwargs)
        if is_new:
            dispatch_event(
                EventType.PIN_POST_CREATE,
                payload={"pin_instance": self, "instance": self},
            )
        else:
            dispatch_event(
                EventType.PIN_POST_UPDATE,
                payload={"pin_instance": self, "instance": self},
            )
        return result

    def delete(self, *args, **kwargs):
        dispatch_event(
            EventType.PIN_PRE_DELETE,
            payload={"pin_instance": self, "instance": self},
        )
        result = super().delete(*args, **kwargs)
        if getattr(settings, "IMAGE_AUTO_DELETE", True):
            try:
                self.image.delete()
            except Image.DoesNotExist:
                pass
        dispatch_event(
            EventType.PIN_POST_DELETE,
            payload={"pin_instance": self, "instance": self},
        )
        return result

    def sync(self, **extra_data):
        dispatch_event(
            EventType.PIN_SYNC,
            payload={
                "pin_instance": self,
                "instance": self,
                "extra_data": extra_data,
            },
        )
