"""Immediate-eval path of ``llm_judge_rubric`` (judge_evaluator impl).

The immediate path resolves the task's Bewertungsbogen exactly like the
bulk cell path: metric ``llm_judge_rubric`` looks up the task row and its
active rubric BEFORE any judge call, and a missing/unusable rubric raises
the shared ``_NO_RUBRIC_ERROR`` so the caller persists a clear config
error instead of silently grading without an instrument.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from evaluation.cell_evaluator import _NO_RUBRIC_ERROR
from evaluation.judge_evaluator import _evaluate_llm_judge_single_impl


def _impl_kwargs(db):
    return dict(
        db=db,
        record_id="rec-1",
        immediate_eval_id="imm-1",
        project_id="proj-1",
        task_id="task-1",
        annotation_id=None,
        user_id="user-1",
        field_name="cfg|pred|ref",
        metric_type="llm_judge_rubric",
        prediction="Bearbeitung …",
        reference="Musterlösung …",
        metric_params={"judge_model": "gpt-5.4-mini"},
        organization_id=None,
    )


def _judge_factory_mock():
    judge = MagicMock()
    judge.ai_service = object()  # truthy → passes the availability gate
    return judge


def test_missing_task_row_raises_no_rubric_error():
    db = MagicMock()
    # DBLLMModel lookup and ProjectTask lookup both go through db.query();
    # returning None everywhere makes the task row None → rubric None.
    db.query.return_value.filter.return_value.first.return_value = None
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=_judge_factory_mock(),
    ):
        with pytest.raises(RuntimeError) as exc:
            _evaluate_llm_judge_single_impl(**_impl_kwargs(db))
    assert str(exc.value) == _NO_RUBRIC_ERROR.format(task_id="task-1")


def test_rubric_multidim_path_binds_rendering_and_stamps_provenance():
    """Happy path: active rubric found → criteria injected, the rendered
    document bound as {bewertungsbogen}, Musterlösung swapped in as
    reference, and rubric id + generator stamped into details and
    judge_prompts_used."""
    db = MagicMock()
    task_row = SimpleNamespace(
        id="task-1", data={"musterlösung": "Die echte Musterlösung"}
    )
    db.query.return_value.filter.return_value.first.return_value = task_row

    rubric = SimpleNamespace(
        id="rub-9",
        generator_model_id="gpt-5.4",
        criteria={"s01_x": {"name": "X", "rubric": "r", "max_score": 100}},
        generation_metadata={"rendered_text": "BEWERTUNGSBOGEN (100 Rohpunkte)"},
    )

    judge = _judge_factory_mock()
    judge.is_multidim_mode.return_value = True
    judge._evaluate_multidim_single_call.return_value = {
        "scores": {"s01_x": {"score": 80, "max": 100, "reason": "ok"}},
        "total_score": 80.0,
        "total_max": 100.0,
        "overall_assessment": "solide",
        "_call_metadata": {},
        "_raw_output": "",
        "_judge_prompts_used": {"system": "…"},
    }

    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=judge,
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=rubric
    ):
        result = _evaluate_llm_judge_single_impl(**_impl_kwargs(db))

    assert result["status"] == "completed"
    assert result["score"] == pytest.approx(0.8)
    # criteria were injected from the rubric, not from config
    assert judge.custom_criteria == rubric.criteria
    call = judge._evaluate_multidim_single_call.call_args.kwargs
    # rendered document bound for the {bewertungsbogen} placeholder
    assert call["task_data"]["bewertungsbogen"].startswith("BEWERTUNGSBOGEN")
    # Musterlösung from task data replaced the passed-in reference
    assert call["ground_truth"] == "Die echte Musterlösung"
    # provenance stamped
    persisted = db.add.call_args.args[0]
    details = persisted.metrics["llm_judge_rubric"]["details"]
    assert details["rubric_id"] == "rub-9"
    assert persisted.judge_prompts_used["task_rubric_id"] == "rub-9"
    assert persisted.judge_prompts_used["task_rubric_generator"] == "gpt-5.4"


def test_unusable_rubric_raises_no_rubric_error():
    db = MagicMock()
    task_row = SimpleNamespace(id="task-1", data={})
    db.query.return_value.filter.return_value.first.return_value = task_row
    with patch(
        "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
        return_value=_judge_factory_mock(),
    ), patch(
        "evaluation.cell_evaluator._resolve_task_rubric", return_value=None
    ) as resolver:
        with pytest.raises(RuntimeError) as exc:
            _evaluate_llm_judge_single_impl(**_impl_kwargs(db))
    assert resolver.called
    assert "task-1" in str(exc.value)
    assert "Bewertungsbogen" in str(exc.value)
