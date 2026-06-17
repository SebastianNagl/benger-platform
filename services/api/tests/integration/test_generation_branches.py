"""Branch-coverage integration tests for the generation router.

Targets the error/edge paths in ``services/api/routers/generation.py`` that the
happy-path suites (``test_generation_endpoints_coverage.py``,
``test_remaining_router_endpoints.py``) leave uncovered:

- ``get_generation_status``: 404 unknown id, 403 when the generation's task
  belongs to an inaccessible project, 200 with the ``error_message``-as-message
  shaping.
- ``stop_generation``: owner-only 403, status-guard 400 (non pending/running),
  200 success path with persisted ``status='stopped'`` + ``completed_at`` +
  ``error_message`` (celery_app patched so the revoke side-effect is a no-op).
- ``pause_generation`` / ``resume_generation`` / ``retry_generation``: 404,
  owner-only 403, and the status-transition 400 guards. The success paths of
  these three crash with 500 because the ResponseGeneration model has no
  ``paused_at`` / ``resumed_at`` / ``retry_count`` / ``current_progress``
  columns (documented pre-existing bug — see the retry test in
  ``test_remaining_router_endpoints.py``), so we only exercise the guard
  branches that return before touching those columns.
- ``delete_generation``: 404, owner-only 403, running-guard 400, and the 200
  success path with cascade deletion of the child ``Generation`` rows
  (asserted via ``test_db``).
- ``get_parse_metrics``: project-access 403, the empty-set early return,
  the populated aggregation (success/failed/validation_error counts +
  success_rate + avg_retries), the ``model_id`` filter, and the
  ``common_parse_errors`` top-N grouping.

Every test calls the endpoint through the ``client`` fixture, asserts the HTTP
status + response JSON, and (where the endpoint mutates rows) verifies the
persisted DB state via ``test_db``. Model providers are never invoked — the
only celery touch point (``celery_app.control.revoke`` in stop) is patched out.
"""

