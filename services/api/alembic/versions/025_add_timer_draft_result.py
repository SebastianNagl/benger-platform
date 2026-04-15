"""Add draft_result to annotation_timer_sessions

Stores periodic draft snapshots from the client so the server-side
auto-submit (Celery) can submit actual progress instead of empty annotations
when a user leaves before the timer expires.

Revision ID: 025_add_timer_draft_result
Revises: 024_add_require_confirm_before_submit
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "025_add_timer_draft_result"
down_revision = "025_add_skip_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotation_timer_sessions",
        sa.Column("draft_result", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotation_timer_sessions", "draft_result")
