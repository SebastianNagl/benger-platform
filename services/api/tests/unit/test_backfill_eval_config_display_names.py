"""Unit tests for the eval-config display-name backfill's pure naming logic.

The heavy DB imports live inside the script's ``main()``, so importing these
pure helpers needs no database. The rule (judge run counts + ensembles) MUST
match the frontend helper ``computeDefaultEvalName`` in
``services/frontend/src/lib/evaluation/evalName.ts``.
"""

from __future__ import annotations

from scripts.backfill_eval_config_display_names import (
    compute_default_eval_name,
    plan_project,
)

FALL = "Falllösung LLM Judge"


def _cfg(judges=None, judge_model=None, metric="llm_judge_falloesung", display_name=FALL):
    params = {}
    if judges is not None:
        params["judges"] = judges
    if judge_model is not None:
        params["judge_model"] = judge_model
    cfg = {"metric": metric, "metric_parameters": params}
    if display_name is not None:
        cfg["display_name"] = display_name
    return cfg


def test_single_judge_one_run_bare_model():
    cfg = _cfg(judges=[{"runs": 1, "judge_model_id": "gpt-5-mini"}])
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini)"


def test_single_judge_three_runs():
    cfg = _cfg(judges=[{"runs": 3, "judge_model_id": "gpt-5-mini"}])
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini ×3)"


def test_same_model_twice_runs_sum():
    cfg = _cfg(
        judges=[
            {"runs": 1, "judge_model_id": "gpt-5-mini"},
            {"runs": 1, "judge_model_id": "gpt-5-mini"},
        ]
    )
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini ×2)"


def test_missing_runs_defaults_to_one():
    cfg = _cfg(judges=[{"judge_model_id": "gpt-5-mini"}])
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini)"


def test_ensemble_three_distinct_preserves_order():
    cfg = _cfg(
        judges=[
            {"runs": 1, "judge_model_id": "gpt-5-mini"},
            {"runs": 1, "judge_model_id": "claude-opus-4-7"},
            {"runs": 1, "judge_model_id": "gemini-3.1-pro-preview"},
        ]
    )
    assert (
        compute_default_eval_name(cfg)
        == f"{FALL} (gpt-5-mini + claude-opus-4-7 + gemini-3.1-pro-preview)"
    )


def test_ensemble_mixed_run_counts():
    cfg = _cfg(
        judges=[
            {"runs": 2, "judge_model_id": "gpt-5-mini"},
            {"runs": 1, "judge_model_id": "claude-opus-4-7"},
        ]
    )
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini ×2 + claude-opus-4-7)"


def test_legacy_judge_model_no_judges():
    cfg = _cfg(judge_model="gpt-5-mini")
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini)"


def test_judges_takes_precedence_over_legacy():
    cfg = _cfg(
        judges=[{"runs": 1, "judge_model_id": "x"}],
        judge_model="gpt-4o",
        metric="llm_judge_classic",
        display_name="Classic LLM Judge",
    )
    assert compute_default_eval_name(cfg) == "Classic LLM Judge (x)"


def test_model_ids_with_slash_pass_through_verbatim():
    cfg = _cfg(
        judges=[
            {"runs": 1, "judge_model_id": "deepseek-ai/DeepSeek-V4-Pro"},
            {"runs": 3, "judge_model_id": "Qwen/Qwen3.5-397B-A17B"},
        ]
    )
    assert (
        compute_default_eval_name(cfg)
        == f"{FALL} (deepseek-ai/DeepSeek-V4-Pro + Qwen/Qwen3.5-397B-A17B ×3)"
    )


def test_non_llm_metric_unchanged():
    cfg = {
        "metric": "bleu",
        "display_name": "BLEU",
        "metric_parameters": {"max_order": 4},
    }
    assert compute_default_eval_name(cfg) == "BLEU"


def test_korrektur_metric_unchanged_no_parens():
    cfg = _cfg(
        judge_model="gpt-5-mini",
        metric="korrektur_falloesung",
        display_name="Korrektur Fallloesung",
    )
    assert compute_default_eval_name(cfg) == "Korrektur Fallloesung"


def test_llm_judge_without_model_unchanged():
    cfg = _cfg(display_name="Classic LLM Judge", metric="llm_judge_classic")
    assert compute_default_eval_name(cfg) == "Classic LLM Judge"


def test_idempotent_already_enriched():
    cfg = _cfg(
        judges=[{"runs": 3, "judge_model_id": "gpt-5-mini"}],
        display_name=f"{FALL} (gpt-5-mini ×3)",
    )
    assert compute_default_eval_name(cfg) == f"{FALL} (gpt-5-mini ×3)"


def test_base_falls_back_to_metric_when_no_display_name():
    cfg = _cfg(judge_model="gpt-4o", metric="llm_judge_classic", display_name=None)
    assert compute_default_eval_name(cfg) == "llm_judge_classic (gpt-4o)"


def test_plan_project_reports_only_changed_configs():
    evaluation_config = {
        "evaluation_configs": [
            _cfg(judges=[{"runs": 3, "judge_model_id": "gpt-5-mini"}]),
            {"metric": "bleu", "display_name": "BLEU", "metric_parameters": {}},
        ]
    }
    changes = plan_project(evaluation_config)
    assert changes == [(0, FALL, f"{FALL} (gpt-5-mini ×3)")]


def test_plan_project_is_idempotent():
    evaluation_config = {
        "evaluation_configs": [
            _cfg(
                judges=[{"runs": 3, "judge_model_id": "gpt-5-mini"}],
                display_name=f"{FALL} (gpt-5-mini ×3)",
            )
        ]
    }
    assert plan_project(evaluation_config) == []


def test_plan_project_handles_non_config_shapes():
    assert plan_project(None) == []
    assert plan_project({}) == []
    assert plan_project({"evaluation_configs": "not-a-list"}) == []
    assert plan_project("garbage") == []
