"""add projects.allow_solution_upload

Lets a project switch off handing in an answer as a file (the overlay's
solution upload, which also sits behind the ``solution_upload`` feature
flag). The overlay hides the writer's upload button and refuses the upload
when this is FALSE; uploads an admin makes on someone's behalf stay
possible.

- TRUE (default): uploads work as before (where the flag allows them).
- FALSE: the writer cannot upload a file as their answer.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 124_project_allow_solution_upload
Revises: 123_project_allow_external_paste
Create Date: 2026-11-02
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "124_project_allow_solution_upload"
down_revision = "123_project_allow_external_paste"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "allow_solution_upload"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
