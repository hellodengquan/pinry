from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_auto_20210311_1521'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='board',
            name='is_archived',
            field=models.BooleanField(default=False),
        ),
    ]
