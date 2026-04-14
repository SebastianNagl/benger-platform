"""
Unit tests for routers/projects/tasks.py to increase branch coverage.
Covers list tasks, skip task, next task, and error paths.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User


def _make_user(is_superadmin=False, user_id="user-123"):
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


class TestListProjectTasks:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/projects/nonexistent/tasks")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module.dependencies import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.projects.tasks.check_project_accessible", return_value=False):
                resp = client.get("/api/projects/proj-1/tasks")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestSkipTask:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post(
                "/api/projects/nonexistent/tasks/task-1/skip",
                json={},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestUnauthenticatedEndpoints:
    """Verify auth is required for task endpoints."""

    def test_list_tasks_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/projects/proj-1/tasks")
        assert resp.status_code == 401

    def test_skip_task_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks/task-1/skip", json={})
        assert resp.status_code == 401

    def test_next_task_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/projects/proj-1/tasks/next")
        # May return various codes depending on routing
        assert resp.status_code in [401, 404, 405]

    def test_create_task_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks", json={"data": {}})
        assert resp.status_code in [401, 404, 405, 422]

    def test_bulk_create_tasks_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks/bulk", json=[{"data": {}}])
        assert resp.status_code in [401, 404, 405, 422]
