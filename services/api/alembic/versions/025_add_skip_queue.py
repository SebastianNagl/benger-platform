"""Add skip_queue to projects

Project-level setting that controls what happens when an annotator skips
a task. Aligned with Label Studio's skip_queue behavior.

Values: requeue_for_me, requeue_for_others, ignore_skipped

Revision ID: 025_add_skip_queue
Revises: 024_add_require_confirm_before_submit
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "025_add_skip_queue"
down_revision = "024_add_require_confirm_before_submit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "skip_queue",
            sa.String(),
            nullable=False,
            server_default="requeue_for_others",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "skip_queue")
