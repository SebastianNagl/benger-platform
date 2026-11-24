"""The evaluation methods that people grade, by name.

A human-graded method has no worker: people submit grades and each one
becomes a ``task_evaluations`` row of one persistent ``EvaluationRun`` per
(project, method), the singleton that
``services.evaluation.human_eval_runs.get_or_create_human_eval_run`` finds or
creates. Hardcoded strings per the open-core split rule: the names are hooks
the extended edition writes, not the grading logic.

Every method listed in ``HUMAN_GRADED_METRICS`` needs its own partial unique
index on ``evaluation_runs`` (migrations 037, 061, 122 and 158), or the
singleton upsert has no constraint to match.

One of them, ``PEER_REVIEW_METRIC``, is feedback only: a participant's
grading of a fellow participant's submission in a project with peer review
on (``projects.peer_review_enabled``). Its rows carry no score
(``value: null``, ``details.feedback_only``), so no reader that looks for a
score can take one for a grade, and the result and model views leave its run
out (``FEEDBACK_ONLY_HUMAN_METRICS``). The author reads it as feedback through
the extended edition.

Lives in /shared so the api, the workers (project import) and the extended
package import one list.
"""

from __future__ import annotations

from typing import Any, Final

PEER_REVIEW_METRIC: Final[str] = "korrektur_peer"

HUMAN_GRADED_METRICS: Final[frozenset[str]] = frozenset(
    {"korrektur_falloesung", "korrektur_custom", "korrektur_feedback", PEER_REVIEW_METRIC}
)

# Human-graded methods whose rows are never a score of the graded subject.
FEEDBACK_ONLY_HUMAN_METRICS: Final[frozenset[str]] = frozenset({PEER_REVIEW_METRIC})


def is_human_graded_metric(metric: Any) -> bool:
    return isinstance(metric, str) and metric in HUMAN_GRADED_METRICS


def is_feedback_only_human_metric(metric: Any) -> bool:
    return isinstance(metric, str) and metric in FEEDBACK_ONLY_HUMAN_METRICS


def run_metric(eval_metadata: Any) -> Any:
    """The method a human-graded singleton run belongs to
    (``eval_metadata.evaluation_type``), or None."""
    if isinstance(eval_metadata, dict):
        return eval_metadata.get("evaluation_type")
    return None


def is_feedback_only_run(model_id: Any, eval_metadata: Any) -> bool:
    """A run whose rows are feedback, never scores: the singleton human run
    of a method in ``FEEDBACK_ONLY_HUMAN_METRICS``."""
    return model_id == "human" and is_feedback_only_human_metric(run_metric(eval_metadata))


def _feedback_only_literals() -> str:
    # Module constants, never user input: safe to inline as SQL literals.
    return ", ".join(f"'{m}'" for m in sorted(FEEDBACK_ONLY_HUMAN_METRICS))


def sql_scored_run(run_entity):
    """SQLAlchemy clause over an ``EvaluationRun`` entity (or alias): the
    run is not a feedback-only human run, so its rows may be scores."""
    from sqlalchemy import cast, func, or_
    from sqlalchemy.dialects.postgresql import JSONB

    metric = cast(run_entity.eval_metadata, JSONB)["evaluation_type"].astext
    return or_(
        run_entity.model_id != "human",
        func.coalesce(metric, "").notin_(sorted(FEEDBACK_ONLY_HUMAN_METRICS)),
    )


def scored_run_sql(alias: str) -> str:
    """Raw SQL twin of :func:`sql_scored_run` for an ``evaluation_runs``
    alias in a text query."""
    return (
        f"({alias}.model_id <> 'human' OR "
        f"COALESCE({alias}.eval_metadata::jsonb ->> 'evaluation_type', '') "
        f"NOT IN ({_feedback_only_literals()}))"
    )
