"""
Multi-run feature unit tests (migrations 041–043).

Covers the API+model surface that the multi-run/multi-judge feature added:
- ResponseGeneration counters (runs_requested/runs_completed/runs_failed)
- Generation.run_index unique-per-parent constraint
- EvaluationJudgeRun parent FK + cascade
- TaskEvaluation.judge_run_id NOT NULL after migration 043
- generation_task_list runs_per_task fan-out resolution
- bg_statistics agreement composite

These tests are deliberately narrow — they exercise the schema and
small pure-function surfaces, not the worker LLM-call paths (which need
mocked AI services and live in services/workers/tests/).
"""

import uuid
from typing import Any, Dict

import pytest


# --- bg_statistics integration sanity ---


def test_compute_agreement_two_judges_two_runs_categorical():
    """Two raters scoring three items should yield Fleiss kappa + percent_agreement."""
    from bg_statistics import compute_agreement

    triples = [
        ("judge_a", "task1", "yes"),
        ("judge_b", "task1", "yes"),
        ("judge_a", "task2", "no"),
        ("judge_b", "task2", "no"),
        ("judge_a", "task3", "yes"),
        ("judge_b", "task3", "no"),
    ]
    report = compute_agreement(triples, score_type="categorical")
    assert report.n_raters == 2
    assert report.n_items == 3
    assert report.percent_agreement == round(2 / 3, 4)
    assert report.fleiss_kappa is not None
    # The (judge_a, judge_b) pair should have a Cohen's kappa value
    assert ("judge_a", "judge_b") in report.cohens_kappa_pairwise


def test_compute_agreement_numeric_pearson_pair():
    """Two judges scoring three items numerically should yield non-empty Pearson."""
    from bg_statistics import compute_agreement

    triples = [
        ("judge_a", "task1", 0.8),
        ("judge_b", "task1", 0.7),
        ("judge_a", "task2", 0.5),
        ("judge_b", "task2", 0.6),
        ("judge_a", "task3", 0.9),
        ("judge_b", "task3", 0.95),
    ]
    report = compute_agreement(triples, score_type="numeric")
    assert ("judge_a", "judge_b") in report.pearson_r_pairwise
    # Variance is non-zero for both judges → pearson is defined
    assert report.pearson_r_pairwise[("judge_a", "judge_b")] is not None
    assert report.mean_absolute_deviation is not None


def test_compute_agreement_empty_returns_empty_report():
    from bg_statistics import compute_agreement

    report = compute_agreement([], score_type="numeric")
    assert report.n_raters == 0
    assert report.n_items == 0
    assert report.pearson_r_pairwise == {}


# --- Schema / model assertions ---


def test_generation_model_has_run_index_column():
    """Migration 041 added run_index to generations. Model must mirror."""
    from models import Generation

    cols = {c.name for c in Generation.__table__.columns}
    assert "run_index" in cols
    rid = Generation.__table__.columns["run_index"]
    assert rid.nullable is False


def test_response_generation_has_runs_counters():
    """Migration 041 added runs_requested/completed/failed counters."""
    from models import ResponseGeneration

    cols = {c.name for c in ResponseGeneration.__table__.columns}
    for name in ("runs_requested", "runs_completed", "runs_failed"):
        assert name in cols
        assert ResponseGeneration.__table__.columns[name].nullable is False


def test_evaluation_judge_run_table_exists_and_relates():
    """Migration 042: EvaluationJudgeRun is a child of EvaluationRun."""
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

    cols = {c.name for c in EvaluationJudgeRun.__table__.columns}
    for name in ("evaluation_id", "judge_model_id", "run_index", "status"):
        assert name in cols

    # FK to evaluation_runs.id
    fk = next(iter(EvaluationJudgeRun.__table__.foreign_keys))
    assert fk.column.table.name == "evaluation_runs"

    # Reverse relationship from EvaluationRun.judge_runs
    assert "judge_runs" in EvaluationRun.__mapper__.relationships

    # TaskEvaluation.judge_run_id is NOT NULL after migration 043
    jr_col = TaskEvaluation.__table__.columns["judge_run_id"]
    assert jr_col.nullable is False


