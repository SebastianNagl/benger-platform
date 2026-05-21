"""Add `completed_response_generations_count` column to `project_summaries`.

The projects-list endpoint still ran two grouped queries on `generations` and
`response_generations` for every list render (via
`calculate_generation_stats_batch`) because `project_summaries` had a total
`response_generations_count` but no equivalent that's narrowed to
`status = 'completed'`. The progress mix on the dashboard tile needs the
completed count, so we couldn't drop the live query without losing accuracy.

This migration adds the column. The worker compute function in
`services/api/services/aggregate_summaries.py` populates it; the API
helper reads it instead of the live `.count()`.

Idempotent — column add is guarded.

Revision ID: 055_completed_generations_summary
Revises: 054_next_task_indexes
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op


revision = "055_completed_generations_summary"
down_revision = "054_next_task_indexes"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("project_summaries", "completed_response_generations_count"):
        op.add_column(
            "project_summaries",
            sa.Column(
                "completed_response_generations_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    if _column_exists("project_summaries", "completed_response_generations_count"):
        op.drop_column("project_summaries", "completed_response_generations_count")
