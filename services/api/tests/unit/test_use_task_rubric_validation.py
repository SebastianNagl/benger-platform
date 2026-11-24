"""Saving an evaluation config with ``metric_parameters.use_task_rubric``.

Only the rubric judge and judges an extension registers grade along the
task's sheet; a platform judge such as ``llm_judge_custom`` with the switch
would be held for a sheet it never reads, so the save is refused.
"""

import copy

import pytest
from fastapi import HTTPException

import services.evaluation.config as cfg
from routers.evaluations.config import validate_evaluation_config_entries
from services.evaluation.config import register_extended_metrics


@pytest.fixture
def extension_judge():
    saved = copy.deepcopy(cfg._extended_metrics)
    register_extended_metrics("long_text", ["llm_judge_sample_extension"], owner="sample")
    try:
        yield "llm_judge_sample_extension"
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


def test_an_extension_judge_may_grade_along_the_sheet(extension_judge):
    validate_evaluation_config_entries(_config(extension_judge, use_task_rubric=True))


def test_the_rubric_judge_may_carry_the_switch():
    validate_evaluation_config_entries(
        _config("llm_judge_rubric", use_task_rubric=True, custom_prompt_template="Grade {answer}")
    )


@pytest.mark.parametrize("metric", ["llm_judge_custom", "llm_judge_coherence", "bleu"])
def test_a_platform_metric_with_the_switch_is_refused(metric, extension_judge):
    with pytest.raises(HTTPException) as refused:
        validate_evaluation_config_entries(_config(metric, use_task_rubric=True))
    assert refused.value.status_code == 422
    assert "use_task_rubric" in refused.value.detail


def test_the_switch_off_is_accepted_on_any_metric():
    validate_evaluation_config_entries(_config("llm_judge_custom", use_task_rubric=False))
