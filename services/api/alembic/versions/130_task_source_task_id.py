"""Remember where an imported task came from: ``tasks.source_task_id``.

Every project import gives each task a fresh id. Without a record of the
exported id, results produced on a copy of a project (a benchmark run on a
local copy of a production project, say) could not be merged back into the
original: the importer had no way to tell which original task an exported task
was. The column holds the id of the task the row was imported from, carried
through repeated hops (the original's id, not an intermediate copy's), and is
NULL for tasks created on this deployment.

Schema is platform-owned. Pure additive and idempotent: guarded by an
inspector check, so a database built from the models (the test DB) runs it as
a no-op.

Revision ID: 130_task_source_task_id
Revises: 129_lti_openolat_and_nrps
Create Date: 2026-11-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "130_task_source_task_id"
down_revision = "129_lti_openolat_and_nrps"
branch_labels = None
depends_on = None

_TABLE = "tasks"
_COLUMN = "source_task_id"


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if _column_exists(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
