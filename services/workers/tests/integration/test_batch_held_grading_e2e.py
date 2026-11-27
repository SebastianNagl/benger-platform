"""A held AI grading in batch runs, against the real test Postgres.

A config whose ``metric_parameters`` say ``auto_release: false`` holds the
AI grading of a submission for a teacher in a batch run too (core 2.92,
``grading_basis.stamp_rows``): its row of a submitted answer is written as
a draft (``details.review = {"status": "draft", "reason": "held"}``) that
no batch notice announces. A config without the key writes and announces
its rows as before, a model generation's row is never held, and a batch
run over an answer with a released grading leaves that one visible.
"""

import pytest
from sqlalchemy.orm.attributes import flag_modified

import tasks
from current_scores import pick_current
from metric_filters import row_awaits_release
from models import EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

HELD = {"status": "draft", "reason": "held"}


def _answer_config(**params):
    return {
        "id": "exam",
        "metric": "exact_match",
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.expected"],
        "metric_parameters": params,
        "enabled": True,
    }


@pytest.fixture()
def exam(db_conn, make_user, make_project, make_task, make_annotation):
    teacher = make_user(name="Teacher")
    student = make_user(name="Student")
    project = make_project(created_by=teacher.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=teacher.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=student.id,
        result=[{"from_name": "loesung", "type": "textarea", "value": {"text": ["ja"]}}],
    )
    return {"teacher": teacher, "project": project, "task": task, "annotation": annotation}


def _batch(db_conn, make_evaluation_run, exam, config, **kwargs):
    project = exam["project"]
    project.evaluation_config = {"evaluation_configs": [config]}
    flag_modified(project, "evaluation_config")
    db_conn.commit()
    run = make_evaluation_run(project.id, exam["teacher"].id, status="pending")
    tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id, evaluation_configs=[config], **kwargs
    )
    db_conn.expire_all()
    rows = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run.id).all()
    return db_conn.get(EvaluationRun, run.id), rows


def _review(row):
    return (row.metrics["exact_match"].get("details") or {}).get("review")


def test_a_missing_only_batch_holds_the_first_grading(db_conn, exam, make_evaluation_run):
    run, rows = _batch(
        db_conn, make_evaluation_run, exam, _answer_config(auto_release=False),
        evaluate_missing_only=True,
    )

    [row] = rows
    assert row.annotation_id == exam["annotation"].id
    assert _review(row) == HELD
    assert row.metrics["exact_match"]["value"] == 1.0
    assert row_awaits_release(row.metrics)
    assert "annotators_notified" not in (run.eval_metadata or {})


def test_a_batch_without_the_key_releases_and_announces(db_conn, exam, make_evaluation_run):
    run, rows = _batch(
        db_conn, make_evaluation_run, exam, _answer_config(), evaluate_missing_only=True
    )

    [row] = rows
    assert _review(row) is None
    assert not row_awaits_release(row.metrics)
    assert run.eval_metadata.get("annotators_notified") is True


def test_a_generation_row_of_a_holding_config_is_not_held(
    db_conn, exam, make_llm_model, make_generation, make_evaluation_run
):
    model = make_llm_model(provider="OpenAI")
    _rg, generation = make_generation(
        exam["project"].id, exam["task"].id, model.id, exam["teacher"].id,
        response_content="ja",
    )
    config = {
        "id": "model",
        "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {"auto_release": False},
        "enabled": True,
    }

    _run, rows = _batch(db_conn, make_evaluation_run, exam, config)

    [row] = [r for r in rows if r.generation_id == generation.id]
    assert _review(row) is None
    assert not row_awaits_release(row.metrics)


def test_a_batch_over_a_released_grading_keeps_that_one_visible(
    db_conn, exam, make_evaluation_run
):
    _first_run, [released] = _batch(db_conn, make_evaluation_run, exam, _answer_config())
    assert not row_awaits_release(released.metrics)

    _second_run, [held] = _batch(
        db_conn, make_evaluation_run, exam, _answer_config(auto_release=False)
    )

    assert held.id != released.id
    assert _review(held) == HELD
    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.annotation_id == exam["annotation"].id)
        .all()
    )
    # A student surface reads only rows that do not await their release.
    visible = [row for row in rows if not row_awaits_release(row.metrics)]
    [current] = pick_current(visible).values()
    assert current.id == released.id
