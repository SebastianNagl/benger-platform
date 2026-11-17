"""import_jobs.object_key may be NULL once the expired upload was deleted

The daily beat task ``tasks.cleanup_expired_job_files`` deletes the
object-storage files of expired export and import jobs and then clears the
job's ``object_key``, so the job row stays as history and is not swept again.
``export_jobs.object_key`` was nullable already; ``import_jobs.object_key`` was
NOT NULL because an import's upload exists before its job is created.

Downgrade writes an empty key into the swept rows so NOT NULL can come back.

Revision ID: 141_import_job_object_key_nullable
Revises: 140_generation_cascades_and_purge_jobs
Create Date: 2026-11-17
"""

from alembic import op

revision = "141_import_job_object_key_nullable"
down_revision = "140_generation_cascades_and_purge_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE import_jobs ALTER COLUMN object_key DROP NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE import_jobs SET object_key = '' WHERE object_key IS NULL")
    op.execute("ALTER TABLE import_jobs ALTER COLUMN object_key SET NOT NULL")
