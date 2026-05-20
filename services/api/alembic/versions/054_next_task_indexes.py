"""Composite indexes for the auto-mode `/projects/{id}/next` selector.

The handler at `routers/projects/tasks.py:get_next_task` builds candidate-task
SQL by NOT-IN'ing two subqueries:

* The set of annotations the current user already submitted for this project
  (filtered on `project_id` and `was_cancelled`).
* The set of tasks whose assignment count for this project is at the
  per-task ceiling (filtered on `project_id` and `status`).

Both subqueries previously had only single-column indexes on `project_id`, so
adding the status / was_cancelled predicate forced a heap walk. On a busy
labeling project (10k+ annotations, 50 active annotators) this fires every
~5 s — i.e. once per task cycle per annotator — and was a non-trivial
share of the auto-mode response time.

Two narrow composite indexes match the planner's preferred shape.

Idempotent — each `CREATE INDEX` is guarded so re-running is safe.

Revision ID: 054_next_task_indexes
Revises: 053_hot_path_indexes
Create Date: 2026-05-20
"""

from sqlalchemy import inspect

from alembic import op


revision = "054_next_task_indexes"
down_revision = "053_hot_path_indexes"
branch_labels = None
depends_on = None


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _index_exists("annotations", "ix_annotations_project_cancelled"):
        op.create_index(
            "ix_annotations_project_cancelled",
            "annotations",
            ["project_id", "was_cancelled"],
        )

    if not _index_exists("task_assignments", "ix_task_assignments_task_status"):
        op.create_index(
            "ix_task_assignments_task_status",
            "task_assignments",
            ["task_id", "status"],
        )


def downgrade() -> None:
    if _index_exists("task_assignments", "ix_task_assignments_task_status"):
        op.drop_index(
            "ix_task_assignments_task_status", table_name="task_assignments"
        )
    if _index_exists("annotations", "ix_annotations_project_cancelled"):
        op.drop_index(
            "ix_annotations_project_cancelled", table_name="annotations"
        )
