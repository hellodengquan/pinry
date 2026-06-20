from django.db import migrations, models
import django.db.models.deletion
import json


BACKUP_TABLE_NAME = 'core_boardcollaborator_backup_0011'


def get_permission_choices():
    return [
        ('view', 'View'),
        ('edit', 'Edit'),
        ('manage', 'Manage'),
    ]


def _ensure_backup_table(schema_editor):
    backup_fields = [
        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
        ('board_id', models.IntegerField()),
        ('user_id', models.IntegerField()),
        ('permission', models.CharField(max_length=10, choices=get_permission_choices(), default='view')),
        ('payload', models.TextField(default='{}')),
    ]
    backup_model = type(
        'BoardCollaboratorBackup0011',
        (models.Model,),
        {
            '__module__': 'core.migrations',
            'Meta': type('Meta', (), {'app_label': 'core', 'db_table': BACKUP_TABLE_NAME}),
        },
    )
    if not schema_editor.connection.introspection.table_name_converter(BACKUP_TABLE_NAME) in \
            schema_editor.connection.introspection.table_names():
        schema_editor.create_model(backup_model)
    return backup_model


def _forward_migrate(apps, schema_editor):
    backup_model = _ensure_backup_table(schema_editor)
    backup_exists = schema_editor.connection.introspection.table_name_converter(BACKUP_TABLE_NAME) in \
        schema_editor.connection.introspection.table_names()

    if backup_exists and backup_model.objects.exists():
        BoardCollaborator = apps.get_model('core', 'BoardCollaborator')
        for record in backup_model.objects.all():
            BoardCollaborator.objects.get_or_create(
                board_id=record.board_id,
                user_id=record.user_id,
                defaults={
                    'permission': record.permission,
                },
            )
        backup_model.objects.all().delete()


def _backward_migrate(apps, schema_editor):
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')
    backup_model = _ensure_backup_table(schema_editor)

    for collab in BoardCollaborator.objects.all():
        backup_model.objects.create(
            board_id=collab.board_id,
            user_id=collab.user_id,
            permission=collab.permission,
            payload=json.dumps({
                'id': collab.id,
                'board_id': collab.board_id,
                'user_id': collab.user_id,
                'permission': collab.permission,
            }),
        )


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
            code=_forward_migrate,
            reverse_code=_backward_migrate,
        ),
    ]
