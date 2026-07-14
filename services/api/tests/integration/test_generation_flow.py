"""
Integration tests for generation flow
Issue #482: Test the complete generation workflow from configuration to results

The generation routers were migrated to the async DB lane:
  - ``routers/projects/generation.py``   (generation-config / generation-status,
    under ``/api/projects/.../generation*``)
  - ``routers/generation.py``            (``/api/generation/...`` — status, stop,
    pause, resume, retry, delete, parse-metrics)
  - ``routers/generation_task_list.py``  (``/api/generation-tasks/...``)

Because the migrated handlers open a SEPARATE async connection, the old sync
``client`` + ``test_db`` fixtures can no longer see rows seeded through the sync
session. Every HTTP-driving test below therefore seeds via ``async_test_db`` and
drives the surface through ``async_test_client``, with ``require_user`` overridden
per-test via the ``_as_user`` context manager (copied from
``test_reports_branches.py``) so the auth User matches a seeded DB user.

The one exception is the WebSocket suite: the WS endpoint
(``/api/ws/projects/{id}/generation-progress``) is still on the sync lane
(``Depends(get_db)``) and httpx's ``AsyncClient`` cannot speak the WS protocol,
so those tests keep the sync ``client`` + ``test_user`` fixtures.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Helpers (mirrors test_reports_branches.py)
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=True, username_prefix="gen") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Generation User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Org") -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        display_name=name,
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user: User, org: Organization, *, role="CONTRIBUTOR"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _create_project(
    db,
    creator: User,
    *,
    title: str = "Test Project",
    generation_config: dict = None,
    org: Organization = None,
    num_tasks: int = 0,
) -> Project:
    """Create a project, optionally linked to an org and seeded with N tasks."""
    project = Project(
        id=_uid(),
        title=title,
        description="Project for testing generation",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()

    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()

    for i in range(num_tasks):
        db.add(
            Task(
                id=_uid(),
                project_id=project.id,
                data={"text": f"Sample text {i}", "id": f"task-{i}"},
                created_by=creator.id,
                inner_id=i,
            )
        )
    if num_tasks:
        await db.flush()

    return project


async def _seed_parse_data(db, project: Project) -> str:
    """Create one parent ResponseGeneration + 6 child Generation rows with the
    parse-status mix the parse-metrics assertions expect:
      3 success (retry_count 1, 2, 1), 2 failed (same error), 1 validation_error.
    Returns the parent response_generation id.
    """
    parent_id = _uid()
    db.add(
        DBResponseGeneration(
            id=parent_id,
            project_id=project.id,
            model_id="gpt-4o",
            status="completed",
            created_by=project.created_by,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
    )
    await db.flush()

    rows = [
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-1",
            model_id="gpt-4o",
            run_index=0,
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 1},
        ),
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-2",
            model_id="gpt-4o",
            run_index=1,
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 2},
        ),
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-3",
            model_id="gpt-4o",
            run_index=2,
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 1},
        ),
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-4",
            model_id="gpt-4o",
            run_index=3,
            case_data="test data",
            response_content="invalid response",
            parse_status="failed",
            parse_error="JSON decode error",
        ),
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-5",
            model_id="gpt-4o",
            run_index=4,
            case_data="test data",
            response_content="invalid response",
            parse_status="failed",
            parse_error="JSON decode error",
        ),
        DBGeneration(
            id=_uid(),
            generation_id=parent_id,
            task_id="task-6",
            model_id="gpt-4o",
            run_index=5,
            case_data="test data",
            response_content="missing fields",
            parse_status="validation_error",
            parse_error="Missing required field: label",
        ),
    ]
    db.add_all(rows)
    await db.flush()
    return parent_id


_CONFIGURED_GENERATION = {
    "selected_configuration": {
        "models": ["gpt-4o", "claude-3-opus-20240229"],
        "prompts": {"system": "Test system prompt", "instruction": "Test instruction"},
        "parameters": {"temperature": 0.7, "max_tokens": 1500, "batch_size": 10},
    }
}


# Sync project fixture for the WebSocket suite (the WS endpoint still reads the
# sync `test_db` session via Depends(get_db); the async-lane HTTP tests above
# seed their own projects through `async_test_db`).
@pytest.fixture
def test_project(db, test_user):
    """Create a test project + tasks in the sync test session for WS tests."""
    project = Project(
        id="test-project-123",
        title="Test Project",
        description="Project for testing generation",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    for i in range(3):
        db.add(
            Task(
                id=f"task-{i}",
                project_id=project.id,
                data={"text": f"Sample text {i}", "id": f"task-{i}"},
                created_by=test_user.id,
                inner_id=i,
            )
        )
    db.commit()
    return project


# ===========================================================================
# Generation configuration  (routers/projects/generation.py)
# ===========================================================================


class TestGenerationConfiguration:
    """Test generation configuration endpoints"""

    @pytest.mark.asyncio
    async def test_get_generation_config_empty(self, async_test_client, async_test_db):
        """Test getting generation config when none exists"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/generation-config"
            )

        assert response.status_code == 200
        data = response.json()
        assert "available_options" in data
        assert "selected_configuration" not in data or data["selected_configuration"] is None

    @pytest.mark.asyncio
    async def test_update_generation_config(self, async_test_client, async_test_db):
        """Test updating generation configuration"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await async_test_db.commit()

        config = {
            "detected_data_types": [{"name": "text", "type": "string"}],
            "available_options": {
                "models": {
                    "openai": ["gpt-4o", "gpt-3.5-turbo"],
                    "anthropic": ["claude-3-opus-20240229"],
                },
                "presentation_modes": ["label_config", "template", "raw_json", "auto"],
            },
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-opus-20240229"],
                "prompts": {
                    "system": "You are an expert annotator",
                    "instruction": "Please annotate the following",
                },
                "parameters": {"temperature": 0.7, "max_tokens": 1500, "batch_size": 10},
                "presentation_mode": "label_config",
                "field_mappings": {},
            },
            "last_updated": datetime.now().isoformat(),
        }

        with _as_user(admin):
            response = await async_test_client.put(
                f"/api/projects/{project.id}/generation-config", json=config
            )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "config" in data

    @pytest.mark.asyncio
    async def test_update_generation_config_unauthorized(self, async_test_client, async_test_db):
        """Test updating config without authentication"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await async_test_db.commit()

        # No _as_user override → require_user gate rejects with 401.
        response = await async_test_client.put(
            f"/api/projects/{project.id}/generation-config", json={}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_clear_generation_config(self, async_test_client, async_test_db):
        """Test clearing generation configuration"""
        admin = await _make_user(async_test_db)
        project = await _create_project(
            async_test_db, admin, generation_config={"test": "config"}
        )
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.delete(
                f"/api/projects/{project_id}/generation-config"
            )

        assert response.status_code == 204

        # Verify it's cleared in the persisted row.
        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(
                select(Project).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
        assert refreshed.generation_config is None


# ===========================================================================
# Generation execution
# ===========================================================================


class TestGenerationExecution:
    """Test generation execution endpoints"""

    @pytest.mark.asyncio
    async def test_get_generation_status(self, async_test_client, async_test_db):
        """Test getting generation status (routers/projects/generation.py)"""
        admin = await _make_user(async_test_db)
        project = await _create_project(
            async_test_db, admin, generation_config=_CONFIGURED_GENERATION
        )
        gen1 = DBResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            status="running",
            created_by=admin.id,
            started_at=datetime.now(),
        )
        gen2 = DBResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="claude-3-opus-20240229",
            status="completed",
            created_by=admin.id,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        async_test_db.add_all([gen1, gen2])
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/generation-status"
            )

        assert response.status_code == 200
        data = response.json()
        assert "generations" in data
        assert len(data["generations"]) == 2
        assert data["is_running"] is True
        assert data["latest_status"] == "completed"  # Most recent first

    @pytest.mark.asyncio
    async def test_stop_generation(self, async_test_client, async_test_db):
        """Test stopping a running generation (routers/generation.py)"""
        admin = await _make_user(async_test_db)
        gen_id = _uid()
        async_test_db.add(
            DBResponseGeneration(
                id=gen_id,
                project_id="test-project",
                model_id="gpt-4o",
                status="running",
                created_by=admin.id,
                started_at=datetime.now(),
            )
        )
        await async_test_db.commit()

        with patch("routers.generation.celery_app.control.revoke") as mock_revoke:  # noqa: F841
            with _as_user(admin):
                response = await async_test_client.post(f"/api/generation/{gen_id}/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "stopped"

        # Verify the persisted generation status updated.
        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
            )
        ).scalar_one_or_none()
        assert refreshed.status == "stopped"

    @pytest.mark.asyncio
    async def test_delete_generation(self, async_test_client, async_test_db):
        """Test deleting generation and its responses (routers/generation.py)"""
        admin = await _make_user(async_test_db)
        gen_id = _uid()
        async_test_db.add(
            DBResponseGeneration(
                id=gen_id,
                project_id="test-project",
                model_id="gpt-4o",
                status="completed",
                created_by=admin.id,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
        )
        async_test_db.add(
            DBGeneration(
                id=_uid(),
                generation_id=gen_id,
                task_id="task-1",
                model_id="gpt-4o",
                run_index=0,
                case_data="test data",
                response_content="test response",
            )
        )
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.delete(f"/api/generation/{gen_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_responses"] == 1

        # Verify deletion of both the parent and child rows.
        async_test_db.expire_all()
        parent = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
            )
        ).scalar_one_or_none()
        assert parent is None
        child = (
            await async_test_db.execute(
                select(DBGeneration).where(DBGeneration.generation_id == gen_id)
            )
        ).scalar_one_or_none()
        assert child is None


