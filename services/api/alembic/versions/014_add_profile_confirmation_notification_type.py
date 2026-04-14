"""Add profile_confirmation_due notification type

Revision ID: 014_profile_confirm_notif
Revises: 013_fix_grade_column_types
Create Date: 2026-02-22

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "014_profile_confirm_notif"
down_revision = "013_fix_grade_column_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen alembic_version column to avoid future truncation issues
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(32),
    )

    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    # Commit the current transaction first.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'profile_confirmation_due'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(32),
        existing_type=sa.String(128),
    )
