"""Add the evaluation_received_* values to the notificationtype Postgres enum.

A new grading on an annotation now notifies the annotator. There is one
notification type per grading source (human Korrektur, immediate AI grading,
batch evaluation run), so users can choose each one in their notification
settings. ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction, so the
values are added the same way as in 034.

Revision ID: 104_add_evaluation_received_notification_types
Revises: 103_import_job_organization_id
Create Date: 2026-09-15
"""

from alembic import op


revision = "104_add_evaluation_received_notification_types"
down_revision = "103_import_job_organization_id"
branch_labels = None
depends_on = None

NEW_VALUES = (
    "evaluation_received_human",
    "evaluation_received_immediate",
    "evaluation_received_batch",
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    op.execute("COMMIT")
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily.
    pass
