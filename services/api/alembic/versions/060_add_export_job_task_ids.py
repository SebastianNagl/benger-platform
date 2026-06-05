"""add task_ids to export_jobs

Issue #158 follow-up. Async export becomes the only export path, so it must also
serve selected-task / filtered exports (previously the synchronous
``/tasks/bulk-export`` endpoint). The task-id subset is stored on the job row so
the worker can pass it to ``stream_export_json``; NULL means a whole-project
export (unchanged behaviour).

Idempotent — guards on column existence so re-running is a no-op. Mirrors the
057/058 guard pattern.

Revision ID: 060_add_export_job_task_ids
Revises: 059_user_delete_fk_ondelete
Create Date: 2026-06-05
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


revision = "060_add_export_job_task_ids"
down_revision = "059_user_delete_fk_ondelete"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("export_jobs", "task_ids"):
        op.add_column(
            "export_jobs",
            sa.Column("task_ids", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("export_jobs", "task_ids"):
        op.drop_column("export_jobs", "task_ids")