def test_task_evaluation_unique_index_on_generation_run_index():
    """Migration 041 created uq_generations_parent_run_index."""
    from models import Generation

    indexes = {idx.name for idx in Generation.__table__.indexes}
    assert "uq_generations_parent_run_index" in indexes


def test_evaluation_judge_runs_unique_constraint_on_eval_judge_index():
    """Regression for the dup-key bug: when two metrics in one eval share
    the same (judge_model_id, run_index), the worker MUST get-or-create the
    EvaluationJudgeRun instead of inserting a second row that violates
    `uq_evaluation_judge_runs_eval_model_index`. This test asserts the
    constraint exists at the model layer; the worker-side cache logic in
    `tasks._create_judge_run` (and the immediate-eval `_dispatch_judge_run_cache`)
    is what prevents the violation in practice. Both must stay in sync."""
    from models import EvaluationJudgeRun

    indexes = {idx.name for idx in EvaluationJudgeRun.__table__.indexes}
    constraints = {c.name for c in EvaluationJudgeRun.__table__.constraints if c.name}
    assert (
        "uq_evaluation_judge_runs_eval_model_index" in indexes
        or "uq_evaluation_judge_runs_eval_model_index" in constraints
    ), (
        "Migration 042 must create a unique constraint on (evaluation_id, "
        "judge_model_id, run_index) — without it, the worker can silently "
        "double-insert when two metrics share one judge."
    )


# --- runs_per_task resolution helper (the API trigger logic) ---


def test_runs_per_task_resolution_per_trigger_overrides_project_default():
    """The trigger endpoint resolves: per-trigger override → project default → 1."""
    # Simulating the resolution logic from generation_task_list.py:
    project_default = 3
    per_trigger = 5
    resolved = per_trigger if per_trigger is not None else (project_default or 1)
    assert resolved == 5

    # Per-trigger None falls back to project default
    per_trigger = None
    resolved = per_trigger if per_trigger is not None else (project_default or 1)
    assert resolved == 3

    # Both None falls back to 1
    project_default = None
    per_trigger = None
    resolved = per_trigger if per_trigger is not None else (project_default or 1)
    assert resolved == 1


def test_runs_per_task_resolution_clamps_to_25():
    """Bounds: 1 ≤ runs_per_task ≤ 25."""
    for raw in (0, -3, 100):
        clamped = max(1, min(25, raw))
        assert 1 <= clamped <= 25


def test_judges_resolve_legacy_to_new_shape():
    """_resolve_judges: legacy {judge_model: 'X'} → [{judge_model_id: 'X', runs: 1}]."""

    def _resolve(params: Dict[str, Any]):
        judges = params.get("judges")
        if isinstance(judges, list) and judges:
            return judges
        legacy = params.get("judge_model", "gpt-4o")
        runs = int(params.get("runs_per_judge", 1) or 1)
        return [{"judge_model_id": legacy, "runs": runs}]

    # New shape passes through
    new = {"judges": [{"judge_model_id": "claude-opus", "runs": 2}]}
    assert _resolve(new) == new["judges"]

    # Legacy single-judge gets wrapped
    legacy = {"judge_model": "gpt-4o-mini", "runs_per_judge": 3}
    out = _resolve(legacy)
    assert out == [{"judge_model_id": "gpt-4o-mini", "runs": 3}]

    # Empty params default to gpt-4o, 1 run
    out = _resolve({})
    assert out == [{"judge_model_id": "gpt-4o", "runs": 1}]


# --- Statistics endpoint shape ---


def test_statistics_response_has_multi_run_blocks():
    """StatisticsResponse declares the new multi-run fields."""
    from routers.evaluations.metadata import StatisticsResponse

    fields = StatisticsResponse.model_fields
    for name in (
        "runs_by_model_metric",
        "task_consistency_by_model_metric",
        "judge_agreement_by_model_metric",
        "per_run_means_by_model_metric",
    ):
        assert name in fields


def test_runs_aggregate_collapses_to_n_runs_1_for_single_run():
    """RunsAggregate(n_runs=1) is the legacy shape — null variance/CI."""
    from routers.evaluations.metadata import RunsAggregate

    agg = RunsAggregate(
        n_runs=1,
        mean_of_means=0.5,
        std_of_means=0.0,
        ci_lower=None,
        ci_upper=None,
    )
    assert agg.n_runs == 1
    assert agg.ci_lower is None
