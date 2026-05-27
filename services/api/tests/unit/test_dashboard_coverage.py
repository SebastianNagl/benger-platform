"""
Unit tests for routers/dashboard.py to increase branch coverage.
Covers dashboard stats with different org contexts and user types.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

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


class TestDashboardStats:
    def test_cached_stats(self):
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
                assert resp.json()["project_count"] == 5
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
                assert resp.json()["project_count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_all_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)
        mock_db = _mock_db()
        # New code path: dashboard reads via `read_dashboard_sum`. The
        # superadmin branch also fires a `SELECT COUNT(*) FROM projects`
        # scalar to backstop the precomputed project_count.
        mock_db.execute.return_value.scalar.return_value = 10

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=None), \
                 patch("routers.dashboard.read_dashboard_sum") as mock_sums, \
                 patch("routers.dashboard._live_evaluations_count", return_value=3):
                mock_cache.get.return_value = None
                mock_sums.return_value = {
                    "project_count": 10, "total_tasks": 200, "labeled_tasks": 100,
                    "annotations_count": 100, "generations_count": 5,
                    "response_generations_count": 8, "evaluation_pairs_count": 3,
                }
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 10
        finally:
            app.dependency_overrides.clear()

    def test_scoped_to_org(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", return_value=["p-1", "p-2"]), \
                 patch("routers.dashboard.read_dashboard_sum") as mock_sums, \
                 patch("routers.dashboard._live_evaluations_count", return_value=1):
                mock_cache.get.return_value = None
                mock_sums.return_value = {
                    "project_count": 3, "total_tasks": 50, "labeled_tasks": 30,
                    "annotations_count": 20, "generations_count": 2,
                    "response_generations_count": 3, "evaluation_pairs_count": 1,
                }
                resp = client.get(
                    "/api/dashboard/stats",
                    headers={"X-Organization-Context": "org-1"},
                )
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 3
        finally:
            app.dependency_overrides.clear()

    def test_db_error_returns_defaults(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.dashboard.cache") as mock_cache, \
                 patch("routers.dashboard.get_accessible_project_ids", side_effect=Exception("DB down")):
                mock_cache.get.return_value = None
                resp = client.get("/api/dashboard/stats")
                assert resp.status_code == 200
                assert resp.json()["project_count"] == 0
        finally:
            app.dependency_overrides.clear()
