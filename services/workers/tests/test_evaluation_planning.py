"""The shared evaluation planner's judge-call count (services/shared/
evaluation_planning.py), which the cost estimate prices. DB-free: the cells
are built by hand the way ``plan_evaluation`` returns them."""

import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[2] / "shared"
if _shared.is_dir() and str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

from evaluation_planning import (  # noqa: E402
    EvaluationPlan,
    judge_call_counts,
    judge_runs,
    resolve_judges,
)


def _plan(gen_cells=(), ann_cells=()):
    return EvaluationPlan(
        task_ids=["t1"],
        config_sides=[],
        classifier_unavailable=False,
        gen_cells=list(gen_cells),
        ann_cells=list(ann_cells),
    )


def _cfg(cid, preds, judges, refs=("musterloesung",), metric="llm_judge_falloesung"):
    return {
        "id": cid,
        "metric": metric,
        "prediction_fields": list(preds),
        "reference_fields": list(refs),
        "metric_parameters": {"judges": judges},
    }


def test_each_open_field_pair_costs_one_call_per_judge_run():
    cfg = _cfg(
        "c1",
        ["__all_model__"],
        [{"judge_model_id": "gpt-5.4-mini", "runs": 3}, {"judge_model_id": "opus", "runs": 1}],
    )
    plan = _plan(gen_cells=[("t1", "g1", []), ("t1", "g2", [])])
    assert judge_call_counts(plan, [cfg]) == {"gpt-5.4-mini": 6, "opus": 2}


def test_graded_field_pairs_are_not_counted_again():
    cfg = _cfg("c1", ["__all_model__"], [{"judge_model_id": "j", "runs": 1}],
               refs=("a", "b"))
    plan = _plan(gen_cells=[("t1", "g1", ["c1|__all_model__|a"])])
    assert judge_call_counts(plan, [cfg]) == {"j": 1}


def test_answer_cells_grade_the_human_fields():
    # Plain fields of a Falllösung config are answer-side; the stored key
    # carries no human: prefix and still counts as graded.
    cfg = _cfg("c1", ["loesung"], [{"judge_model_id": "j", "runs": 1}])
    plan = _plan(ann_cells=[("t1", "a1", []), ("t1", "a2", ["c1|loesung|musterloesung"])])
    assert judge_call_counts(plan, [cfg]) == {"j": 1}


def test_metrics_without_a_judge_cost_nothing():
    cfg = {"id": "b", "metric": "bleu", "prediction_fields": ["__all_model__"],
           "reference_fields": ["musterloesung"]}
    assert judge_call_counts(_plan(gen_cells=[("t1", "g1", [])]), [cfg]) == {}


def test_a_config_without_judges_uses_the_default_judge():
    from model_defaults import DEFAULT_JUDGE_MODEL_ID

    cfg = {"id": "c", "metric": "llm_judge_classic", "metric_parameters": None}
    assert judge_runs(cfg) == [(DEFAULT_JUDGE_MODEL_ID, 1)]
    assert resolve_judges({"judge_model": "x", "runs_per_judge": 2}) == [
        {"judge_model_id": "x", "runs": 2}
    ]
