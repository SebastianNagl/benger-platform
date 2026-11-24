"""A judge that reads its reference fields itself grades once per answer.

A judge whose prompt names a reference field (``{bewertungsbogen}``) sees
every reference in one call, so a batch run used to write one near-identical
score per reference field. It now writes one row per prediction field, under
the first reference field (or the next one when the task lacks the first).
A judge whose prompt only uses ``{ground_truth}`` still grades once per
reference field: each one is a different grading. The judge runs in its
built-in E2E mock (no network); assertions are on the persisted rows.
"""

import pytest

import tasks
from models import TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

REFS = ["task.musterloesung", "task.bewertungsbogen"]


@pytest.fixture()
def mock_judge_mode(monkeypatch):
    monkeypatch.setenv("E2E_TEST_MODE", "true")
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: None
    )


def _config(config_id, template):
    return {
        "id": config_id,
        "metric": "llm_judge_correctness",
        "prediction_fields": ["human:loesung"],
        "reference_fields": REFS,
        "metric_parameters": {
            "judges": [{"judge_model_id": "gpt-4o", "runs": 1}],
            "score_scale": "0-1",
            "custom_prompt_template": template,
        },
        "enabled": True,
    }


def _grade(db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
           config, task_data):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, task_data, created_by=user.id)
    make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": ["Antwort"]}}],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()
    tasks.run_evaluation(evaluation_id=run.id, project_id=project.id, evaluation_configs=[config])
    db_conn.expire_all()
    return (
        db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    )


def test_prompt_naming_a_reference_grades_once(
    mock_judge_mode, db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    config = _config("sheet", "{ground_truth}\n{bewertungsbogen}\n{prediction}")
    rows = _grade(
        db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
        config, {"musterloesung": "M", "bewertungsbogen": "B"},
    )
    assert [r.field_name for r in rows] == ["sheet|human:loesung|task.musterloesung"]
    assert rows[0].ground_truth == "M"


def test_missing_first_reference_falls_back_to_the_next(
    mock_judge_mode, db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    config = _config("sheet", "{ground_truth}\n{bewertungsbogen}\n{prediction}")
    rows = _grade(
        db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
        config, {"bewertungsbogen": "B"},
    )
    # Same cell key as on a task that has both, so a later missing-only run
    # recognises it; the judge got the reference the task has.
    assert [r.field_name for r in rows] == ["sheet|human:loesung|task.musterloesung"]
    assert rows[0].ground_truth == "B"


def test_ground_truth_only_prompt_grades_per_reference(
    mock_judge_mode, db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    config = _config("plain", "{ground_truth}\n{prediction}")
    rows = _grade(
        db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
        config, {"musterloesung": "M", "bewertungsbogen": "B"},
    )
    assert sorted(r.field_name for r in rows) == [
        "plain|human:loesung|task.bewertungsbogen",
        "plain|human:loesung|task.musterloesung",
    ]


def test_on_submit_row_names_the_answer_field_it_graded(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    """A config that lists a model-side selector first grades the answer
    field on submit; its row used to carry ``__all_model__`` as its field."""
    import sys
    import types
    import uuid

    from models import EvaluationRun

    pkg = types.ModuleType("benger_extended")
    pkg.workers = types.ModuleType("benger_extended.workers")
    monkeypatch.setitem(sys.modules, "benger_extended", pkg)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", pkg.workers)

    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "Die Klage ist zulässig."})
    answer = [{"from_name": "loesung", "to_name": "text", "type": "textarea",
               "value": {"text": ["Die Klage ist zulässig."]}}]
    annotation = make_annotation(project.id, task.id, completed_by=user.id, result=answer)
    config = {
        "id": "cfg-both", "metric": "exact_match", "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["task.musterloesung"], "metric_parameters": {},
    }
    run_id = str(uuid.uuid4())
    cleanup.evaluation_run_ids.append(run_id)
    out = tasks.run_single_sample_evaluation.run(
        evaluation_record_id=run_id,
        project_id=project.id,
        task_id=task.id,
        annotation_id=annotation.id,
        evaluation_configs=[config],
        annotation_results={"loesung": "Die Klage ist zulässig."},
        task_data=task.data,
        user_id=annotation.completed_by,
    )
    assert out["status"] == "completed", out
    db_conn.expire_all()
    assert db_conn.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()
    rows = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run_id).all()
    assert [(r.field_name, r.evaluation_config_id) for r in rows] == [("human:loesung", "cfg-both")]
