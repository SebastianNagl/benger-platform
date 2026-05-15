"""
Integration tests for the cancel endpoints + idempotency guard added
in PR #94 (per-cell eval fan-out).

Source-grep tests in `tests/unit/test_evaluation_multi_field_endpoints.py`
already pin the presence of the auth/datetime/dispatch_hash logic in
the handler source; these go further: real HTTP round-trip through
the FastAPI test client, real Postgres state mutations via the test
DB, real auth via the existing `auth_headers` fixture.

What this covers that the unit greps don't:
  - The SQL actually runs (catches the json/jsonb cast errors that
    blew up three times during dev).
  - The cancel preserves `task_evaluations` rows (the core promise).
  - Annotators (`PROJECT_VIEW` only) are rejected on cancel-all.
  - Same-payload double-POST resolves to one EvaluationRun.
  - Different-payload double-POST resolves to two EvaluationRuns
    (the dispatch_hash discriminator).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

BASE = "/api/evaluations"


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project_with_inflight_eval(db, admin: User, org, *, with_task_evals: int = 0):
    """Seed a project + a single in-flight EvaluationRun + N task_evaluations."""
    project = Project(
        id=_uid(),
        title=f"CancelTest {uuid.uuid4().hex[:6]}",
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

    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": "t"},
        inner_id=1,
        created_by=admin.id,
    )
    db.add(task)
    db.flush()

    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=admin.id,
        result=[],
        was_cancelled=False,
    )
    db.add(ann)
    db.flush()

    eval_run = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["bleu"],
        metrics={},
        status="running",
        samples_evaluated=0,
        created_by=admin.id,
        created_at=datetime.now(timezone.utc),
        eval_metadata={"evaluation_type": "evaluation"},
    )
    db.add(eval_run)
    db.flush()

    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_model_id="gpt-4o",
        run_index=0,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(judge_run)
    db.flush()

    for i in range(with_task_evals):
        db.add(
            TaskEvaluation(
                id=_uid(),
                evaluation_id=eval_run.id,
                judge_run_id=judge_run.id,
                task_id=task.id,
                generation_id=None,
                annotation_id=ann.id,
                field_name=f"smoke|__response__|musterloesung|{i}",
                answer_type="text",
                ground_truth="gt",
                prediction="pred",
                metrics={"bleu": 0.5},
                passed=True,
            )
        )
    db.flush()

    return {
        "project": project,
        "task": task,
        "annotation": ann,
        "eval_run": eval_run,
        "judge_run": judge_run,
    }


@pytest.mark.integration
class TestCancelSingle:
    """POST /api/evaluations/run/{evaluation_id}/cancel"""

    def test_cancel_flips_status_and_preserves_rows(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _make_project_with_inflight_eval(
            test_db, test_users[0], test_org, with_task_evals=5
        )
        eval_id = data["eval_run"].id

        resp = client.post(
            f"{BASE}/run/{eval_id}/cancel",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cancelled_run_ids"] == [eval_id]
        assert body["preserved_task_evaluation_count"] == 5

        # DB state: parent flipped, judge_run failed, task_evaluations untouched.
        test_db.expire_all()
        assert test_db.query(EvaluationRun).filter_by(id=eval_id).one().status == "cancelled"
        assert test_db.query(EvaluationJudgeRun).filter_by(
            id=data["judge_run"].id
        ).one().status == "failed"
        assert (
            test_db.query(TaskEvaluation)
            .filter_by(evaluation_id=eval_id)
            .count()
            == 5
        )

    def test_cancel_already_terminal_is_noop(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _make_project_with_inflight_eval(test_db, test_users[0], test_org)
        data["eval_run"].status = "completed"
        test_db.flush()

        resp = client.post(
            f"{BASE}/run/{data['eval_run'].id}/cancel",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["cancelled_run_ids"] == []
        assert "already terminal" in resp.json()["message"]

    def test_cancel_nonexistent_run_404(self, client, test_db, auth_headers):
        resp = client.post(
            f"{BASE}/run/{_uid()}/cancel",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestCancelAll:
    """POST /api/evaluations/projects/{project_id}/runs/cancel-all"""

    def test_cancel_all_flips_multiple_runs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        admin = test_users[0]
        # Two in-flight runs on the same project.
        data1 = _make_project_with_inflight_eval(test_db, admin, test_org, with_task_evals=3)
        project_id = data1["project"].id
        # Add a second eval_run to the same project.
        second = EvaluationRun(
            id=_uid(),
            project_id=project_id,
            model_id="gpt-4o",
            evaluation_type_ids=["bleu"],
            metrics={},
            status="pending",
            samples_evaluated=0,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
            eval_metadata={"evaluation_type": "evaluation"},
        )
        test_db.add(second)
        test_db.flush()

        resp = client.post(
            f"{BASE}/projects/{project_id}/runs/cancel-all",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body["cancelled_run_ids"]) == {data1["eval_run"].id, second.id}
        assert body["preserved_task_evaluation_count"] == 3

    def test_cancel_all_no_inflight_runs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        data = _make_project_with_inflight_eval(test_db, test_users[0], test_org)
        # Flip the seeded run to terminal so nothing is in flight.
        data["eval_run"].status = "completed"
        test_db.flush()

        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/runs/cancel-all",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["cancelled_run_ids"] == []


@pytest.mark.integration
class TestCancelAuth:
    """The cancel endpoints' permission gate. Annotators have only
    PROJECT_VIEW; without the PR #94 tightening they could nuke an
    admin's 6940-cell ZJS run from the runs UI."""

    def test_annotator_cannot_bulk_cancel(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        admin = next(u for u in test_users if u.is_superadmin)
        data = _make_project_with_inflight_eval(test_db, admin, test_org)
        # Annotator has PROJECT_VIEW (via project membership / org role) but
        # not PROJECT_EDIT. cancel-all requires PROJECT_EDIT strictly.
        resp = client.post(
            f"{BASE}/projects/{data['project'].id}/runs/cancel-all",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": test_org.id,
            },
        )
        # 403 (forbidden) or 404 (no access path) — both forbid the
        # bulk-nuke. The unacceptable result would be a 200 with
        # cancelled_run_ids populated.
        assert resp.status_code in (403, 404), (
            f"annotator unexpectedly able to bulk-cancel: {resp.status_code} {resp.text}"
        )


