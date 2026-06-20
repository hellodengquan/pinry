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
    table_names = [
        schema_editor.connection.introspection.table_name_converter(t)
        for t in schema_editor.connection.introspection.table_names()
    ]
    if schema_editor.connection.introspection.table_name_converter(BACKUP_TABLE_NAME) not in table_names:
        schema_editor.create_model(backup_model)
    return backup_model


def _board_has_legacy_field(schema_editor):
    table_names = [
        schema_editor.connection.introspection.table_name_converter(t)
        for t in schema_editor.connection.introspection.table_names()
    ]
    board_table = schema_editor.connection.introspection.table_name_converter('core_board')
    if board_table not in table_names:
        return False
    cursor = schema_editor.connection.cursor()
    columns = [
        col[0] for col in schema_editor.connection.introspection.get_table_description(cursor, board_table)
    ]
    return '_legacy_collaborators' in columns


def _forward_migrate(apps, schema_editor):
    backup_model = _ensure_backup_table(schema_editor)
    table_names = [
        schema_editor.connection.introspection.table_name_converter(t)
        for t in schema_editor.connection.introspection.table_names()
    ]
    backup_exists = schema_editor.connection.introspection.table_name_converter(BACKUP_TABLE_NAME) in table_names

    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')

    if backup_exists and backup_model.objects.exists():
        for record in backup_model.objects.all():
            if not record.board_id or not record.user_id:
                continue
            try:
                BoardCollaborator.objects.get_or_create(
                    board_id=record.board_id,
                    user_id=record.user_id,
                    defaults={
                        'permission': record.permission or 'view',
                    },
                )
            except Exception:
                continue
        try:
            backup_model.objects.all().delete()
        except Exception:
            pass

    if _board_has_legacy_field(schema_editor):
        Board = apps.get_model('core', 'Board')
        for board in Board.objects.all():
            if board is None or board.id is None:
                continue
            try:
                legacy_data = json.loads(board._legacy_collaborators)
            except (ValueError, TypeError):
                legacy_data = []
            if not isinstance(legacy_data, list):
                continue
            for item in legacy_data:
                if not isinstance(item, dict):
                    continue
                user_id = item.get('user_id')
                if user_id is None:
                    continue
                try:
                    BoardCollaborator.objects.get_or_create(
                        board_id=board.id,
                        user_id=user_id,
                        defaults={
                            'permission': item.get('permission', 'view'),
                        },
                    )
                except Exception:
                    continue
            if legacy_data:
                try:
                    board._legacy_collaborators = '[]'
                    board.save(update_fields=['_legacy_collaborators'])
                except Exception:
                    pass


def _backward_migrate(apps, schema_editor):
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')
    backup_model = _ensure_backup_table(schema_editor)

    collab_data_by_board = {}
    for collab in BoardCollaborator.objects.all():
        if collab is None or collab.board_id is None or collab.user_id is None:
            continue
        try:
            backup_model.objects.create(
                board_id=collab.board_id,
                user_id=collab.user_id,
                permission=collab.permission or 'view',
                payload=json.dumps({
                    'id': collab.id,
                    'board_id': collab.board_id,
                    'user_id': collab.user_id,
                    'permission': collab.permission or 'view',
                }),
            )
        except Exception:
            continue
        if collab.board_id not in collab_data_by_board:
            collab_data_by_board[collab.board_id] = []
        collab_data_by_board[collab.board_id].append({
            'user_id': collab.user_id,
            'permission': collab.permission or 'view',
        })

    if _board_has_legacy_field(schema_editor):
        Board = apps.get_model('core', 'Board')
        for board in Board.objects.all():
            if board is None or board.id is None:
                continue
            data = collab_data_by_board.get(board.id, [])
            try:
                existing = json.loads(board._legacy_collaborators)
                if not isinstance(existing, list):
                    existing = []
            except (ValueError, TypeError):
                existing = []
            existing_user_ids = {
                item.get('user_id') for item in existing if isinstance(item, dict)
            }
            combined = list(existing)
            for item in data:
                if item.get('user_id') in existing_user_ids:
                    continue
                combined.append(item)
            try:
                board._legacy_collaborators = json.dumps(combined)
                board.save(update_fields=['_legacy_collaborators'])
            except Exception:
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
            code=_forward_migrate,
            reverse_code=_backward_migrate,
        ),
    ]
