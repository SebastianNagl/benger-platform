"""Composite indexes for the by-task-model results queries (issue #280).

The project results endpoint (routers/evaluations/results/by_task_model.
get_project_results_by_task_model) runs two latest-wins window functions on
ZJS-scale data (~78k task_evaluations):

- row_number() OVER (PARTITION BY task_evaluations.generation_id,
  task_evaluations.field_name ORDER BY created_at DESC) — served by
  ix_task_evaluations_gen_field_created. The existing single-column index on
  generation_id can find the rows but not order them; the composite lets the
  planner produce the partition ordering directly.
- row_number() OVER (PARTITION BY generations.task_id, generations.model_id
  ORDER BY created_at DESC) — served by ix_generations_task_model_created.
  generations.task_id previously had NO index at all, so the latest-gen
  window seq-scanned the table.

No annotations index: uq_annotations_active_task_user (partial unique on
(task_id, completed_by) WHERE was_cancelled = false) already guarantees at
most one active row per partition and serves the latest-annotation scan.

Idempotent — guarded against re-application.

Revision ID: 086_task_eval_results_indexes
Revises: 085_add_pending_activation_email
Create Date: 2026-07-31
"""

from sqlalchemy import inspect

from alembic import op


revision = "086_task_eval_results_indexes"
down_revision = "085_add_pending_activation_email"
branch_labels = None
depends_on = None


INDEXES = {
    "ix_task_evaluations_gen_field_created": (
        "task_evaluations",
        ["generation_id", "field_name", "created_at"],
    ),
    "ix_generations_task_model_created": (
        "generations",
        ["task_id", "model_id", "created_at"],
    ),
}


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}


def upgrade() -> None:
    for index_name, (table_name, columns) in INDEXES.items():
        if not _index_exists(table_name, index_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    for index_name, (table_name, _) in INDEXES.items():
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
