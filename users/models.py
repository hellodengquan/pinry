import hashlib

from django.conf import settings
from django.contrib.auth.models import User as BaseUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


LANGUAGE_CHOICES = [
    (code, code.upper())
    for code, _ in getattr(settings, "LANGUAGES", [("en", "English"), ("zh", "中文"), ("fr", "Français")])
]


def create_token_if_necessary(user: BaseUser):
    from rest_framework.authtoken.models import Token
    token = Token.objects.filter(user=user).first()
    if token is not None:
        return token
    else:
        return Token.objects.create(user=user)


class User(BaseUser):

    @property
    def gravatar(self):
        return hashlib.md5(self.email.encode('utf-8')).hexdigest()

    @property
    def locale(self):
        try:
            return self.settings.language
        except UserSettings.DoesNotExist:
            return None

    class Meta:
        proxy = True


class UserSettings(models.Model):
    user = models.OneToOneField(
        BaseUser, on_delete=models.CASCADE, related_name="settings", primary_key=True
    )
    language = models.CharField(
        max_length=8, choices=LANGUAGE_CHOICES, null=True, blank=True, default=None
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"UserSettings(user={self.user_id}, language={self.language})"


@receiver(post_save, sender=BaseUser)
def create_profile(sender, instance: BaseUser, **kwargs):
    create_token_if_necessary(instance)
    UserSettings.objects.get_or_create(user=instance)
