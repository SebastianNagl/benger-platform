"""handwritten solution uploads: submission_ocr_jobs + OCR columns

- New table ``submission_ocr_jobs``: one transcription of handwritten pages
  (photos or scans) by a vision model, run by an async worker task. ``mode``
  is own | on_behalf | pending; ``user_id`` may only be NULL for ``pending``
  (staff uploads for someone without an account yet).
- ``submission_files.ocr_job_id`` + ``page_index``: the stored pages of a job.
- ``projects.handwriting_ocr_enabled`` (NOT NULL, default FALSE) switches
  handwritten uploads on; ``projects.handwriting_ocr_model`` overrides the
  model (NULL = the organization's default in its settings JSON).

Idempotent: guards on table/column existence, safe to re-run (091 pattern).

Revision ID: 125_submission_ocr_jobs
Revises: 124_project_allow_solution_upload
Create Date: 2026-11-02
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


revision = "125_submission_ocr_jobs"
down_revision = "124_project_allow_solution_upload"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    if not _has_table("submission_ocr_jobs"):
        op.create_table(
            "submission_ocr_jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "task_id", sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "user_id", sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
            ),
            sa.Column(
                "requested_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("mode", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column(
                "page_keys", postgresql.JSONB(), nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pages_ocr", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("model_id", sa.String(255), nullable=True),
            sa.Column(
                "billed_org_id", sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column(
                "annotation_id", sa.String(),
                sa.ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "auto_persisted", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "mode IN ('own', 'on_behalf', 'pending')", name="ck_submission_ocr_jobs_mode"
            ),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'done', 'failed')",
                name="ck_submission_ocr_jobs_status",
            ),
            sa.CheckConstraint(
                "user_id IS NOT NULL OR mode = 'pending'",
                name="ck_submission_ocr_jobs_user_unless_pending",
            ),
        )
    if not _has_index("submission_ocr_jobs", "ix_submission_ocr_jobs_task_user"):
        op.create_index(
            "ix_submission_ocr_jobs_task_user",
            "submission_ocr_jobs",
            ["task_id", "user_id", "created_at"],
        )
    if not _has_index("submission_ocr_jobs", "ix_submission_ocr_jobs_project"):
        op.create_index(
            "ix_submission_ocr_jobs_project", "submission_ocr_jobs", ["project_id"]
        )

    if not _has_column("submission_files", "ocr_job_id"):
        op.add_column(
            "submission_files",
            sa.Column(
                "ocr_job_id", sa.String(),
                sa.ForeignKey(
                    "submission_ocr_jobs.id", ondelete="SET NULL",
                    name="fk_submission_files_ocr_job_id",
                ),
                nullable=True,
            ),
        )
    if not _has_column("submission_files", "page_index"):
        op.add_column("submission_files", sa.Column("page_index", sa.Integer(), nullable=True))
    if not _has_index("submission_files", "ix_submission_files_ocr_job"):
        op.create_index("ix_submission_files_ocr_job", "submission_files", ["ocr_job_id"])

    if not _has_column("projects", "handwriting_ocr_enabled"):
        op.add_column(
            "projects",
            sa.Column(
                "handwriting_ocr_enabled", sa.Boolean(), nullable=False,
                server_default=sa.false(),
            ),
        )
    if not _has_column("projects", "handwriting_ocr_model"):
        op.add_column(
            "projects", sa.Column("handwriting_ocr_model", sa.String(255), nullable=True)
        )


def downgrade() -> None:
    if _has_column("projects", "handwriting_ocr_model"):
        op.drop_column("projects", "handwriting_ocr_model")
    if _has_column("projects", "handwriting_ocr_enabled"):
        op.drop_column("projects", "handwriting_ocr_enabled")
    if _has_index("submission_files", "ix_submission_files_ocr_job"):
        op.drop_index("ix_submission_files_ocr_job", table_name="submission_files")
    if _has_column("submission_files", "page_index"):
        op.drop_column("submission_files", "page_index")
    if _has_column("submission_files", "ocr_job_id"):
        op.drop_column("submission_files", "ocr_job_id")
    if _has_table("submission_ocr_jobs"):
        op.drop_table("submission_ocr_jobs")
