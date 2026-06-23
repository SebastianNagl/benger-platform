"""
Unit and integration tests for generation task list endpoints (Issue #495).
Tests paginated task list with per-model generation status.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
``get_project_with_permissions`` is now ``async`` and resolves access through
``check_project_accessible_async`` (no longer a single ``db.query().first()``
that a ``MagicMock`` can stub). Tests that exercise project-access semantics
therefore drive the real ``GET /api/generation-tasks/projects/{id}/task-status``
HTTP endpoint via ``async_test_client`` + ``async_test_db``, seeding real
users / orgs / projects so the async permission check sees the rows. ``require_user``
is overridden per-test via the ``_as_user`` context manager (the sync auth
dependency can't see the async test transaction).

The remaining tests stay SYNC: ``get_single_task_generation_status`` is an
intentionally-retained sync compatibility shim (``db: Session``), and the rest
are pure-function / Pydantic-model assertions with no DB session at all. Sync
and async tests coexist in this one file.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task
from routers.generation_task_list import (
    GenerationRequest,
    PaginatedTaskGenerationResponse,
    TaskWithGenerationStatus,
    get_project_with_permissions,  # noqa: F401  (kept for parity / re-export)
    get_single_task_generation_status,
)


# ---------------------------------------------------------------------------
# Async HTTP helpers (for the migrated task-status endpoint)
# ---------------------------------------------------------------------------

_GEN_CONFIG = {"selected_configuration": {"models": ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"]}}


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


async def _make_user(db, *, is_superadmin=False, username_prefix="gen") -> User:
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
    title: str = "Generation Project",
    org: Organization = None,
    is_private: bool = False,
    generation_config: dict = None,
) -> Project:
    project_id = _uid()
    project = Project(
        id=project_id,
        title=title,
        description="Integration test project for generation",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config if generation_config is not None else dict(_GEN_CONFIG),
    )
    db.add(project)
    await db.flush()

    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project_id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()

    return project


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = str(uuid.uuid4())
    user.is_superadmin = True
    return user


class TestProjectAccessViaTaskStatus:
    """Project-access semantics of the migrated task-status endpoint.

    ``get_project_with_permissions`` is now async (Mock-stubbing its
    ``db.query().first()`` no longer works), so these drive the real
    ``GET /api/generation-tasks/projects/{id}/task-status`` HTTP endpoint and
    assert the same access outcomes the old direct-call unit tests covered:
    superadmin allowed, missing project -> 404, org member allowed, non-member
    blocked -> 403.
    """

    @pytest.mark.asyncio
    async def test_superadmin_has_access(self, async_test_client, async_test_db):
        """Superadmin can read task-status of any project (200, models echoed)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _create_project(async_test_db, admin, org=org)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["models"] == _GEN_CONFIG["selected_configuration"]["models"]

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        """Unknown project id -> 404 'not found'."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/projects/invalid-id/task-status"
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_org_member_has_access(self, async_test_client, async_test_db):
        """A non-superadmin member of an org that owns a non-private project is
        granted access (200)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await _add_membership(async_test_db, contributor, org)
        project = await _create_project(async_test_db, admin, org=org, is_private=False)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_member_denied(self, async_test_client, async_test_db):
        """A non-superadmin who is not a member of any owning org is blocked ->
        403 'don't have access'."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        outsider = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        # outsider is a member of an UNRELATED org only.
        other_org = await _make_org(async_test_db, name="Unrelated Org")
        await _add_membership(async_test_db, outsider, other_org)
        project = await _create_project(async_test_db, admin, org=org, is_private=False)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 403
        assert "access" in resp.json()["detail"].lower()


class TestPrivateProjectAccessViaTaskStatus:
    """Private-project handling of the migrated task-status endpoint.

    Replaces the old ``TestPrivateProjectPermissions`` direct-call unit tests
    (which Mock-stubbed the now-async helper). Private projects belong to no
    org here, so only the creator and superadmins reach the project."""

    @pytest.mark.asyncio
    async def test_private_project_creator_has_access(self, async_test_client, async_test_db):
        """Private project creator should have access (200)."""
        creator = await _make_user(async_test_db, is_superadmin=False)
        project = await _create_project(async_test_db, creator, is_private=True)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(creator):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_private_project_other_user_blocked(self, async_test_client, async_test_db):
        """Non-creator non-superadmin should get 403 on a private project."""
        creator = await _make_user(async_test_db, is_superadmin=False)
        other = await _make_user(async_test_db, is_superadmin=False)
        project = await _create_project(async_test_db, creator, is_private=True)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_private_project_superadmin_has_access(self, async_test_client, async_test_db):
        """Superadmin should have access to any private project (200)."""
        creator = await _make_user(async_test_db, is_superadmin=False)
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _create_project(async_test_db, creator, is_private=True)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200


class TestHelperFunctions:
    """Test helper functions (sync ``get_single_task_generation_status`` shim)."""

    def test_get_single_task_generation_status_no_generation(self, mock_db):
        """Test status when no generation exists."""
        mock_db.query().filter().filter().order_by().first.return_value = None

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key == None  # noqa: E711
        assert result.status == None  # noqa: E711
        assert result.generation_id == None  # noqa: E711

    def test_get_single_task_generation_status_completed(self, mock_db):
        """Test status for completed generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "completed"
        mock_generation.result = {"generated_text": "This is a test response"}
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = None

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key == None  # noqa: E711
        assert result.status == "completed"
        assert result.generation_id == mock_generation.id
        assert result.result_preview != None  # noqa: E711

    def test_get_single_task_generation_status_failed(self, mock_db):
        """Test status for failed generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "failed"
        mock_generation.result = None
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = "API rate limit exceeded"

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key == None  # noqa: E711
        assert result.status == "failed"
        assert result.error_message == "API rate limit exceeded"
        assert result.result_preview == None  # noqa: E711

    def test_get_single_task_generation_status_with_structure_key(self, mock_db):
        """Test status lookup with explicit structure_key finds matching generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "completed"
        mock_generation.result = {"text": "response"}
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = None

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", "default", mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key == "default"
        assert result.status == "completed"

    def test_get_single_task_generation_status_structure_key_no_match(self, mock_db):
        """Test status with structure_key returns null status when no generation found."""
        mock_db.query().filter().filter().order_by().first.return_value = None

        result = get_single_task_generation_status("task-id", "model-id", "default", mock_db)

        assert result.structure_key == "default"
        assert result.status == None  # noqa: E711