# ===========================================================================
# Generation start  (routers/generation_task_list.py)
# ===========================================================================


class TestStartGeneration:
    """Test the start_generation endpoint persists ResponseGeneration rows and
    returns the expected response shape. Celery dispatch is patched out so no
    real broker call fires."""

    @pytest.mark.asyncio
    async def test_start_generation_persists_rows(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db)
        admin_id = admin.id
        org = await _make_org(async_test_db)
        project = await _create_project(
            async_test_db,
            admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4o", "claude-3-opus-20240229"]}
            },
            org=org,
            num_tasks=3,
        )
        project_id = project.id
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            with _as_user(admin):
                response = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project_id}/generate",
                    json={"mode": "all"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project_id
        assert data["mode"] == "all"
        assert data["models_count"] == 2
        # 3 tasks x 2 models x 1 (no structures) = 6 cells queued.
        assert data["tasks_queued"] == 6
        assert len(data["generation_job_ids"]) == 6

        # A Celery send_task was attempted per dispatched run (patched away).
        assert mock_celery.send_task.call_count == 6

        # ResponseGeneration rows were persisted for the project. Select the
        # columns explicitly (rather than ORM objects) so the assertions don't
        # trigger a lazy expired-attribute refresh inside the async session.
        async_test_db.expire_all()
        rows = (
            await async_test_db.execute(
                select(
                    DBResponseGeneration.status,
                    DBResponseGeneration.created_by,
                ).where(DBResponseGeneration.project_id == project_id)
            )
        ).all()
        assert len(rows) == 6
        assert all(status == "pending" for status, _ in rows)
        assert all(created_by == admin_id for _, created_by in rows)

    @pytest.mark.asyncio
    async def test_start_generation_no_models_400(self, async_test_client, async_test_db):
        """A project with no configured models cannot start generation -> 400."""
        admin = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        project = await _create_project(
            async_test_db,
            admin,
            generation_config={"selected_configuration": {"models": []}},
            org=org,
            num_tasks=1,
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app"):
            with _as_user(admin):
                response = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project.id}/generate",
                    json={"mode": "all"},
                )

        assert response.status_code == 400
        assert "no models configured" in response.json()["detail"].lower()


