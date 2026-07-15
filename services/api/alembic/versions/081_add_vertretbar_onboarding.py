"""add users.vertretbar_onboarding_completed_at

Vertretbar new-user plan-choice greeting (extended one-time modal). Persists
server-side that the student has made their Free-vs-Subscription choice, so the
once-only modal follows them across devices/browsers. Nullable timestamp
(NULL = not yet shown; stamped = chosen).

Idempotent — guards on column existence; safe to re-run. Mirrors the 067
guard pattern (users.preferred_ui_mode).

Revision ID: 081_add_vertretbar_onboarding
Revises: 080_add_custom_llm_models
Create Date: 2026-07-15
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "081_add_vertretbar_onboarding"
down_revision = "080_add_custom_llm_models"
branch_labels = None
depends_on = None


TABLE_NAME = "users"
COLUMN_NAME = "vertretbar_onboarding_completed_at"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
