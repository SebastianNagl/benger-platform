"""
Extended tests for dashboard router - covering uncovered branches.

Targets: routers/dashboard.py lines 37-119
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestDashboardStats:
    """Test dashboard stats endpoint covering all branches."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

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

    def test_dashboard_stats_cached(self, client, mock_user):
        """Test dashboard stats returns cached result."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        cached_stats = {
            "project_count": 5,
            "task_count": 20,
            "annotation_count": 50,
            "projects_with_generations": 2,
            "projects_with_evaluations": 1,
        }

        with patch("routers.dashboard.cache") as mock_cache:
            mock_cache.get.return_value = cached_stats

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 5
                assert data["task_count"] == 20
            finally:
                app.dependency_overrides.clear()

    def test_dashboard_stats_no_accessible_projects(self, client, mock_user):
        """Test dashboard stats with no accessible projects."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.return_value = []  # Empty list = no projects

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 0
                assert data["task_count"] == 0
            finally:
                app.dependency_overrides.clear()

    def test_dashboard_stats_superadmin(self, client, mock_superadmin):
        """Test dashboard stats for superadmin (sees all projects)."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_superadmin

        mock_db = Mock(spec=Session)
        mock_result = Mock()
        mock_result.project_count = 10
        mock_result.task_count = 100
        mock_result.annotation_count = 200
        mock_result.projects_with_generations = 5
        mock_result.projects_with_evaluations = 3
        mock_db.execute.return_value = Mock(fetchone=Mock(return_value=mock_result))

        def override_get_db():
            return mock_db

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.return_value = None  # None = superadmin

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 10
            finally:
                app.dependency_overrides.clear()

    def test_dashboard_stats_with_org_context(self, client, mock_user):
        """Test dashboard stats with org context header."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_result = Mock()
        mock_result.project_count = 3
        mock_result.task_count = 15
        mock_result.annotation_count = 30
        mock_result.projects_with_generations = 1
        mock_result.projects_with_evaluations = 0
        mock_db.execute.return_value = Mock(fetchone=Mock(return_value=mock_result))

        def override_get_db():
            return mock_db

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.return_value = ["proj-1", "proj-2", "proj-3"]

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get(
                    "/api/dashboard/stats",
                    headers={"X-Organization-Context": "org-123"},
                )
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 3
            finally:
                app.dependency_overrides.clear()

    def test_dashboard_stats_exception(self, client, mock_user):
        """Test dashboard stats handles exceptions gracefully."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.dashboard.cache") as mock_cache, \
             patch("routers.dashboard.get_accessible_project_ids") as mock_ids:
            mock_cache.get.return_value = None
            mock_ids.side_effect = Exception("Database connection error")

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/dashboard/stats")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["project_count"] == 0  # Default on error
            finally:
                app.dependency_overrides.clear()
