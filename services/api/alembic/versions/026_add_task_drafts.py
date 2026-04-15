"""Add task_drafts table for server-side draft auto-save

Stores annotation drafts for all projects (not just timer projects).
Survives browser crashes, device switches, and cache clears.
Drafts are deleted on annotation submission.

Revision ID: 026_add_task_drafts
Revises: 025_add_timer_draft_result
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "026_add_task_drafts"
down_revision = "025_add_timer_draft_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_drafts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("draft_result", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "user_id", name="unique_task_draft"),
    )
    op.create_index("ix_task_drafts_project_user", "task_drafts", ["project_id", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_task_drafts_project_user")
    op.drop_table("task_drafts")
