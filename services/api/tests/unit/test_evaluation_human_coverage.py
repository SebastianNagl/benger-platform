"""
Unit tests for routers/evaluations/human.py to increase branch coverage.
Covers all human evaluation session endpoints.
"""

import uuid
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
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# Start Session
# ---------------------------------------------------------------------------


class TestStartHumanEvaluationSession:
    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=False):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "likert"},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "likert"},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_start_likert_session(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.count.return_value = 5
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={
                        "project_id": "p-1",
                        "session_type": "likert",
                        "dimensions": ["correctness", "completeness"],
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_type"] == "likert"
                assert data["total_items"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_start_preference_session(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.count.return_value = 3
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "preference"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_type"] == "preference"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Next Item
# ---------------------------------------------------------------------------


class TestGetNextEvaluationItem:
    def test_session_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/next-item?session_id=nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_session_not_active(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"
        session.status = "completed"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/next-item?session_id=s-1")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_no_more_items(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"
        session.status = "active"
        session.session_type = "likert"
        session.project_id = "p-1"
        session.items_evaluated = 5
        session.total_items = 5

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.distinct.return_value = mock_q

        call_count = [0]
        def mock_first():
            call_count[0] += 1
            if call_count[0] == 1:
                return session  # Session query
            return None  # No next task
        mock_q.first.side_effect = mock_first
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/next-item?session_id=s-1")
            assert resp.status_code == 404
            assert "completed" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    # test_next_item_preference_session removed: The mock DB was too shallow
    # to cover the preference session code path (querying PreferenceRanking
    # and Task models). The test originally accepted 500 to hide the crash.
    # The likert branch is tested properly in test_no_more_items above.


# ---------------------------------------------------------------------------
# Submit Likert Rating
# ---------------------------------------------------------------------------


class TestSubmitLikertRating:
    def test_session_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/human/likert",
                json={
                    "session_id": "nonexistent",
                    "task_id": "t-1",
                    "response_id": "r-1",
                    "ratings": {"correctness": 4},
                },
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_submit_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"
        session.session_type = "likert"
        session.items_evaluated = 0
        session.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/human/likert",
                json={
                    "session_id": "s-1",
                    "task_id": "t-1",
                    "response_id": "r-1",
                    "ratings": {"correctness": 4, "completeness": 5},
                    "comments": {"correctness": "Good!"},
                    "time_spent_seconds": 30,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["items_evaluated"] == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Submit Preference Ranking
# ---------------------------------------------------------------------------


class TestSubmitPreferenceRanking:
    def test_session_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/human/preference",
                json={
                    "session_id": "nonexistent",
                    "task_id": "t-1",
                    "response_a_id": "ra",
                    "response_b_id": "rb",
                    "winner": "a",
                },
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_submit_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"
        session.session_type = "preference"
        session.items_evaluated = 0
        session.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/human/preference",
                json={
                    "session_id": "s-1",
                    "task_id": "t-1",
                    "response_a_id": "ra",
                    "response_b_id": "rb",
                    "winner": "a",
                    "confidence": 0.9,
                    "reasoning": "Response A was more complete",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["items_evaluated"] == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Session Progress
# ---------------------------------------------------------------------------


class TestSessionProgress:
    def test_session_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/session/nonexistent/progress")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "other-user"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/session/s-1/progress")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_progress_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"
        session.project_id = "p-1"
        session.items_evaluated = 3
        session.total_items = 10
        session.status = "active"
        session.session_type = "likert"
        session.created_at = datetime.now(timezone.utc)
        session.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/session/s-1/progress")
            assert resp.status_code == 200
            data = resp.json()
            assert data["items_evaluated"] == 3
            assert data["progress_percentage"] == 30.0
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Sessions for Project
# ---------------------------------------------------------------------------


class TestGetSessionsForProject:
    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.human.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/human/sessions/p-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_returns_sessions(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.project_id = "p-1"
        session.evaluator_id = "user-123"
        session.session_type = "likert"
        session.items_evaluated = 5
        session.total_items = 10
        session.status = "active"
        session.session_config = {}
        session.created_at = datetime.now(timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [session]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.human.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/human/sessions/p-1")
                assert resp.status_code == 200
                assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Human Evaluation Config
# ---------------------------------------------------------------------------


class TestGetHumanEvaluationConfig:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/human/config/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_evaluation_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.human.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/human/config/p-1")
                assert resp.status_code == 200
                assert resp.json()["human_methods"] == {}
        finally:
            app.dependency_overrides.clear()

    def test_with_human_methods(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {
            "selected_methods": {
                "answer": {
                    "human": [
                        {"name": "likert_scale", "parameters": {"dimensions": ["correctness"]}}
                    ]
                }
            }
        }

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.human.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/human/config/p-1")
                assert resp.status_code == 200
                data = resp.json()
                assert "answer" in data["human_methods"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Delete Session
# ---------------------------------------------------------------------------


class TestDeleteHumanEvaluationSession:
    def test_session_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/evaluations/human/session/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "other-user"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_q.delete.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/evaluations/human/session/s-1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_delete_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        session = Mock()
        session.id = "s-1"
        session.evaluator_id = "user-123"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = session
        mock_q.delete.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/evaluations/human/session/s-1")
            assert resp.status_code == 200
            assert "deleted" in resp.json()["message"].lower()
        finally:
            app.dependency_overrides.clear()
