"""End-to-end: an overlay inline judge (core 2.41) through the real bulk cells.

Drives ``run_evaluation`` over a human annotation and over a model
generation with an ``llm_judge_feedback`` config whose judge comes from the
overlay hook (faked here). The judge returns written feedback and no score:
the rows must land with ``value=None``, ``passed=True``, the judge's audit
prompt and the row context, and the run must complete, without the generic
score parser turning them into "LLM judge evaluation failed" rows.
"""

import uuid

import pytest

import tasks
from models import TaskEvaluation
from project_models import TaskRubric
from task_rubric_resolution import (
    RUBRIC_MISSING,
    register_sheet_judge_metric,
    unregister_sheet_judge_metric,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


class _FeedbackJudge:
    calls = []

    @staticmethod
    def compute(**kwargs):
        _FeedbackJudge.calls.append(kwargs)
        return {
            "feedback_markdown": f"## Overview\n\nOn: {kwargs['prediction']}",
            "_judge_prompts_used": {"system": "s", "user": "u"},
        }

    @staticmethod
    def build_row(*, result, error_message):
        return {
            "metrics": {
                "llm_judge_feedback": {
                    "value": None,
                    "method": "llm_judge_feedback",
                    "details": {"feedback_only": True, **(result or {})},
                    "error": error_message,
                }
            },
            "passed": not error_message,
        }


@pytest.fixture()
def feedback_overlay(monkeypatch):
    monkeypatch.setenv("E2E_TEST_MODE", "true")
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: None
    )
    import evaluation.cell_evaluator as cell_evaluator

    monkeypatch.setattr(
        cell_evaluator,
        "resolve_inline_judge",
        lambda metric: _FeedbackJudge if metric == "llm_judge_feedback" else None,
    )
    _FeedbackJudge.calls = []
    return _FeedbackJudge


@pytest.fixture()
def registered_sheet_judge():
    register_sheet_judge_metric("llm_judge_feedback")
    try:
        yield
    finally:
        unregister_sheet_judge_metric("llm_judge_feedback")


def _config(pred_field):
    return {
        "id": "fb",
        "metric": "llm_judge_feedback",
        "prediction_fields": [pred_field],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {
            "judges": [{"judge_model_id": "gpt-4o", "runs": 1}],
            "exam_type": "sample",
        },
        "enabled": True,
    }


def test_annotation_cell_writes_score_less_feedback_rows(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay,
):
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"sachverhalt": "case text", "musterloesung": "reference text"}, created_by=user.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": "answer text"}}],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[_config("human:loesung")],
    )
    db_conn.expire_all()
    assert result["ann_cells"] == 1

    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.annotation_id == annotation.id
    assert row.generation_id is None
    assert row.passed is True
    assert row.error_message is None
    assert row.judge_prompts_used == {"system": "s", "user": "u"}
    blob = row.metrics["llm_judge_feedback"]
    assert blob["value"] is None
    assert blob["details"]["feedback_markdown"].endswith("answer text")
    [call] = feedback_overlay.calls
    assert call["metric_params"]["exam_type"] == "sample"
    assert call["task_data"]["sachverhalt"] == "case text"

    # A "missing only" re-run does not pay for the same feedback again.
    run2 = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()
    tasks.run_evaluation(
        evaluation_id=run2.id, project_id=project.id,
        evaluation_configs=[_config("human:loesung")], evaluate_missing_only=True,
    )
    assert len(feedback_overlay.calls) == 1


def test_generation_cell_writes_score_less_feedback_rows(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, feedback_overlay,
):
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "reference text"}, created_by=user.id)
    _, gen = make_generation(project.id, task.id, model.id, user.id, response_content="model answer")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[_config("__all_model__")],
    )
    db_conn.expire_all()
    assert result["gen_cells"] == 1
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.generation_id == gen.id
    assert row.passed is True
    assert row.metrics["llm_judge_feedback"]["value"] is None


@pytest.fixture()
def switched_off_overlay(monkeypatch):
    """The package that judges llm_judge_feedback is off for the task."""
    monkeypatch.setenv("E2E_TEST_MODE", "true")
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: None
    )
    import evaluation.cell_evaluator as cell_evaluator

    monkeypatch.setattr(cell_evaluator, "resolve_inline_judge", lambda metric: None)
    monkeypatch.setattr(
        cell_evaluator,
        "inactive_inline_judge_owner",
        lambda metric: "benger_extended" if metric == "llm_judge_feedback" else None,
        raising=False,
    )


