"""Blocked gradings in the shared immediate-eval dispatch (CORE 2.20).

``ensure_immediate_evaluation`` asks the optional extended hook
``benger_extended.workers.get_grading_block_fn`` whether a grading may run.
A blocked grading keeps exactly one failed run with the reason and gets no
Celery task; once the hook stops blocking, the next call dispatches and marks
the old run superseded. Real Postgres; the extended package is faked through
``sys.modules`` and the Celery send is captured.
"""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import immediate_eval_dispatch as ied
from models import EvaluationRun
from project_models import Annotation, Project, Task

CONFIG = {
    "id": "cfg-judge",
    "metric": "llm_judge_custom",
    "display_name": "Judge",
    "enabled": True,
    "prediction_fields": ["answer"],
    "reference_fields": ["task.reference"],
}


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def graded_setup(test_db: Session, test_users):
    student = test_users[2]
    project = Project(
        id=_uid(),
        title="Blocked grading exam",
        created_by=test_users[1].id,
        kind="exam",
        evaluation_config={"evaluation_configs": [dict(CONFIG)]},
    )
    task = Task(
        id=_uid(), project_id=project.id, inner_id=1, data={"reference": "ref"}
    )
    test_db.add_all([project, task])
    test_db.flush()
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=student.id,
        result=[
            {
                "from_name": "answer",
                "to_name": "text",
                "type": "textarea",
                "value": {"text": ["my answer"]},
            }
        ],
        was_cancelled=False,
    )
    test_db.add(annotation)
    test_db.commit()
    return project, task, annotation


class _Hook:
    """A controllable ``get_grading_block_fn`` result."""

    def __init__(self, block=None, error=None):
        self.block = block
        self.error = error
        self.calls = []

    def __call__(self, db, *, project, user_id, configs):
        self.calls.append((project.id, user_id, [c["metric"] for c in configs]))
        if self.error is not None:
            raise self.error
        return self.block


def _fake_extended(hook):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    if hook is not None:
        workers.get_grading_block_fn = lambda: hook
    pkg.workers = workers
    return {"benger_extended": pkg, "benger_extended.workers": workers}


def _ensure(db, setup, hook, sent):
    project, task, annotation = setup

    def fake_send(name, kwargs, queue):
        sent.append((name, kwargs["evaluation_record_id"]))

    with patch.dict(sys.modules, _fake_extended(hook)):
        with patch.object(ied, "_dispatch_task", side_effect=fake_send):
            return ied.ensure_immediate_evaluation_outcome(
                db, project, task, annotation, trigger="sweep_missing_immediate_evals"
            )


def _runs(db, project_id):
    db.expire_all()
    return (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .order_by(EvaluationRun.created_at)
        .all()
    )


