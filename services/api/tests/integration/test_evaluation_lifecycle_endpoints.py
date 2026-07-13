"""
Integration tests for the evaluation lifecycle endpoints (issue #198):

    POST /api/evaluations/run/{id}/pause
    POST /api/evaluations/run/{id}/resume
    POST /api/evaluations/run/{id}/retry

Same harness as test_evaluation_cancel_idempotency.py: real HTTP round-trip
through the FastAPI test client, real Postgres state via the test DB, real
auth via `auth_headers`. Celery dispatch is mocked at the lifecycle module's
`celery_app` binding — resume/retry must re-dispatch `tasks.run_evaluation`
with the eval_metadata dispatch snapshot and `evaluate_missing_only=True`.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import EvaluationRun, TaskEvaluation, EvaluationJudgeRun, User
from project_models import Annotation, Project, ProjectOrganization, Task

BASE = "/api/evaluations"

SNAPSHOT_CONFIGS = [
    {
        "id": "cfg1",
        "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": None,
        "enabled": True,
    }
]


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_run(db, admin: User, org, *, status: str = "running",
              with_snapshot: bool = True, with_task_evals: int = 0,
              created_by: str = None):
    """Project + one EvaluationRun (+ optional task_evaluations)."""
    project = Project(
        id=_uid(),
        title=f"LifecycleTest {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=admin.id,
        )
    )
    db.flush()

    meta = {"evaluation_type": "evaluation"}
    if with_snapshot:
        meta.update(
            {
                "evaluation_configs": SNAPSHOT_CONFIGS,
                "batch_size": 50,
                "label_config_version": None,
                "organization_id": None,
                "task_ids": None,
                "model_ids": None,
                "annotator_user_ids": None,
            }
        )
    eval_run = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["exact_match"],
        metrics={},
        status=status,
        samples_evaluated=0,
        created_by=created_by or admin.id,
        created_at=datetime.now(timezone.utc),
        eval_metadata=meta,
    )
    db.add(eval_run)
    db.flush()

    if with_task_evals:
        task = Task(
            id=_uid(), project_id=project.id, data={"text": "t"},
            inner_id=1, created_by=admin.id,
        )
        db.add(task)
        db.flush()
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=project.id,
            completed_by=admin.id, result=[], was_cancelled=False,
        )
        db.add(ann)
        db.flush()
        judge_run = EvaluationJudgeRun(
            id=_uid(), evaluation_id=eval_run.id, judge_model_id=None,
            run_index=0, status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(judge_run)
        db.flush()
        for i in range(with_task_evals):
            db.add(
                TaskEvaluation(
                    id=_uid(), evaluation_id=eval_run.id,
                    judge_run_id=judge_run.id, task_id=task.id,
                    generation_id=None, annotation_id=ann.id,
                    field_name=f"cfg1|__all_model__|task.expected|{i}",
                    answer_type="text", ground_truth="gt", prediction="p",
                    metrics={"exact_match": 1.0}, passed=True,
                )
            )
        db.flush()

    return {"project": project, "eval_run": eval_run}


@pytest.mark.integration
class TestPause:
    def test_pause_running_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="running",
                         with_task_evals=3)
        eval_id = data["eval_run"].id
        resp = client.post(
            f"{BASE}/run/{eval_id}/pause",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["changed"] is True
        assert body["previous_status"] == "running"
        assert body["status"] == "paused"

        test_db.expire_all()
        run = test_db.query(EvaluationRun).filter_by(id=eval_id).one()
        assert run.status == "paused"
        assert run.paused_at is not None
        # Partial rows survive the pause.
        assert (
            test_db.query(TaskEvaluation).filter_by(evaluation_id=eval_id).count()
            == 3
        )

    def test_pause_pending_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="pending")
        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/pause",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["changed"] is True

    def test_pause_completed_run_is_noop(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="completed")
        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/pause",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["changed"] is False
        assert body["status"] == "completed"
        test_db.expire_all()
        assert (
            test_db.query(EvaluationRun)
            .filter_by(id=data["eval_run"].id)
            .one()
            .status
            == "completed"
        )

    def test_pause_nonexistent_run_404(self, client, auth_headers):
        resp = client.post(
            f"{BASE}/run/{_uid()}/pause", headers=auth_headers["admin"]
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestResume:
    def test_resume_paused_run_redispatches_missing_only(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="paused")
        eval_id = data["eval_run"].id
        fake_task = MagicMock()
        fake_task.id = "celery-task-resume-1"
        with patch(
            "routers.evaluations.multi_field.lifecycle.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = fake_task
            resp = client.post(
                f"{BASE}/run/{eval_id}/resume",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["changed"] is True
        assert body["previous_status"] == "paused"
        assert body["status"] == "pending"
        assert body["celery_task_id"] == "celery-task-resume-1"

        # Re-dispatch carries the snapshot + missing-only.
        name, kwargs = (
            mock_celery.send_task.call_args.args[0],
            mock_celery.send_task.call_args.kwargs["kwargs"],
        )
        assert name == "tasks.run_evaluation"
        assert kwargs["evaluation_id"] == eval_id
        assert kwargs["evaluate_missing_only"] is True
        assert kwargs["evaluation_configs"] == SNAPSHOT_CONFIGS
        assert kwargs["batch_size"] == 50

        test_db.expire_all()
        run = test_db.query(EvaluationRun).filter_by(id=eval_id).one()
        assert run.status == "pending"
        assert run.paused_at is None
        assert run.eval_metadata["celery_task_id"] == "celery-task-resume-1"

    def test_resume_cancelled_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Formalizes the operator procedure: continue a cancelled run under
        the SAME run id, missing-only."""
        data = _seed_run(test_db, test_users[0], test_org, status="cancelled")
        data["eval_run"].completed_at = datetime.now(timezone.utc)
        data["eval_run"].error_message = "Cancelled via API"
        test_db.flush()
        fake_task = MagicMock()
        fake_task.id = "celery-task-resume-2"
        with patch(
            "routers.evaluations.multi_field.lifecycle.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = fake_task
            resp = client.post(
                f"{BASE}/run/{data['eval_run'].id}/resume",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["changed"] is True
        test_db.expire_all()
        run = test_db.query(EvaluationRun).filter_by(id=data["eval_run"].id).one()
        assert run.status == "pending"
        assert run.completed_at is None
        assert run.error_message is None

    def test_resume_running_run_is_noop(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="running")
        with patch(
            "routers.evaluations.multi_field.lifecycle.celery_app"
        ) as mock_celery:
            resp = client.post(
                f"{BASE}/run/{data['eval_run'].id}/resume",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["changed"] is False
        mock_celery.send_task.assert_not_called()

    def test_resume_without_snapshot_409_and_state_unchanged(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Runs predating config snapshotting can't be re-dispatched — the
        guard must fire BEFORE the status flip so nothing strands in
        'pending' with no celery task."""
        data = _seed_run(
            test_db, test_users[0], test_org, status="paused", with_snapshot=False
        )
        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/resume",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 409
        test_db.expire_all()
        assert (
            test_db.query(EvaluationRun)
            .filter_by(id=data["eval_run"].id)
            .one()
            .status
            == "paused"
        )


@pytest.mark.integration
class TestRetry:
    def test_retry_failed_run_bumps_counter_and_redispatches(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="failed")
        data["eval_run"].error_message = "all judge_runs failed"
        test_db.flush()
        eval_id = data["eval_run"].id
        fake_task = MagicMock()
        fake_task.id = "celery-task-retry-1"
        with patch(
            "routers.evaluations.multi_field.lifecycle.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = fake_task
            resp = client.post(
                f"{BASE}/run/{eval_id}/retry",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["changed"] is True
        assert body["retry_count"] == 1
        assert body["celery_task_id"] == "celery-task-retry-1"
        kwargs = mock_celery.send_task.call_args.kwargs["kwargs"]
        assert kwargs["evaluate_missing_only"] is True

        test_db.expire_all()
        run = test_db.query(EvaluationRun).filter_by(id=eval_id).one()
        assert run.status == "pending"
        assert run.retry_count == 1
        assert run.error_message is None

    def test_retry_non_failed_run_is_noop(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _seed_run(test_db, test_users[0], test_org, status="running")
        with patch(
            "routers.evaluations.multi_field.lifecycle.celery_app"
        ) as mock_celery:
            resp = client.post(
                f"{BASE}/run/{data['eval_run'].id}/retry",
                headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["changed"] is False
        assert body["status"] == "running"
        mock_celery.send_task.assert_not_called()


@pytest.mark.integration
class TestLifecycleAuth:
    """Permission gate mirrors single-run cancel: run owner OR project-edit."""

    def test_annotator_cannot_pause_someone_elses_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        admin = test_users[0]
        data = _seed_run(test_db, admin, test_org, status="running")
        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/pause",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        # 403 (forbidden) or 404 (no access path) — both deny; the
        # unacceptable result is a 200 that pauses the admin's run.
        assert resp.status_code in (403, 404), resp.text
        test_db.expire_all()
        assert (
            test_db.query(EvaluationRun)
            .filter_by(id=data["eval_run"].id)
            .one()
            .status
            == "running"
        )

    def test_owner_can_pause_own_run_without_edit(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The 'I can pause what I started' disjunction — same symmetry as
        cancel."""
        admin = test_users[0]
        annotator = next(u for u in test_users if "annotator" in u.username)
        data = _seed_run(
            test_db, admin, test_org, status="running",
            created_by=annotator.id,
        )
        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/pause",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] is True
