"""Soft delete for projects: deleted_at + deleted_by.

Non-superadmin "delete" now only stamps ``deleted_at`` (the project becomes
invisible to everyone, all cascaded data survives); superadmins restore or
purge from the deleted-projects view. Partial index on ``deleted_at IS NOT
NULL``: the hot queries filter ``IS NULL`` (which no btree on a mostly-NULL
column helps), so the index only needs to serve the rare superadmin
``only_deleted`` listing — and stays near-empty.

Idempotent — mirrors the 067/092 guard pattern; the index carries its OWN
guard so a drift-created column (test fixtures' ADD COLUMN IF NOT EXISTS)
still gets it.

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
INDEX_NAME = "ix_projects_deleted_at"


def _has_column(name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == name for c in inspector.get_columns(TABLE_NAME))


def _has_index() -> bool:
    inspector = inspect(op.get_bind())
    return any(ix["name"] == INDEX_NAME for ix in inspector.get_indexes(TABLE_NAME))


def upgrade() -> None:
    if not _has_column("deleted_at"):
        op.add_column(
            TABLE_NAME, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
    if not _has_column("deleted_by"):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "deleted_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _has_index():
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["deleted_at"],
            postgresql_where=sa.text("deleted_at IS NOT NULL"),
        )


def downgrade() -> None:
    if _has_index():
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    if _has_column("deleted_by"):
        op.drop_column(TABLE_NAME, "deleted_by")
    if _has_column("deleted_at"):
        op.drop_column(TABLE_NAME, "deleted_at")
