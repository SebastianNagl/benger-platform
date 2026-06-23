"""Singleton EvaluationRun for human-graded evaluation methods.

Some evaluation methods (today: `korrektur_falloesung`, the human-graded
Standard Falllösung correction, and `korrektur_custom`, its
custom-annotation-type sibling) are not run by a worker against an LLM —
humans submit grades through the Korrektur queue and each submission
becomes a `TaskEvaluation` row. There is **one persistent EvaluationRun
per (project, metric)** for all of those rows; correctors append to it
indefinitely so we can later compute inter-rater agreement from the
preserved per-grader history.

This module owns the find-or-create helper that both
`POST /evaluations/run` (when the configured metric is human-graded) and
the extended `submit_falloesung_grade` / `submit_custom_grade` endpoints
use to resolve the destination run. The per-metric partial unique
indexes (migration 037 for `korrektur_falloesung`, 061 for
`korrektur_custom`) make the upsert safe under concurrent submits.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import EvaluationRun


# The set of metrics whose EvaluationRun is human-driven (one persistent
# row per project, no worker involvement). Hardcoded string list per the
# open-core split rule: this is a hook, not the implementation.
#
# NOTE: every metric listed here needs a matching partial unique index on
# evaluation_runs (see migrations 037 and 061) — the upsert below infers
# the index from a per-metric predicate, and without the index the
# ON CONFLICT clause raises "no unique or exclusion constraint matching
# the ON CONFLICT specification".
HUMAN_GRADED_METRICS: Final[frozenset[str]] = frozenset(
    {"korrektur_falloesung", "korrektur_custom"}
)


def is_human_graded_metric(metric: str) -> bool:
    return metric in HUMAN_GRADED_METRICS


def _build_upsert_human_eval_run(project_id: str, metric: str, created_by: str):
    """Shared upsert statement builder for the (project_id, metric) singleton.

    Both the sync entry point and the async twin execute this exact INSERT …
    ON CONFLICT … RETURNING so the two lanes are byte-identical in their SQL.
    Caller is responsible for validating ``metric`` against
    HUMAN_GRADED_METRICS before building (the index_where interpolation below
    relies on that validation).
    """
    return (
        pg_insert(EvaluationRun)
        .values(
            id=str(uuid.uuid4()),
            project_id=project_id,
            model_id="human",
            evaluation_type_ids=[metric],
            metrics={},
            # `evaluation_configs` is a list of one synthetic config matching
            # the metric — the EvaluationResults frontend filters runs by
            # `e.evaluation_configs?.some(c => selectedMetrics.includes(c.metric))`,
            # so without this stub the human run never surfaces in the
            # active-metric dropdown next to the LLM runs.
            eval_metadata={
                "evaluation_type": metric,
                "evaluation_configs": [
                    {
                        "id": metric,
                        "metric": metric,
                        "enabled": True,
                        "display_name": metric.replace("_", " ").title(),
                    }
                ],
            },
            # 'completed' (rather than 'in_progress') because numerous read
            # endpoints filter status='completed'; the singleton would
            # disappear from the project-wide rollups (evaluated-models,
            # by-task-model, leaderboards) otherwise. The eval list label
            # remap surfaces 'ongoing' to users — see multi_field.py.
            status="completed",
            samples_evaluated=0,
            has_sample_results=True,
            created_by=created_by,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "model_id"],
            # The predicate must be a literal (not a bind param) so Postgres
            # can infer the matching partial unique index at plan time.
            # Interpolating `metric` is safe: it was validated against the
            # HUMAN_GRADED_METRICS whitelist above.
            index_where=text(
                "model_id = 'human' "
                f"AND (eval_metadata ->> 'evaluation_type') = '{metric}'"
            ),
            # No-op SET to force ON CONFLICT to RETURN the existing id rather
            # than skip (DO NOTHING would suppress RETURNING on conflict).
            set_={"model_id": "human"},
        )
        .returning(EvaluationRun.id)
    )


def get_or_create_human_eval_run(
    db: Session,
    project_id: str,
    metric: str,
    created_by: str,
) -> EvaluationRun:
    """Return the singleton EvaluationRun for (project_id, metric).

    Creates it on first call; on every subsequent call (including
    concurrent ones from different graders) returns the same row via the
    metric's partial unique index (`uq_human_eval_run_per_project_metric`
    for korrektur_falloesung, `uq_human_eval_run_per_project_metric_custom`
    for korrektur_custom).

    `created_by` is the user who triggered this call and is recorded
    only on first creation; it has no semantic meaning for the ongoing
    run beyond auditability of who first opened the human-grading workflow.
    """
    if not is_human_graded_metric(metric):
        raise ValueError(
            "get_or_create_human_eval_run is only valid for human-graded metrics; "
            f"got {metric!r} (allowed: {sorted(HUMAN_GRADED_METRICS)})"
        )

    stmt = _build_upsert_human_eval_run(project_id, metric, created_by)
    run_id = db.execute(stmt).scalar_one()
    return db.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()


async def get_or_create_human_eval_run_async(
    db: AsyncSession,
    project_id: str,
    metric: str,
    created_by: str,
) -> EvaluationRun:
    """Async twin of :func:`get_or_create_human_eval_run`.

    Shares the exact upsert statement so the persistence semantics (and the
    partial-unique-index conflict resolution) are identical to the sync lane.
    """
    if not is_human_graded_metric(metric):
        raise ValueError(
            "get_or_create_human_eval_run is only valid for human-graded metrics; "
            f"got {metric!r} (allowed: {sorted(HUMAN_GRADED_METRICS)})"
        )

    stmt = _build_upsert_human_eval_run(project_id, metric, created_by)
    run_id = (await db.execute(stmt)).scalar_one()
    result = await db.execute(
        select(EvaluationRun).where(EvaluationRun.id == run_id)
    )
    return result.scalar_one()
