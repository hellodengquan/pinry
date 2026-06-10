from __future__ import unicode_literals

from django.apps import AppConfig
from django.db import models


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.dispatch import receiver
        from django_images.models import Thumbnail
        from pinry_plugins.events import dispatch_event, EventType

        @receiver(models.signals.pre_save, sender=Thumbnail)
        def _thumbnail_pre_save(sender, instance, **kwargs):
            if instance.pk is None:
                dispatch_event(
                    EventType.THUMBNAIL_PRE_CREATE,
                    payload={"thumbnail_instance": instance, "instance": instance},
                )

        @receiver(models.signals.post_save, sender=Thumbnail)
        def _thumbnail_post_save(sender, instance, created, **kwargs):
            if created:
                dispatch_event(
                    EventType.THUMBNAIL_POST_CREATE,
                    payload={"thumbnail_instance": instance, "instance": instance},
                )
