"""Backfill: collapse per-submission Korrektur-Falllösung EvaluationRuns
into the singleton human run added in migration 037 / the
human_eval_runs upsert helper.

Before this release, every `submit_falloesung_grade` call created a fresh
`EvaluationRun` with `model_id='human:<user_id>'` (one row per submission).
Those orphan runs are unreachable from the eval list and the eval results
table — only the singleton `(project_id, model_id='human',
eval_metadata.evaluation_type='korrektur_falloesung')` is queried by
the new code path.

This migration:
  1. For each project that has any orphan run, finds-or-creates the
     singleton (`model_id='human'`).
  2. Repoints all `task_evaluations.evaluation_id` from the orphan IDs
     to the singleton ID; copies the grader user_id from
     `judge_prompts_used.grader_user_id` (legacy JSON path) into the new
     first-class `created_by` column where it's not already set.
  3. Deletes the orphan runs.

Idempotent: re-running it finds zero orphan rows and exits cleanly.
Batched in 1000-row chunks for prod data volumes.

Downgrade is intentionally a no-op — there is no faithful way to
reconstitute per-submission orphan runs from the merged singleton.

Revision ID: 038_korrektur_backfill_orphan_human_runs
Revises: 037_korrektur_human_run_singleton
Create Date: 2026-05-04
"""

from __future__ import annotations

import logging
import uuid

from alembic import op
from sqlalchemy import text

revision = "038_korrektur_backfill_orphan_human_runs"
down_revision = "037_korrektur_human_run_singleton"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)
BATCH = 1000


def upgrade() -> None:
    conn = op.get_bind()

    # Affected projects: those with at least one orphan per-submission run.
    affected = conn.execute(
        text(
            """
            SELECT DISTINCT project_id
            FROM evaluation_runs
            WHERE model_id LIKE 'human:%'
              AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'
            """
        )
    ).fetchall()

    if not affected:
        logger.info("[038] No orphan human korrektur_falloesung runs to backfill.")
        return

    for (project_id,) in affected:
        # Pick a created_by — earliest grader's user_id — to record on the
        # singleton if we end up creating it. If the singleton already exists,
        # this value is unused.
        first_grader = conn.execute(
            text(
                """
                SELECT created_by
                FROM evaluation_runs
                WHERE project_id = :pid
                  AND model_id LIKE 'human:%'
                  AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'
                ORDER BY created_at
                LIMIT 1
                """
            ),
            {"pid": project_id},
        ).scalar()

        # Find-or-create the singleton. We do an explicit SELECT first so we
        # don't have to rely on ON CONFLICT ... RETURNING semantics inside the
        # migration; the partial unique index from 037 still blocks any race.
        singleton_id = conn.execute(
            text(
                """
                SELECT id
                FROM evaluation_runs
                WHERE project_id = :pid
                  AND model_id = 'human'
                  AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'
                """
            ),
            {"pid": project_id},
        ).scalar()
        if singleton_id is None:
            singleton_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO evaluation_runs
                      (id, project_id, model_id, evaluation_type_ids, metrics,
                       eval_metadata, status, samples_evaluated,
                       has_sample_results, created_by, created_at)
                    VALUES
                      (:id, :pid, 'human',
                       '["korrektur_falloesung"]'::json,
                       '{}'::json,
                       ('{"evaluation_type": "korrektur_falloesung", '
                        '"evaluation_configs": [{"id": "korrektur_falloesung", '
                        '"metric": "korrektur_falloesung", "enabled": true, '
                        '"display_name": "Korrektur Falloesung"}]}')::json,
                       'completed', 0, true, :uid, now())
                    """
                ),
                {"id": singleton_id, "pid": project_id, "uid": first_grader},
            )

        # Collect orphan IDs for this project.
        orphan_ids = [
            r[0]
            for r in conn.execute(
                text(
                    """
                    SELECT id
                    FROM evaluation_runs
                    WHERE project_id = :pid
                      AND model_id LIKE 'human:%'
                      AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'
                    """
                ),
                {"pid": project_id},
            ).fetchall()
        ]

        if not orphan_ids:
            continue

        # Repoint TaskEvaluation rows in batches; backfill created_by from
        # the legacy JSON path where it's not already populated.
        for i in range(0, len(orphan_ids), BATCH):
            batch = orphan_ids[i : i + BATCH]
            conn.execute(
                text(
                    """
                    UPDATE task_evaluations
                    SET evaluation_id = :singleton_id,
                        created_by = COALESCE(
                            created_by,
                            NULLIF(judge_prompts_used ->> 'grader_user_id', '')
                        )
                    WHERE evaluation_id = ANY(:orphan_ids)
                    """
                ),
                {"singleton_id": singleton_id, "orphan_ids": batch},
            )

        # Delete now-empty orphan runs in batches.
        for i in range(0, len(orphan_ids), BATCH):
            batch = orphan_ids[i : i + BATCH]
            conn.execute(
                text(
                    """
                    DELETE FROM evaluation_runs
                    WHERE id = ANY(:orphan_ids)
                    """
                ),
                {"orphan_ids": batch},
            )

        logger.info(
            "[038] project %s: collapsed %d orphan runs into singleton %s",
            project_id,
            len(orphan_ids),
            singleton_id,
        )


def downgrade() -> None:
    """No-op: per-submission orphan runs cannot be faithfully reconstructed
    from the merged singleton. Re-running upgrade() on collapsed data is
    safe (idempotent), so a missing downgrade only blocks the unusual case
    of needing to revert specifically migration 038 below older code that
    still expects per-submission rows — and that older code is what this
    release is removing in the first place."""