class TestStartGenerationCustomModelGuard:
    """BYOM guard in start_generation: custom ("custom-...") model ids must
    exist, be active, and be visible to the triggering user. Official ids
    keep the pre-existing behavior."""

    @staticmethod
    def _custom_model(created_by, **overrides):
        from models import LLMModel as DBLLMModel

        data = dict(
            id=f"custom-{_uid()}",
            name="Custom vLLM",
            provider="Custom",
            model_type="chat",
            capabilities=["text_generation"],
            is_active=True,
            is_official=False,
            created_by=created_by,
            is_private=True,
            is_public=False,
            base_url="http://10.10.3.7:8000/v1",
            endpoint_model_name="llama-3-8b",
            requires_api_key=False,
            created_at=datetime.now(timezone.utc),
        )
        data.update(overrides)
        return DBLLMModel(**data)

    @pytest.mark.asyncio
    async def test_inaccessible_custom_model_403(self, async_test_client, async_test_db):
        """A non-superadmin project owner cannot dispatch against someone
        else's private custom model."""
        owner = await _make_user(async_test_db, is_superadmin=False)
        stranger = await _make_user(async_test_db, is_superadmin=False)
        foreign_model = self._custom_model(stranger.id)
        async_test_db.add(foreign_model)
        project = await _create_project(
            async_test_db,
            owner,
            generation_config={"selected_configuration": {"models": []}},
            num_tasks=1,
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            with _as_user(owner):
                response = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project.id}/generate",
                    json={"mode": "all", "model_ids": [foreign_model.id]},
                )

        assert response.status_code == 403
        assert foreign_model.id in response.json()["detail"]
        mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_or_inactive_custom_model_400(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db, is_superadmin=False)
        inactive_model = self._custom_model(owner.id, is_active=False)
        async_test_db.add(inactive_model)
        project = await _create_project(
            async_test_db,
            owner,
            generation_config={"selected_configuration": {"models": []}},
            num_tasks=1,
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app"):
            with _as_user(owner):
                missing = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project.id}/generate",
                    json={"mode": "all", "model_ids": ["custom-does-not-exist"]},
                )
                inactive = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project.id}/generate",
                    json={"mode": "all", "model_ids": [inactive_model.id]},
                )

        assert missing.status_code == 400
        assert "custom-does-not-exist" in missing.json()["detail"]
        assert inactive.status_code == 400
        assert inactive_model.id in inactive.json()["detail"]

    @pytest.mark.asyncio
    async def test_accessible_custom_model_dispatches(
        self, async_test_client, async_test_db
    ):
        """Happy path: the creator's own custom model passes the guard and
        the run dispatches like any official model (Celery patched)."""
        owner = await _make_user(async_test_db, is_superadmin=False)
        own_model = self._custom_model(owner.id)
        async_test_db.add(own_model)
        project = await _create_project(
            async_test_db,
            owner,
            generation_config={"selected_configuration": {"models": []}},
            num_tasks=2,
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            with _as_user(owner):
                response = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project.id}/generate",
                    json={"mode": "all", "model_ids": [own_model.id]},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["models_count"] == 1
        assert data["tasks_queued"] == 2
        assert mock_celery.send_task.call_count == 2


