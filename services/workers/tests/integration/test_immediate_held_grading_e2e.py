"""A grading on submit held for the teacher, against the real test Postgres.

A config whose ``metric_parameters`` say ``auto_release: false`` holds its
first AI grading (core 2.92, ``grading_basis.holds_first_grading``):
``run_single_sample_evaluation`` stores its row as a draft
(``details.review = {"status": "draft", "reason": "held"}``) in the commit
that completes the run, and no "grading received" notice goes out. A
config without the key grades and notifies exactly as before, also next to
a held one in the same run.
"""

import uuid

import pytest

import tasks
from metric_filters import row_awaits_release
from models import EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    def _record(db, user_ids, notification_type, title, message, data=None,
                organization_id=None):
        calls.append(
            {
                "user_ids": list(user_ids),
                "type": getattr(notification_type, "value", notification_type),
            }
        )
        return []

    monkeypatch.setattr(
        tasks.NotificationService, "create_notification", staticmethod(_record)
    )
    return calls


def _config(cid, **params):
    return {
        "id": cid,
        "metric": "exact_match",
        "display_name": cid,
        "enabled": True,
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.expected"],
        "metric_parameters": params,
    }


def _grade(db_conn, cleanup, project, task, annotation, configs):
    run_id = str(uuid.uuid4())
    cleanup.evaluation_run_ids.append(run_id)
    out = tasks.run_single_sample_evaluation.run(
        evaluation_record_id=run_id,
        project_id=project.id,
        task_id=task.id,
        annotation_id=annotation.id,
        evaluation_configs=configs,
        annotation_results={"loesung": "ja"},
        task_data=task.data,
        user_id=annotation.completed_by,
    )
    db_conn.expire_all()
    run = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()
    rows = {
        row.evaluation_config_id: row
        for row in db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run_id)
    }
    return out, run, rows


@pytest.fixture
def submission(make_user, make_project, make_task, make_annotation):
    student = make_user("Student")
    project = make_project(created_by=student.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=student.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=student.id,
        result=[{"from_name": "loesung", "to_name": "text", "type": "textarea",
                 "value": {"text": ["ja"]}}],
    )
    return student, project, task, annotation


def test_a_held_config_stores_its_grading_as_a_draft(db_conn, cleanup, recorded, submission):
    student, project, task, annotation = submission

    out, run, rows = _grade(
        db_conn, cleanup, project, task, annotation, [_config("held", auto_release=False)]
    )

    assert out["status"] == "completed"
    assert run.status == "completed"
    row = rows["held"]
    blob = row.metrics["exact_match"]
    assert blob["details"]["review"] == {"status": "draft", "reason": "held"}
    # The judge's result is kept as written; readers skip the draft.
    assert blob["value"] == 1.0
    assert row_awaits_release(row.metrics)
    # The student hears about it when a teacher releases it, not now.
    assert recorded == []


def test_without_the_key_the_grading_is_released_and_announced(
    db_conn, cleanup, recorded, submission
):
    student, project, task, annotation = submission

    _out, _run, rows = _grade(
        db_conn, cleanup, project, task, annotation,
        [_config("plain"), _config("released", auto_release=True)],
    )

    for row in rows.values():
        assert "review" not in (row.metrics["exact_match"].get("details") or {})
        assert not row_awaits_release(row.metrics)
    assert [call["user_ids"] for call in recorded] == [[student.id]]
    assert recorded[0]["type"] == "evaluation_received_immediate"


def test_a_held_config_next_to_a_released_one(db_conn, cleanup, recorded, submission):
    """Only the held config's row waits; the other one is the student's at
    once and announces the grading."""
    student, project, task, annotation = submission

    _out, _run, rows = _grade(
        db_conn, cleanup, project, task, annotation,
        [_config("held", auto_release=False), _config("plain")],
    )

    assert row_awaits_release(rows["held"].metrics)
    assert not row_awaits_release(rows["plain"].metrics)
    assert [call["user_ids"] for call in recorded] == [[student.id]]
