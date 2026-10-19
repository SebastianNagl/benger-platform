"""End-to-end: an overlay inline judge (core 2.41) through the real bulk cells.

Drives ``run_evaluation`` over a human annotation and over a model
generation with an ``llm_judge_feedback`` config whose judge comes from the
overlay hook (faked here). The judge returns written feedback and no score:
the rows must land with ``value=None``, ``passed=True``, the judge's audit
prompt and the row context, and the run must complete, without the generic
score parser turning them into "LLM judge evaluation failed" rows.
"""

import pytest

import tasks
from models import TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


class _FeedbackJudge:
    calls = []

    @staticmethod
    def compute(**kwargs):
        _FeedbackJudge.calls.append(kwargs)
        return {
            "feedback_markdown": f"## Introduction\n\nSur: {kwargs['prediction']}",
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


def _config(pred_field):
    return {
        "id": "fb",
        "metric": "llm_judge_feedback",
        "prediction_fields": [pred_field],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {
            "judges": [{"judge_model_id": "gpt-4o", "runs": 1}],
            "exam_type": "fr-dissertation",
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
    task = make_task(project.id, {"sachverhalt": "Sujet", "musterloesung": "Corrigé"}, created_by=user.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": "Ma copie"}}],
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
    assert blob["details"]["feedback_markdown"].endswith("Ma copie")
    [call] = feedback_overlay.calls
    assert call["metric_params"]["exam_type"] == "fr-dissertation"
    assert call["task_data"]["sachverhalt"] == "Sujet"

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
    task = make_task(project.id, {"musterloesung": "Corrigé"}, created_by=user.id)
    _, gen = make_generation(project.id, task.id, model.id, user.id, response_content="Copie du modèle")
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
