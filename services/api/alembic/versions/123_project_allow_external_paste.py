"""add projects.allow_external_paste

Lets a project forbid pasting text that was copied outside BenGER into the
annotation interface (exam-style projects: no answers prepared in another
document or a chatbot). Enforcement is in the labeling frontend, which only
accepts pastes and drops whose text was copied inside the app.

- TRUE (default): pasting is allowed, exactly the previous behaviour.
- FALSE: external pastes and drops are blocked in the labeling interface.

Existing projects get TRUE through the server default, so nothing changes
until someone unticks the switch.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 123_project_allow_external_paste
Revises: 122_korrektur_feedback_human_run_singleton
Create Date: 2026-11-02
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "123_project_allow_external_paste"
down_revision = "122_korrektur_feedback_human_run_singleton"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "allow_external_paste"


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
