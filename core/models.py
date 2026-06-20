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
    _legacy_collaborators = models.TextField(
        default='[]',
        blank=True,
        help_text="Legacy field for collaborator data backup during migration rollback."
    )

    published = models.DateTimeField(auto_now_add=True)


class BoardCollaborator(models.Model):
    class PermissionLevel(models.TextChoices):
        VIEW = 'view', 'View'
        EDIT = 'edit', 'Edit'
        MANAGE = 'manage', 'Manage'

    PERMISSION_LEVELS = PermissionLevel  # alias for backwards compatibility

    _PERMISSION_HIERARCHY = {
        PermissionLevel.VIEW: 10,
        PermissionLevel.EDIT: 20,
        PermissionLevel.MANAGE: 30,
    }

    _RESERVED_HIERARCHY_SLOTS = [12, 15, 18, 22, 25, 28]

    _METHOD_PERMISSION_MAP = {
        'GET': PermissionLevel.VIEW,
        'HEAD': PermissionLevel.VIEW,
        'OPTIONS': PermissionLevel.VIEW,
        'POST': PermissionLevel.MANAGE,
        'PATCH': PermissionLevel.EDIT,
        'PUT': PermissionLevel.EDIT,
        'DELETE': PermissionLevel.MANAGE,
    }

    class Meta:
        unique_together = ("board", "user")

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="collaborators")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="board_collaborations")
    permission = models.CharField(
        max_length=10,
        choices=PermissionLevel.choices,
        default=PermissionLevel.VIEW,
    )

    @classmethod
    def get_permission_level(cls, user, board):
        if user == board.submitter:
            return cls.PermissionLevel.MANAGE
        collab = cls.objects.filter(board=board, user=user).first()
        if collab:
            return collab.permission
        return None

    @classmethod
    def has_permission_for_method(cls, user, board, method):
        perm = cls.get_permission_level(user, board)
        if perm is None:
            return False
        required = cls._METHOD_PERMISSION_MAP.get(method, cls.PermissionLevel.MANAGE)
        return cls._PERMISSION_HIERARCHY[perm] >= cls._PERMISSION_HIERARCHY[required]

    @classmethod
    def has_min_permission(cls, user, board, required_perm):
        perm = cls.get_permission_level(user, board)
        if perm is None:
            return False
        return cls._PERMISSION_HIERARCHY[perm] >= cls._PERMISSION_HIERARCHY[required_perm]

    @classmethod
    def has_strictly_higher_permission(cls, user, board, compare_perm):
        perm = cls.get_permission_level(user, board)
        if perm is None or compare_perm is None:
            return False
        return cls._PERMISSION_HIERARCHY[perm] > cls._PERMISSION_HIERARCHY[compare_perm]

    @classmethod
    def can_manage_collaborator(cls, user, board):
        return cls.has_min_permission(user, board, cls.PermissionLevel.MANAGE)

    @classmethod
    def can_delete_collaborator(cls, actor, target_record):
        if target_record.user_id == actor.id:
            return True
        board = target_record.board
        if actor == board.submitter:
            return True
        return cls.has_strictly_higher_permission(
            actor, board, target_record.permission
        )

    @classmethod
    def can_modify_collaborator_record(cls, user, collaborator_record, method):
        board = collaborator_record.board
        if user == board.submitter:
            return True
        if method == 'DELETE':
            return cls.can_delete_collaborator(user, collaborator_record)
        required = cls._METHOD_PERMISSION_MAP.get(method, cls.PermissionLevel.MANAGE)
        if not cls.has_min_permission(user, board, required):
            return False
        if method in ('PATCH', 'PUT'):
            return collaborator_record.user == user
        return True


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