@pytest.mark.parametrize("pred_field", ["human:loesung", "__all_model__"])
def test_a_switched_off_owner_writes_the_feature_disabled_row(
    pred_field, db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_generation, make_evaluation_run, switched_off_overlay,
):
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "reference text"}, created_by=user.id)
    make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": "answer text"}}],
    )
    make_generation(project.id, task.id, model.id, user.id, response_content="model answer")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[_config(pred_field)],
    )
    db_conn.expire_all()
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    blob = row.metrics["llm_judge_feedback"]
    # No generic judge ran: no score, the switched-off package named.
    assert blob["value"] is None
    assert blob["error"] == "feature_disabled"
    assert blob["details"]["reason"] == "feature_disabled"
    assert row.passed is False
    assert row.judge_prompts_used is None


def _sheet_config():
    config = _config("human:loesung")
    config["metric_parameters"] = {**config["metric_parameters"], "use_task_rubric": True}
    return config


def _graded_annotation(db_conn, make_user, make_llm_model, make_project, make_task, make_annotation):
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"sachverhalt": "case text", "musterloesung": "reference text"}, created_by=user.id)
    make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": "answer text"}}],
    )
    return user, project, task


def test_a_sheet_judge_cell_gets_the_tasks_active_sheet(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay, registered_sheet_judge,
):
    """Core 2.81: an inline judge config with use_task_rubric grades along
    the task's active sheet, which the cell hands to ``compute``."""
    user, project, task = _graded_annotation(
        db_conn, make_user, make_llm_model, make_project, make_task, make_annotation
    )
    sheet = TaskRubric(
        id=str(uuid.uuid4()), task_id=task.id, project_id=project.id,
        criteria={"s01_first": {"name": "First criterion", "rubric": "r", "max_score": 2}},
        total_points=2, status="active",
    )
    db_conn.add(sheet)
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id, evaluation_configs=[_sheet_config()],
    )
    [call] = feedback_overlay.calls
    assert call["task_rubric"].id == sheet.id
    db_conn.expire_all()
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.passed is True


def test_a_sheet_judge_cell_without_a_sheet_is_the_rubric_missing_row(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay, registered_sheet_judge,
):
    user, project, task = _graded_annotation(
        db_conn, make_user, make_llm_model, make_project, make_task, make_annotation
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id, evaluation_configs=[_sheet_config()],
    )
    assert feedback_overlay.calls == []
    db_conn.expire_all()
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.passed is False
    assert row.metrics["llm_judge_feedback"]["error_code"] == RUBRIC_MISSING


def test_an_unregistered_metric_with_the_switch_is_no_sheet_judge(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay,
):
    """Without a registration the switch makes no sheet judge: the cell runs
    the judge without a sheet instead of writing the rubric_missing row."""
    user, project, task = _graded_annotation(
        db_conn, make_user, make_llm_model, make_project, make_task, make_annotation
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id, evaluation_configs=[_sheet_config()],
    )
    [call] = feedback_overlay.calls
    assert "task_rubric" not in call
    db_conn.expire_all()
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.passed is True


def test_a_judge_without_the_setting_gets_no_sheet(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay,
):
    user, project, task = _graded_annotation(
        db_conn, make_user, make_llm_model, make_project, make_task, make_annotation
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id, evaluation_configs=[_config("human:loesung")],
    )
    [call] = feedback_overlay.calls
    assert "task_rubric" not in call


def test_a_bewertungsbogen_judge_cell_without_a_sheet_is_the_rubric_missing_row(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, feedback_overlay,
):
    """Regression: with only LLM judge configs in the run there is no
    default judge run, and the sheet-missing row of an llm_judge_rubric cell
    was written without a judge_run_id (NOT NULL), failing the whole cell."""
    user, project, task = _graded_annotation(
        db_conn, make_user, make_llm_model, make_project, make_task, make_annotation
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()
    config = {
        "id": "sheet",
        "metric": "llm_judge_rubric",
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {"judges": [{"judge_model_id": "gpt-4o", "runs": 1}]},
        "enabled": True,
    }
    tasks.run_evaluation(evaluation_id=run.id, project_id=project.id, evaluation_configs=[config])
    db_conn.expire_all()
    [row] = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert row.judge_run_id is not None
    assert row.metrics["llm_judge_rubric"]["error_code"] == RUBRIC_MISSING
