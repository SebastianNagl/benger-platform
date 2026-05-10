"""Unit tests for `CostEstimateRequest` cross-mode validator (issue #69 B3).

The validator rejects payloads that mix generation mode with eval-only
keys (`evaluation_configs`, `annotator_user_ids`, `judge_models`). Keeps
the behavior contract — silent ignore was the prior bug. Pure Pydantic
roundtrip; no DB or app boot."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from routers.cost_estimate import CostEstimateRequest, EvalConfigForCost


def test_generation_mode_minimal_payload_accepts():
    req = CostEstimateRequest(
        project_id="p1",
        mode="generation",
        model_ids=["gpt-5"],
        runs_per_call=1,
    )
    assert req.mode == "generation"


def test_generation_mode_with_judge_models_rejects():
    with pytest.raises(ValidationError) as exc_info:
        CostEstimateRequest(
            project_id="p1",
            mode="generation",
            model_ids=["gpt-5"],
            judge_models=["claude-haiku"],
        )
    assert "judge_models" in str(exc_info.value)


def test_generation_mode_with_eval_configs_rejects():
    with pytest.raises(ValidationError) as exc_info:
        CostEstimateRequest(
            project_id="p1",
            mode="generation",
            model_ids=["gpt-5"],
            evaluation_configs=[
                EvalConfigForCost(metric="exact_match", prediction_fields=["x"])
            ],
        )
    assert "evaluation_configs" in str(exc_info.value)


def test_generation_mode_with_annotator_user_ids_rejects():
    with pytest.raises(ValidationError) as exc_info:
        CostEstimateRequest(
            project_id="p1",
            mode="generation",
            model_ids=["gpt-5"],
            annotator_user_ids=["uid-1"],
        )
    assert "annotator_user_ids" in str(exc_info.value)


def test_evaluation_mode_with_eval_only_keys_accepts():
    """The eval-only keys are exactly what eval mode needs — accepting them
    is the whole point. This is the positive control for the validator."""
    req = CostEstimateRequest(
        project_id="p1",
        mode="evaluation",
        judge_models=["claude-haiku"],
        annotator_user_ids=["uid-1", "uid-2"],
        evaluation_configs=[
            EvalConfigForCost(metric="llm_judge_falloesung", prediction_fields=["loesung"])
        ],
    )
    assert req.mode == "evaluation"
    assert req.annotator_user_ids == ["uid-1", "uid-2"]
    assert len(req.evaluation_configs) == 1


def test_evaluation_mode_with_model_ids_accepts():
    """`model_ids` is shared between modes — for eval it narrows generation
    subjects, for generation it picks which models to call. Validator must
    not reject it."""
    req = CostEstimateRequest(
        project_id="p1",
        mode="evaluation",
        judge_models=["claude-haiku"],
        model_ids=["gpt-5"],
    )
    assert req.model_ids == ["gpt-5"]


def test_validator_lists_all_offending_keys():
    """When multiple cross-mode keys are set, the error message names all of
    them — clients can fix the payload in one shot instead of trial-and-error."""
    with pytest.raises(ValidationError) as exc_info:
        CostEstimateRequest(
            project_id="p1",
            mode="generation",
            model_ids=["gpt-5"],
            judge_models=["claude-haiku"],
            annotator_user_ids=["uid-1"],
            evaluation_configs=[
                EvalConfigForCost(metric="x", prediction_fields=["y"])
            ],
        )
    msg = str(exc_info.value)
    assert "evaluation_configs" in msg
    assert "annotator_user_ids" in msg
    assert "judge_models" in msg
