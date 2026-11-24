"""Upload batches and grading files

Two additions for bulk uploads by staff:

- ``submission_files.purpose`` (``String(16)``, NOT NULL, server default
  ``submission``, CHECK ``submission`` | ``grading``) and
  ``submission_files.task_evaluation_id`` (nullable FK to
  ``task_evaluations.id``, ON DELETE SET NULL, indexed): besides the files a
  person handed in, the table now also holds files a grader returned with a
  grading (a corrected copy), linked to that grading's row. Existing rows
  are handed-in files and get ``submission`` from the server default.
- New table ``upload_batches``: one row per committed staff bulk upload
  (what it wrote as ``kind``, the project and optionally the task, who
  uploaded it, the stored source file, the chosen options, a report per row,
  row counts, ``status`` ``committed`` | ``undone`` with when and by whom).
  ``project_id`` cascades; ``task_id``, ``created_by`` and ``undone_by`` are
  SET NULL so the record survives.

Downgrade drops the table, the index, the constraint and both columns.
Every step is guarded, so a re-run is a no-op.

Revision ID: 156_upload_batches_and_grading_files
Revises: 155_add_evaluation_released_notification_type
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision = "156_upload_batches_and_grading_files"
down_revision = "155_add_evaluation_released_notification_type"
branch_labels = None
depends_on = None

_FILES = "submission_files"
_PURPOSE_CHECK = "ck_submission_files_purpose"
_EVALUATION_FK = "fk_submission_files_task_evaluation_id"
_EVALUATION_INDEX = "ix_submission_files_task_evaluation"
_BATCHES = "upload_batches"


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _checks(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_check_constraints(table)}


def _indexes(table: str) -> set:
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    columns = _columns(_FILES)
    if "purpose" not in columns:
        op.add_column(
            _FILES,
            sa.Column(
                "purpose", sa.String(16), nullable=False, server_default="submission"
            ),
        )
    if _PURPOSE_CHECK not in _checks(_FILES):
        op.create_check_constraint(
            _PURPOSE_CHECK, _FILES, "purpose IN ('submission', 'grading')"
        )
    if "task_evaluation_id" not in columns:
        op.add_column(_FILES, sa.Column("task_evaluation_id", sa.String(), nullable=True))
    if not any(
        fk.get("referred_table") == "task_evaluations"
        for fk in inspect(op.get_bind()).get_foreign_keys(_FILES)
    ):
        op.create_foreign_key(
            _EVALUATION_FK,
            _FILES,
            "task_evaluations",
            ["task_evaluation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if _EVALUATION_INDEX not in _indexes(_FILES):
        op.create_index(_EVALUATION_INDEX, _FILES, ["task_evaluation_id"])

    if inspect(op.get_bind()).has_table(_BATCHES):
        return
    op.create_table(
        _BATCHES,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="committed"),
        sa.Column("source_filename", sa.String(), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("source_storage_key", sa.String(), nullable=True),
        sa.Column(
            "options",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "report",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "undone_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('committed', 'undone')", name="ck_upload_batches_status"
        ),
    )
    op.create_index("ix_upload_batches_project_created", _BATCHES, ["project_id", "created_at"])
    op.create_index("ix_upload_batches_task", _BATCHES, ["task_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_BATCHES):
        op.drop_table(_BATCHES)
    if _EVALUATION_INDEX in _indexes(_FILES):
        op.drop_index(_EVALUATION_INDEX, table_name=_FILES)
    for fk in inspect(bind).get_foreign_keys(_FILES):
        if fk.get("referred_table") == "task_evaluations" and fk.get("name"):
            op.drop_constraint(fk["name"], _FILES, type_="foreignkey")
    columns = _columns(_FILES)
    if "task_evaluation_id" in columns:
        op.drop_column(_FILES, "task_evaluation_id")
    if _PURPOSE_CHECK in _checks(_FILES):
        op.drop_constraint(_PURPOSE_CHECK, _FILES, type_="check")
    if "purpose" in columns:
        op.drop_column(_FILES, "purpose")
