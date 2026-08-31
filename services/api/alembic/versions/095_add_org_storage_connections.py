"""add org_storage_connections table

Org-level S3-compatible storage connections (AWS S3, self-hosted MinIO, ...)
for the cloud-import flow: an org admin stores read-only bucket credentials
once, then members browse the bucket server-side and import files without
round-tripping them through the browser. Platform owns only the persistence
and the generic CRUD/browse surface; nothing proprietary lives here.

- ``endpoint_url`` NULL means the AWS default endpoint.
- ``prefix`` jails every listing/download to a sub-tree of the bucket.
- ``encrypted_access_key`` / ``encrypted_secret_key`` are Fernet ciphertext
  via the shared ``encryption_service`` — the same path as
  ``organization_api_keys.encrypted_key``.
- ``uq_org_storage_connection_name`` keeps connection names unique per org
  so the UI can address them by name.

FKs: organization CASCADE (connections die with their org), created_by
SET NULL (audit hint only).

Idempotent — guards on table existence; safe to re-run.

Revision ID: 095_add_org_storage_connections
Revises: 094_backfill_project_kind
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "095_add_org_storage_connections"
down_revision = "094_backfill_project_kind"
branch_labels = None
depends_on = None

TABLE_NAME = "org_storage_connections"


def _table_exists() -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return TABLE_NAME in insp.get_table_names()


def upgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column(
            "organization_id",
            sa.String(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("endpoint_url", sa.String(), nullable=True),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False, server_default=""),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column(
            "use_ssl", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("encrypted_access_key", sa.Text(), nullable=False),
        sa.Column("encrypted_secret_key", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_org_storage_connection_name"
        ),
    )


def downgrade() -> None:
    if _table_exists():
        op.drop_table(TABLE_NAME)
