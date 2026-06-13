import PIL.Image
import requests

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.dispatch import receiver

from django_images.models import Image as BaseImage, Thumbnail
from taggit.managers import TaggableManager

from users.models import User


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

    # FIXME: Move this into an asynchronous task
    def create_for_url(self, url, referer=None):
        file_name = url.split("/")[-1].split('#')[0].split('?')[0]
        buf = BytesIO()
        headers = dict(self._default_ua)
        if referer is not None:
            headers["Referer"] = referer
        response = requests.get(url, headers=headers)
        buf.write(response.content)
        if not self._is_valid_image(buf):
            return None
        obj = InMemoryUploadedFile(buf, 'image', file_name,
                                   None, buf.tell(), None)
        # create the image and its thumbnails in one transaction, removing
        # a chance of getting Database into a inconsistent state when we
        # try to create thumbnails one by one later
        image = self.create(image=obj)
        Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
        return image


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

    def __unicode__(self):
        return '%s - %s' % (self.submitter, self.published)


@receiver(models.signals.post_delete, sender=Pin)
def delete_pin_images(sender, instance, **kwargs):
    try:
        instance.image.delete()
    except Image.DoesNotExist:
        pass


class LinkCheck(models.Model):
    class Status:
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        CHOICES = (
            (PENDING, "待检查"),
            (RUNNING, "检查中"),
            (SUCCESS, "正常"),
            (FAILED, "失效"),
        )

    class ActionStatus:
        UNHANDLED = "unhandled"
        IGNORED = "ignored"
        FIXED = "fixed"
        DELETED = "deleted"
        HANDLED = "handled"
        CHOICES = (
            (UNHANDLED, "待处理"),
            (IGNORED, "已忽略"),
            (FIXED, "已修复"),
            (DELETED, "已删除"),
            (HANDLED, "已处理"),
        )

    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name="link_checks")
    url = models.CharField(max_length=2048)
    status = models.CharField(max_length=16, choices=Status.CHOICES, default=Status.PENDING)
    http_status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    action_status = models.CharField(
        max_length=16,
        choices=ActionStatus.CHOICES,
        default=ActionStatus.UNHANDLED,
    )
    action_note = models.TextField(null=True, blank=True)
    action_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "action_status"]),
            models.Index(fields=["pin", "created_at"]),
        ]

    def __str__(self):
        return f"LinkCheck(pin={self.pin_id}, status={self.status})"


class LinkCheckTask(models.Model):
    class Status:
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        CHOICES = (
            (PENDING, "待执行"),
            (RUNNING, "执行中"),
            (COMPLETED, "已完成"),
            (FAILED, "失败"),
        )

    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.CHOICES, default=Status.PENDING)
    total_pins = models.IntegerField(default=0)
    checked_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"LinkCheckTask(id={self.id}, status={self.status})"