class TestGradingBlockHook:
    def test_blocked_grading_records_one_failed_run_and_sends_nothing(
        self, test_db, graded_setup
    ):
        project, _task, annotation = graded_setup
        hook = _Hook(
            block={
                "code": "lti_org_unfunded",
                "reason": "org_key_missing",
                "missing_providers": ["openai"],
            }
        )
        sent = []

        outcome = _ensure(test_db, graded_setup, hook, sent)

        assert outcome.status == ied.OUTCOME_BLOCKED
        assert sent == []
        assert hook.calls == [
            (project.id, annotation.completed_by, ["llm_judge_custom"])
        ]
        (run,) = _runs(test_db, project.id)
        assert run.id == outcome.run_id
        assert run.status == "failed"
        assert run.model_id == "immediate"
        assert run.created_by == annotation.completed_by
        assert run.error_message == "billing_blocked:org_key_missing"
        meta = run.eval_metadata
        assert meta["annotation_id"] == annotation.id
        assert meta["expected_config_count"] == 1
        assert meta["error"] == "billing_blocked:org_key_missing"
        block = meta["billing_block"]
        assert block["code"] == "lti_org_unfunded"
        assert block["reason"] == "org_key_missing"
        assert block["missing_providers"] == ["openai"]
        assert block["checked_at"] and block["first_blocked_at"]
        assert ied.latest_blocked_run(test_db, project.id, annotation).id == run.id

    def test_repeat_while_blocked_refreshes_the_same_run(self, test_db, graded_setup):
        project, _task, annotation = graded_setup
        sent = []
        first = _ensure(test_db, graded_setup, _Hook(block="org_not_paying"), sent)
        first_meta = _runs(test_db, project.id)[0].eval_metadata["billing_block"]

        second = _ensure(
            test_db, graded_setup, _Hook(block={"reason": "org_key_missing"}), sent
        )

        assert second.status == ied.OUTCOME_BLOCKED
        assert second.run_id == first.run_id
        assert sent == []
        (run,) = _runs(test_db, project.id)
        block = run.eval_metadata["billing_block"]
        # The newest reason wins; the first time the grading was blocked stays.
        assert block["reason"] == "org_key_missing"
        assert block["first_blocked_at"] == first_meta["first_blocked_at"]
        assert block["checked_at"] >= first_meta["checked_at"]
        assert run.eval_metadata["error"] == "billing_blocked:org_key_missing"

    def test_repeat_with_another_acting_user_refreshes_the_same_run(
        self, test_db, graded_setup, test_users
    ):
        """The run belongs to the submitter even when a caller acts as
        someone else, so the lookup still finds it and nothing piles up."""
        project, _task, annotation = graded_setup
        other = test_users[0]
        assert other.id != annotation.completed_by

        first_id = ied.record_blocked_immediate_run(
            test_db,
            project,
            annotation,
            user_id=other.id,
            configs=[dict(CONFIG)],
            block="org_not_paying",
        )
        second_id = ied.record_blocked_immediate_run(
            test_db,
            project,
            annotation,
            user_id=other.id,
            configs=[dict(CONFIG)],
            block="org_key_missing",
        )

        assert second_id == first_id
        (run,) = _runs(test_db, project.id)
        assert run.created_by == annotation.completed_by
        assert run.eval_metadata["billing_block"]["reason"] == "org_key_missing"
        assert ied.latest_blocked_run(test_db, project.id, annotation).id == run.id

    def test_lifted_block_dispatches_and_supersedes_the_blocked_run(
        self, test_db, graded_setup
    ):
        project, _task, annotation = graded_setup
        sent = []
        blocked = _ensure(test_db, graded_setup, _Hook(block="org_key_missing"), sent)

        lifted = _ensure(test_db, graded_setup, _Hook(block=None), sent)

        assert lifted.status == ied.OUTCOME_DISPATCHED
        assert lifted.run_id != blocked.run_id
        assert sent == [("tasks.run_single_sample_evaluation", lifted.run_id)]
        runs = {r.id: r for r in _runs(test_db, project.id)}
        assert runs[lifted.run_id].status == "running"
        old_block = runs[blocked.run_id].eval_metadata["billing_block"]
        assert old_block["superseded_by"] == lifted.run_id
        assert ied.latest_blocked_run(test_db, project.id, annotation) is None

        # The dispatched run is now in flight: a further call attaches to it.
        again = _ensure(test_db, graded_setup, _Hook(block=None), sent)
        assert again.status == ied.OUTCOME_IN_FLIGHT
        assert again.run_id == lifted.run_id
        assert len(sent) == 1

    def test_ensure_immediate_evaluation_returns_the_blocked_run_id(
        self, test_db, graded_setup
    ):
        project, task, annotation = graded_setup
        with patch.dict(sys.modules, _fake_extended(_Hook(block="org_not_paying"))):
            with patch.object(ied, "_dispatch_task") as send:
                run_id = ied.ensure_immediate_evaluation(
                    test_db, project, task, annotation
                )
        send.assert_not_called()
        (run,) = _runs(test_db, project.id)
        assert run_id == run.id
        assert run.eval_metadata["trigger"] == "annotation_submit"

    @pytest.mark.parametrize(
        "hook",
        [None, _Hook(error=RuntimeError("policy exploded"))],
        ids=["no_hook", "hook_raises"],
    )
    def test_missing_or_failing_hook_dispatches_normally(
        self, test_db, graded_setup, hook
    ):
        project, _task, _annotation = graded_setup
        sent = []

        outcome = _ensure(test_db, graded_setup, hook, sent)

        assert outcome.status == ied.OUTCOME_DISPATCHED
        assert sent == [("tasks.run_single_sample_evaluation", outcome.run_id)]
        (run,) = _runs(test_db, project.id)
        assert run.status == "running"
        assert "billing_block" not in run.eval_metadata

    def test_failed_run_without_block_is_not_a_blocked_run(
        self, test_db, graded_setup
    ):
        """An ordinary failed grading (judge outage) is retried, not treated
        as blocked, and never gets a supersede stamp."""
        project, _task, annotation = graded_setup
        failed = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id="immediate",
            evaluation_type_ids=["llm_judge_custom"],
            status="failed",
            created_by=annotation.completed_by,
            eval_metadata={"annotation_id": annotation.id, "error": "timeout"},
            metrics={},
        )
        test_db.add(failed)
        test_db.commit()
        assert ied.latest_blocked_run(test_db, project.id, annotation) is None

        sent = []
        outcome = _ensure(test_db, graded_setup, _Hook(block=None), sent)

        assert outcome.status == ied.OUTCOME_DISPATCHED
        runs = {r.id: r for r in _runs(test_db, project.id)}
        assert "billing_block" not in runs[failed.id].eval_metadata


class TestNormalizeBillingBlock:
    @pytest.mark.parametrize("value", [None, "", {}, 0, False])
    def test_empty_values_mean_not_blocked(self, value):
        assert ied.normalize_billing_block(value) is None

    def test_reason_falls_back_to_code(self):
        assert ied.normalize_billing_block({"code": "lti_org_unfunded"}) == {
            "code": "lti_org_unfunded",
            "reason": "lti_org_unfunded",
        }

    def test_string_becomes_reason_and_input_is_not_mutated(self):
        original = {"reason": "org_key_missing", "missing_providers": ["openai"]}
        out = ied.normalize_billing_block(original)
        assert out == original and out is not original
        assert ied.normalize_billing_block("org_not_paying") == {
            "reason": "org_not_paying"
        }
