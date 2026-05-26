"""add evaluation_config_id column to task_evaluations

Issue #111. ``task_evaluations.field_name`` was overloaded as the sole carrier
of the evaluation config id — workers encode it as
``"{config_id}|{pred_field}|{ref_field}"`` and every downstream reader has to
``split('|', 1)`` on the string. This migration adds a discrete
``evaluation_config_id`` column (indexed, nullable) so subsequent read paths
can filter cleanly without parsing.

The backfill rewrites pipe-encoded rows from the existing ``field_name``
contents. Bare-name legacy rows (no ``|`` in ``field_name``) stay NULL —
that's documented behavior in ``services/workers/tasks.py::_normalize_field_key``
(legacy single-config projects didn't have a config id to preserve).

Idempotent — guards on column/index existence; the UPDATE uses an
``evaluation_config_id IS NULL`` filter so re-running the migration is a
no-op once the backfill has run.

Revision ID: 057_add_task_evaluation_config_id
Revises: 056_notifications_cursor_index
Create Date: 2026-05-26
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "057_add_task_evaluation_config_id"
down_revision = "056_notifications_cursor_index"
branch_labels = None
depends_on = None


COLUMN_NAME = "evaluation_config_id"
INDEX_NAME = "ix_task_evaluations_evaluation_config_id"
TABLE_NAME = "task_evaluations"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(), nullable=True),
        )

    if not _index_exists(TABLE_NAME, INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            [COLUMN_NAME],
        )

    # Backfill pipe-encoded rows. Bare-name legacy rows stay NULL by design
    # (documented in workers/tasks.py::_normalize_field_key). The IS NULL
    # guard keeps this idempotent on re-runs.
    op.execute(
        """
        UPDATE task_evaluations
           SET evaluation_config_id = split_part(field_name, '|', 1)
         WHERE field_name LIKE '%|%'
           AND evaluation_config_id IS NULL
        """
    )


def downgrade() -> None:
    if _index_exists(TABLE_NAME, INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
