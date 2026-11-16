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
list views can name them without reading the rows. Only a run that has
settled carries it (written from its rows, empty when it graded no
generation); dispatch records the models in scope as ``planned_model_ids``.
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


def _ranked(counts: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """(model, rows) pairs most rows first, ties by id."""
    return sorted(
        ((model_id, count) for model_id, count in counts if model_id),
        key=lambda pair: (-pair[1], pair[0]),
    )


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
    return [model_id for model_id, _count in _ranked(rows)]


def graded_model_counts_by_run(
    db, evaluation_ids: Iterable[str]
) -> dict[str, list[tuple[str, int]]]:
    """For each run, the (model, rows) pairs its rows graded, in the order of
    ``graded_model_ids``. A run that graded no generation is absent."""
    from models import Generation, TaskEvaluation

    ids = list(dict.fromkeys(evaluation_ids))
    counts: dict[str, list[tuple[str, int]]] = {}
    for start in range(0, len(ids), 1000):
        rows = (
            db.query(
                TaskEvaluation.evaluation_id,
                Generation.model_id,
                func.count(TaskEvaluation.id),
            )
            .join(Generation, TaskEvaluation.generation_id == Generation.id)
            .filter(TaskEvaluation.evaluation_id.in_(ids[start : start + 1000]))
            .group_by(TaskEvaluation.evaluation_id, Generation.model_id)
            .all()
        )
        for evaluation_id, model_id, count in rows:
            counts.setdefault(evaluation_id, []).append((model_id, count))
    ranked = {run_id: _ranked(pairs) for run_id, pairs in counts.items()}
    return {run_id: pairs for run_id, pairs in ranked.items() if pairs}


def label_run_from_rows(db, evaluation, graded: list[str] | None = None) -> list[str]:
    """Set ``evaluation.model_id`` and ``eval_metadata["evaluated_model_ids"]``
    from the generations its rows graded, once the run is terminal. A run
    that graded no generation records no model and keeps its dispatch-time
    label. ``graded`` passes the run's ``graded_model_ids`` when the caller
    already read them. Returns the graded models. Does not commit; the
    caller flags ``eval_metadata`` as modified and commits."""
    if graded is None:
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


#: ``eval_metadata`` key of the labels a run carried before a relabel of
#: stored runs (``POST /api/admin/evaluation-runs/relabel``), oldest first.
#: Each entry has ``relabeled_at``, ``relabeled_by``, ``superseded`` (the
#: previous ``model_id`` and ``eval_metadata``) and ``applied`` (what the
#: relabel wrote).
RELABEL_HISTORY_KEY = "relabel_history"


def relabel_history(eval_metadata) -> list[dict]:
    if not isinstance(eval_metadata, dict):
        return []
    history = eval_metadata.get(RELABEL_HISTORY_KEY)
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, dict)]


def run_label_aliases(model_id: str | None, eval_metadata) -> list[str]:
    """The labels a run is known by: its label, then the labels a relabel
    superseded (newest first). A merge matches a run by any of them, so a
    relabelled run is still found as the copy of a run exported before."""
    labels = [model_id] + [
        (entry.get("superseded") or {}).get("model_id")
        for entry in reversed(relabel_history(eval_metadata))
    ]
    return list(dict.fromkeys(m for m in labels if isinstance(m, str) and m))
