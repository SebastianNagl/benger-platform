"""
Extended tests for dashboard router - covering uncovered branches.

Targets: routers/dashboard.py get_dashboard_stats branches.

Migrated to the async DB lane alongside the handler (Depends(get_async_db),
AsyncSession). Drives an httpx AsyncClient with an async-session double; see
test_dashboard_coverage.py for the pattern and rationale.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from main import app
from models import User


def _mock_async_db(scalar_value=None):
    mock_db = MagicMock()

    result = MagicMock()
    result.scalar.return_value = scalar_value
    result.all.return_value = []
    result.first.return_value = None

    async def _execute(*_args, **_kwargs):
        return result

    async def _run_sync(fn, *args, **kwargs):
        return fn(Mock(), *args, **kwargs)

    mock_db.execute = _execute
    mock_db.run_sync = _run_sync
    return mock_db


def _override_async_db(mock_db):
    from database import get_async_db

    async def _override():
        yield mock_db

    app.dependency_overrides[get_async_db] = _override


async def _async_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


def _async_return(value):
    async def _fn(*_a, **_k):
        return value

    return _fn


class TestDashboardStats:
    """Test dashboard stats endpoint covering all branches."""

    @pytest.fixture
    def mock_user(self):
        return User(
            id="dash-user-1",
            username="dashuser",
            email="dash@test.com",
            name="Dash User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="dash-admin-1",
            username="dashadmin",
            email="dashadmin@test.com",
            name="Dash Admin",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_dashboard_stats_cached(self, mock_user):
        """Test dashboard stats returns cached result."""
        from auth_module.dependencies import require_user

        cached_stats = {
            "project_count": 5,
            "task_count": 20,
            "annotation_count": 50,
            "projects_with_generations": 2,
            "projects_with_evaluations": 1,
        }

        with patch("routers.dashboard.cache") as mock_cache:
            mock_cache.get.return_value = cached_stats

            app.dependency_overrides[require_user] = lambda: mock_user
            _override_async_db(_mock_async_db())
            try:
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 5
                assert data["task_count"] == 20
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_dashboard_stats_no_accessible_projects(self, mock_user):
        """Test dashboard stats with no accessible projects."""
        from auth_module.dependencies import require_user

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.return_value = []  # Empty list = no projects

            app.dependency_overrides[require_user] = lambda: mock_user
            _override_async_db(_mock_async_db())
            try:
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 0
                assert data["task_count"] == 0
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_dashboard_stats_superadmin(self, mock_superadmin):
        """Test dashboard stats for superadmin (sees all projects)."""
        from auth_module.dependencies import require_user

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids, \
             patch("routers.dashboard.read_dashboard_sum_async") as mock_sums, \
             patch("routers.dashboard._live_evaluations_count_async") as mock_eval:
            mock_cache.get.return_value = None
            mock_ids.return_value = None  # None = superadmin
            mock_sums.side_effect = _async_return({
                "project_count": 10, "total_tasks": 100, "labeled_tasks": 50,
                "annotations_count": 200, "generations_count": 5,
                "response_generations_count": 6, "evaluation_pairs_count": 3,
            })
            mock_eval.side_effect = _async_return(3)

            app.dependency_overrides[require_user] = lambda: mock_superadmin
            # Superadmin branch's SELECT COUNT(*) FROM projects scalar backstop.
            _override_async_db(_mock_async_db(scalar_value=10))
            try:
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 10
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_dashboard_stats_with_org_context(self, mock_user):
        """Test dashboard stats with org context header."""
        from auth_module.dependencies import require_user

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids, \
             patch("routers.dashboard.read_dashboard_sum_async") as mock_sums, \
             patch("routers.dashboard._live_evaluations_count_async") as mock_eval:
            mock_cache.get.return_value = None
            mock_ids.return_value = ["proj-1", "proj-2", "proj-3"]
            mock_sums.side_effect = _async_return({
                "project_count": 3, "total_tasks": 15, "labeled_tasks": 7,
                "annotations_count": 30, "generations_count": 1,
                "response_generations_count": 1, "evaluation_pairs_count": 0,
            })
            mock_eval.side_effect = _async_return(0)

            app.dependency_overrides[require_user] = lambda: mock_user
            _override_async_db(_mock_async_db())
            try:
                async with await _async_client() as client:
                    response = await client.get(
                        "/api/dashboard/stats",
                        headers={"X-Organization-Context": "org-123"},
                    )
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 3
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_dashboard_stats_exception(self, mock_user):
        """Test dashboard stats handles exceptions gracefully."""
        from auth_module.dependencies import require_user

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.side_effect = Exception("Database connection error")

            app.dependency_overrides[require_user] = lambda: mock_user
            _override_async_db(_mock_async_db())
            try:
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 0  # Default on error
            finally:
                app.dependency_overrides.clear()
