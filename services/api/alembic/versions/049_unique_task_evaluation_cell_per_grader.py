"""Multi-grader fix for the partial unique index on task_evaluations.

Migration 048's index keyed on
  `(evaluation_id, judge_run_id, COALESCE(generation_id, sentinel),
    COALESCE(annotation_id, sentinel), field_name)`
which was correct for LLM-driven evaluations (one row per cell-per-metric)
but collapsed multi-grader human korrektur rows. The 048 pre-dedup DELETE
treated two different graders on the same annotation as duplicates and
kept only the newer, deleting the older grader's score.

Confirmed prod incident (Benchathon project, 2026-05-15): Ann-Kristin
Mayrhofer's 0.72 grade on annotation 27f1716e-12a3-4885-a748-702378ef0f14
was deleted because Aleyna Koçak's later 0.0 grade on the same annotation
won the dedup. The human korrektur workflow is designed for multi-grader
(inter-rater-agreement scoring), so the dedup was wrong for that shape.

Fix: add `created_by` to the unique index key. Multi-grader rows now
coexist (different created_by → different key tuple); LLM redelivery
dedup still works (same eval-run → same created_by NULL/system → bare
`ON CONFLICT DO NOTHING` still catches the conflict).

No pre-dedup DELETE this time: any rows that pass the OLD index but
violate the NEW (per-grader) index would have to be two grader-NULL
rows for the same cell — which is exactly the LLM-redelivery scenario
that the bare ON CONFLICT was already preventing in steady state. There
should be zero of those in current data. (Verified empirically before
applying: the post-048 prod data has zero rows sharing the cell key,
because 048 just collapsed them.)

Revision ID: 049_unique_task_evaluation_cell_per_grader
Revises: 048_unique_task_evaluation_cell
Create Date: 2026-05-15
"""

from sqlalchemy import inspect

from alembic import op


revision = "049_unique_task_evaluation_cell_per_grader"
down_revision = "048_unique_task_evaluation_cell"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_task_evaluations_cell"
SENTINEL = "00000000-0000-0000-0000-000000000000"


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}


def upgrade() -> None:
    if _index_exists("task_evaluations", INDEX_NAME):
        op.execute(f"DROP INDEX {INDEX_NAME}")

    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON task_evaluations (
            evaluation_id,
            judge_run_id,
            COALESCE(generation_id, '{SENTINEL}'),
            COALESCE(annotation_id, '{SENTINEL}'),
            field_name,
            COALESCE(created_by, '{SENTINEL}')
        )
        WHERE evaluation_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Restore 048's shape. Note: downgrading does NOT re-run the
    # pre-dedup DELETE — if the system has accumulated multi-grader
    # rows under the per-grader index, downgrading without that
    # re-dedup will fail with a duplicate-key error on the
    # CREATE INDEX. That's the right failure mode: silently dropping
    # multi-grader rows during a downgrade would lose data, so the
    # operator must consciously decide what to do.
    if _index_exists("task_evaluations", INDEX_NAME):
        op.execute(f"DROP INDEX {INDEX_NAME}")
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON task_evaluations (
            evaluation_id,
            judge_run_id,
            COALESCE(generation_id, '{SENTINEL}'),
            COALESCE(annotation_id, '{SENTINEL}'),
            field_name
        )
        WHERE evaluation_id IS NOT NULL
        """
    )