# ===========================================================================
# WebSocket (still sync lane — Depends(get_db))
# ===========================================================================


class TestWebSocketGeneration:
    """Test WebSocket functionality for real-time updates.

    The WS endpoint is still on the sync DB lane and httpx's AsyncClient cannot
    speak the WS protocol, so these keep the sync ``client`` + ``test_user``
    fixtures (the WS auth check reads the sync test session).
    """

    @pytest.mark.asyncio
    async def test_websocket_connection(self, client, test_project, test_user):
        """Test WebSocket connection for generation progress"""
        # Use the shared `client` fixture (sets up dependency_overrides[get_db]
        # → test_db) so the WS auth check sees the test_user committed to the
        # test session. WS handshake now authenticates via the access_token
        # cookie before `accept()` (see auth_module.verify_token_for_websocket);
        # without it the server closes with 4401.
        client.cookies.set("access_token", test_user.token)

        with patch('routers.generation.get_redis_client') as mock_redis:
            # Mock Redis client to trigger polling fallback (no pubsub attribute)
            mock_redis_instance = MagicMock()
            # Remove pubsub attribute to force polling mode
            del mock_redis_instance.pubsub
            mock_redis.return_value = mock_redis_instance

            # Test WebSocket connection
            with client.websocket_connect(
                f"/api/ws/projects/{test_project.id}/generation-progress"
            ) as websocket:
                # Should receive connection confirmation
                data = websocket.receive_json()
                assert data["type"] in ["connection", "connection_polling"]
                assert data["project_id"] == test_project.id

    @pytest.mark.asyncio
    async def test_websocket_progress_updates(self, test_project):
        """Test receiving progress updates via WebSocket"""
        from fastapi.testclient import TestClient

        TestClient(app)

        with patch('routers.generation.get_redis_client') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis.return_value = mock_redis_instance

            # Mock Redis pub/sub
            mock_pubsub = MagicMock()
            mock_redis_instance.pubsub.return_value = mock_pubsub

            # Simulate progress message
            progress_message = {
                "type": "progress",
                "project_id": test_project.id,
                "generations": [
                    {"id": "gen-1", "model_id": "gpt-4o", "status": "running", "progress": 50}
                ],
            }

            # This would normally come from Redis pub/sub
            # Testing the message format expected by frontend
            assert "generations" in progress_message
            assert progress_message["generations"][0]["status"] == "running"


