"""Add korrektur_assigned to the notificationtype Postgres enum.

The Korrektur item-assignment endpoints (proprietary, in extended) dispatch
through the platform's NotificationService, which writes to a column typed
as the `notificationtype` Postgres enum. Adding a new value to that enum
must happen via migration since `ALTER TYPE ... ADD VALUE` cannot run
inside a transaction.

Revision ID: 034_add_korrektur_assigned_notification_type
Revises: 033_task_assignment_polymorphic_target
Create Date: 2026-05-02
"""

from alembic import op


revision = "034_add_korrektur_assigned_notification_type"
down_revision = "033_task_assignment_polymorphic_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'korrektur_assigned'"
    )


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily.
    pass
