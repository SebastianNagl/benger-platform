"""add export_jobs and import_jobs tables

Issue #158. Async export/import moves the bulk data plane off the API request
thread: a worker streams an export into object storage (multipart upload) and
the client downloads via a presigned URL; imports invert this. These two tables
track the lifecycle of each job (status, progress, the storage object_key, and
the artifact's expiry).

``status`` is a plain ``String`` guarded by a CHECK constraint (not a DB-native
enum) so adding a state later is a code change, not an ``ALTER TYPE``. Both
tables are created in one migration.

Idempotent — guards on table/index existence so re-running is a no-op. Mirrors
the 057 guard pattern.

Revision ID: 058_add_export_import_jobs
Revises: 057_add_task_evaluation_config_id
Create Date: 2026-06-01
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


revision = "058_add_export_import_jobs"
down_revision = "057_add_task_evaluation_config_id"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _table_exists("export_jobs"):
        op.create_table(
            "export_jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "requested_by",
                sa.String(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("format", sa.String(), nullable=False),
            sa.Column(
                "status", sa.String(), nullable=False, server_default="pending"
            ),
            sa.Column("object_key", sa.String(), nullable=True),
            sa.Column("byte_size", sa.BigInteger(), nullable=True),
            sa.Column(
                "progress",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_export_jobs_status",
            ),
            sa.CheckConstraint(
                "progress >= 0 AND progress <= 100",
                name="ck_export_jobs_progress_range",
            ),
        )
    _create_index_if_missing(
        "ix_export_jobs_project_id", "export_jobs", ["project_id"]
    )
    _create_index_if_missing(
        "ix_export_jobs_requested_by", "export_jobs", ["requested_by"]
    )

    if not _table_exists("import_jobs"):
        op.create_table(
            "import_jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "requested_by",
                sa.String(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("format", sa.String(), nullable=True),
            sa.Column(
                "status", sa.String(), nullable=False, server_default="pending"
            ),
            sa.Column("object_key", sa.String(), nullable=False),
            sa.Column("byte_size", sa.BigInteger(), nullable=True),
            sa.Column(
                "progress",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "result",
                postgresql.JSONB(),
                nullable=True,
            ),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_import_jobs_status",
            ),
            sa.CheckConstraint(
                "progress >= 0 AND progress <= 100",
                name="ck_import_jobs_progress_range",
            ),
        )
    _create_index_if_missing(
        "ix_import_jobs_project_id", "import_jobs", ["project_id"]
    )
    _create_index_if_missing(
        "ix_import_jobs_requested_by", "import_jobs", ["requested_by"]
    )


def downgrade() -> None:
    if _table_exists("import_jobs"):
        op.drop_table("import_jobs")
    if _table_exists("export_jobs"):
        op.drop_table("export_jobs")
