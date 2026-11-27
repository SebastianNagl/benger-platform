"""A grading on submit held for the teacher, against the real test Postgres.

A config whose ``metric_parameters`` say ``auto_release: false`` holds its
first AI grading (core 2.92, ``grading_basis.holds_first_grading``):
``run_single_sample_evaluation`` stores its row as a draft
(``details.review = {"status": "draft", "reason": "held"}``) and no
"grading received" notice goes out. The row is a draft from the moment a
second session can see it, while other configs of the run still grade, and
it stays one when the run fails afterwards. A config without the key grades
and notifies exactly as before, also next to a held one in the same run.
"""

import threading
import uuid

import pytest
from celery.exceptions import SoftTimeLimitExceeded

import tasks
from evaluation import orchestration
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


def _seen_review(record_id):
    """The review of a row as another session sees it right now."""
    db = tasks.SessionLocal()
    try:
        row = db.query(TaskEvaluation).filter(TaskEvaluation.id == record_id).first()
        if row is None:
            return "missing"
        blob = row.metrics.get(next(k for k in row.metrics if k != "raw_score"))
        return ((blob or {}).get("details") or {}).get("review")
    finally:
        db.close()


def _probe_while_running(monkeypatch, held_id):
    """Let every other config's job wait for the held job to return, then
    record what a separate session sees of the held row."""
    seen = {}
    held_done = threading.Event()
    real_job = tasks._run_immediate_config_job

    def _job(**kwargs):
        job = kwargs["job"]
        if job["evaluation_config_id"] == held_id:
            try:
                return real_job(**kwargs)
            finally:
                seen["record_id"] = job["record_id"]
                held_done.set()
        assert held_done.wait(timeout=30)
        seen["review"] = _seen_review(seen["record_id"])
        return real_job(**kwargs)

    monkeypatch.setattr(tasks, "_run_immediate_config_job", _job)
    return seen


def test_a_held_row_is_a_draft_while_another_config_still_grades(
    db_conn, cleanup, recorded, submission, monkeypatch
):
    student, project, task, annotation = submission
    seen = _probe_while_running(monkeypatch, "held")

    _out, run, rows = _grade(
        db_conn, cleanup, project, task, annotation,
        [_config("held", auto_release=False), _config("plain")],
    )

    assert seen["review"] == {"status": "draft", "reason": "held"}
    assert run.status == "completed"
    assert row_awaits_release(rows["held"].metrics)
    assert not row_awaits_release(rows["plain"].metrics)


class _OverlayJudge:
    """An overlay judge that persists its own row and stores no review."""

    def evaluate_single(self, *, db, record_id, immediate_eval_id, task_id,
                        annotation_id, field_name, prediction, judge_run_id,
                        evaluation_config_id, metric, **_kwargs):
        db.add(
            TaskEvaluation(
                id=record_id,
                evaluation_id=immediate_eval_id,
                judge_run_id=judge_run_id,
                task_id=task_id,
                annotation_id=annotation_id,
                generation_id=None,
                field_name=field_name,
                evaluation_config_id=evaluation_config_id,
                answer_type="text",
                ground_truth="",
                prediction=prediction,
                metrics={metric: {"value": 0.8, "method": metric, "details": {}}},
                passed=True,
            )
        )
        db.commit()
        return {"status": "completed", "record_id": record_id, "metric": metric}


def test_an_overlay_writers_held_row_is_a_draft_while_another_config_still_grades(
    db_conn, cleanup, recorded, submission, monkeypatch
):
    student, project, task, annotation = submission
    metric = "llm_judge_overlay_probe"
    monkeypatch.setattr(
        orchestration,
        "resolve_inline_judge",
        lambda name: _OverlayJudge() if name == metric else None,
    )
    seen = _probe_while_running(monkeypatch, "held")
    held = {**_config("held", auto_release=False), "metric": metric}

    _out, run, rows = _grade(
        db_conn, cleanup, project, task, annotation, [held, _config("plain")]
    )

    assert seen["review"] == {"status": "draft", "reason": "held"}
    assert run.status == "completed"
    assert rows["held"].metrics[metric]["value"] == 0.8
    assert row_awaits_release(rows["held"].metrics)
    assert not row_awaits_release(rows["plain"].metrics)


@pytest.mark.parametrize("failure", [RuntimeError("boom"), SoftTimeLimitExceeded()])
def test_a_run_that_fails_after_the_held_row_was_committed_keeps_it_a_draft(
    db_conn, cleanup, recorded, submission, monkeypatch, failure
):
    """A writer committed the held row without its draft; the run then
    fails before its completion pass. The failure handler stores the draft."""
    student, project, task, annotation = submission

    def _bare_writer(**kwargs):
        job = kwargs["job"]
        db = tasks.SessionLocal()
        try:
            db.add(
                TaskEvaluation(
                    id=job["record_id"],
                    evaluation_id=kwargs["dispatch_eval_id"],
                    judge_run_id=job["judge_run_id"],
                    task_id=kwargs["task_id"],
                    annotation_id=kwargs["annotation_id"],
                    generation_id=None,
                    field_name=job["field_name"],
                    evaluation_config_id=job["evaluation_config_id"],
                    answer_type="text",
                    ground_truth="ja",
                    prediction="ja",
                    metrics={"exact_match": {"value": 1.0, "method": "exact_match",
                                             "details": {}}},
                    passed=True,
                )
            )
            db.commit()
        finally:
            db.close()
        return {"status": "completed", "record_id": job["record_id"]}

    def _fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(tasks, "_run_immediate_config_job", _bare_writer)
    monkeypatch.setattr(tasks, "_finalize_judge_runs_by_rows", _fail)

    out, run, rows = _grade(
        db_conn, cleanup, project, task, annotation,
        [_config("held", auto_release=False), _config("plain")],
    )

    assert out["status"] == "error"
    assert run.status == "failed"
    assert rows["held"].metrics["exact_match"]["details"]["review"] == {
        "status": "draft", "reason": "held"
    }
    assert row_awaits_release(rows["held"].metrics)
    assert not row_awaits_release(rows["plain"].metrics)
    assert recorded == []
