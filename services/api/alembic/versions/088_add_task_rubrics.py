"""add task_rubrics table

Per-task grading rubrics (Bewertungsbogen) — exam-specific 100-point step
schemes generated from a task's Sachverhalt + Musterlösung and consumed by
the ``llm_judge_rubric`` metric (and task-aware korrektur grading). The
generation workflow lives in the extended worker; platform owns only the
persistence.

- ``criteria`` holds the custom_criteria-shaped step dict
  ``{step_key: {name, description, rubric, max_score}}`` so the existing
  multi-dim judge schema builder consumes it unchanged.
- Multiple rows per task are expected (candidate rubrics from different
  generator models); ``ux_task_rubrics_one_active`` (partial unique) pins at
  most one ``status='active'`` row per task — the one judge runs resolve.

All FKs ``ondelete=CASCADE`` (created_by SET NULL) so deleted
projects/tasks self-clean.

Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 088_add_task_rubrics
Revises: 091_add_user_exam_layout_prefs
Create Date: 2026-08-02
"""

from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
import sqlalchemy as sa


revision = "088_add_task_rubrics"
down_revision = "091_add_user_exam_layout_prefs"
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


def upgrade() -> None:
    if not _table_exists("task_rubrics"):
        op.create_table(
            "task_rubrics",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("criteria", JSONB(), nullable=False),
            sa.Column(
                "total_points", sa.Integer(), nullable=False, server_default="100"
            ),
            sa.Column("source", sa.String(length=16), nullable=False, server_default="llm"),
            sa.Column("generator_model_id", sa.String(), nullable=True),
            sa.Column("prompt_key", sa.String(), nullable=True),
            sa.Column("prompt_version", sa.String(), nullable=True),
            sa.Column(
                "generation_metadata", JSONB(), nullable=True
            ),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="candidate"
            ),
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
        )

    if not _index_exists("task_rubrics", "ix_task_rubrics_id"):
        op.create_index("ix_task_rubrics_id", "task_rubrics", ["id"])
    if not _index_exists("task_rubrics", "ix_task_rubrics_task_id"):
        op.create_index("ix_task_rubrics_task_id", "task_rubrics", ["task_id"])
    if not _index_exists("task_rubrics", "ix_task_rubrics_project_id"):
        op.create_index("ix_task_rubrics_project_id", "task_rubrics", ["project_id"])
    if not _index_exists("task_rubrics", "ix_task_rubrics_status"):
        op.create_index("ix_task_rubrics_status", "task_rubrics", ["status"])
    if not _index_exists("task_rubrics", "ix_task_rubrics_task_status"):
        op.create_index(
            "ix_task_rubrics_task_status", "task_rubrics", ["task_id", "status"]
        )
    if not _index_exists("task_rubrics", "ix_task_rubrics_generator"):
        op.create_index(
            "ix_task_rubrics_generator", "task_rubrics", ["project_id", "generator_model_id"]
        )
    if not _index_exists("task_rubrics", "ux_task_rubrics_one_active"):
        op.create_index(
            "ux_task_rubrics_one_active",
            "task_rubrics",
            ["task_id"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        )


def downgrade() -> None:
    if _table_exists("task_rubrics"):
        op.drop_table("task_rubrics")
