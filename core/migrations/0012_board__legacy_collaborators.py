from django.db import migrations, models
import json


def _board_to_legacy_field_forward(apps, schema_editor):
    Board = apps.get_model('core', 'Board')
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')

    for board in Board.objects.all():
        if board is None or board.id is None:
            continue
        legacy_data = []
        for collab in BoardCollaborator.objects.filter(board=board):
            if collab is None or collab.user_id is None:
                continue
            legacy_data.append({
                'user_id': collab.user_id,
                'permission': collab.permission or 'view',
            })
        if legacy_data:
            try:
                board._legacy_collaborators = json.dumps(legacy_data)
                board.save(update_fields=['_legacy_collaborators'])
            except Exception:
                pass


def _board_to_legacy_field_backward(apps, schema_editor):
    Board = apps.get_model('core', 'Board')
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')

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
                    board=board,
                    user_id=user_id,
                    defaults={
                        'permission': item.get('permission', 'view'),
                    },
                )
            except Exception:
                continue


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_boardcollaborator'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='_legacy_collaborators',
            field=models.TextField(
                default='[]',
                blank=True,
                help_text='Legacy field for collaborator data backup during migration rollback.',
            ),
        ),
        migrations.RunPython(
            code=_board_to_legacy_field_forward,
            reverse_code=_board_to_legacy_field_backward,
        ),
    ]
