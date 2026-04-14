"""
Unit tests for routers/tasks.py (global tasks) to increase branch coverage.
Covers list_all_tasks, bulk_assign, bulk_update_status, export_tasks.
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
    mock_q.join.return_value = mock_q
    mock_q.outerjoin.return_value = mock_q
    mock_q.options.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.subquery.return_value = MagicMock()
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# List All Tasks
# ---------------------------------------------------------------------------


class TestListAllTasks:
    def test_empty_results(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.get("/api/data/")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 0
                assert data["items"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_project_filter_no_access(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-2"]):
                resp = client.get("/api/data/?project_ids=p-1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_with_status_filters(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                for status_filter in ["completed", "incomplete", "in_progress", "all"]:
                    resp = client.get(f"/api/data/?status={status_filter}")
                    assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_with_search_and_date_filters(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.get(
                    "/api/data/?search=test&assigned_to=user-1"
                    "&date_from=2025-01-01T00:00:00&date_to=2025-12-31T23:59:59"
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_with_sort_options(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.get("/api/data/?sort_by=created_at&sort_order=asc")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_with_invalid_sort_field(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.get("/api/data/?sort_by=nonexistent_field")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_user_accessible_projects
# ---------------------------------------------------------------------------


class TestGetUserAccessibleProjects:
    def test_superadmin_gets_all(self):
        from routers.tasks import get_user_accessible_projects

        mock_db = _mock_db()
        p1 = Mock()
        p1.id = "p-1"
        p2 = Mock()
        p2.id = "p-2"

        mock_q = MagicMock()
        mock_q.all.return_value = [p1, p2]
        mock_db.query.return_value = mock_q

        user = _make_user(is_superadmin=True)
        result = get_user_accessible_projects(mock_db, user)
        assert "p-1" in result
        assert "p-2" in result

    def test_regular_user_scoped(self):
        from routers.tasks import get_user_accessible_projects

        mock_db = _mock_db()
        user = _make_user(is_superadmin=False)

        p1 = Mock()
        p1.id = "p-1"
        p1.project_id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.subquery.return_value = MagicMock()
        mock_q.all.return_value = [p1]
        mock_db.query.return_value = mock_q

        result = get_user_accessible_projects(mock_db, user)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Bulk Assign
# ---------------------------------------------------------------------------


class TestBulkAssign:
    def test_no_access_to_some_tasks(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        task = Mock()
        task.id = "t-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]  # Only 1 task found out of 2 requested
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/bulk-assign?user_id=assignee-1",
                    json=["t-1", "t-2"],
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_bulk_assign_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        task = Mock()
        task.id = "t-1"
        task.assigned_to = None
        task.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/bulk-assign?user_id=assignee-1",
                    json=["t-1"],
                )
                assert resp.status_code == 200
                assert "Successfully assigned" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Bulk Update Status
# ---------------------------------------------------------------------------


class TestBulkUpdateStatus:
    def test_no_access_to_some_tasks(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/bulk-update-status?is_labeled=true",
                    json=["t-1"],
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_bulk_update_complete(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        task = Mock()
        task.id = "t-1"
        task.is_labeled = False
        task.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/bulk-update-status?is_labeled=true",
                    json=["t-1"],
                )
                assert resp.status_code == 200
                assert "completed" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()

    def test_bulk_update_incomplete(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        task = Mock()
        task.id = "t-1"
        task.is_labeled = True
        task.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/bulk-update-status?is_labeled=false",
                    json=["t-1"],
                )
                assert resp.status_code == 200
                assert "incomplete" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Export Tasks
# ---------------------------------------------------------------------------


class TestExportTasks:
    def test_export_json(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.title = "Test Project"

        task = Mock()
        task.id = "t-1"
        task.project_id = "p-1"
        task.project = project
        task.data = {"text": "sample"}
        task.meta = {}
        task.is_labeled = False
        task.assigned_to = None
        task.created_at = datetime.now(timezone.utc)
        task.updated_at = None

        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post("/api/data/export?format=json")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_export_csv(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.title = "Test Project"

        task = Mock()
        task.id = "t-1"
        task.project_id = "p-1"
        task.project = project
        task.data = {"text": "sample"}
        task.meta = {}
        task.is_labeled = True
        task.assigned_to = "user-1"
        task.created_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)

        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [task]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post("/api/data/export?format=csv")
                assert resp.status_code == 200
                assert "text/csv" in resp.headers.get("content-type", "")
        finally:
            app.dependency_overrides.clear()

    def test_export_with_task_ids(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.tasks.get_user_accessible_projects", return_value=["p-1"]):
                resp = client.post(
                    "/api/data/export?format=json",
                    json=["t-1", "t-2"],
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
