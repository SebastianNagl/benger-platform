"""Sheet judges without a Bewertungsbogen, against the real test Postgres.

Prod regression (2026-11): students got the raw English error row "No usable
Bewertungsbogen for task ..." from the immediate grading of an exam whose
task had no active sheet. Since core 2.54:

* ``run_single_sample_evaluation`` skips such a judge
  (``skipped_configs[].reason == "rubric_missing"``) and writes no error row;
  the other configs still grade.
* the hourly sweep holds a grading that has only such judges as one blocked
  run (reason ``rubric_missing``) and keeps retrying it beyond
  ``SWEEP_MAX_ATTEMPTS``;
* ``tasks.dispatch_waiting_gradings`` grades the held answers of a task once
  its sheet is active;
* an error row that still says the sheet is missing carries
  ``error_code == "rubric_missing"``.

The extended package is faked through ``sys.modules``; Celery sends are
captured.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import immediate_eval_dispatch as ied
import tasks
from models import EvaluationRun, TaskEvaluation
from project_models import TaskRubric
from task_rubric_resolution import RUBRIC_MISSING, NoUsableRubricError

pytestmark = [pytest.mark.integration, pytest.mark.database]

SHEET_CRITERIA = {"s01_pruefung": {"name": "Prüfung", "rubric": "r", "max_score": 10}}


def _install_extended(monkeypatch, **hooks):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    for name, fn in hooks.items():
        setattr(workers, name, (lambda f: (lambda: f))(fn))
    pkg.workers = workers
    monkeypatch.setitem(sys.modules, "benger_extended", pkg)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)


def _sheet_judge(cid="cfg-sheet"):
    return {
        "id": cid,
        "metric": "llm_judge_rubric",
        "display_name": "Bewertungsbogen",
        "enabled": True,
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {"provider": "openai", "judge_model": "gpt-test"},
    }


def _exact(cid="cfg-exact"):
    return {
        "id": cid,
        "metric": "exact_match",
        "display_name": cid,
        "enabled": True,
        "prediction_fields": ["human:loesung"],
        "reference_fields": ["task.musterloesung"],
        "metric_parameters": {},
    }


def _answer(text="Die Klage ist zulässig."):
    return [
        {"from_name": "loesung", "to_name": "text", "type": "textarea", "value": {"text": [text]}}
    ]


def _exam(db_conn, make_project, user, configs):
    project = make_project(created_by=user.id)
    project.immediate_evaluation_enabled = True
    project.evaluation_config = {"evaluation_configs": configs}
    db_conn.commit()
    return project


def _sheet(db_conn, task, *, status="active", review_state=None):
    row = TaskRubric(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=task.project_id,
        criteria=SHEET_CRITERIA,
        total_points=10,
        status=status,
        review_state=review_state,
    )
    db_conn.add(row)
    db_conn.commit()
    return row


def _run_worker(db_conn, cleanup, project, task, annotation, configs):
    run_id = str(uuid.uuid4())
    cleanup.evaluation_run_ids.append(run_id)
    out = tasks.run_single_sample_evaluation.run(
        evaluation_record_id=run_id,
        project_id=project.id,
        task_id=task.id,
        annotation_id=annotation.id,
        evaluation_configs=configs,
        annotation_results={"loesung": "Die Klage ist zulässig."},
        task_data=task.data,
        user_id=annotation.completed_by,
    )
    db_conn.expire_all()
    run = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()
    rows = db_conn.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id == run_id).all()
    return out, run, rows


def _runs(db_conn, project_id):
    db_conn.expire_all()
    return (
        db_conn.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .order_by(EvaluationRun.created_at)
        .all()
    )


def _age(db_conn, *annotations):
    for a in annotations:
        a.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_conn.commit()


def test_worker_skips_a_sheet_judge_without_a_sheet(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "Die Klage ist zulässig."})
    annotation = make_annotation(project.id, task.id, completed_by=user.id, result=_answer())
    settled = []
    _install_extended(
        monkeypatch,
        get_grading_finalize_fn=lambda run_id, success: settled.append((run_id, success)),
    )

    out, run, rows = _run_worker(
        db_conn, cleanup, project, task, annotation, [_sheet_judge(), _exact()]
    )

    assert out["status"] == "completed"
    # The other config grades; the sheet judge writes no error row.
    assert [set(r.metrics) for r in rows] == [{"exact_match", "raw_score"}]
    assert not any(r.error_message for r in rows)
    assert run.status == "completed"
    assert "nothing_to_grade" not in run.eval_metadata
    assert settled == [(run.id, True)]


def test_worker_with_only_held_sheet_judges_grades_nothing(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "Die Klage ist zulässig."})
    # A candidate is not usable: only the active sheet grades.
    _sheet(db_conn, task, status="candidate")
    annotation = make_annotation(project.id, task.id, completed_by=user.id, result=_answer())
    settled = []
    _install_extended(
        monkeypatch,
        get_grading_finalize_fn=lambda run_id, success: settled.append((run_id, success)),
    )

    out, run, rows = _run_worker(db_conn, cleanup, project, task, annotation, [_sheet_judge()])

    assert out["status"] == "completed"
    assert rows == []
    marker = run.eval_metadata["nothing_to_grade"]
    assert marker["reason"] == RUBRIC_MISSING
    assert marker["skipped_configs"] == [
        {
            "id": "cfg-sheet",
            "metric": "llm_judge_rubric",
            "prediction_fields": ["human:loesung"],
            "reason": RUBRIC_MISSING,
        }
    ]
    assert settled == [(run.id, False)]


def test_worker_keeps_a_sheet_judge_with_an_active_sheet(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "Die Klage ist zulässig."})
    _sheet(db_conn, task)
    annotation = make_annotation(project.id, task.id, completed_by=user.id, result=_answer())
    _install_extended(monkeypatch)
    judged = []

    def fake_judge(**kwargs):
        judged.append(kwargs["metric_type"])
        return {"status": "completed", "metric": kwargs["metric_type"]}

    monkeypatch.setattr(tasks, "_evaluate_llm_judge_single", fake_judge)

    out, run, _rows = _run_worker(db_conn, cleanup, project, task, annotation, [_sheet_judge()])

    assert judged == ["llm_judge_rubric"]
    assert "nothing_to_grade" not in run.eval_metadata


def test_a_late_missing_sheet_error_row_carries_the_code(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    """The sheet went away between the skip check and the judge."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"musterloesung": "Die Klage ist zulässig."})
    _sheet(db_conn, task)
    annotation = make_annotation(project.id, task.id, completed_by=user.id, result=_answer())
    _install_extended(monkeypatch)

    def vanished(**kwargs):
        raise NoUsableRubricError(kwargs["task_id"])

    monkeypatch.setattr(tasks, "_evaluate_llm_judge_single", vanished)

    _out, _run, rows = _run_worker(db_conn, cleanup, project, task, annotation, [_sheet_judge()])

    (row,) = rows
    cell = row.metrics["llm_judge_rubric"]
    assert cell["error_code"] == RUBRIC_MISSING
    assert cell["error"].startswith("No usable Bewertungsbogen")


