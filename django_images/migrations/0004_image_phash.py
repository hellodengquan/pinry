# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_images', '0003_image_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='image',
            name='phash',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=16, null=True),
        ),
    ]
