"""add lifecycle columns to evaluation_runs (pause/resume/retry, issue #198)

Evaluation runs gain the pause/resume/retry lifecycle that generation got
in migration 063:

- ``paused_at``: set when an operator pauses a running run (NULL = not
  paused). Cell sub-tasks check the parent status and skip while paused;
  the chord finalizer no-ops so the run stays ``paused`` with its partial
  ``task_evaluations`` intact until resume re-dispatches missing-only.
- ``retry_count``: incremented by POST /run/{id}/retry on a failed run.

Idempotent — guards on column existence.

Revision ID: 078_evaluation_lifecycle_columns
Revises: 077_grading_usage_weekly_tiering
Create Date: 2026-07-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "078_evaluation_lifecycle_columns"
down_revision = "077_grading_usage_weekly_tiering"
branch_labels = None
depends_on = None


TABLE_NAME = "evaluation_runs"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, "paused_at"):
        op.add_column(
            TABLE_NAME,
            sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists(TABLE_NAME, "retry_count"):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, "retry_count"):
        op.drop_column(TABLE_NAME, "retry_count")
    if _column_exists(TABLE_NAME, "paused_at"):
        op.drop_column(TABLE_NAME, "paused_at")