def test_sweep_holds_the_grading_without_cap_then_the_sheet_releases_it(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation, monkeypatch
):
    user = make_user()
    exam = _exam(db_conn, make_project, user, [_sheet_judge()])
    task = make_task(exam.id, {"musterloesung": "Die Klage ist zulässig."})
    other_task = make_task(exam.id, {"musterloesung": "Die Klage ist unbegründet."})
    answer = make_annotation(exam.id, task.id, completed_by=user.id, result=_answer())
    other = make_annotation(exam.id, other_task.id, completed_by=user.id, result=_answer())
    _age(db_conn, answer, other)

    sent = []
    monkeypatch.setattr(
        ied, "_dispatch_task", lambda name, kwargs, queue: sent.append((name, kwargs))
    )
    _install_extended(monkeypatch)

    try:
        for _ in range(ied.SWEEP_MAX_ATTEMPTS + 2):
            result = tasks.sweep_missing_immediate_evals.run()
            assert result["status"] == "success"
        # Never dispatched, never capped: one held run per answer, refreshed.
        assert [k for _n, k in sent if k["project_id"] == exam.id] == []
        held = _runs(db_conn, exam.id)
        assert len(held) == 2
        for run in held:
            block = run.eval_metadata["billing_block"]
            assert block["reason"] == RUBRIC_MISSING
            assert run.error_message == "billing_blocked:rubric_missing"
        assert ied.grading_retry_state(db_conn, exam, answer)["state"] == ied.RETRY_HELD

        # The sheet of one task becomes usable: only its answer is graded.
        _sheet(db_conn, task, review_state="confirmed")
        out = tasks.dispatch_waiting_gradings.run(task_id=task.id)

        assert out == {
            "status": "success",
            "waiting": 1,
            "dispatched": 1,
            "blocked": 0,
            "other": 0,
            "failed": 0,
        }
        dispatched = [(n, k) for n, k in sent if k["project_id"] == exam.id]
        assert [(n, k["annotation_id"]) for n, k in dispatched] == [
            ("tasks.run_single_sample_evaluation", answer.id)
        ]
        assert [c["metric"] for c in dispatched[0][1]["evaluation_configs"]] == [
            "llm_judge_rubric"
        ]
        by_annotation = {}
        for run in _runs(db_conn, exam.id):
            by_annotation.setdefault(run.eval_metadata["annotation_id"], []).append(run)
        released = by_annotation[answer.id]
        assert released[0].eval_metadata["billing_block"]["superseded_by"] == released[1].id
        assert released[1].eval_metadata["trigger"] == ied.RUBRIC_READY_TRIGGER
        assert ied.latest_blocked_run(db_conn, exam.id, other) is not None

        # Nothing else waits on that task any more.
        again = tasks.dispatch_waiting_gradings.run(task_id=task.id)
        assert again["waiting"] == 0
    finally:
        cleanup.evaluation_run_ids.extend(r.id for r in _runs(db_conn, exam.id))


def test_dispatch_waiting_gradings_routes_to_interactive():
    import celery_queues

    assert celery_queues.queue_for("tasks.dispatch_waiting_gradings") == celery_queues.INTERACTIVE
    assert "tasks.dispatch_waiting_gradings" in tasks.app.tasks
