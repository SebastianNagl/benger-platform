"""default projects.restorable_checkpoints_enabled to true (future projects)

Restorable draft checkpoints (the append-only 5-min recovery history) ship
disabled-by-default in migration 073. This flips the column DEFAULT so every
*newly created* project opts in automatically — timed exams get a recovery
history out of the box, and a truncated/lost submission always has a checkpoint
to fall back on.

Only the column DEFAULT changes. Existing rows are intentionally left untouched
(no data UPDATE): projects already created keep whatever they were set to, so a
project someone deliberately turned off stays off. Keeps the DB default in sync
with the model ``server_default="true"`` (project_models.py) so the startup
schema validator doesn't flag a drift.

Idempotent — ALTER COLUMN ... SET DEFAULT is safe to re-run; guards on the
column existing.

Revision ID: 075_default_checkpoints_enabled
Revises: 074_add_project_access_window
Create Date: 2026-07-06
"""

from sqlalchemy import inspect

from alembic import op


revision = "075_default_checkpoints_enabled"
down_revision = "074_add_project_access_window"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "restorable_checkpoints_enabled"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.alter_column(
            TABLE_NAME,
            COLUMN_NAME,
            server_default="true",
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.alter_column(
            TABLE_NAME,
            COLUMN_NAME,
            server_default="false",
        )
