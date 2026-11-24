"""Add the evaluation_released value to the notificationtype Postgres enum.

A teacher who releases a grading that was held back for review now notifies
the student with a type of its own, so the student can switch it on or off
in the notification settings like every other type. ``ALTER TYPE ... ADD
VALUE`` cannot run inside a transaction, so the value is added the same way
as in 104.

Revision ID: 155_add_evaluation_released_notification_type
Revises: 154_korrektur_comment_highlight_field
Create Date: 2026-11-24
"""

from alembic import op


revision = "155_add_evaluation_released_notification_type"
down_revision = "154_korrektur_comment_highlight_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'evaluation_released'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily.
    pass
