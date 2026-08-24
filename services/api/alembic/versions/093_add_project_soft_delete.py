"""Soft delete for projects: deleted_at + deleted_by.

Non-superadmin "delete" now only stamps ``deleted_at`` (the project becomes
invisible to everyone, all cascaded data survives); superadmins restore or
purge from the deleted-projects view. Indexed ``deleted_at`` because every
visibility query filters on it.

Idempotent — mirrors the 067/092 guard pattern (inspector check before DDL).

Revision ID: 093_add_project_soft_delete
Revises: 092_add_project_icon
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "093_add_project_soft_delete"
down_revision = "092_add_project_icon"
branch_labels = None
depends_on = None

TABLE_NAME = "projects"


def _has_column(name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == name for c in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    if not _has_column("deleted_at"):
        op.add_column(
            TABLE_NAME, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index("ix_projects_deleted_at", TABLE_NAME, ["deleted_at"])
    if not _has_column("deleted_by"):
        op.add_column(TABLE_NAME, sa.Column("deleted_by", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("deleted_by"):
        op.drop_column(TABLE_NAME, "deleted_by")
    if _has_column("deleted_at"):
        op.drop_index("ix_projects_deleted_at", table_name=TABLE_NAME)
        op.drop_column(TABLE_NAME, "deleted_at")
