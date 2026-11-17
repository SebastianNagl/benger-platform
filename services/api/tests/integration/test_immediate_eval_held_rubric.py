"""Sheet judges without a usable Bewertungsbogen in the shared dispatch (CORE 2.54).

``ensure_immediate_evaluation`` leaves out an ``llm_judge_rubric`` config
whose task has no usable sheet (``task_rubric_resolution``) instead of
dispatching a grading that only writes an error row:

- the other configs of the grading still run, the held ones are listed in
  ``eval_metadata.held_configs``;
- with nothing else to grade, the grading is one blocked run with reason
  ``rubric_missing`` (no Celery task), refreshed on every retry;
- ``dispatch_waiting_gradings`` grades the held answers of a task once its
  sheet is usable;
- ``rubric_selector`` grades only with a confirmed sheet when the project
  requires the check.

Real Postgres; the extended package is faked through ``sys.modules`` and the
Celery send is captured.
"""

from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import immediate_eval_dispatch as ied
from models import EvaluationRun
from project_models import Annotation, Project, Task, TaskRubric
from task_rubric_resolution import (
    RUBRIC_MISSING,
    resolve_grading_rubric,
    split_held_rubric_judges,
)

SHEET = {
    "id": "cfg-sheet",
    "metric": "llm_judge_rubric",
    "display_name": "Bewertungsbogen",
    "enabled": True,
    "prediction_fields": ["answer"],
    "reference_fields": ["task.musterloesung"],
}
JUDGE = {
    "id": "cfg-judge",
    "metric": "llm_judge_custom",
    "display_name": "Judge",
    "enabled": True,
    "prediction_fields": ["answer"],
    "reference_fields": ["task.musterloesung"],
}
SCORED = {"s01_x": {"name": "X", "rubric": "r", "max_score": 10}}


def _uid() -> str:
    return str(uuid.uuid4())


def _project(db, owner, configs, *, review_required=False):
    project = Project(
        id=_uid(),
        title="Sheet-graded exam",
        created_by=owner.id,
        kind="exam",
        immediate_evaluation_enabled=True,
        rubric_review_required=review_required,
        evaluation_config={"evaluation_configs": [dict(c) for c in configs]},
    )
    db.add(project)
    db.flush()
    return project


def _task(db, project, inner_id=1):
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"musterloesung": "Die Klage ist zulässig."},
    )
    db.add(task)
    db.flush()
    return task


def _answer(db, project, task, student):
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
                "value": {"text": ["Die Klage ist zulässig."]},
            }
        ],
        was_cancelled=False,
    )
    db.add(annotation)
    db.commit()
    return annotation