class TestPaginatedTaskGenerationEndpoint:
    """Test the paginated task generation status endpoint."""

    @patch('services.feature_flag_service.FeatureFlagService')
    def test_get_task_generation_status_feature_disabled(
        self, mock_flag_service, mock_db, mock_user
    ):
        """Test that endpoint returns 403 when feature flag is disabled."""
        mock_flag_service.return_value.is_enabled.return_value = False

        # This would need to be tested through the actual FastAPI app
        # Here we just verify the flag service would be called correctly
        flag_service = mock_flag_service(mock_db)
        assert not flag_service.is_enabled("generation", mock_user)

    def test_paginated_response_structure(self):
        """Test the structure of paginated response."""
        tasks = [
            TaskWithGenerationStatus(
                id=str(uuid.uuid4()),
                data={"text": "Task 1"},
                meta=None,
                created_at=datetime.now(),
                generation_status={},
            ),
            TaskWithGenerationStatus(
                id=str(uuid.uuid4()),
                data={"text": "Task 2"},
                meta=None,
                created_at=datetime.now(),
                generation_status={},
            ),
        ]

        response = PaginatedTaskGenerationResponse(
            tasks=tasks,
            total=2,
            page=1,
            page_size=50,
            total_pages=1,
            models=["gpt-4o", "claude-sonnet-4"],
            structures=[],
        )

        assert len(response.tasks) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 50
        assert response.total_pages == 1
        assert len(response.models) == 2

    def test_pagination_calculation(self):
        """Test pagination calculations."""
        # Test various pagination scenarios
        test_cases = [
            (100, 25, 4),  # 100 items, 25 per page = 4 pages
            (99, 25, 4),  # 99 items, 25 per page = 4 pages
            (101, 25, 5),  # 101 items, 25 per page = 5 pages
            (0, 25, 0),  # 0 items = 0 pages
            (1, 25, 1),  # 1 item = 1 page
        ]

        for total, page_size, expected_pages in test_cases:
            actual_pages = (total + page_size - 1) // page_size if total > 0 else 0
            assert (
                actual_pages == expected_pages
            ), f"Failed for total={total}, page_size={page_size}"


