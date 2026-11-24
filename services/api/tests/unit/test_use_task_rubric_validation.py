"""Saving an evaluation config with ``metric_parameters.use_task_rubric``.

Only the rubric judge and metrics registered as sheet judges
(``task_rubric_resolution.register_sheet_judge_metric``) grade along the
task's sheet; any other metric with the switch would be held for a sheet it
never reads, so the save is refused. Registering a metric for an answer type
alone does not make it a sheet judge.
"""

import copy

import pytest
from fastapi import HTTPException

import services.evaluation.config as cfg
from routers.evaluations.config import validate_evaluation_config_entries
from services.evaluation.config import register_extended_metrics
from task_rubric_resolution import register_sheet_judge_metric, unregister_sheet_judge_metric


@pytest.fixture
def sheet_judge():
    register_sheet_judge_metric("sample_sheet_judge")
    try:
        yield "sample_sheet_judge"
    finally:
        unregister_sheet_judge_metric("sample_sheet_judge")


@pytest.fixture
def extension_metric():
    saved = copy.deepcopy(cfg._extended_metrics)
    register_extended_metrics("long_text", ["sample_extension_judge"], owner="sample")
    try:
        yield "sample_extension_judge"
    finally:
        cfg._extended_metrics.clear()
        cfg._extended_metrics.update(saved)


def _config(metric, **params):
    return [{
        "id": "judge",
        "metric": metric,
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.reference"],
        "metric_parameters": params,
        "enabled": True,
    }]


def test_a_registered_sheet_judge_may_grade_along_the_sheet(sheet_judge):
    validate_evaluation_config_entries(_config(sheet_judge, use_task_rubric=True))


def test_the_rubric_judge_may_carry_the_switch():
    validate_evaluation_config_entries(
        _config("llm_judge_rubric", use_task_rubric=True, custom_prompt_template="Grade {answer}")
    )


@pytest.mark.parametrize("metric", ["llm_judge_custom", "llm_judge_coherence", "bleu", "unregistered_judge"])
def test_an_unregistered_metric_with_the_switch_is_refused(metric, sheet_judge):
    with pytest.raises(HTTPException) as refused:
        validate_evaluation_config_entries(_config(metric, use_task_rubric=True))
    assert refused.value.status_code == 422
    assert "use_task_rubric" in refused.value.detail


def test_an_extension_metric_not_registered_as_sheet_judge_is_refused(extension_metric):
    with pytest.raises(HTTPException) as refused:
        validate_evaluation_config_entries(_config(extension_metric, use_task_rubric=True))
    assert refused.value.status_code == 422


def test_the_switch_off_is_accepted_on_any_metric():
    validate_evaluation_config_entries(_config("llm_judge_custom", use_task_rubric=False))
