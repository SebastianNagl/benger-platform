"""A held-back feedback draft counts as graded (real Postgres).

A feedback-only judge (``details.feedback_only``, core 2.41) writes its
grading as a draft whose ``value`` stays null until a teacher releases it.
On prod the hourly sweep took such drafts for ungraded: when that judge was
a project's only immediate judge, every held-back submission was graded
again each hour until the sweep's attempt cap, each run a new paid draft
whose note differed from the last. ``scan_ungraded`` and
``ensure_immediate_evaluation_outcome`` now count a written draft as graded,
while an error row still leaves the annotation open for a retry.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import immediate_eval_dispatch as ied
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
from project_models import Annotation, Project, Task

pytestmark = pytest.mark.integration

METRIC = "llm_judge_feedback"
FEEDBACK_JUDGE = {
    "id": "cfg-feedback",
    "metric": METRIC,
    "display_name": "Feedback",
    "enabled": True,
    "prediction_fields": ["human:loesung"],
    "reference_fields": ["task.reference"],
}

# The row shapes the feedback judge writes: a held-back draft (note only in
# details.grade), the same draft once released, and a failed call.
DRAFT = {
    METRIC: {
        "value": None,
        "method": METRIC,
        "details": {"feedback_only": True, "grade": {"note": 9.5}, "markdown": "..."},
        "error": None,
    }
}
RELEASED = {
    METRIC: {
        "value": 0.475,
        "method": METRIC,
        "details": {
            "feedback_only": True,
            "grade": {"note": 9.5},
            "review": {"status": "released"},
        },
        "error": None,
    }
}
ERROR = {
    METRIC: {
        "value": None,
        "method": METRIC,
        "details": {},
        "error": "judge call failed",
    }
}


def _uid() -> str:
    return str(uuid.uuid4())


def _no_extended():
    # An installed extended package must not narrow configs or block here.
    return patch.dict(sys.modules, {"benger_extended": None})


@pytest.fixture
def make_setup(test_db: Session, test_users):
    """A project with the feedback judge as its only immediate judge and one
    old submission per entry of ``rows`` (``None``: no grading row yet)."""
    student = test_users[2]

    def _make(rows: dict):
        project = Project(
            id=_uid(),
            title="Held-back feedback",
            created_by=test_users[1].id,
            kind="exam",
            immediate_evaluation_enabled=True,
            evaluation_config={"evaluation_configs": [dict(FEEDBACK_JUDGE)]},
        )
        test_db.add(project)
        test_db.flush()
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        out = {}
        for n, (key, metrics) in enumerate(rows.items(), start=1):
            task = Task(
                id=_uid(), project_id=project.id, inner_id=n, data={"reference": "r"}
            )
            test_db.add(task)
            test_db.flush()
            annotation = Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=student.id,
                result=[
                    {
                        "from_name": "loesung",
                        "to_name": "text",
                        "type": "textarea",
                        "value": {"text": ["Commentaire d'arrêt ..."]},
                    }
                ],
                was_cancelled=False,
                created_at=old,
            )
            test_db.add(annotation)
            test_db.flush()
            run = None
            if metrics is not None:
                run = EvaluationRun(
                    id=_uid(),
                    project_id=str(project.id),
                    model_id="immediate",
                    evaluation_type_ids=[METRIC],
                    status="completed",
                    created_by=str(student.id),
                    eval_metadata={
                        "evaluation_type": "immediate",
                        "trigger": "annotation_submit",
                        "annotation_id": str(annotation.id),
                    },
                    metrics={},
                )
                test_db.add(run)
                test_db.flush()
                judge_run = EvaluationJudgeRun(id=_uid(), evaluation_id=run.id)
                test_db.add(judge_run)
                test_db.flush()
                test_db.add(
                    TaskEvaluation(
                        id=_uid(),
                        evaluation_id=run.id,
                        judge_run_id=judge_run.id,
                        task_id=task.id,
                        annotation_id=annotation.id,
                        field_name="human:loesung",
                        answer_type="long_text",
                        ground_truth="",
                        prediction="Commentaire d'arrêt ...",
                        metrics=metrics,
                        passed=True,
                    )
                )
            out[key] = (task, annotation, run)
        test_db.commit()
        return project, out

    return _make


def test_scan_counts_a_held_back_draft_as_graded(test_db, make_setup):
    project, subs = make_setup(
        {"draft": DRAFT, "released": RELEASED, "error": ERROR, "none": None}
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    candidates, partials = ied.scan_ungraded(test_db, project, cutoff=cutoff)

    # The draft and the released row are graded; the failed call and the
    # submission without any row are still swept.
    assert {a.id for a, _t in candidates} == {subs["error"][1].id, subs["none"][1].id}
    assert partials == []


def _ensure(test_db, project, task, annotation, trigger):
    sent = []
    with (
        _no_extended(),
        patch.object(ied, "_dispatch_task", side_effect=lambda *a, **k: sent.append(a)),
    ):
        outcome = ied.ensure_immediate_evaluation_outcome(
            test_db, project, task, annotation, trigger=trigger, min_age_minutes=15
        )
    return outcome, sent


def test_sweep_does_not_grade_a_held_back_draft_again(test_db, make_setup):
    project, subs = make_setup({"draft": DRAFT})
    task, annotation, run = subs["draft"]

    outcome, sent = _ensure(test_db, project, task, annotation, ied.SWEEP_TRIGGER)

    assert outcome == ied.EnsureOutcome(str(run.id), ied.OUTCOME_GRADED)
    assert sent == []


def test_sweep_still_retries_a_failed_grading(test_db, make_setup):
    project, subs = make_setup({"error": ERROR})
    task, annotation, _run = subs["error"]

    outcome, sent = _ensure(test_db, project, task, annotation, ied.SWEEP_TRIGGER)

    assert outcome.status == ied.OUTCOME_DISPATCHED
    assert len(sent) == 1