@pytest.mark.integration
class TestDispatchIdempotency:
    """`POST /run` idempotency guard: same user, same project, same
    config payload within 30s returns the existing run id with
    `status='already_running'` instead of duplicate-dispatching."""

    def _make_project_with_generations(self, test_db, admin, org):
        """Eval dispatch needs at least one task on the project to
        avoid the empty-config short-circuit."""
        project = Project(
            id=_uid(),
            title=f"IdempTest {uuid.uuid4().hex[:6]}",
            created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=admin.id,
            )
        )
        for i in range(2):
            test_db.add(
                Task(
                    id=_uid(),
                    project_id=project.id,
                    data={"text": f"t{i}"},
                    inner_id=i + 1,
                    created_by=admin.id,
                )
            )
        test_db.flush()
        return project

    def _post_run(self, client, headers, payload):
        # Patch celery dispatch to a no-op so the test doesn't hit the
        # broker. The idempotency guard runs BEFORE dispatch so we
        # only need the EvaluationRun row to land.
        with patch(
            "routers.evaluations.helpers.celery_app.send_task",
            return_value=type("T", (), {"id": "task-stub"})(),
        ):
            return client.post(f"{BASE}/run", headers=headers, json=payload)

    def test_same_payload_double_post_returns_one_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        admin = next(u for u in test_users if u.is_superadmin)
        project = self._make_project_with_generations(test_db, admin, test_org)

        payload = {
            "project_id": project.id,
            "evaluation_configs": [
                {
                    "id": "c1",
                    "metric": "bleu",
                    "prediction_fields": ["__response__"],
                    "reference_fields": ["ref"],
                    "enabled": True,
                }
            ],
            "force_rerun": True,
        }
        headers = {**auth_headers["admin"], "X-Organization-Context": test_org.id}
        r1 = self._post_run(client, headers, payload)
        r2 = self._post_run(client, headers, payload)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        id1 = r1.json()["evaluation_id"]
        id2 = r2.json()["evaluation_id"]
        assert id1 == id2, "same payload should dedupe to one run"
        assert r2.json()["status"] == "already_running"

        # Exactly one EvaluationRun in DB.
        test_db.expire_all()
        rows = (
            test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project.id)
            .all()
        )
        assert len(rows) == 1

    def test_different_payload_double_post_returns_two_runs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        admin = next(u for u in test_users if u.is_superadmin)
        project = self._make_project_with_generations(test_db, admin, test_org)
        headers = {**auth_headers["admin"], "X-Organization-Context": test_org.id}

        payload_a = {
            "project_id": project.id,
            "evaluation_configs": [
                {
                    "id": "bleu-cfg",
                    "metric": "bleu",
                    "prediction_fields": ["__response__"],
                    "reference_fields": ["ref"],
                    "enabled": True,
                }
            ],
            "force_rerun": True,
        }
        payload_b = {
            **payload_a,
            "evaluation_configs": [
                {**payload_a["evaluation_configs"][0], "id": "rouge-cfg", "metric": "rouge_l"}
            ],
        }
        r1 = self._post_run(client, headers, payload_a)
        r2 = self._post_run(client, headers, payload_b)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["evaluation_id"] != r2.json()["evaluation_id"], (
            "different configs MUST NOT collapse to one run "
            "(dispatch_hash discriminator failed)"
        )
        # Both rows landed.
        test_db.expire_all()
        rows = (
            test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == project.id)
            .all()
        )
        assert len(rows) == 2
