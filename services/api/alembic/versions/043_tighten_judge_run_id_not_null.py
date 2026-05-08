"""Backfill remaining null judge_run_ids and tighten the column to NOT NULL.

Migration 042 added `task_evaluations.judge_run_id` (nullable) and synthetic
backfill rows for every legacy `EvaluationRun`. Between 042 and now, the four
remaining writer paths (`run_single_sample_evaluation`, the extended Falllösung
worker, the korrektur grader endpoint, and the import_export bulk loader) were
updated to populate `judge_run_id`. This migration:

1. Catches any rows still missing a `judge_run_id` — typically rows produced by
   immediate-eval flows that ran between 042 and now, OR pre-042 imports — by
   creating one synthetic per-EvaluationRun catch-all judge_run with
   `judge_model_id = NULL` and `run_index = 0`, and pointing every orphan row at
   it. Idempotent: if the synthetic row already exists, reuse it.
2. ALTERs `task_evaluations.judge_run_id` to `NOT NULL`. Once this lands, every
   future TaskEvaluation insert MUST set the column.

Revision ID: 043_tighten_judge_run_id_not_null
Revises: 042_add_evaluation_judge_runs
Create Date: 2026-05-06
"""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "043_tighten_judge_run_id_not_null"
down_revision = "042_add_evaluation_judge_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Find every EvaluationRun whose TaskEvaluation rows include any with a
    # null judge_run_id, and ensure it has a synthetic catch-all judge_run.
    orphan_eval_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT te.evaluation_id
            FROM task_evaluations te
            WHERE te.judge_run_id IS NULL
            """
        )
    ).fetchall()

    for (eval_id,) in orphan_eval_ids:
        existing = bind.execute(
            sa.text(
                """
                SELECT id FROM evaluation_judge_runs
                WHERE evaluation_id = :eid
                  AND judge_model_id IS NULL
                  AND run_index = 0
                LIMIT 1
                """
            ),
            {"eid": eval_id},
        ).fetchone()

        if existing:
            jr_id = existing[0]
        else:
            jr_id = str(uuid.uuid4())
            bind.execute(
                sa.text(
                    """
                    INSERT INTO evaluation_judge_runs
                        (id, evaluation_id, judge_model_id, run_index,
                         status, samples_evaluated, error_message,
                         metric_parameters_snapshot)
                    VALUES
                        (:id, :eid, NULL, 0, 'completed', NULL, NULL, NULL)
                    """
                ),
                {"id": jr_id, "eid": eval_id},
            )

        bind.execute(
            sa.text(
                """
                UPDATE task_evaluations
                SET judge_run_id = :jr_id
                WHERE evaluation_id = :eid AND judge_run_id IS NULL
                """
            ),
            {"jr_id": jr_id, "eid": eval_id},
        )

    # Sanity assertion: nothing should be NULL now.
    remaining = bind.execute(
        sa.text("SELECT COUNT(*) FROM task_evaluations WHERE judge_run_id IS NULL")
    ).scalar()
    if remaining and remaining > 0:
        raise RuntimeError(
            f"043 backfill left {remaining} task_evaluations with null judge_run_id; "
            f"abort before tightening to NOT NULL"
        )

    op.alter_column(
        "task_evaluations",
        "judge_run_id",
        existing_type=sa.String(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "task_evaluations",
        "judge_run_id",
        existing_type=sa.String(),
        nullable=True,
    )
    # Don't delete synthetic judge_runs on downgrade — they're harmless when
    # the column is nullable again, and removing them would orphan
    # task_evaluations.judge_run_id pointers (CASCADE would delete the
    # task_evaluations themselves, which is data loss).
