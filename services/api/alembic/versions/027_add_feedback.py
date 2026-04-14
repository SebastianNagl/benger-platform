"""Add feedback workflow with comments and highlights

Adds project-level feedback settings and a feedback_comments table
for threaded, highlight-anchored comments on annotations, generations,
and evaluations. Also adds denormalized feedback counts to tasks.

Revision ID: 027_add_feedback
Revises: 026_add_task_drafts
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "027_add_feedback"
down_revision = "026_add_task_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add feedback settings to projects
    op.add_column("projects", sa.Column("feedback_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("projects", sa.Column("feedback_config", JSONB, nullable=True))

    # Add denormalized feedback counts to tasks
    op.add_column("tasks", sa.Column("feedback_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("unresolved_feedback_count", sa.Integer(), nullable=False, server_default="0"))

    # Create feedback_comments table
    op.create_table(
        "feedback_comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("feedback_comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("highlight_start", sa.Integer(), nullable=True),
        sa.Column("highlight_end", sa.Integer(), nullable=True),
        sa.Column("highlight_text", sa.Text(), nullable=True),
        sa.Column("highlight_label", sa.String(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes
    op.create_index("ix_feedback_comments_project_task", "feedback_comments", ["project_id", "task_id"])
    op.create_index("ix_feedback_comments_target", "feedback_comments", ["target_type", "target_id"])
    op.create_index("ix_feedback_comments_parent", "feedback_comments", ["parent_id"])
    op.create_index("ix_feedback_comments_created_by", "feedback_comments", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_feedback_comments_created_by")
    op.drop_index("ix_feedback_comments_parent")
    op.drop_index("ix_feedback_comments_target")
    op.drop_index("ix_feedback_comments_project_task")
    op.drop_table("feedback_comments")
    op.drop_column("tasks", "unresolved_feedback_count")
    op.drop_column("tasks", "feedback_count")
    op.drop_column("projects", "feedback_config")
    op.drop_column("projects", "feedback_enabled")
