"""A peer grading adds nothing to any reader of grades or results.

A participant's grading of a fellow participant's submission is stored as a
row of the feedback-only human method ``korrektur_peer`` with no score
(``value: null``, ``details.feedback_only``), in its own singleton run. Each
reader below answers exactly the same before and after such a row lands next
to a staff grading of the same submission, also when the peer row is the
newer one: the project result grid, the run list, the evaluated models, the
student score history, the report snapshot, the grade-scale drift check and
the current-score pick.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
from project_models import Annotation, Project, Task
from services.evaluation.human_eval_runs import (
    PEER_REVIEW_METRIC,
    get_or_create_human_eval_run,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)


def _user(*, superadmin=False) -> User:
    return User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=NOW,
    )


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=NOW,
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


def _judge_run(session, run_id):
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=run_id, judge_model_id=None,
        run_index=0, status="completed",
    )
    session.add(judge_run)
    session.flush()
    return judge_run.id


def _staff_row(run_id, judge_run_id, task_id, annotation_id, grader_id, created):
    return TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=run_id,
        judge_run_id=judge_run_id,
        task_id=task_id,
        annotation_id=annotation_id,
        field_name="loesung",
        answer_type="text",
        ground_truth="",
        prediction="Antwort",
        metrics={
            "korrektur_feedback": {
                "value": 0.75,
                "method": "korrektur_feedback",
                "details": {"grade_points": 15.0, "note": 15.0},
            }
        },
        passed=True,
        created_by=grader_id,
        created_at=created,
    )


def _peer_row(run_id, judge_run_id, task_id, annotation_id, peer_id, created):
    return TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=run_id,
        judge_run_id=judge_run_id,
        task_id=task_id,
        annotation_id=annotation_id,
        field_name="loesung",
        answer_type="text",
        ground_truth="",
        prediction="Antwort",
        metrics={
            PEER_REVIEW_METRIC: {
                "value": None,
                "method": PEER_REVIEW_METRIC,
                "details": {
                    "feedback_only": True,
                    "lane": "korrektur_feedback",
                    # The lane's own blob, as the grading form produced it.
                    "grade": {"value": 0.2, "details": {"grade_points": 4.0}},
                },
            }
        },
        passed=False,
        created_by=peer_id,
        created_at=created,
    )


async def _readers(db, client, project, author, staff):
    """Every reader's answer for this project, as plain data."""
    from current_scores import current_row_ids
    from report_snapshot import build_report_snapshot
    from services.grade_scale_recompute import grade_scale_drift

    out = {}
    with _as_user(staff):
        r = await client.get(f"/api/evaluations/projects/{project.id}/results/by-task-model")
        assert r.status_code == 200, r.text
        out["grid"] = r.json()
        r = await client.get(
            f"/api/evaluations/run/results/project/{project.id}", params={"latest_only": False}
        )
        assert r.status_code == 200, r.text
        out["runs"] = sorted(e["evaluation_id"] for e in r.json()["evaluations"])
        r = await client.get(f"/api/evaluations/projects/{project.id}/evaluated-models")
        assert r.status_code == 200, r.text
        out["models"] = r.json()
    with _as_user(author):
        r = await client.get("/api/student/score-history", params={"scope": "all"})
        assert r.status_code == 200, r.text
        out["history"] = r.json()

    def _sync(session):
        snapshot = build_report_snapshot(session, project.id, now=NOW)
        rows = session.query(TaskEvaluation).join(
            EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id
        ).filter(EvaluationRun.project_id == project.id).all()
        return {
            "snapshot_counts": snapshot.get("counts"),
            "snapshot_metrics": snapshot.get("metrics"),
            "drift": grade_scale_drift(session, session.get(Project, project.id)),
            "current": sorted(current_row_ids(rows)),
        }

    out.update(await db.run_sync(_sync))
    return out


async def test_a_peer_grading_changes_no_reader(async_test_db, async_test_client):
    db = async_test_db
    owner, author, peer = _user(), _user(), _user()
    db.add_all([owner, author, peer])
    await db.flush()
    project = Project(
        id=str(uuid.uuid4()), title="Peer", created_by=owner.id, is_private=False,
        label_config=CONFIG, peer_review_enabled=True,
    )
    db.add(project)
    await db.flush()
    task = Task(
        id=str(uuid.uuid4()), project_id=project.id, inner_id=1,
        data={"sachverhalt": "Fall"}, created_by=owner.id,
    )
    db.add(task)
    await db.flush()
    annotation = Annotation(
        id=str(uuid.uuid4()), task_id=task.id, project_id=project.id,
        completed_by=author.id, result=[{"v": 1}], was_cancelled=False,
        created_at=NOW - timedelta(days=1),
    )
    db.add(annotation)
    await db.commit()

    def _staff(session):
        run = get_or_create_human_eval_run(session, project.id, "korrektur_feedback", owner.id)
        session.add(
            _staff_row(
                run.id, _judge_run(session, run.id), task.id, annotation.id, owner.id,
                NOW - timedelta(hours=2),
            )
        )
        session.commit()

    await db.run_sync(_staff)
    before = await _readers(db, async_test_client, project, author, owner)
    # The staff grade is there to be hidden: the grid and history show it.
    assert before["history"] and before["history"][0]["score"] == 0.75
    assert len(before["current"]) == 1

    def _peer(session):
        run = get_or_create_human_eval_run(session, project.id, PEER_REVIEW_METRIC, peer.id)
        # Newer than the staff row: a latest-wins reader would pick it.
        session.add(
            _peer_row(run.id, _judge_run(session, run.id), task.id, annotation.id, peer.id, NOW)
        )
        session.commit()
        return run.id

    peer_run_id = await db.run_sync(_peer)
    after = await _readers(db, async_test_client, project, author, owner)

    assert peer_run_id not in after["runs"]
    for reader in before:
        assert after[reader] == before[reader], reader
