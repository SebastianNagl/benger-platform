"""Indexes for hot query paths surfaced in the 2026-05-20 perf pass.

Three indexes covering filter columns that the planner was previously seq-scanning
on tables already in the seven-figure row count range:

* `task_evaluations(generation_id)` — used by `/evaluations/results/*` and
  the report endpoints to pull every evaluation row for a model's generations.
  The model column was missing `index=True`, so the planner walked the heap.
* `evaluation_runs(project_id, status)` — composite covering the common
  shape `WHERE project_id = :p AND status = 'completed'` in
  `_scored_pairs_query`, the runs router, and the leaderboard read path.
  Single-column `project_id` index alone forced a heap walk for the
  status predicate.
* `response_generations(project_id, status)` — same shape as above for the
  generation router (`/generation/responses`) and the WebSocket-fallback
  poll. Without it, status filters on the project's full generation
  history were O(rows-per-project).

Idempotent — each index creation is guarded against re-application so the
migration is safe to re-run.

Revision ID: 053_hot_path_indexes
Revises: 052_response_generations_cell_index
Create Date: 2026-05-20
"""

from sqlalchemy import inspect

from alembic import op


revision = "053_hot_path_indexes"
down_revision = "052_response_generations_cell_index"
branch_labels = None
depends_on = None


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _index_exists("task_evaluations", "ix_task_evaluations_generation_id"):
        op.create_index(
            "ix_task_evaluations_generation_id",
            "task_evaluations",
            ["generation_id"],
        )

    if not _index_exists("evaluation_runs", "ix_evaluation_runs_project_status"):
        op.create_index(
            "ix_evaluation_runs_project_status",
            "evaluation_runs",
            ["project_id", "status"],
        )

    if not _index_exists(
        "response_generations", "ix_response_generations_project_status"
    ):
        op.create_index(
            "ix_response_generations_project_status",
            "response_generations",
            ["project_id", "status"],
        )


def downgrade() -> None:
    if _index_exists(
        "response_generations", "ix_response_generations_project_status"
    ):
        op.drop_index(
            "ix_response_generations_project_status",
            table_name="response_generations",
        )
    if _index_exists("evaluation_runs", "ix_evaluation_runs_project_status"):
        op.drop_index(
            "ix_evaluation_runs_project_status", table_name="evaluation_runs"
        )
    if _index_exists("task_evaluations", "ix_task_evaluations_generation_id"):
        op.drop_index(
            "ix_task_evaluations_generation_id", table_name="task_evaluations"
        )
