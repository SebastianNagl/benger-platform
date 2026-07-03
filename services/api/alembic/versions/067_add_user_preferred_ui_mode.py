"""add users.preferred_ui_mode

Student exam-training experience (issue #35). Persists the student/expert view
choice server-side so it follows the user across devices. Nullable
``String(16)`` ("student" / "expert" / NULL).

This is a default HINT only — never an authorization input. Expert-view gating
is always recomputed from role/org membership on every render, so a
stale/persisted value can never grant expert access.

Idempotent — guards on column existence; safe to re-run. Mirrors the 062
guard pattern.

Revision ID: 067_add_user_preferred_ui_mode
Revises: 066_add_project_share_tables
Create Date: 2026-06-25
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "067_add_user_preferred_ui_mode"
down_revision = "066_add_project_share_tables"
branch_labels = None
depends_on = None


TABLE_NAME = "users"
COLUMN_NAME = "preferred_ui_mode"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
