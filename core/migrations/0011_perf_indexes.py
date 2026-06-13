from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_auto_20210311_1521'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['private', 'submitter'], name='pin_priv_subm_idx'),
        ),
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['submitter'], name='pin_submitter_idx'),
        ),
        migrations.AddIndex(
            model_name='pin',
            index=models.Index(fields=['-published'], name='pin_pub_desc_idx'),
        ),
        migrations.AddIndex(
            model_name='board',
            index=models.Index(fields=['private', 'submitter'], name='board_priv_subm_idx'),
        ),
        migrations.AddIndex(
            model_name='board',
            index=models.Index(fields=['-published'], name='board_pub_desc_idx'),
        ),
    ]
