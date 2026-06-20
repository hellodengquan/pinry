# Generated manually
import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('core', '0010_auto_20210311_1521'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaCheckAuditLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[
                    ('check', 'Check only'),
                    ('delete_orphans', 'Delete orphan files'),
                    ('fix_missing', 'Fix missing files'),
                    ('all', 'All actions'),
                ], default='check', max_length=32)),
                ('media_root', models.CharField(max_length=1024)),
                ('scan_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('max_depth', models.IntegerField(default=10)),
                ('total_files', models.IntegerField(default=0)),
                ('total_db_files', models.IntegerField(default=0)),
                ('orphan_count', models.IntegerField(default=0)),
                ('missing_count', models.IntegerField(default=0)),
                ('pins_without_image_count', models.IntegerField(default=0)),
                ('details_json', models.TextField(blank=True, default='{}')),
                ('success', models.BooleanField(default=True)),
                ('error_message', models.TextField(blank=True, default='')),
                ('initiated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='media_check_audit_logs',
                    to='users.User',
                )),
            ],
            options={
                'ordering': ['-scan_time'],
            },
        ),
        migrations.AddIndex(
            model_name='mediacheckauditlog',
            index=models.Index(fields=['scan_time'], name='core_media__scan_ti_2b1d13_idx'),
        ),
        migrations.AddIndex(
            model_name='mediacheckauditlog',
            index=models.Index(fields=['action'], name='core_media__action_a66e96_idx'),
        ),
        migrations.AddIndex(
            model_name='mediacheckauditlog',
            index=models.Index(fields=['success'], name='core_media__success_b3c9e2_idx'),
        ),
    ]
