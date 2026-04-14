"""
Unit tests for routers/projects/members.py to increase coverage.
Tests list members, add member, remove member, and get annotators.
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
    mock_q.options.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_q.update.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


class TestListProjectMembers:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/projects/nonexistent/members")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=False):
                resp = client.get("/api/projects/p-1/members")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_returns_empty_members(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=True):
                resp = client.get("/api/projects/p-1/members")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()


class TestAddProjectMember:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/projects/nonexistent/members/user-2",
                json={"role": "ANNOTATOR"},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/projects/p-1/members/user-2",
                json={"role": "ANNOTATOR"},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_target_user_not_found(self):
        client = TestClient(app)
        user = _make_user()  # superadmin
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        call_count = [0]
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        def first_side():
            call_count[0] += 1
            if call_count[0] == 1:
                return project  # project query
            return None  # user query (and membership query)
        mock_q.first.side_effect = first_side
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/projects/p-1/members/nonexistent",
                json={"role": "ANNOTATOR"},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestRemoveProjectMember:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/projects/nonexistent/members/user-2")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_cannot_remove_creator(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-2"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/projects/p-1/members/user-2")
            assert resp.status_code == 400
            assert "creator" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/projects/p-1/members/user-2")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_user_not_member(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.created_by = "creator-id"
        project.member_count = 0

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_q.update.return_value = 0
        mock_q.count.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/projects/p-1/members/user-2")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_successful_remove(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.created_by = "creator-id"
        project.member_count = 1

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_q.update.return_value = 1  # 1 row affected
        mock_q.count.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/projects/p-1/members/user-2")
            assert resp.status_code == 200
            assert "removed" in resp.json()["message"].lower()
        finally:
            app.dependency_overrides.clear()


class TestGetProjectAnnotators:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/projects/nonexistent/annotators")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=False):
                resp = client.get("/api/projects/p-1/annotators")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_empty_annotators(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=True):
                resp = client.get("/api/projects/p-1/annotators")
                assert resp.status_code == 200
                data = resp.json()
                assert data["annotators"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_annotators(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        # Annotator results from the query
        annotator_result = Mock()
        annotator_result.user_id = "user-2"
        annotator_result.name = "Annotator"
        annotator_result.pseudonym = None
        annotator_result.use_pseudonym = False
        annotator_result.annotation_count = 15

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [annotator_result]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=True):
                resp = client.get("/api/projects/p-1/annotators")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["annotators"]) == 1
                assert data["annotators"][0]["name"] == "Annotator"
                assert data["annotators"][0]["count"] == 15
        finally:
            app.dependency_overrides.clear()

    def test_with_pseudonym(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        annotator_result = Mock()
        annotator_result.user_id = "user-2"
        annotator_result.name = "Real Name"
        annotator_result.pseudonym = "PseudoAnnotator"
        annotator_result.use_pseudonym = True
        annotator_result.annotation_count = 5

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [annotator_result]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.members.check_project_accessible", return_value=True):
                resp = client.get("/api/projects/p-1/annotators")
                assert resp.status_code == 200
                data = resp.json()
                assert data["annotators"][0]["name"] == "PseudoAnnotator"
        finally:
            app.dependency_overrides.clear()