def _sheet(db, task, *, status="active", review_state=None, generator=None, criteria=SCORED,
           created_at=None):
    row = TaskRubric(
        id=_uid(),
        task_id=task.id,
        project_id=task.project_id,
        criteria=criteria,
        total_points=10,
        status=status,
        review_state=review_state,
        generator_model_id=generator,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def people(test_users):
    return test_users[1], test_users[2]


def _fake_extended(block_hook=None):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    if block_hook is not None:
        workers.get_grading_block_fn = lambda: block_hook
    pkg.workers = workers
    return {"benger_extended": pkg, "benger_extended.workers": workers}


def _ensure(db, project, task, annotation, sent, *, trigger="annotation_submit", hook=None):
    def fake_send(name, kwargs, queue):
        sent.append((name, kwargs))

    with patch.dict(sys.modules, _fake_extended(hook)):
        with patch.object(ied, "_dispatch_task", side_effect=fake_send):
            return ied.ensure_immediate_evaluation_outcome(
                db, project, task, annotation, trigger=trigger
            )


def _runs(db, project_id):
    db.expire_all()
    return (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .order_by(EvaluationRun.created_at)
        .all()
    )


# ── the lookup ───────────────────────────────────────────────────────────────
class TestResolveGradingRubric:
    def test_default_takes_only_the_active_scored_sheet(self, test_db: Session, people):
        owner, _student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        assert resolve_grading_rubric(test_db, task, {}) is None
        _sheet(test_db, task, status="candidate")
        assert resolve_grading_rubric(test_db, task, {}) is None
        active = _sheet(test_db, task)
        assert resolve_grading_rubric(test_db, task, None).id == active.id

    def test_a_scoreless_sheet_does_not_count(self, test_db, people):
        owner, _student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        _sheet(test_db, task, criteria={"s01_x": {"name": "X", "rubric": "r"}})
        assert resolve_grading_rubric(test_db, task, {}) is None

    def test_selector_takes_the_newest_non_archived_sheet_of_the_generator(self, test_db, people):
        owner, _student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        now = datetime.now(timezone.utc)
        _sheet(test_db, task, status="candidate", generator="gen-a",
               created_at=now - timedelta(minutes=5))
        newest = _sheet(test_db, task, status="candidate", generator="gen-a", created_at=now)
        _sheet(test_db, task, status="archived", generator="gen-a",
               created_at=now + timedelta(minutes=1))
        _sheet(test_db, task, status="active", generator="gen-b")
        params = {"rubric_selector": {"generator_model_id": "gen-a"}}
        assert resolve_grading_rubric(test_db, task, params).id == newest.id

    def test_selector_needs_a_confirmed_sheet_when_the_check_is_required(self, test_db, people):
        owner, _student = people
        project = _project(test_db, owner, [SHEET], review_required=True)
        task = _task(test_db, project)
        now = datetime.now(timezone.utc)
        confirmed = _sheet(test_db, task, status="candidate", generator="gen-a",
                           review_state="confirmed", created_at=now - timedelta(minutes=5))
        _sheet(test_db, task, status="candidate", generator="gen-a", created_at=now)
        _sheet(test_db, task, status="candidate", generator="gen-a",
               review_state="unusable", created_at=now + timedelta(minutes=1))
        params = {"rubric_selector": {"generator_model_id": "gen-a"}}

        assert resolve_grading_rubric(test_db, task, params).id == confirmed.id
        # An explicit answer from the caller wins over the project's column.
        assert resolve_grading_rubric(test_db, task, params, review_required=False).id != (
            confirmed.id
        )

    def test_split_keeps_other_metrics_and_order(self, test_db, people):
        owner, _student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        other_sheet = dict(SHEET, id="cfg-sheet-2")
        kept, held = split_held_rubric_judges(test_db, task, [SHEET, JUDGE, other_sheet])
        assert [c["id"] for c in kept] == ["cfg-judge"]
        assert [c["id"] for c in held] == ["cfg-sheet", "cfg-sheet-2"]
        _sheet(test_db, task)
        kept, held = ied.split_held_configs(test_db, project, task, [SHEET, JUDGE])
        assert [c["id"] for c in kept] == ["cfg-sheet", "cfg-judge"] and held == []


# ── the dispatch ─────────────────────────────────────────────────────────────
class TestHeldDispatch:
    def test_only_a_sheet_judge_without_sheet_holds_the_grading(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [SHEET], review_required=True)
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        sent = []

        outcome = _ensure(test_db, project, task, annotation, sent)

        assert outcome.status == ied.OUTCOME_BLOCKED
        assert sent == []
        (run,) = _runs(test_db, project.id)
        assert run.status == "failed"
        assert run.error_message == "billing_blocked:rubric_missing"
        assert run.eval_metadata["expected_config_count"] == 1
        block = run.eval_metadata["billing_block"]
        assert block["code"] == RUBRIC_MISSING
        assert block["reason"] == RUBRIC_MISSING
        assert block["task_id"] == task.id
        assert [c["id"] for c in block["held_configs"]] == ["cfg-sheet"]

        # A retry refreshes the same run instead of adding one.
        again = _ensure(test_db, project, task, annotation, sent, trigger=ied.SWEEP_TRIGGER)
        assert again.status == ied.OUTCOME_BLOCKED
        assert again.run_id == outcome.run_id
        assert len(_runs(test_db, project.id)) == 1
        # Held runs never count against the sweep's attempt cap.
        assert ied.sweep_attempt_counts(test_db, project.id) == {}
        assert ied.grading_retry_state(test_db, project, annotation) == {
            "state": ied.RETRY_HELD,
            "reason": RUBRIC_MISSING,
            "attempts": 0,
            "max_attempts": ied.SWEEP_MAX_ATTEMPTS,
        }

    def test_a_fresh_held_answer_stays_in_the_sweep_scan(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        _ensure(test_db, project, task, annotation, [])

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        candidates, _partials = ied.scan_ungraded(test_db, project, cutoff=cutoff)
        assert [a.id for a, _t in candidates] == [annotation.id]

    def test_other_configs_still_run_and_the_held_ones_are_listed(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [SHEET, JUDGE])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        hook_calls = []

        def hook(db, *, project, user_id, configs):
            hook_calls.append([c["id"] for c in configs])
            return None

        sent = []
        outcome = _ensure(test_db, project, task, annotation, sent, hook=hook)

        assert outcome.status == ied.OUTCOME_DISPATCHED
        ((name, kwargs),) = sent
        assert name == "tasks.run_single_sample_evaluation"
        assert [c["id"] for c in kwargs["evaluation_configs"]] == ["cfg-judge"]
        # Billing is asked only about what will run.
        assert hook_calls == [["cfg-judge"]]
        (run,) = _runs(test_db, project.id)
        assert run.evaluation_type_ids == ["llm_judge_custom"]
        assert run.eval_metadata["expected_config_count"] == 1
        assert run.eval_metadata["held_configs"] == [
            {
                "id": "cfg-sheet",
                "metric": "llm_judge_rubric",
                "display_name": "Bewertungsbogen",
                "reason": RUBRIC_MISSING,
            }
        ]

    def test_a_usable_sheet_dispatches_as_before(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [SHEET, JUDGE])
        task = _task(test_db, project)
        _sheet(test_db, task)
        annotation = _answer(test_db, project, task, student)
        sent = []

        outcome = _ensure(test_db, project, task, annotation, sent)

        assert outcome.status == ied.OUTCOME_DISPATCHED
        ((_name, kwargs),) = sent
        assert [c["id"] for c in kwargs["evaluation_configs"]] == ["cfg-sheet", "cfg-judge"]
        (run,) = _runs(test_db, project.id)
        assert "held_configs" not in run.eval_metadata

    def test_a_billing_block_is_not_asked_while_the_sheet_is_missing(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        hook_calls = []

        def hook(db, *, project, user_id, configs):
            hook_calls.append(configs)
            return {"code": "lti_org_unfunded", "reason": "org_key_missing"}

        outcome = _ensure(test_db, project, task, annotation, [], hook=hook)
        assert outcome.status == ied.OUTCOME_BLOCKED
        assert hook_calls == []
        (run,) = _runs(test_db, project.id)
        assert run.eval_metadata["billing_block"]["reason"] == RUBRIC_MISSING

        # Once the sheet is there, the billing block takes over.
        _sheet(test_db, task)
        outcome = _ensure(test_db, project, task, annotation, [], hook=hook)
        assert outcome.status == ied.OUTCOME_BLOCKED
        (run,) = _runs(test_db, project.id)
        assert run.eval_metadata["billing_block"]["reason"] == "org_key_missing"


# ── waiting gradings ─────────────────────────────────────────────────────────
class TestDispatchWaitingGradings:
    def test_grades_the_waiting_answers_of_the_task_only(self, test_db, people, test_users):
        owner, student = people
        second_student = test_users[0]
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project, 1)
        other_task = _task(test_db, project, 2)
        waiting = [
            _answer(test_db, project, task, student),
            _answer(test_db, project, task, second_student),
        ]
        elsewhere = _answer(test_db, project, other_task, student)
        for annotation, its_task in ((waiting[0], task), (waiting[1], task), (elsewhere, other_task)):
            _ensure(test_db, project, its_task, annotation, [])

        # Still no sheet: everything keeps waiting.
        sent = []
        with patch.dict(sys.modules, _fake_extended()):
            with patch.object(
                ied, "_dispatch_task", side_effect=lambda n, k, q: sent.append((n, k))
            ):
                assert ied.dispatch_waiting_gradings(test_db, task.id) == {
                    "waiting": 2,
                    "dispatched": 0,
                    "blocked": 2,
                    "other": 0,
                    "failed": 0,
                }
                _sheet(test_db, task, review_state="confirmed")
                counts = ied.dispatch_waiting_gradings(test_db, task.id)

        assert counts == {"waiting": 2, "dispatched": 2, "blocked": 0, "other": 0, "failed": 0}
        assert sorted(k["annotation_id"] for _n, k in sent) == sorted(a.id for a in waiting)
        assert ied.latest_blocked_run(test_db, project.id, elsewhere) is not None
        for annotation in waiting:
            assert ied.latest_blocked_run(test_db, project.id, annotation) is None
        triggers = {
            r.eval_metadata["trigger"]
            for r in _runs(test_db, project.id)
            if r.status == "running"
        }
        assert triggers == {ied.RUBRIC_READY_TRIGGER}

    def test_no_op_for_unknown_tasks_and_projects_without_immediate_grading(
        self, test_db, people
    ):
        owner, student = people
        project = _project(test_db, owner, [SHEET])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        _ensure(test_db, project, task, annotation, [])
        _sheet(test_db, task)
        project.immediate_evaluation_enabled = False
        test_db.commit()

        empty = {"waiting": 0, "dispatched": 0, "blocked": 0, "other": 0, "failed": 0}
        assert ied.dispatch_waiting_gradings(test_db, _uid()) == empty
        assert ied.dispatch_waiting_gradings(test_db, task.id) == empty

    def test_queue_sends_the_worker_task(self):
        sent = []
        with patch.object(
            ied, "_dispatch_task", side_effect=lambda n, k, q: sent.append((n, k, q))
        ):
            ied.queue_waiting_gradings("task-1")
        assert sent == [("tasks.dispatch_waiting_gradings", {"task_id": "task-1"}, "interactive")]


# ── retry state ──────────────────────────────────────────────────────────────
class TestGradingRetryState:
    def _failed_sweep_run(self, db, project, annotation, n):
        for _ in range(n):
            db.add(
                EvaluationRun(
                    id=_uid(),
                    project_id=project.id,
                    model_id="immediate",
                    evaluation_type_ids=["llm_judge_custom"],
                    status="failed",
                    created_by=annotation.completed_by,
                    eval_metadata={
                        "trigger": ied.SWEEP_TRIGGER,
                        "annotation_id": annotation.id,
                    },
                    metrics={},
                )
            )
        db.commit()

    def test_retrying_until_the_cap_then_exhausted(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [JUDGE])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)

        state = ied.grading_retry_state(test_db, project, annotation)
        assert (state["state"], state["attempts"]) == (ied.RETRY_SWEEP, 0)
        self._failed_sweep_run(test_db, project, annotation, ied.SWEEP_MAX_ATTEMPTS - 1)
        state = ied.grading_retry_state(test_db, project, annotation)
        assert (state["state"], state["attempts"]) == (
            ied.RETRY_SWEEP,
            ied.SWEEP_MAX_ATTEMPTS - 1,
        )
        self._failed_sweep_run(test_db, project, annotation, 1)
        state = ied.grading_retry_state(test_db, project, annotation)
        assert (state["state"], state["attempts"]) == (
            ied.RETRY_EXHAUSTED,
            ied.SWEEP_MAX_ATTEMPTS,
        )

    def test_nothing_retries_without_immediate_grading(self, test_db, people):
        owner, student = people
        project = _project(test_db, owner, [JUDGE])
        task = _task(test_db, project)
        annotation = _answer(test_db, project, task, student)
        project.immediate_evaluation_enabled = False
        test_db.commit()
        assert ied.grading_retry_state(test_db, project, annotation)["state"] == ied.RETRY_NONE
        assert ied.grading_retry_state(test_db, None, annotation)["state"] == ied.RETRY_NONE
