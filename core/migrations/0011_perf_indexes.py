from django.db import migrations, connection


PIN_INDEXES = [
    ("pin_priv_subm_idx", "core_pin", "private, submitter_id"),
    ("pin_submitter_idx", "core_pin", "submitter_id"),
    ("pin_pub_desc_idx", "core_pin", "published DESC"),
]

BOARD_INDEXES = [
    ("board_priv_subm_idx", "core_board", "private, submitter_id"),
    ("board_pub_desc_idx", "core_board", "published DESC"),
]


def _create_index_concurrently(apps, schema_editor, index_name, table_name, columns):
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}" '
            f'ON "{table_name}" ({columns})'
        )
    else:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{table_name}" ({columns})'
        )


def _drop_index_concurrently(apps, schema_editor, index_name, table_name):
    if connection.vendor == 'postgresql':
        schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"')
    else:
        schema_editor.execute(f'DROP INDEX IF EXISTS "{index_name}"')


def add_pin_indexes(apps, schema_editor):
    for name, table, cols in PIN_INDEXES:
        _create_index_concurrently(apps, schema_editor, name, table, cols)


def remove_pin_indexes(apps, schema_editor):
    for name, table, _cols in reversed(PIN_INDEXES):
        _drop_index_concurrently(apps, schema_editor, name, table)


def add_board_indexes(apps, schema_editor):
    for name, table, cols in BOARD_INDEXES:
        _create_index_concurrently(apps, schema_editor, name, table, cols)


def remove_board_indexes(apps, schema_editor):
    for name, table, _cols in reversed(BOARD_INDEXES):
        _drop_index_concurrently(apps, schema_editor, name, table)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('core', '0010_auto_20210311_1521'),
    ]

    operations = [
        migrations.RunPython(add_pin_indexes, remove_pin_indexes),
        migrations.RunPython(add_board_indexes, remove_board_indexes),
    ]
