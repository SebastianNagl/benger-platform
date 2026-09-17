"""Billing extension hooks against the real test Postgres (core 2.20).

* ``run_evaluation``: a batch run the billing policy refuses fails with the
  reason before any judge run or cell; an allowed run carries the policy's
  organization into every cell.
* ``sweep_missing_immediate_evals``: a grading the block hook refuses keeps
  one failed run per sweep and is dispatched on the first sweep after the
  block is lifted.

The extended package is faked through ``sys.modules``; the Celery send of
the sweep is captured.
"""

import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

import immediate_eval_dispatch as ied
import tasks
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _install_extended(monkeypatch, **hooks):
    """Fake ``benger_extended.workers`` with the given hook functions.

    Only these two ``sys.modules`` keys are swapped. Replacing all of
    ``sys.modules`` for the test would also drop the numpy/scipy modules a
    run imports, and numpy's C extensions cannot be loaded twice.
    """
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    for name, fn in hooks.items():
        setattr(workers, name, (lambda f: (lambda: f))(fn))
    pkg.workers = workers
    monkeypatch.setitem(sys.modules, "benger_extended", pkg)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)


def _human_exact_match_config():
    return {
        "id": "cfg1",
        "metric": "exact_match",
        "prediction_fields": ["human:answer"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {},
        "enabled": True,
    }


def _answer(text):
    return [{"from_name": "answer", "type": "textarea", "value": {"text": [text]}}]


def test_refused_batch_run_fails_before_any_judge_work(
    db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
    monkeypatch,
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_annotation(project.id, task.id, completed_by=user.id, result=_answer("ja"))
    run = make_evaluation_run(project.id, user.id, status="pending")
    seen = {}
    block = {
        "code": "lti_org_unfunded",
        "reason": "org_not_paying",
        "org_id": "org-lms",
        "missing_providers": [],
    }

    def policy(db, **kwargs):
        # The run's session is closed after the task; read the ids now.
        seen.update(
            user_id=kwargs["user_id"],
            project_id=kwargs["project"].id,
            organization_id=kwargs["organization_id"],
        )
        return "org-lms", block

    _install_extended(monkeypatch, get_batch_evaluation_policy_fn=policy)
    result = tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[_human_exact_match_config()],
    )

    assert result == {"status": "blocked", "evaluation_id": run.id, "block": block}
    assert seen == {
        "user_id": user.id,
        "project_id": project.id,
        "organization_id": None,
    }
    db_conn.expire_all()
    fresh = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()
    assert fresh.status == "failed"
    assert fresh.error_message == "billing_blocked:org_not_paying"
    assert fresh.completed_at is not None
    assert fresh.eval_metadata["triggered_by"] == user.id
    assert fresh.eval_metadata["billing_block"]["reason"] == "org_not_paying"
    assert (
        db_conn.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id == run.id)
        .count()
        == 0
    )
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


def test_allowed_batch_run_bills_the_policy_org_in_every_cell(
    db_conn, make_user, make_project, make_task, make_annotation, make_evaluation_run,
    monkeypatch,
):
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_annotation(project.id, task.id, completed_by=user.id, result=_answer("ja"))
    run = make_evaluation_run(project.id, user.id, status="pending")

    import evaluation.cell_evaluator as cell_module

    cell_orgs = []
    original = cell_module.evaluate_annotation_cell_impl

    def _spy(self, evaluation_id, task_id, annotation_id, project_id, configs_for_cell,
             judge_run_ids_by_config, default_judge_run_id, organization_id, *rest):
        cell_orgs.append(organization_id)
        return original(
            self, evaluation_id, task_id, annotation_id, project_id, configs_for_cell,
            judge_run_ids_by_config, default_judge_run_id, organization_id, *rest,
        )

    monkeypatch.setattr(cell_module, "evaluate_annotation_cell_impl", _spy)

    _install_extended(
        monkeypatch,
        get_batch_evaluation_policy_fn=lambda db, **k: ("org-lms", None),
    )
    result = tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[_human_exact_match_config()],
        organization_id="org-dispatched",
    )

    assert result["status"] == "dispatched"
    assert cell_orgs == ["org-lms"]
    db_conn.expire_all()
    fresh = db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()
    assert fresh.status == "completed"
    assert "billing_block" not in (fresh.eval_metadata or {})


