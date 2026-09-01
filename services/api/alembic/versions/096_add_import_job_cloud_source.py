"""add import_jobs.source_connection_id (cloud-import source)

A cloud import pulls its artifact from a customer bucket (an
``org_storage_connections`` row) instead of our own object storage.
``source_connection_id`` records which connection a job read from —
nullable because plain upload-based imports have no connection, and
SET NULL on connection delete so the job history survives while the
worker (and the history endpoint) can tell "storage connection removed".
Indexed: the cloud-import history endpoint filters on it.

Idempotent — mirrors the 093/095 guard pattern; the index carries its own
guard so a drift-created column still gets it.

Revision ID: 096_add_import_job_cloud_source
Revises: 095_add_org_storage_connections
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "096_add_import_job_cloud_source"
down_revision = "095_add_org_storage_connections"
branch_labels = None
depends_on = None

TABLE_NAME = "import_jobs"
COLUMN_NAME = "source_connection_id"
INDEX_NAME = "ix_import_jobs_source_connection_id"


def _has_column() -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME))


def _has_index() -> bool:
    inspector = inspect(op.get_bind())
    return any(ix["name"] == INDEX_NAME for ix in inspector.get_indexes(TABLE_NAME))


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.String(),
                sa.ForeignKey(
                    "org_storage_connections.id", ondelete="SET NULL"
                ),
                nullable=True,
            ),
        )
    if not _has_index():
        op.create_index(INDEX_NAME, TABLE_NAME, [COLUMN_NAME])


def downgrade() -> None:
    if _has_index():
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    if _has_column():
        op.drop_column(TABLE_NAME, COLUMN_NAME)
