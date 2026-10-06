"""LTI resource links can be bound to one task of an exam

``lti_resource_links.task_id`` (nullable, FK ``tasks.id`` ON DELETE SET NULL)
scopes an LMS activity to one task of a Klausurensammlung, so each activity
gets exactly that task's grade. NULL keeps the old meaning: the link covers
the whole exam, which is only valid while the exam has exactly one task.

Backfill: every link whose exam has exactly one task is bound to that task,
so imports into those exams stop being blocked once the exam grows. Links on
exams with zero or several tasks stay NULL.

Downgrade drops the index and the column. Every step is guarded, so a re-run
is a no-op.

Revision ID: 112_lti_resource_link_task
Revises: 111_group_membership_roles
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op


revision = "112_lti_resource_link_task"
down_revision = "111_group_membership_roles"
branch_labels = None
depends_on = None

_TABLE = "lti_resource_links"
_COLUMN = "task_id"
_INDEX = "ix_lti_resource_links_task"
# The name Postgres gives the unnamed FK that create_all emits for the model.
_FK = "lti_resource_links_task_id_fkey"

# Bind every still-unbound link to the only task of its exam. Exams with zero
# or several tasks keep NULL (whole-exam link or legacy collection link).
BACKFILL_SQL = """
    UPDATE lti_resource_links rl
       SET task_id = only_task.task_id
      FROM (
            SELECT project_id, MIN(id) AS task_id
              FROM tasks
             GROUP BY project_id
            HAVING COUNT(*) = 1
           ) AS only_task
     WHERE rl.task_id IS NULL
       AND rl.project_id IS NOT NULL
       AND rl.project_id = only_task.project_id
"""


def _columns() -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(_TABLE)}


def _indexes() -> set:
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    if _COLUMN not in _columns():
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))
        op.create_foreign_key(
            _FK, _TABLE, "tasks", [_COLUMN], ["id"], ondelete="SET NULL"
        )
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, [_COLUMN])

    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _columns():
        # Dropping the column drops its FK constraint with it.
        op.drop_column(_TABLE, _COLUMN)