def test_sweep_retries_a_refused_grading_once_the_block_is_lifted(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    user = make_user()
    project = make_project(created_by=user.id)
    project.immediate_evaluation_enabled = True
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": "cfg-judge",
                "metric": "llm_judge_custom",
                "display_name": "Judge",
                "enabled": True,
                "prediction_fields": ["answer"],
                "reference_fields": ["task.expected"],
            }
        ]
    }
    db_conn.commit()
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    annotation = make_annotation(
        project.id, task.id, completed_by=user.id, result=_answer("ja")
    )
    # Old enough for the sweep's min-age cutoff.
    annotation.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_conn.commit()

    state = {"blocked": True}

    def block_fn(db, *, project, user_id, configs):
        if project.id == project_id and state["blocked"]:
            return {
                "code": "lti_org_unfunded",
                "reason": "org_key_missing",
                "org_id": "org-lms",
                "missing_providers": ["openai"],
            }
        return None

    project_id = project.id
    sent = []
    monkeypatch.setattr(
        ied, "_dispatch_task", lambda name, kwargs, queue: sent.append(kwargs)
    )

    _install_extended(monkeypatch, get_grading_block_fn=block_fn)

    def _sweep():
        return tasks.sweep_missing_immediate_evals.run()

    def _our_runs():
        db_conn.expire_all()
        return (
            db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .order_by(EvaluationRun.created_at)
            .all()
        )

    try:
        first = _sweep()
        assert first["status"] == "success"
        assert first["blocked"] >= 1
        [blocked_run] = _our_runs()
        assert blocked_run.status == "failed"
        assert blocked_run.eval_metadata["billing_block"]["reason"] == "org_key_missing"
        assert not [k for k in sent if k["project_id"] == project_id]

        _sweep()
        runs = _our_runs()
        assert [r.id for r in runs] == [blocked_run.id]
        checked = runs[0].eval_metadata["billing_block"]
        assert checked["first_blocked_at"] <= checked["checked_at"]

        state["blocked"] = False
        third = _sweep()
        assert third["dispatched"] >= 1
        ours = [k for k in sent if k["project_id"] == project_id]
        assert len(ours) == 1
        assert ours[0]["annotation_id"] == annotation.id
        runs = _our_runs()
        assert len(runs) == 2
        old, new = runs
        assert old.eval_metadata["billing_block"]["superseded_by"] == new.id
        assert new.status == "running"
        assert ied.latest_blocked_run(db_conn, project_id, annotation) is None
    finally:
        cleanup.evaluation_run_ids.extend(
            r.id
            for r in db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .all()
        )


def test_sweep_does_not_hold_back_a_recent_refused_grading(
    db_conn, cleanup, make_user, make_project, make_task, make_annotation,
    monkeypatch,
):
    """A submit refused at submit time is swept at once after the block is
    lifted, not only once it is older than the sweep's min age. A fresh
    submit without such a block still waits (a client grading may run)."""
    student = make_user()
    other = make_user()
    project = make_project(created_by=student.id)
    project.immediate_evaluation_enabled = True
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": "cfg-judge",
                "metric": "llm_judge_custom",
                "display_name": "Judge",
                "enabled": True,
                "prediction_fields": ["answer"],
                "reference_fields": ["task.expected"],
            }
        ]
    }
    db_conn.commit()
    task = make_task(project.id, {"expected": "ja"}, created_by=student.id)
    refused = make_annotation(
        project.id, task.id, completed_by=student.id, result=_answer("ja")
    )
    fresh = make_annotation(
        project.id, task.id, completed_by=other.id, result=_answer("nein")
    )
    project_id = project.id
    state = {"blocked": True}

    def block_fn(db, *, project, user_id, configs):
        if project.id == project_id and state["blocked"]:
            return {"code": "lti_org_unfunded", "reason": "org_not_paying"}
        return None

    sent = []
    monkeypatch.setattr(
        ied, "_dispatch_task", lambda name, kwargs, queue: sent.append(kwargs)
    )
    _install_extended(monkeypatch, get_grading_block_fn=block_fn)

    def _our_runs():
        db_conn.expire_all()
        return (
            db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .order_by(EvaluationRun.created_at)
            .all()
        )

    def _ours():
        return [k for k in sent if k["project_id"] == project_id]

    try:
        # The submit hook: no min age, the grading is refused.
        outcome = ied.ensure_immediate_evaluation_outcome(
            db_conn, project, task, refused, trigger="annotation_submit"
        )
        assert outcome.status == ied.OUTCOME_BLOCKED
        [blocked_run] = _our_runs()

        # Still blocked: the sweep refreshes the one run and sends nothing;
        # the fresh submit without a run is left for later.
        assert tasks.sweep_missing_immediate_evals.run()["blocked"] >= 1
        assert [r.id for r in _our_runs()] == [blocked_run.id]
        assert _ours() == []

        state["blocked"] = False
        result = tasks.sweep_missing_immediate_evals.run()

        assert result["dispatched"] >= 1
        ours = _ours()
        assert [k["annotation_id"] for k in ours] == [refused.id]
        assert fresh.id not in {k["annotation_id"] for k in ours}
        runs = _our_runs()
        assert len(runs) == 2
        assert runs[0].eval_metadata["billing_block"]["superseded_by"] == runs[1].id
    finally:
        cleanup.evaluation_run_ids.extend(
            r.id
            for r in db_conn.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project_id)
            .all()
        )
