"""Singleton EvaluationRun for human-graded evaluation methods.

Some evaluation methods (today: `korrektur_falloesung`, the human-graded
Standard Falllösung correction) are not run by a worker against an LLM —
humans submit grades through the Korrektur queue and each submission
becomes a `TaskEvaluation` row. There is **one persistent EvaluationRun
per (project, metric)** for all of those rows; correctors append to it
indefinitely so we can later compute inter-rater agreement from the
preserved per-grader history.

This module owns the find-or-create helper that both
`POST /evaluations/run` (when the configured metric is human-graded) and
the extended `submit_falloesung_grade` endpoint use to resolve the
destination run. The partial unique index added in migration 037 makes
the upsert safe under concurrent submits.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import EvaluationRun


# The set of metrics whose EvaluationRun is human-driven (one persistent
# row per project, no worker involvement). Hardcoded string list per the
# open-core split rule: this is a hook, not the implementation.
HUMAN_GRADED_METRICS: Final[frozenset[str]] = frozenset({"korrektur_falloesung"})


def is_human_graded_metric(metric: str) -> bool:
    return metric in HUMAN_GRADED_METRICS


def get_or_create_human_eval_run(
    db: Session,
    project_id: str,
    metric: str,
    created_by: str,
) -> EvaluationRun:
    """Return the singleton EvaluationRun for (project_id, metric).

    Creates it on first call; on every subsequent call (including
    concurrent ones from different graders) returns the same row via the
    partial unique index `uq_human_eval_run_per_project_metric`.

    `created_by` is the user who triggered this call and is recorded
    only on first creation; it has no semantic meaning for the ongoing
    run beyond auditability of who first opened the human-grading workflow.
    """
    if not is_human_graded_metric(metric):
        raise ValueError(
            f"get_or_create_human_eval_run is only valid for human-graded metrics; "
            f"got {metric!r} (allowed: {sorted(HUMAN_GRADED_METRICS)})"
        )

    stmt = (
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
            index_where=text(
                "model_id = 'human' "
                "AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'"
            ),
            # No-op SET to force ON CONFLICT to RETURN the existing id rather
            # than skip (DO NOTHING would suppress RETURNING on conflict).
            set_={"model_id": "human"},
        )
        .returning(EvaluationRun.id)
    )

    run_id = db.execute(stmt).scalar_one()
    return db.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()
