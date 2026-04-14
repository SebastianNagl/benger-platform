"""
Comprehensive tests for the dashboard router endpoints.
Tests the current router architecture mounted at /api/dashboard/*.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User
from project_models import Project


class TestDashboardRouter:
    """Test dashboard router endpoints mounted at /api/dashboard/"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

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

    def test_get_dashboard_stats_as_superadmin(self, client, mock_superadmin_user):
        """Test getting dashboard stats as superadmin at /api/dashboard/stats with new metrics"""
        from database import get_db
        from main import app
        from routers.dashboard import require_user

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock database query result with new metrics
            mock_result = Mock()
            mock_result.project_count = 10
            mock_result.task_count = 50
            mock_result.annotation_count = 150
            mock_result.projects_with_generations = 8
            mock_result.projects_with_evaluations = 5
            mock_db.execute.return_value.fetchone.return_value = mock_result
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/dashboard/stats")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Test new dashboard metrics
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

    def test_get_dashboard_stats_as_regular_user(self, client, mock_regular_user):
        """Test getting dashboard stats as regular user with organization filtering and new metrics"""
        from database import get_db
        from main import app
        from routers.dashboard import require_user

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock database query result with access control applied
            mock_result = Mock()
            mock_result.project_count = 5  # Regular user sees fewer projects
            mock_result.task_count = 25  # Fewer tasks than superadmin
            mock_result.annotation_count = 75  # Fewer annotations
            mock_result.projects_with_generations = 3  # Fewer with generations
            mock_result.projects_with_evaluations = 2  # Fewer with evaluations
            mock_db.execute.return_value.fetchone.return_value = mock_result
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Mock get_accessible_project_ids to return a list of project IDs
            # (avoids needing to mock the full db.query chain for project filtering)
            with patch("routers.dashboard.get_accessible_project_ids") as mock_get_ids:
                mock_get_ids.return_value = ["proj-1", "proj-2", "proj-3", "proj-4", "proj-5"]

                response = client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                # Test organization filtering is applied (fewer results than superadmin)
                assert "project_count" in data
                assert "task_count" in data
                assert "annotation_count" in data
                assert "projects_with_generations" in data
                assert "projects_with_evaluations" in data
                assert data["project_count"] == 5
                assert data["task_count"] == 25
                assert data["annotation_count"] == 75
                assert data["projects_with_generations"] == 3
                assert data["projects_with_evaluations"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_get_dashboard_stats_database_error(self, client, mock_regular_user):
        """Test dashboard stats with database error returns default values for new metrics"""
        from database import get_db
        from main import app
        from routers.dashboard import require_user

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock database error
            mock_db.execute.side_effect = Exception("Database connection failed")
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Mock the cache to return None (no cached value)
            # Mock get_accessible_project_ids to simulate error scenario
            with patch("routers.dashboard.cache") as mock_cache, patch(
                "routers.dashboard.get_accessible_project_ids",
                side_effect=Exception("Database connection failed"),
            ):
                mock_cache.get.return_value = None

                response = client.get("/api/dashboard/stats")

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

    def test_get_dashboard_stats_edge_case_no_generations(self, client, mock_superadmin_user):
        """Test dashboard stats when no projects have generations"""
        from database import get_db
        from main import app
        from routers.dashboard import require_user

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock result where projects exist but none have generations or evaluations
            mock_result = Mock()
            mock_result.project_count = 5
            mock_result.task_count = 20
            mock_result.annotation_count = 0  # No annotations yet
            mock_result.projects_with_generations = 0  # No projects with generations
            mock_result.projects_with_evaluations = 0  # No projects with evaluations
            mock_db.execute.return_value.fetchone.return_value = mock_result
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Mock the cache to return None (no cached value)
            with patch("routers.dashboard.cache") as mock_cache:
                mock_cache.get.return_value = None

                response = client.get("/api/dashboard/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 5
                assert data["task_count"] == 20
                assert data["annotation_count"] == 0
                assert data["projects_with_generations"] == 0
                assert data["projects_with_evaluations"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_get_dashboard_stats_edge_case_empty_database(self, client, mock_superadmin_user):
        """Test dashboard stats with completely empty database"""
        from database import get_db
        from main import app
        from routers.dashboard import require_user

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock result with all zeros
            mock_result = Mock()
            mock_result.project_count = 0
            mock_result.task_count = 0
            mock_result.annotation_count = 0
            mock_result.projects_with_generations = 0
            mock_result.projects_with_evaluations = 0
            mock_db.execute.return_value.fetchone.return_value = mock_result
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Mock the cache to return None (no cached value)
            with patch("routers.dashboard.cache") as mock_cache:
                mock_cache.get.return_value = None

                response = client.get("/api/dashboard/stats")

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