# ===========================================================================
# Parse metrics  (routers/generation.py)
# ===========================================================================


class TestParseMetrics:
    """Test parse metrics endpoint"""

    @pytest.mark.asyncio
    async def test_get_parse_metrics_no_filters(self, async_test_client, async_test_db):
        """Test getting parse metrics scoped to project for exact counts"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await _seed_parse_data(async_test_db, project)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/generation/parse-metrics?project_id={project.id}"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert data["parse_success"] == 3
        assert data["parse_failed"] == 2
        assert data["parse_validation_error"] == 1
        assert data["parse_failed_max_retries"] == 0
        assert data["parse_success_rate"] == 0.5
        assert data["avg_retries_until_success"] == pytest.approx(4 / 3, rel=0.01)
        assert len(data["common_parse_errors"]) == 2

    @pytest.mark.asyncio
    async def test_get_parse_metrics_by_project(self, async_test_client, async_test_db):
        """Test getting parse metrics filtered by project"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await _seed_parse_data(async_test_db, project)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/generation/parse-metrics?project_id={project.id}"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert "common_parse_errors" in data

    @pytest.mark.asyncio
    async def test_get_parse_metrics_by_model(self, async_test_client, async_test_db):
        """Test getting parse metrics filtered by model and project"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await _seed_parse_data(async_test_db, project)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/generation/parse-metrics?project_id={project.id}&model_id=gpt-4o"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert data["parse_success"] == 3

    @pytest.mark.asyncio
    async def test_get_parse_metrics_empty(self, async_test_client, async_test_db):
        """Test getting parse metrics when no generations exist"""
        admin = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                "/api/generation/parse-metrics?project_id=nonexistent-project"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 0
        assert data["parse_success"] == 0
        assert data["parse_success_rate"] == 0
        assert data["avg_retries_until_success"] == 0
        assert data["common_parse_errors"] == []

    @pytest.mark.asyncio
    async def test_get_parse_metrics_common_errors(self, async_test_client, async_test_db):
        """Test that common parse errors are sorted by count"""
        admin = await _make_user(async_test_db)
        project = await _create_project(async_test_db, admin)
        await _seed_parse_data(async_test_db, project)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                f"/api/generation/parse-metrics?project_id={project.id}"
            )

        assert response.status_code == 200
        data = response.json()

        errors = data["common_parse_errors"]
        assert len(errors) == 2
        assert errors[0]["error"] == "JSON decode error"
        assert errors[0]["count"] == 2
        assert errors[1]["error"] == "Missing required field: label"
        assert errors[1]["count"] == 1
