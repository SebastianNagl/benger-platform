"""The ``text_pattern`` metric in a real generation cell."""

from __future__ import annotations

import pytest

# The feature is behind a platform flag (off by default in the suite).
pytestmark = pytest.mark.flags_on("variant_experiments")

PATTERN_SET = {
    "name": "parties",
    "version": "3",
    "codes": {"names_party": {"mode": "count", "patterns": [r"\b{{task.party}}\b"]}},
}


def _params(code):
    return {"pattern_set": PATTERN_SET, "code": code}

@pytest.mark.integration
@pytest.mark.database
@pytest.mark.parametrize(
    "reference_fields", [[], ["task.expected"], ["task.expected", "task.party"]],
    ids=["none", "absent", "two"],
)
def test_a_generation_cell_codes_the_answer_without_a_reference(
    reference_fields,
    db_conn, make_user, make_llm_model, make_project, make_task, make_generation, make_evaluation_run
):
    """A real generation cell: a code runs once per prediction field,
    whether the config lists no reference field, one the task lacks (which
    skips any other metric) or two."""
    import uuid

    import tasks
    from models import EvaluationJudgeRun, TaskEvaluation

    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"party": "Meier"}, created_by=user.id)
    _, gen = make_generation(project.id, task.id, model.id, user.id, response_content="Meier, the Claimant")
    run = make_evaluation_run(project.id, user.id, status="running")
    judge_run_id = str(uuid.uuid4())
    db_conn.add(EvaluationJudgeRun(id=judge_run_id, evaluation_id=run.id, judge_model_id=None,
                                   run_index=0, status="running"))
    db_conn.commit()
    config = {
        "id": "codes", "metric": "text_pattern", "prediction_fields": ["__all_model__"],
        "reference_fields": reference_fields, "metric_parameters": _params("names_party"), "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs={
        "evaluation_id": run.id, "task_id": task.id, "generation_id": gen.id, "project_id": project.id,
        "configs_for_cell": [config], "judge_run_ids_by_config": {},
        "default_judge_run_id": judge_run_id, "organization_id": None,
        "triggered_by_user_id": user.id, "already_evaluated_field_keys": [],
    }).get()
    assert res.get("status") == "ok", res
    rows = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert len(rows) == 1
    assert rows[0].field_name == "codes|__all_model__|"
    metric = rows[0].metrics["text_pattern"]
    assert metric["value"] == 1.0 and metric["details"]["pattern_set"]["ref"] == "parties@3"


@pytest.mark.integration
@pytest.mark.database
def test_an_annotation_cell_codes_the_answer_once_without_a_reference(
    db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run
):
    import uuid

    import tasks
    from models import EvaluationJudgeRun, TaskEvaluation

    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"party": "Meier"}, created_by=user.id)
    ann = make_annotation(project.id, task.id, user.id, [
        {"from_name": "loesung", "to_name": "text", "type": "textarea",
         "value": {"text": ["Meier and Meier again"]}},
    ])
    run = make_evaluation_run(project.id, user.id, status="running")
    judge_run_id = str(uuid.uuid4())
    db_conn.add(EvaluationJudgeRun(id=judge_run_id, evaluation_id=run.id, judge_model_id=None,
                                   run_index=0, status="running"))
    db_conn.commit()
    config = {
        "id": "codes", "metric": "text_pattern", "prediction_fields": ["human:loesung"],
        "reference_fields": [], "metric_parameters": _params("names_party"), "enabled": True,
    }
    res = tasks.evaluate_annotation_cell.apply(kwargs={
        "evaluation_id": run.id, "task_id": task.id, "annotation_id": ann.id, "project_id": project.id,
        "configs_for_cell": [config], "judge_run_ids_by_config": {},
        "default_judge_run_id": judge_run_id, "organization_id": None,
        "triggered_by_user_id": user.id, "already_evaluated_field_keys": [],
    }).get()
    assert res.get("status") == "ok", res
    rows = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    assert [r.field_name for r in rows] == ["codes|human:loesung|"]
    assert rows[0].metrics["text_pattern"]["value"] == 2.0
