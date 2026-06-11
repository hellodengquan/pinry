import PIL.Image
import requests
import secrets

from io import BytesIO
from datetime import timedelta

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
        indexes = [models.Index(fields=["submitter", "name"])]

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


class BoardShareTokenManager(models.Manager):
    def create_token(self, board, creator, expires_days=None):
        token = secrets.token_urlsafe(32)
        expires_at = None
        if expires_days is not None:
            expires_at = timezone.now() + timedelta(days=expires_days)
        return self.create(
            board=board,
            token=token,
            created_by=creator,
            expires_at=expires_at,
        )


class BoardShareToken(models.Model):
    class Meta:
        ordering = ('-created_at',)

    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        related_name='share_tokens',
    )
    token = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_share_tokens',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)

    objects = BoardShareTokenManager()

    @property
    def is_valid(self):
        if self.is_revoked:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    def revoke(self):
        self.is_revoked = True
        self.revoked_at = timezone.now()
        self.save()

    def record_access(self):
        self.last_accessed_at = timezone.now()
        self.access_count += 1
        self.save()

    def regenerate(self, expires_days=None):
        self.token = secrets.token_urlsafe(32)
        self.created_at = timezone.now()
        self.is_revoked = False
        self.revoked_at = None
        self.access_count = 0
        self.last_accessed_at = None
        if expires_days is not None:
            self.expires_at = timezone.now() + timedelta(days=expires_days)
        else:
            self.expires_at = None
        self.save()
        return self
