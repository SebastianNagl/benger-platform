"""Immediate gradings with nothing to grade, against the real test Postgres.

Prod regression: the hourly sweep re-dispatched the same 14 annotations
every hour. Every run skipped all configs ("no prediction value") and was
still stamped ``completed`` with no grade, so the next sweep saw the
annotation as ungraded again.

* ``run_single_sample_evaluation`` marks such a run ``nothing_to_grade``
  and reports it to the finalize hook as not successful.
* ``sweep_missing_immediate_evals`` dispatches only annotations with an
  answer, and stops after ``SWEEP_MAX_ATTEMPTS`` runs without a grade.

The extended package is faked through ``sys.modules``; the Celery send of
the sweep is captured.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import immediate_eval_dispatch as ied
import tasks
from models import EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _install_extended(monkeypatch, **hooks):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    for name, fn in hooks.items():
        setattr(workers, name, (lambda f: (lambda: f))(fn))
    pkg.workers = workers
    monkeypatch.setitem(sys.modules, "benger_extended", pkg)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)


def _config(cid, *fields):
    return {
        "id": cid,
        "metric": "exact_match",
        "display_name": cid,
        "enabled": True,
        "prediction_fields": list(fields),
        "reference_fields": ["task.expected"],
        "metric_parameters": {},
    }


def _textarea(name, value):
    return {"from_name": name, "to_name": "text", "type": "textarea", "value": value}


def _run_worker(db_conn, cleanup, project, task, annotation, configs, results):
    run_id = str(uuid.uuid4())
    cleanup.evaluation_run_ids.append(run_id)
    out = tasks.run_single_sample_evaluation.run(
        evaluation_record_id=run_id,
        project_id=project.id,
        task_id=task.id,
        annotation_id=annotation.id,
        evaluation_configs=configs,
        annotation_results=results,
        task_data=task.data,
        user_id=annotation.completed_by,
    )
    db_conn.expire_all()
    run = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run_id).one()
    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run_id)
        .count()
    )
    return out, run, rows


def test_worker_marks_a_run_with_nothing_to_grade(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=user.id, result=[_textarea("loesung", "")]
    )
    settled = []
    _install_extended(
        monkeypatch,
        get_grading_finalize_fn=lambda run_id, success: settled.append((run_id, success)),
    )

    configs = [_config("cfg-human", "human:loesung"), _config("cfg-model", "__all_model__")]
    out, run, rows = _run_worker(
        db_conn, cleanup, project, task, annotation, configs, {"loesung": ""}
    )

    assert out["status"] == "completed"
    assert out["results"] == []
    assert rows == 0
    # Still `completed`: the results modal lists the methods as skipped.
    assert run.status == "completed"
    assert run.samples_evaluated == 0
    marker = run.eval_metadata["nothing_to_grade"]
    assert marker["reason"] == "no_prediction_value"
    assert [c["id"] for c in marker["skipped_configs"]] == ["cfg-human", "cfg-model"]
    # Not a successful grading: a metered ledger row is voided.
    assert settled == [(run.id, False)]


def test_worker_grades_a_real_answer_as_before(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_textarea("loesung", {"text": ["ja"]})],
    )
    settled = []
    _install_extended(
        monkeypatch,
        get_grading_finalize_fn=lambda run_id, success: settled.append((run_id, success)),
    )

    configs = [_config("cfg-human", "human:loesung"), _config("cfg-model", "__all_model__")]
    out, run, rows = _run_worker(
        db_conn, cleanup, project, task, annotation, configs, {"loesung": "ja"}
    )

    assert out["status"] == "completed"
    assert rows == 1
    assert run.status == "completed"
    assert run.samples_evaluated == 1
    assert "nothing_to_grade" not in run.eval_metadata
    assert settled == [(run.id, True)]


def _immediate_project(db_conn, make_project, user, configs):
    project = make_project(created_by=user.id)
    project.immediate_evaluation_enabled = True
    project.evaluation_config = {"evaluation_configs": configs}
    db_conn.commit()
    return project


def _age(db_conn, *annotations):
    for a in annotations:
        a.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_conn.commit()


def test_sweep_dispatches_only_annotations_with_an_answer(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    """The three prod shapes (empty list, empty string, fields other than the
    graded one) and a model-only project are never dispatched."""
    user = make_user()
    exam = _immediate_project(
        db_conn, make_project, user,
        [_config("cfg-human", "human:loesung"), _config("cfg-model", "__all_model__")],
    )

    def _submit(result):
        # One task per annotation: a user has one active annotation per task.
        task = make_task(exam.id, {"expected": "ja"}, created_by=user.id)
        return make_annotation(exam.id, task.id, completed_by=user.id, result=result)

    empty_list = _submit([])
    empty_text = _submit([_textarea("loesung", "")])
    other_fields = _submit([_textarea("notizen", ""), _textarea("gliederung", "")])
    real = _submit([_textarea("loesung", {"text": ["ja"]})])

    model_only = _immediate_project(
        db_conn, make_project, user, [_config("cfg-model", "__all_model__")]
    )
    model_task = make_task(model_only.id, {"expected": "ja"}, created_by=user.id)
    model_real = make_annotation(
        model_only.id, model_task.id, completed_by=user.id,
        result=[_textarea("answer", {"text": ["Nein, belastendes ..."]})],
    )
    _age(db_conn, empty_list, empty_text, other_fields, real, model_real)

    sent = []
    monkeypatch.setattr(
        ied, "_dispatch_task", lambda name, kwargs, queue: sent.append(kwargs)
    )
    _install_extended(monkeypatch)
    ours = {exam.id, model_only.id}

    def _our_runs():
        db_conn.expire_all()
        return (
            db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id.in_(ours))
            .all()
        )

    try:
        for _ in range(2):
            assert tasks.sweep_missing_immediate_evals.run()["status"] == "success"
            # The fake send never runs the worker, so finish the run the
            # way prod did: completed without a grade.
            for r in _our_runs():
                if r.status == "running":
                    r.status = "completed"
            db_conn.commit()

        dispatched = [k["annotation_id"] for k in sent if k["project_id"] in ours]
        # The real answer is retried (its runs graded nothing); nothing else
        # is ever dispatched.
        assert dispatched == [real.id, real.id]
    finally:
        cleanup.evaluation_run_ids.extend(r.id for r in _our_runs())


def test_sweep_stops_after_max_attempts(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    user = make_user()
    exam = _immediate_project(
        db_conn, make_project, user, [_config("cfg-human", "human:loesung")]
    )
    task = make_task(exam.id, {"expected": "ja"}, created_by=user.id)
    real = make_annotation(
        exam.id, task.id, completed_by=user.id,
        result=[_textarea("loesung", {"text": ["ja"]})],
    )
    _age(db_conn, real)

    sent = []
    monkeypatch.setattr(
        ied, "_dispatch_task", lambda name, kwargs, queue: sent.append(kwargs)
    )
    _install_extended(monkeypatch)

    def _our_runs():
        db_conn.expire_all()
        return (
            db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id == exam.id)
            .all()
        )

    try:
        for _ in range(ied.SWEEP_MAX_ATTEMPTS + 2):
            tasks.sweep_missing_immediate_evals.run()
            for r in _our_runs():
                if r.status == "running":
                    # A transient judge outage: the run fails every time.
                    r.status = "failed"
                    r.error_message = "judge unavailable"
            db_conn.commit()

        ours = [k for k in sent if k["project_id"] == exam.id]
        assert len(ours) == ied.SWEEP_MAX_ATTEMPTS
        assert len(_our_runs()) == ied.SWEEP_MAX_ATTEMPTS
        result = tasks.sweep_missing_immediate_evals.run()
        assert result["capped"] >= 1

        # A manual retrigger is not capped.
        outcome = ied.ensure_immediate_evaluation_outcome(
            db_conn, exam, task, real, trigger="manual_retrigger"
        )
        assert outcome.status == ied.OUTCOME_DISPATCHED
    finally:
        cleanup.evaluation_run_ids.extend(r.id for r in _our_runs())
