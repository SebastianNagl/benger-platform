"""
Unit tests for routers/dashboard.py to increase coverage.
Tests dashboard stats endpoint with various org contexts.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


class TestGetDashboardStats:
    def test_cache_hit(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache:
                mock_cache.get.return_value = {
                    "project_count": 5,
                    "task_count": 100,
                    "annotation_count": 50,
                    "projects_with_generations": 3,
                    "projects_with_evaluations": 2,
                }
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                data = resp.json()
                assert data["project_count"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_no_accessible_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=[]):
                mock_cache.get.return_value = None
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                data = resp.json()
                assert data["project_count"] == 0
                assert data["task_count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_all_projects(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        # Mock the raw SQL result
        mock_result = Mock()
        mock_result.project_count = 10
        mock_result.task_count = 200
        mock_result.annotation_count = 100
        mock_result.projects_with_generations = 5
        mock_result.projects_with_evaluations = 3
        mock_db.execute.return_value.fetchone.return_value = mock_result

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=None):
                mock_cache.get.return_value = None
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                data = resp.json()
                assert data["project_count"] == 10
                assert data["task_count"] == 200
        finally:
            app.dependency_overrides.clear()

    def test_org_scoped_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        mock_result = Mock()
        mock_result.project_count = 3
        mock_result.task_count = 50
        mock_result.annotation_count = 20
        mock_result.projects_with_generations = 1
        mock_result.projects_with_evaluations = 0
        mock_db.execute.return_value.fetchone.return_value = mock_result

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=["p-1", "p-2", "p-3"]):
                mock_cache.get.return_value = None
                resp = client.get(
                    "/api/dashboard/stats",
                    headers={"X-Organization-Context": "org-1"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["project_count"] == 3
        finally:
            app.dependency_overrides.clear()

    def test_exception_returns_defaults(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", side_effect=Exception("DB error")):
                mock_cache.get.return_value = None
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                data = resp.json()
                assert data["project_count"] == 0
                assert data["task_count"] == 0
        finally:
            app.dependency_overrides.clear()
