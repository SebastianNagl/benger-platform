"""rubric_generation_jobs: one row per Bewertungsbogen generation job

- New table ``rubric_generation_jobs``: the durable record of a
  ``tasks.generate_bewertungsbogen`` job. The extended API writes the row at
  dispatch, its status poll and the Celery task wrapper update it, an
  extended beat sweep marks a job no worker finished in time ``lost``. The
  failure reason (``error_code``, ``error_message``, ``error_stage``,
  ``attempt_errors``) is what the task panel and the superadmin list
  (``GET /api/admin/rubric-generation-jobs``) show.
- Every foreign key is ``ON DELETE SET NULL``: rows outlive the project,
  task, user, organization and sheet because they are the record of how
  often generation succeeds. ``celery_task_id`` is unique (NULL when the
  dispatch itself failed); the writer upserts on it.

Pure additive and idempotent: table and indexes are guarded by inspector
checks, so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 136_rubric_generation_jobs
Revises: 135_custom_model_request_timeout
Create Date: 2026-11-16
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "136_rubric_generation_jobs"
down_revision = "135_custom_model_request_timeout"
branch_labels = None
depends_on = None

_TABLE = "rubric_generation_jobs"

_INDEXES = (
    ("ix_rubric_generation_jobs_created", ["created_at"]),
    ("ix_rubric_generation_jobs_status_created", ["status", "created_at"]),
    ("ix_rubric_generation_jobs_project_created", ["project_id", "created_at"]),
    ("ix_rubric_generation_jobs_task_created", ["task_id", "created_at"]),
    ("ix_rubric_generation_jobs_user_created", ["user_id", "created_at"]),
    ("ix_rubric_generation_jobs_org_created", ["organization_id", "created_at"]),
)


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def _fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(target, ondelete="SET NULL")


def upgrade() -> None:
    if not _has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("celery_task_id", sa.String(255), nullable=True, unique=True),
            sa.Column("entry_point", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("project_id", sa.String(), _fk("projects.id"), nullable=True),
            sa.Column("task_id", sa.String(), _fk("tasks.id"), nullable=True),
            sa.Column("user_id", sa.String(), _fk("users.id"), nullable=True),
            sa.Column("organization_id", sa.String(), _fk("organizations.id"), nullable=True),
            sa.Column("rubric_id", sa.String(), _fk("task_rubrics.id"), nullable=True),
            sa.Column("retry_of", sa.String(), _fk("rubric_generation_jobs.id"), nullable=True),
            sa.Column("generator_model_id", sa.String(255), nullable=True),
            sa.Column("prompt_key", sa.String(255), nullable=True),
            sa.Column("contract", sa.String(64), nullable=True),
            sa.Column("contract_version", sa.String(64), nullable=True),
            sa.Column("prompt_sha256", sa.String(64), nullable=True),
            sa.Column("validator_sha256", sa.String(64), nullable=True),
            sa.Column("app_version", sa.String(128), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("error_stage", sa.String(32), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=True),
            sa.Column("attempt_errors", postgresql.JSONB(), nullable=True),
            sa.Column("fallback", sa.String(64), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column(
                "details", postgresql.JSONB(), nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.CheckConstraint(
                "entry_point IN ('wizard', 'bulk', 'task', 'proposal')",
                name="ck_rubric_generation_jobs_entry_point",
            ),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'completed', 'failed', 'lost')",
                name="ck_rubric_generation_jobs_status",
            ),
        )
    for name, columns in _INDEXES:
        if not _has_index(_TABLE, name):
            op.create_index(name, _TABLE, columns)


def downgrade() -> None:
    if _has_table(_TABLE):
        op.drop_table(_TABLE)