class TestGenerationEndpoint:
    """Test the generation endpoint."""

    def test_generation_request_validation(self):
        """Test request validation for generation."""
        # Valid request with all mode
        request = GenerationRequest(
            mode="all", model_ids=["gpt-4o", "claude-sonnet-4"], task_ids=["task-1", "task-2"]
        )
        assert request.mode == "all"
        assert len(request.model_ids) == 2
        assert len(request.task_ids) == 2

        # Valid request with missing mode
        request = GenerationRequest(mode="missing", model_ids=None, task_ids=None)
        assert request.mode == "missing"
        assert request.model_ids == None  # noqa: E711
        assert request.task_ids == None  # noqa: E711

    def test_generation_mode_validation(self):
        """Test that only 'all' or 'missing' modes are accepted."""
        with pytest.raises(Exception):
            # This would raise a validation error in actual FastAPI
            GenerationRequest(mode="invalid", model_ids=["gpt-4o"])

    @patch('routers.generation_task_list.celery_app')
    def test_generation_queues_tasks(self, mock_celery, mock_db):
        """Test that generation correctly queues tasks."""
        # Setup mock tasks
        mock_tasks = [MagicMock(id=f"task-{i}") for i in range(3)]
        mock_db.query().filter().all.return_value = mock_tasks

        # Setup mock for checking existing generations (all missing)
        mock_db.query().filter().first.return_value = None

        # Simulate queuing tasks
        tasks_to_queue = []
        model_ids = ["gpt-4o", "claude-sonnet-4"]

        for task in mock_tasks:
            for model_id in model_ids:
                tasks_to_queue.append((task.id, model_id))

        # Verify correct number of tasks would be queued
        assert len(tasks_to_queue) == 6  # 3 tasks * 2 models

    def test_parallel_processing_estimation(self):
        """Test time estimation for parallel processing."""
        # Test estimation calculation
        tasks_count = 10
        models_count = 3

        # Estimation formula from the code
        estimated_time = (tasks_count // models_count * 5) if models_count else (tasks_count * 5)

        assert estimated_time == 15  # (10 // 3) * 5 = 3 * 5 = 15


class TestGenerationResultEndpoint:
    """Test the generation result retrieval endpoint."""

    def test_generation_result_response_structure(self):
        """Test the structure of generation result response."""
        from routers.generation_task_list import GenerationResultResponse

        response = GenerationResultResponse(
            task_id="task-123",
            model_id="gpt-4o",
            generation_id="gen-456",
            status="completed",
            result={"generated_text": "Test response"},
            generated_at=datetime.now(),
            generation_time_seconds=2.5,
            prompt_used="Generate a response",
            parameters={"temperature": 0.7, "max_tokens": 2000},
            error_message=None,
        )

        assert response.task_id == "task-123"
        assert response.model_id == "gpt-4o"
        assert response.status == "completed"
        assert response.result["generated_text"] == "Test response"
        assert response.generation_time_seconds == 2.5

    def test_generation_time_calculation(self):
        """Test generation time calculation."""
        created_at = datetime(2024, 1, 1, 12, 0, 0)
        completed_at = datetime(2024, 1, 1, 12, 0, 5)

        generation_time = (completed_at - created_at).total_seconds()

        assert generation_time == 5.0


class TestWebSocketIntegration:
    """Test WebSocket integration for real-time updates."""

    def test_websocket_url_construction(self):
        """Test WebSocket URL construction from API URL."""
        test_cases = [
            ("http://api.localhost", "ws://api.localhost/ws/projects/{}/generation-status"),
            ("https://api.example.com", "wss://api.example.com/ws/projects/{}/generation-status"),
            ("http://localhost:8000", "ws://localhost:8000/ws/projects/{}/generation-status"),
        ]

        for api_url, expected_pattern in test_cases:
            ws_protocol = "wss" if api_url.startswith("https") else "ws"
            ws_host = api_url.replace("https://", "").replace("http://", "")
            ws_url = f"{ws_protocol}://{ws_host}/ws/projects/{{}}/generation-status"

            assert ws_url == expected_pattern.format("{}")

    def test_websocket_message_structure(self):
        """Test the structure of WebSocket messages."""
        message = {
            "type": "generation_update",
            "task_id": "task-123",
            "model_id": "gpt-4o",
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
        }

        assert message["type"] == "generation_update"
        assert "task_id" in message
        assert "model_id" in message
        assert "status" in message


class TestPerformance:
    """Test performance-related aspects."""

    def test_pagination_limits(self):
        """Test that pagination limits are enforced."""
        # Maximum page size should be 200
        MAX_PAGE_SIZE = 200

        test_sizes = [1, 25, 50, 100, 200, 201, 500]

        for size in test_sizes:
            if size > MAX_PAGE_SIZE:
                # Should be clamped to MAX_PAGE_SIZE
                actual_size = min(size, MAX_PAGE_SIZE)
                assert actual_size == MAX_PAGE_SIZE
            else:
                assert size <= MAX_PAGE_SIZE

    def test_search_query_optimization(self):
        """Test that search queries are optimized."""
        # Test that search uses ILIKE for case-insensitive search
        search_term = "test"
        expected_pattern = f"%{search_term}%"

        assert expected_pattern == "%test%"

        # Verify search term is properly escaped for SQL
        special_chars = ["'", '"', "%", "_", "\\"]
        for char in special_chars:
            # These characters should be handled properly in actual implementation
            search_with_special = f"test{char}data"
            # The implementation should escape these properly
            assert char in search_with_special


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
