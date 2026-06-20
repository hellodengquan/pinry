import PIL.Image
import json
import requests

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.dispatch import receiver
from django.utils import timezone

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


class MediaCheckAuditLog(models.Model):
    ACTION_CHECK = 'check'
    ACTION_DELETE_ORPHANS = 'delete_orphans'
    ACTION_FIX_MISSING = 'fix_missing'
    ACTION_ALL = 'all'

    ACTION_CHOICES = [
        (ACTION_CHECK, 'Check only'),
        (ACTION_DELETE_ORPHANS, 'Delete orphan files'),
        (ACTION_FIX_MISSING, 'Fix missing files'),
        (ACTION_ALL, 'All actions'),
    ]

    action = models.CharField(max_length=32, choices=ACTION_CHOICES, default=ACTION_CHECK)
    initiated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='media_check_audit_logs',
    )
    media_root = models.CharField(max_length=1024)
    scan_time = models.DateTimeField(default=timezone.now)
    max_depth = models.IntegerField(default=10)
    total_files = models.IntegerField(default=0)
    total_db_files = models.IntegerField(default=0)
    orphan_count = models.IntegerField(default=0)
    missing_count = models.IntegerField(default=0)
    pins_without_image_count = models.IntegerField(default=0)
    details_json = models.TextField(blank=True, default='{}')
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-scan_time']
        indexes = [
            models.Index(fields=['scan_time']),
            models.Index(fields=['action']),
            models.Index(fields=['success']),
        ]

    def __str__(self):
        return f'{self.action} - {self.scan_time.strftime("%Y-%m-%d %H:%M:%S")}'

    @property
    def details(self):
        try:
            return json.loads(self.details_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @details.setter
    def details(self, value):
        self.details_json = json.dumps(value, ensure_ascii=False)

    @staticmethod
    def create_from_report(report, action=ACTION_CHECK, user=None, success=True, error_message=''):
        pins_count = len(report.get('pins_without_image', []))
        log = MediaCheckAuditLog(
            action=action,
            initiated_by=user,
            media_root=report.get('media_root', ''),
            max_depth=report.get('max_depth', 10),
            total_files=report.get('total_files', 0),
            total_db_files=report.get('total_db_files', 0),
            orphan_count=report.get('orphan_count', 0),
            missing_count=report.get('missing_count', 0),
            pins_without_image_count=pins_count,
            success=success,
            error_message=error_message,
        )
        details = {
            'exclude_dirs': report.get('exclude_dirs', []),
            'orphan_files': report.get('orphan_files', []),
            'missing_files': report.get('missing_files', []),
            'pins_without_image': report.get('pins_without_image', []),
        }
        if 'delete_orphans_result' in report:
            details['delete_orphans_result'] = report['delete_orphans_result']
        if 'fix_missing_result' in report:
            details['fix_missing_result'] = report['fix_missing_result']
        log.details = details
        log.save()
        return log

    @staticmethod
    def cleanup_old_logs(retention_days=None):
        from core.utils import get_audit_log_retention_days

        if retention_days is None:
            retention_days = get_audit_log_retention_days()

        cutoff_date = timezone.now() - timezone.timedelta(days=retention_days)
        old_logs = MediaCheckAuditLog.objects.filter(scan_time__lt=cutoff_date)
        count, _ = old_logs.delete()
        return count
