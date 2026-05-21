"""Composite index on response_generations(task_id, model_id, structure_key).

The generation task-status list endpoint
(routers/generation_task_list.get_task_generation_status) bulk-fetches the
latest ResponseGeneration row per (task_id, model_id, structure_key) for the
current page of tasks via `DISTINCT ON`. The existing single-column index on
`structure_key` is no help — the planner needs the leading `task_id` + `model_id`
columns to seek into the right partition before sorting on `created_at DESC`.

Adding this composite turns the per-page bulk query from a sort-and-merge over
the whole table into an indexed range scan keyed by the page's task ids.

Idempotent — guarded against re-application.

Revision ID: 052_response_generations_cell_index
Revises: 051_aggregate_summaries
Create Date: 2026-05-20
"""

from sqlalchemy import inspect

from alembic import op


revision = "052_response_generations_cell_index"
down_revision = "051_aggregate_summaries"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_response_generations_cell"


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}


def upgrade() -> None:
    if not _index_exists("response_generations", INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "response_generations",
            ["task_id", "model_id", "structure_key", "created_at"],
        )


def downgrade() -> None:
    if _index_exists("response_generations", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="response_generations")
