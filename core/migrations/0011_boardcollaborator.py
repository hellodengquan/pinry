from django.db import migrations, models
import django.db.models.deletion


def get_permission_choices():
    return [
        ('view', 'View'),
        ('edit', 'Edit'),
        ('manage', 'Manage'),
    ]


def _noop_forward(apps, schema_editor):
    pass


def _noop_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_auto_20210311_1521'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoardCollaborator',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission', models.CharField(
                    choices=get_permission_choices(),
                    default='view',
                    max_length=10,
                )),
                ('board', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collaborators', to='core.Board')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='board_collaborations', to='users.User')),
            ],
            options={
                'unique_together': (('board', 'user'),),
            },
        ),
        migrations.RunPython(
            code=_noop_forward,
            reverse_code=_noop_backward,
        ),
    ]
