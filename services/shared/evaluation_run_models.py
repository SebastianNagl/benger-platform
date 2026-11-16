"""Which models an evaluation run graded, and the run's model label.

An ``EvaluationRun`` carries one ``model_id``. A run grades the generations
of one or several models, and every ``TaskEvaluation`` row points at the
generation it graded, so the row is the authoritative per-model attribution
(the same way a judge run's rows hang off one ``EvaluationJudgeRun`` per
judge model). The run's own label is:

- the model, when every graded generation belongs to one model;
- ``MULTI_MODEL_RUN_LABEL`` (``"unknown"``) when the run graded several
  models (or none, such as a run over submitted answers only). Every
  per-model view already skips that value and reads the model per row.

``eval_metadata["evaluated_model_ids"]`` lists the models a run graded, so
list views can name them without reading the rows. Dispatch writes the
models it plans to grade; once the run is terminal that is replaced with
the models whose generations it actually graded (empty when it graded
none).
"""

from collections.abc import Iterable

from sqlalchemy import func

MULTI_MODEL_RUN_LABEL = "unknown"

# Labels that name no model: the run-level placeholder for multi-model and
# answer-only runs, the human-graded singleton runs and legacy immediate runs.
PSEUDO_RUN_MODEL_IDS = frozenset({MULTI_MODEL_RUN_LABEL, "human", "immediate"})


def run_model_label(model_ids: Iterable[str]) -> str:
    """``EvaluationRun.model_id`` for a run over ``model_ids``: the one model,
    else ``MULTI_MODEL_RUN_LABEL``."""
    distinct = list(dict.fromkeys(m for m in model_ids if m))
    return distinct[0] if len(distinct) == 1 else MULTI_MODEL_RUN_LABEL


def graded_model_ids(db, evaluation_id: str) -> list[str]:
    """Models whose generations the run's rows graded, most rows first (ties
    by id). Rows over annotations have no generation and add no model."""
    from models import Generation, TaskEvaluation

    rows = (
        db.query(Generation.model_id, func.count(TaskEvaluation.id))
        .join(Generation, TaskEvaluation.generation_id == Generation.id)
        .filter(TaskEvaluation.evaluation_id == evaluation_id)
        .group_by(Generation.model_id)
        .all()
    )
    ranked = sorted(
        ((model_id, count) for model_id, count in rows if model_id),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [model_id for model_id, _count in ranked]


def label_run_from_rows(db, evaluation) -> list[str]:
    """Set ``evaluation.model_id`` and ``eval_metadata["evaluated_model_ids"]``
    from the generations its rows graded, once the run is terminal. A run
    that graded no generation records no model and keeps its dispatch-time
    label. Returns the graded models. Does not commit; the caller flags
    ``eval_metadata`` as modified and commits."""
    graded = graded_model_ids(db, evaluation.id)
    if graded:
        evaluation.model_id = run_model_label(graded)
    evaluation.eval_metadata = {
        **(evaluation.eval_metadata or {}),
        "evaluated_model_ids": graded,
        "evaluated_model_id": evaluation.model_id,
    }
    return graded


def run_evaluated_model_ids(model_id: str | None, eval_metadata) -> list[str]:
    """The models a stored run graded, for display: the recorded
    ``evaluated_model_ids`` (empty for a run that graded no generation),
    else the run's label when it names a model."""
    recorded = (eval_metadata or {}).get("evaluated_model_ids")
    if isinstance(recorded, list):
        return list(dict.fromkeys(m for m in recorded if isinstance(m, str) and m))
    if isinstance(model_id, str) and model_id and model_id not in PSEUDO_RUN_MODEL_IDS:
        return [model_id]
    return []
