"""add grading_feedback table

Solver reaction to ONE grading of ONE own submission: thumbs up/down plus an
optional comment, collected so the operators can tune the LLM judges and the
human Korrektur workflow over time.

NOT the Korrektur feature: "feedback" was its pre-031 name (migration 027
created ``feedback_comments``, 031 renamed everything to ``korrektur_*``) and
the student UI still labels a human correction "Feedback deiner Korrektur".
This table is meta-feedback ABOUT a grading.

- ``grading_source`` = ``'llm'`` (a judge run), ``'human'`` (Korrektur grade
  and/or Randbemerkungen) or ``'general'`` (free-text feedback about the exam
  or the platform, no rating, no snapshot). ``evaluation_run_id`` records which
  run was rated (NULL for comment-only human corrections and general feedback)
  and is SET NULL on run deletion so the opinion survives.
- ``judge_model_id`` / ``grade_points`` / ``passed`` snapshot what the solver
  saw at vote time as discrete columns (SQL/CSV slicing); ``context`` JSONB
  keeps the long tail (metric keys, task_evaluation ids, judge/grader ids,
  comment count, run status).
- ``uq_grading_feedback_user_annotation_source``: one row per (user,
  annotation, source); the extended write path upserts on it, so the index
  must exist wherever the app runs (the model mirrors it in ``__table_args__``).
- CHECK constraints pin the two enums and forbid an empty row (no rating AND
  no comment).

Platform owns the persistence and the generic reads
(``routers/grading_feedback.py``); the write path lives in
``benger_extended.api.routers.grading_feedback``.

All FKs ``ondelete=CASCADE`` (evaluation_runs SET NULL) so deleted
projects/tasks/annotations/users self-clean.

Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 099_add_grading_feedback
Revises: 098_project_report_public
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "099_add_grading_feedback"
down_revision = "098_project_report_public"
branch_labels = None
depends_on = None

TABLE = "grading_feedback"


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


def upgrade() -> None:
    if not _table_exists(TABLE):
        op.create_table(
            TABLE,
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
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "annotation_id",
                sa.String(),
                sa.ForeignKey("annotations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("grading_source", sa.String(length=8), nullable=False),
            sa.Column(
                "evaluation_run_id",
                sa.String(),
                sa.ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("judge_model_id", sa.String(), nullable=True),
            sa.Column("grade_points", sa.Float(), nullable=True),
            sa.Column("passed", sa.Boolean(), nullable=True),
            sa.Column("rating", sa.String(length=8), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("context", JSONB(), nullable=True),
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
            sa.CheckConstraint(
                "grading_source IN ('llm', 'human', 'general')",
                name="ck_grading_feedback_source",
            ),
            sa.CheckConstraint(
                "rating IS NULL OR rating IN ('up', 'down')",
                name="ck_grading_feedback_rating",
            ),
            sa.CheckConstraint(
                "rating IS NOT NULL OR comment IS NOT NULL",
                name="ck_grading_feedback_not_empty",
            ),
        )

    for name, cols in (
        ("ix_grading_feedback_id", ["id"]),
        ("ix_grading_feedback_project_id", ["project_id"]),
        ("ix_grading_feedback_task_id", ["task_id"]),
        ("ix_grading_feedback_annotation_id", ["annotation_id"]),
        ("ix_grading_feedback_user_id", ["user_id"]),
        ("ix_grading_feedback_project_created", ["project_id", "created_at"]),
        ("ix_grading_feedback_evaluation_run", ["evaluation_run_id"]),
    ):
        if not _index_exists(TABLE, name):
            op.create_index(name, TABLE, cols)

    if not _index_exists(TABLE, "uq_grading_feedback_user_annotation_source"):
        op.create_index(
            "uq_grading_feedback_user_annotation_source",
            TABLE,
            ["user_id", "annotation_id", "grading_source"],
            unique=True,
        )


def downgrade() -> None:
    if _table_exists(TABLE):
        op.drop_table(TABLE)
