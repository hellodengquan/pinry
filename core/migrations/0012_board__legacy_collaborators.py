from django.db import migrations, models
import json


def _board_to_legacy_field_forward(apps, schema_editor):
    Board = apps.get_model('core', 'Board')
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')

    for board in Board.objects.all():
        legacy_data = []
        for collab in BoardCollaborator.objects.filter(board=board):
            legacy_data.append({
                'user_id': collab.user_id,
                'permission': collab.permission,
            })
        if legacy_data:
            board._legacy_collaborators = json.dumps(legacy_data)
            board.save(update_fields=['_legacy_collaborators'])


def _board_to_legacy_field_backward(apps, schema_editor):
    Board = apps.get_model('core', 'Board')
    BoardCollaborator = apps.get_model('core', 'BoardCollaborator')

    for board in Board.objects.all():
        try:
            legacy_data = json.loads(board._legacy_collaborators)
        except (ValueError, TypeError):
            legacy_data = []
        for item in legacy_data:
            BoardCollaborator.objects.get_or_create(
                board=board,
                user_id=item.get('user_id'),
                defaults={
                    'permission': item.get('permission', 'view'),
                },
            )


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