import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    *,
    num_tasks: int = 1,
    is_private: bool = False,
    link_org: bool = True,
) -> Project:
    """Project owned by admin (test_users[0]). Linked to test_org by default so
    member access checks pass; private + unlinked for the 403 paths."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="gen-branches-test",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=admin.id,
        is_published=True,
        is_private=is_private,
    )
    test_db.add(project)
    test_db.flush()
    if link_org:
        test_db.add(ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=admin.id,
        ))
    test_db.flush()
    for i in range(num_tasks):
        test_db.add(Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i + 1}"},
            created_by=admin.id,
            updated_by=admin.id,
        ))
    test_db.commit()
    return project


def _seed_generation(
    test_db: Session,
    project: Project,
    *,
    created_by: str,
    status_val: str = "completed",
    model_id: str = "gpt-4o",
    task_id: str = None,
) -> DBResponseGeneration:
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task_id,
        model_id=model_id,
        status=status_val,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(gen)
    test_db.commit()
    return gen


def _first_task(test_db: Session, project: Project) -> Task:
    return test_db.query(Task).filter(Task.project_id == project.id).first()


# ---------------------------------------------------------------------------
# get_generation_status — GET /api/generation/status/{generation_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetGenerationStatus:
    def test_unknown_generation_returns_404(self, client, auth_headers):
        resp = client.get(
            f"/api/generation/status/missing-{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"].lower()

    def test_inaccessible_project_returns_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The generation's task belongs to a PRIVATE project the requester did
        not create → check_project_accessible False → 403."""
        project = _seed_project(
            test_db, test_users, test_org, is_private=True, link_org=False
        )
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id,
            status_val="running", task_id=task.id,
        )
        # annotator is neither superadmin nor the private project's creator.
        resp = client.get(
            f"/api/generation/status/{gen.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"].lower()

    def test_status_returns_error_message_as_message(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A failed generation surfaces its error_message in the `message`
        field; status echoes the DB row."""
        project = _seed_project(test_db, test_users, test_org)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id,
            status_val="failed", task_id=task.id,
        )
        gen.error_message = "boom while generating"
        test_db.commit()

        resp = client.get(
            f"/api/generation/status/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == gen.id
        assert body["status"] == "failed"
        assert body["message"] == "boom while generating"
        assert body["progress"] is None

    def test_status_default_message_when_no_error(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """No error_message → the fallback 'Generation status' string."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.get(
            f"/api/generation/status/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "Generation status"


# ---------------------------------------------------------------------------
# stop_generation — POST /api/generation/{generation_id}/stop
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStopGeneration:
    def test_stop_unknown_returns_404(self, client, auth_headers):
        resp = client.post(
            f"/api/generation/missing-{_uid()}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Generation not found"

    def test_non_owner_non_superadmin_forbidden(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """contributor is not the generation creator (admin is) and is not a
        superadmin → 403, and the row stays 'running'."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "your own" in resp.json()["detail"].lower()
        test_db.refresh(gen)
        assert gen.status == "running"

    def test_stop_completed_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Only pending/running may be stopped → completed yields 400 and the
        status is unchanged."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="completed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "completed" in resp.json()["detail"]
        test_db.refresh(gen)
        assert gen.status == "completed"

    @patch("routers.generation.celery_app")
    def test_stop_running_persists_stopped_state(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        """Happy path: a running generation transitions to 'stopped', gets a
        completed_at, and an error_message naming the user. celery_app is
        patched so control.revoke is a harmless no-op."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "stopped"
        assert body["generation_id"] == gen.id

        # Persisted state.
        test_db.refresh(gen)
        assert gen.status == "stopped"
        assert gen.completed_at is not None
        assert "Stopped by user" in (gen.error_message or "")
        # (celery_app is patched only to prevent a real broker call; the seeded
        # generation has no dispatched task id, so revoke is not necessarily hit.)

    @patch("routers.generation.celery_app")
    def test_stop_pending_persists_stopped_state(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        """'pending' is the other stoppable status."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="pending"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/stop",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        test_db.refresh(gen)
        assert gen.status == "stopped"


# ---------------------------------------------------------------------------
# pause_generation — POST /api/generation/{generation_id}/pause
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPauseGeneration:
    def test_pause_unknown_returns_404(self, client, auth_headers):
        resp = client.post(
            f"/api/generation/missing-{_uid()}/pause",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Generation not found"

    def test_pause_non_owner_forbidden(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/pause",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "your own" in resp.json()["detail"].lower()

    def test_pause_non_running_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Only running generations may be paused → completed yields 400 (the
        guard returns before the model's missing paused_at column is touched)."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="completed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/pause",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "completed" in resp.json()["detail"]
        test_db.refresh(gen)
        assert gen.status == "completed"


# ---------------------------------------------------------------------------
# resume_generation — POST /api/generation/{generation_id}/resume
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestResumeGeneration:
    def test_resume_unknown_returns_404(self, client, auth_headers):
        resp = client.post(
            f"/api/generation/missing-{_uid()}/resume",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Generation not found"

    def test_resume_non_owner_forbidden(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="paused"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/resume",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "your own" in resp.json()["detail"].lower()

    def test_resume_non_paused_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Only paused generations may be resumed → running yields 400 (the
        guard returns before the model's missing resumed_at column is touched)."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/resume",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "running" in resp.json()["detail"]
        test_db.refresh(gen)
        assert gen.status == "running"


# ---------------------------------------------------------------------------
# retry_generation — POST /api/generation/{generation_id}/retry
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRetryGeneration:
    def test_retry_unknown_returns_404(self, client, auth_headers):
        resp = client.post(
            f"/api/generation/missing-{_uid()}/retry",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Generation not found"

    def test_retry_non_owner_forbidden(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="failed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/retry",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "your own" in resp.json()["detail"].lower()

    def test_retry_completed_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Only failed/stopped generations may be retried → completed yields 400.
        The guard returns before the model's missing retry_count column would
        otherwise 500."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="completed"
        )
        resp = client.post(
            f"/api/generation/{gen.id}/retry",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "completed" in resp.json()["detail"]
        test_db.refresh(gen)
        assert gen.status == "completed"


# ---------------------------------------------------------------------------
# delete_generation — DELETE /api/generation/{generation_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteGeneration:
    def test_delete_unknown_returns_404(self, client, auth_headers):
        resp = client.delete(
            f"/api/generation/missing-{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Generation not found"

    def test_delete_non_owner_forbidden(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="completed"
        )
        resp = client.delete(
            f"/api/generation/{gen.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403, resp.text
        assert "your own" in resp.json()["detail"].lower()
        # Still present.
        assert (
            test_db.query(DBResponseGeneration)
            .filter(DBResponseGeneration.id == gen.id)
            .first()
            is not None
        )

    def test_delete_running_returns_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        resp = client.delete(
            f"/api/generation/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400, resp.text
        assert "running" in resp.json()["detail"].lower()
        assert (
            test_db.query(DBResponseGeneration)
            .filter(DBResponseGeneration.id == gen.id)
            .first()
            is not None
        )

    def test_delete_completed_cascades_child_responses(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Deleting a completed generation removes the ResponseGeneration row
        AND its child Generation rows; the response reports the deleted count."""
        project = _seed_project(test_db, test_users, test_org)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id,
            status_val="completed", task_id=task.id,
        )
        # Two child Generation rows (different run_index so the unique index
        # on (generation_id, run_index) is satisfied).
        for run_index in (0, 1):
            test_db.add(DBLLMResponse(
                id=_uid(),
                generation_id=gen.id,
                task_id=task.id,
                model_id=gen.model_id,
                case_data="input case",
                response_content="generated answer",
                status="completed",
                run_index=run_index,
            ))
        test_db.commit()

        # Sanity: 2 child rows exist before deletion.
        assert (
            test_db.query(DBLLMResponse)
            .filter(DBLLMResponse.generation_id == gen.id)
            .count()
            == 2
        )

        resp = client.delete(
            f"/api/generation/{gen.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["generation_id"] == gen.id
        assert body["deleted_responses"] == 2

        # Parent + children gone.
        assert (
            test_db.query(DBResponseGeneration)
            .filter(DBResponseGeneration.id == gen.id)
            .first()
            is None
        )
        assert (
            test_db.query(DBLLMResponse)
            .filter(DBLLMResponse.generation_id == gen.id)
            .count()
            == 0
        )


# ---------------------------------------------------------------------------
# get_parse_metrics — GET /api/generation/parse-metrics
# ---------------------------------------------------------------------------


def _seed_response(
    test_db: Session,
    gen: DBResponseGeneration,
    task: Task,
    *,
    model_id: str,
    parse_status: str,
    parse_error: str = None,
    parse_metadata: dict = None,
    status_val: str = "completed",
    run_index: int = 0,
) -> None:
    test_db.add(DBLLMResponse(
        id=_uid(),
        generation_id=gen.id,
        task_id=task.id,
        model_id=model_id,
        case_data="input case",
        response_content="generated answer",
        status=status_val,
        parse_status=parse_status,
        parse_error=parse_error,
        parse_metadata=parse_metadata,
        run_index=run_index,
    ))


@pytest.mark.integration
class TestParseMetrics:
    def test_inaccessible_project_returns_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """project_id of a PRIVATE project the requester did not create → 403."""
        project = _seed_project(
            test_db, test_users, test_org, is_private=True, link_org=False
        )
        resp = client.get(
            f"/api/generation/parse-metrics?project_id={project.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"].lower()

    def test_empty_project_returns_zeroed_metrics(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Accessible project with no responses → the total==0 early return."""
        project = _seed_project(test_db, test_users, test_org)
        resp = client.get(
            f"/api/generation/parse-metrics?project_id={project.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] == 0
        assert body["parse_success_rate"] == 0
        assert body["avg_retries_until_success"] == 0
        assert body["common_parse_errors"] == []

    def test_populated_metrics_aggregate_and_avg_retries(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Mixed parse_status rows aggregate into success/failed/validation_error
        counts; success_rate and avg_retries are computed; the top failure
        error is grouped into common_parse_errors."""
        project = _seed_project(test_db, test_users, test_org)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id,
            status_val="completed", task_id=task.id,
        )
        # 2 success (retry_count 1 and 3 → avg 2), 1 failed, 1 validation_error.
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 3}, run_index=1,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="failed", parse_error="JSON decode error", run_index=2,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="validation_error", parse_error="schema mismatch",
            run_index=3,
        )
        test_db.commit()

        resp = client.get(
            f"/api/generation/parse-metrics?project_id={project.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] == 4
        assert body["parse_success"] == 2
        assert body["parse_failed"] == 1
        assert body["parse_validation_error"] == 1
        assert body["parse_success_rate"] == 0.5
        # (1 + 3) / 2 == 2.0
        assert body["avg_retries_until_success"] == 2.0
        # Both failure rows grouped; two distinct error strings, each count 1.
        errors = {e["error"]: e["count"] for e in body["common_parse_errors"]}
        assert errors.get("JSON decode error") == 1
        assert errors.get("schema mismatch") == 1

    def test_model_id_filter_narrows_aggregation(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The model_id query param restricts the aggregation to one model's
        rows."""
        project = _seed_project(test_db, test_users, test_org)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id,
            status_val="completed", task_id=task.id,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        _seed_response(
            test_db, gen, task, model_id="claude-3",
            parse_status="failed", parse_error="boom", run_index=1,
        )
        test_db.commit()

        resp = client.get(
            f"/api/generation/parse-metrics?project_id={project.id}&model_id=gpt-4o",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Only the gpt-4o success row is counted.
        assert body["total_generations"] == 1
        assert body["parse_success"] == 1
        assert body["parse_failed"] == 0
        assert body["common_parse_errors"] == []
