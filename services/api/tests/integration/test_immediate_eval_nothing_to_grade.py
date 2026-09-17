"""Annotations with nothing to grade are not dispatched (real Postgres).

On prod the hourly sweep re-dispatched the same 14 annotations every hour
for months. Each run finished ``completed`` with no grade, because the
worker skipped every config ("no prediction value"): the answer was empty,
the graded field was missing, or every config read ``__all_model__`` only.
``scan_ungraded`` and ``ensure_immediate_evaluation_outcome`` now ask the
same resolver as the worker and leave such annotations alone.
``sweep_attempt_counts`` backs the sweep's retry cap for gradings that keep
failing for other reasons.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import immediate_eval_dispatch as ied
from models import EvaluationRun
from project_models import Annotation, Project, Task

pytestmark = pytest.mark.integration

HUMAN_JUDGE = {
    "id": "cfg-human",
    "metric": "llm_judge_custom",
    "display_name": "Judge",
    "enabled": True,
    "prediction_fields": ["human:loesung"],
    "reference_fields": ["task.reference"],
}
MODEL_JUDGE = {
    "id": "cfg-model",
    "metric": "llm_judge_classic",
    "display_name": "Classic",
    "enabled": True,
    "prediction_fields": ["__all_model__"],
    "reference_fields": [],
}


def _uid() -> str:
    return str(uuid.uuid4())


def _textarea(name, text):
    return {"from_name": name, "to_name": "text", "type": "textarea", "value": text}


@pytest.fixture
def make_setup(test_db: Session, test_users):
    student = test_users[2]

    def _make(configs, results):
        project = Project(
            id=_uid(),
            title="Nothing to grade",
            created_by=test_users[1].id,
            kind="exam",
            immediate_evaluation_enabled=True,
            evaluation_config={"evaluation_configs": [dict(c) for c in configs]},
        )
        test_db.add(project)
        test_db.flush()
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        annotations = {}
        task = None
        # One task per annotation: a user has one active annotation per task.
        for n, (key, result) in enumerate(results.items(), start=1):
            task = Task(
                id=_uid(), project_id=project.id, inner_id=n, data={"reference": "r"}
            )
            test_db.add(task)
            test_db.flush()
            a = Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=student.id,
                result=result,
                was_cancelled=False,
                created_at=old,
            )
            test_db.add(a)
            annotations[key] = a
        test_db.commit()
        # The last task; tests that dispatch use a single annotation.
        return project, task, annotations

    return _make


def _no_extended():
    # An installed extended package must not narrow configs or block here.
    return patch.dict(sys.modules, {"benger_extended": None})


def test_scan_skips_annotations_without_a_gradable_answer(test_db, make_setup):
    project, _task, anns = make_setup(
        [HUMAN_JUDGE, MODEL_JUDGE],
        {
            "empty_list": [],
            "empty_text": [_textarea("loesung", "")],
            "blank_text": [_textarea("loesung", {"text": ["  "]})],
            "other_fields_only": [_textarea("notizen", ""), _textarea("gliederung", "x")],
            "real": [_textarea("loesung", {"text": ["Die Antwort"]})],
        },
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    candidates, partials = ied.scan_ungraded(test_db, project, cutoff=cutoff)

    assert [a.id for a, _t in candidates] == [anns["real"].id]
    assert partials == []


def test_scan_skips_real_text_when_every_config_reads_model_output(
    test_db, make_setup
):
    # Prod project "Test": a real answer under `answer`, configs on __all_model__.
    project, _task, _anns = make_setup(
        [MODEL_JUDGE],
        {"real": [_textarea("answer", {"text": ["Nein, belastendes ..."]})]},
    )
    candidates, _ = ied.scan_ungraded(test_db, project)
    assert candidates == []


def test_ensure_reports_nothing_to_grade_and_creates_no_run(test_db, make_setup):
    project, task, anns = make_setup(
        [HUMAN_JUDGE], {"empty": [_textarea("loesung", "")]}
    )
    sent = []
    with _no_extended(), patch.object(
        ied, "_dispatch_task", side_effect=lambda *a, **k: sent.append(a)
    ):
        outcome = ied.ensure_immediate_evaluation_outcome(
            test_db, project, task, anns["empty"], trigger="annotation_submit"
        )

    assert outcome == ied.EnsureOutcome(None, ied.OUTCOME_NOTHING_TO_GRADE)
    assert sent == []
    assert (
        test_db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project.id)
        .count()
        == 0
    )


def test_ensure_still_dispatches_a_real_answer(test_db, make_setup):
    project, task, anns = make_setup(
        [HUMAN_JUDGE, MODEL_JUDGE],
        {"real": [_textarea("loesung", {"text": ["Die Antwort"]})]},
    )
    sent = []

    def fake_send(name, kwargs, queue):
        sent.append(kwargs)

    with _no_extended(), patch.object(ied, "_dispatch_task", side_effect=fake_send):
        outcome = ied.ensure_immediate_evaluation_outcome(
            test_db, project, task, anns["real"], trigger="annotation_submit"
        )

    assert outcome.status == ied.OUTCOME_DISPATCHED
    [kwargs] = sent
    assert kwargs["annotation_results"] == {"loesung": "Die Antwort"}
    # All eligible configs still go out; the worker marks the model-only one
    # as skipped, which the results modal shows.
    assert [c["id"] for c in kwargs["evaluation_configs"]] == ["cfg-human", "cfg-model"]


def _run(test_db, project, annotation, *, status, trigger, block=None):
    meta = {
        "evaluation_type": "immediate",
        "trigger": trigger,
        "annotation_id": str(annotation.id),
    }
    if block is not None:
        meta[ied.BILLING_BLOCK_KEY] = block
    run = EvaluationRun(
        id=_uid(),
        project_id=str(project.id),
        model_id="immediate",
        evaluation_type_ids=["llm_judge_custom"],
        status=status,
        created_by=str(annotation.completed_by),
        eval_metadata=meta,
        metrics={},
    )
    test_db.add(run)
    return run


def test_sweep_attempt_counts_only_finished_unblocked_sweep_runs(test_db, make_setup):
    project, _task, anns = make_setup(
        [HUMAN_JUDGE],
        {
            "a": [_textarea("loesung", "x")],
            "b": [_textarea("loesung", "y")],
            "c": [_textarea("loesung", "z")],
        },
    )
    sweep = ied.SWEEP_TRIGGER
    for status in ("completed", "failed", "cancelled"):
        _run(test_db, project, anns["a"], status=status, trigger=sweep)
    # Not counted: in flight, another trigger, a billing block.
    _run(test_db, project, anns["a"], status="running", trigger=sweep)
    _run(test_db, project, anns["a"], status="failed", trigger="annotation_submit")
    _run(
        test_db, project, anns["b"], status="failed", trigger=sweep,
        block={"reason": "org_key_missing"},
    )
    _run(test_db, project, anns["c"], status="completed", trigger=sweep)
    test_db.commit()

    counts = ied.sweep_attempt_counts(test_db, project.id)

    assert counts == {str(anns["a"].id): 3, str(anns["c"].id): 1}
    assert ied.sweep_attempt_counts(test_db, _uid()) == {}


def test_finished_empty_run_still_does_not_block_a_manual_retrigger(
    test_db, make_setup
):
    """IN_FLIGHT_RUN_STATUSES semantics are unchanged: a finished run without
    a grade does not pin the annotation."""
    project, task, anns = make_setup(
        [HUMAN_JUDGE], {"real": [_textarea("loesung", {"text": ["Antwort"]})]}
    )
    _run(test_db, project, anns["real"], status="completed", trigger=ied.SWEEP_TRIGGER)
    test_db.commit()
    sent = []
    with _no_extended(), patch.object(
        ied, "_dispatch_task", side_effect=lambda *a, **k: sent.append(a)
    ):
        outcome = ied.ensure_immediate_evaluation_outcome(
            test_db, project, task, anns["real"], trigger="manual_retrigger"
        )
    assert outcome.status == ied.OUTCOME_DISPATCHED
    assert len(sent) == 1

