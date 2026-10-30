"""add projects.enable_prompts

Fourth per-project feature-visibility flag (next to enable_annotation /
enable_generation / enable_evaluation from 032): controls whether the
"Prompts" card renders on the project detail page. The card collects the
generation prompt structures (system + instruction prompt) and the
evaluation prompts of the configured judge methods in one place. Pure UI
gate like the other three; the data stays where it is.

Existing projects get TRUE so the new card shows up everywhere.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 121_project_enable_prompts
Revises: 120_group_jurisdiction
Create Date: 2026-10-30
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "121_project_enable_prompts"
down_revision = "120_group_jurisdiction"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "enable_prompts"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
