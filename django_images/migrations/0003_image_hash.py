# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_images', '0002_auto_20180826_0814'),
    ]

    operations = [
        migrations.AddField(
            model_name='image',
            name='hash',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=32, null=True),
        ),
    ]
