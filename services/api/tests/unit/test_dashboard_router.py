"""
Comprehensive tests for the dashboard router endpoints.
Tests the current router architecture mounted at /api/dashboard/*.

The dashboard handler was migrated to the async DB lane (Depends(get_async_db),
AsyncSession). These tests drive an httpx AsyncClient and override
`get_async_db` with an async-session double whose `run_sync` invokes the passed
callable (so the sync `get_accessible_project_ids` shims keep working) and whose
`execute` is awaitable. The read/fallback helpers are patched under their new
`*_async` names.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from main import app
from models import User
from project_models import Project


def _mock_async_db(scalar_value=None):
    """Async-session double for the dashboard handler."""
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


class TestDashboardRouter:
    """Test dashboard router endpoints mounted at /api/dashboard/"""

    @pytest.fixture
    def mock_regular_user(self):
        """Create mock regular user with organization membership"""
        user = Mock(spec=User)
        user.id = "regular-user-123"
        user.username = "regular"
        user.email = "regular@example.com"
        user.name = "Regular User"
        user.is_superadmin = False
        user.is_active = True
        user.email_verified = True
        user.created_at = datetime.now(timezone.utc)
        # Mock organization memberships
        membership = Mock()
        membership.organization_id = "org-123"
        user.organization_memberships = [membership]
        return user

    @pytest.fixture
    def mock_superadmin_user(self):
        """Create mock superadmin user"""
        user = Mock(spec=User)
        user.id = "admin-user-123"
        user.username = "admin"
        user.email = "admin@example.com"
        user.name = "Admin User"
        user.is_superadmin = True
        user.is_active = True
        user.email_verified = True
        user.created_at = datetime.now(timezone.utc)
        user.organization_memberships = []
        return user

    @pytest.fixture
    def mock_project(self):
        """Create mock project"""
        project = Mock(spec=Project)
        project.id = "project-123"
        project.title = "Test Project"
        project.description = "Test project description"
        project.organization_ids = ["org-123"]
        project.created_at = datetime.now(timezone.utc)
        return project

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_as_superadmin(self, mock_superadmin_user):
        """Test getting dashboard stats as superadmin at /api/dashboard/stats with new metrics.

        The endpoint now reads from the precomputed `project_summaries` table
        via `read_dashboard_sum_async`; mock that helper rather than raw SQL.
        """
        from routers.dashboard import require_user

        app.dependency_overrides[require_user] = lambda: mock_superadmin_user
        # COUNT(*) backstop returns a value consistent with project_count.
        _override_async_db(_mock_async_db(scalar_value=10))

        try:
            with patch("routers.dashboard.read_dashboard_sum_async") as mock_sums:
                async def _sums(*_a, **_k):
                    return {
                        "project_count": 10,
                        "total_tasks": 50,
                        "labeled_tasks": 30,
                        "annotations_count": 150,
                        "generations_count": 8,
                        "response_generations_count": 12,
                        "evaluation_pairs_count": 5,
                    }

                mock_sums.side_effect = _sums
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "project_count" in data
            assert "task_count" in data
            assert "annotation_count" in data
            assert "projects_with_generations" in data
            assert "projects_with_evaluations" in data
            assert data["project_count"] == 10
            assert data["task_count"] == 50
            assert data["annotation_count"] == 150
            assert data["projects_with_generations"] == 8
            assert data["projects_with_evaluations"] == 5
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_as_regular_user(self, mock_regular_user):
        """Test getting dashboard stats as regular user with organization filtering and new metrics."""
        from routers.dashboard import require_user

        app.dependency_overrides[require_user] = lambda: mock_regular_user
        _override_async_db(_mock_async_db())

        try:
            with patch("routers.dashboard.get_accessible_project_ids") as mock_get_ids, \
                 patch("routers.dashboard.read_dashboard_sum_async") as mock_sums:
                mock_get_ids.return_value = ["proj-1", "proj-2", "proj-3", "proj-4", "proj-5"]

                async def _sums(*_a, **_k):
                    return {
                        "project_count": 5,
                        "total_tasks": 25,
                        "labeled_tasks": 12,
                        "annotations_count": 75,
                        "generations_count": 3,
                        "response_generations_count": 4,
                        "evaluation_pairs_count": 2,
                    }

                mock_sums.side_effect = _sums
                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 5
                assert data["task_count"] == 25
                assert data["annotation_count"] == 75
                assert data["projects_with_generations"] == 3
                assert data["projects_with_evaluations"] == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_database_error(self, mock_regular_user):
        """Test dashboard stats with database error returns default values for new metrics"""
        from routers.dashboard import require_user

        app.dependency_overrides[require_user] = lambda: mock_regular_user
        _override_async_db(_mock_async_db())

        try:
            with patch("routers.dashboard.cache") as mock_cache, patch(
                "routers.dashboard.get_accessible_project_ids",
                side_effect=Exception("Database connection failed"),
            ):
                mock_cache.get.return_value = None

                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                # Should return default values on error for all new metrics
                assert data["project_count"] == 0
                assert data["task_count"] == 0
                assert data["annotation_count"] == 0
                assert data["projects_with_generations"] == 0
                assert data["projects_with_evaluations"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_edge_case_no_generations(self, mock_superadmin_user):
        """Test dashboard stats when no projects have generations"""
        from routers.dashboard import require_user

        app.dependency_overrides[require_user] = lambda: mock_superadmin_user
        _override_async_db(_mock_async_db(scalar_value=5))

        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.read_dashboard_sum_async") as mock_sums, \
                 patch("routers.dashboard._live_evaluations_count_async") as mock_live_eval, \
                 patch("routers.dashboard._live_dashboard_counts_async") as mock_live_dash:
                mock_cache.get.return_value = None

                async def _sums(*_a, **_k):
                    return {
                        "project_count": 5,
                        "total_tasks": 20,
                        "labeled_tasks": 0,
                        "annotations_count": 0,
                        "generations_count": 0,
                        "response_generations_count": 0,
                        "evaluation_pairs_count": 0,
                    }

                mock_sums.side_effect = _sums

                async def _live_eval(*_a, **_k):
                    return 0

                mock_live_eval.side_effect = _live_eval

                # `_live_dashboard_counts_async` is the brand-new-project
                # fallback for task / annotation / generation counts. With
                # everything else mocked to 0 it fires; the
                # edge-case-no-generations scenario wants those to stay 0.
                async def _live_dash(*_a, **_k):
                    return {
                        "total_tasks": 0,
                        "annotations_count": 0,
                        "generations_count": 0,
                    }

                mock_live_dash.side_effect = _live_dash

                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 5
                assert data["task_count"] == 20
                assert data["annotation_count"] == 0
                assert data["projects_with_generations"] == 0
                assert data["projects_with_evaluations"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_edge_case_empty_database(self, mock_superadmin_user):
        """Test dashboard stats with completely empty database"""
        from routers.dashboard import require_user

        app.dependency_overrides[require_user] = lambda: mock_superadmin_user
        # No accessible projects -> all-zeros short circuit.
        _override_async_db(_mock_async_db())

        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=[]):
                mock_cache.get.return_value = None

                async with await _async_client() as client:
                    response = await client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert all(
                    data[key] == 0
                    for key in [
                        "project_count",
                        "task_count",
                        "annotation_count",
                        "projects_with_generations",
                        "projects_with_evaluations",
                    ]
                )
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestDashboardRouterIntegration:
    """Integration tests for dashboard router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_dashboard_endpoints_require_authentication(self, client):
        """Test that dashboard endpoints require authentication"""
        endpoints = [
            "/api/dashboard/stats",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should require authentication
            assert response.status_code in [401, 403]

    # test_dashboard_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.
