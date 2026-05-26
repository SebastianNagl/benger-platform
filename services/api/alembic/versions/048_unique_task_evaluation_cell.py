"""Add partial unique index on task_evaluations cell-tuple for dedup safety.

The cell-level fan-out refactor (`tasks.evaluate_generation_cell`,
`tasks.evaluate_annotation_cell`) needs an upsert target so concurrent
sub-tasks for the same (evaluation, judge_run, gen-or-ann, field_name)
land exactly one row instead of two. Today the eval pipeline runs in
one Celery task with no concurrency, so duplicates have been avoided
implicitly; under per-cell dispatch we need a DB-level guarantee.

The index covers (evaluation_id, judge_run_id, COALESCE(generation_id,
sentinel), COALESCE(annotation_id, sentinel), field_name). Exactly one
of generation_id/annotation_id is non-null per row, so the sentinel
trick gives a deterministic tuple either way. judge_run_id was tightened
to NOT NULL in migration 043 so no COALESCE there.

`WHERE evaluation_id IS NOT NULL` skips legacy orphan rows defensively
(none observed in prod 2026-05-14, but cheap).

Idempotent: pre-existing duplicates are deduped first, keeping the most
recent row per tuple. The dedup window targets only rows that share the
exact (evaluation_id, judge_run_id, gen, ann, field_name) — historical
multi-attempt evaluations on the same cell (e.g., two separate eval_runs)
have different evaluation_id and are left alone.

Revision ID: 048_unique_task_evaluation_cell
Revises: 047_drop_projects_organization_id
Create Date: 2026-05-14
"""

from sqlalchemy import inspect

from alembic import op


revision = "048_unique_task_evaluation_cell"
down_revision = "047_drop_projects_organization_id"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_task_evaluations_cell"


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}


def upgrade() -> None:
    if _index_exists("task_evaluations", INDEX_NAME):
        return

    # Dedup any pre-existing rows that would violate the unique constraint.
    # Keep the latest by created_at; delete older duplicates.
    op.execute(
        """
        DELETE FROM task_evaluations a
        USING task_evaluations b
        WHERE a.id <> b.id
          AND a.evaluation_id IS NOT NULL
          AND b.evaluation_id IS NOT NULL
          AND a.evaluation_id = b.evaluation_id
          AND a.judge_run_id = b.judge_run_id
          AND COALESCE(a.generation_id, '00000000-0000-0000-0000-000000000000')
              = COALESCE(b.generation_id, '00000000-0000-0000-0000-000000000000')
          AND COALESCE(a.annotation_id, '00000000-0000-0000-0000-000000000000')
              = COALESCE(b.annotation_id, '00000000-0000-0000-0000-000000000000')
          AND a.field_name = b.field_name
          AND (a.created_at < b.created_at
               OR (a.created_at = b.created_at AND a.id < b.id))
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON task_evaluations (
            evaluation_id,
            judge_run_id,
            COALESCE(generation_id, '00000000-0000-0000-0000-000000000000'),
            COALESCE(annotation_id, '00000000-0000-0000-0000-000000000000'),
            field_name
        )
        WHERE evaluation_id IS NOT NULL
        """
    )


def downgrade() -> None:
    if not _index_exists("task_evaluations", INDEX_NAME):
        return
    op.execute(f"DROP INDEX {INDEX_NAME}")
