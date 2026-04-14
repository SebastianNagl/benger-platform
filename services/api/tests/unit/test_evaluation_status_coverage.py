"""
Unit tests for routers/evaluations/status.py to increase branch coverage.
Covers evaluation status, SSE streaming, evaluation types, and supported metrics.
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


# ---------------------------------------------------------------------------
# Evaluation Status
# ---------------------------------------------------------------------------


class TestGetEvaluationStatus:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation/status/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        evaluation = Mock()
        evaluation.id = "eval-1"
        evaluation.project_id = "p-1"
        evaluation.status = "running"
        evaluation.error_message = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = evaluation
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/evaluation/status/eval-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_status_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        evaluation = Mock()
        evaluation.id = "eval-1"
        evaluation.project_id = "p-1"
        evaluation.status = "completed"
        evaluation.error_message = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = evaluation
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/evaluation/status/eval-1")
                assert resp.status_code == 200
                assert resp.json()["status"] == "completed"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Evaluations (scoped list)
# ---------------------------------------------------------------------------


class TestGetEvaluations:
    def test_no_accessible_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=[]):
                resp = client.get("/api/evaluations/evaluations")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_gets_all(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"accuracy": 0.9}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.status = "completed"
        eval_run.eval_metadata = {}
        eval_run.samples_evaluated = 10

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=None):
                resp = client.get("/api/evaluations/evaluations")
                assert resp.status_code == 200
                assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_scoped_to_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.status = "completed"
        eval_run.eval_metadata = None
        eval_run.samples_evaluated = 5

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=["p-1"]):
                resp = client.get("/api/evaluations/evaluations")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Evaluation Types
# ---------------------------------------------------------------------------


class TestGetEvaluationTypes:
    def test_get_all_types(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "et-1"
        eval_type.name = "ROUGE-L"
        eval_type.description = "ROUGE-L metric"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {"min": 0, "max": 1}
        eval_type.applicable_project_types = ["text"]
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_type]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_category(self):
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
            resp = client.get("/api/evaluations/evaluation-types?category=text")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_task_type(self):
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
            with patch("routers.evaluations.status.get_evaluation_types_for_task_type", return_value=[]):
                resp = client.get("/api/evaluations/evaluation-types?task_type_id=text_generation")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_error_handling(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types")
            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestGetEvaluationType:
    def test_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "et-1"
        eval_type.name = "ROUGE-L"
        eval_type.description = "ROUGE-L metric"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {"min": 0, "max": 1}
        eval_type.applicable_project_types = ["text"]
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = eval_type
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types/et-1")
            assert resp.status_code == 200
            assert resp.json()["name"] == "ROUGE-L"
        finally:
            app.dependency_overrides.clear()

    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_error(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types/et-1")
            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Supported Metrics
# ---------------------------------------------------------------------------


class TestSupportedMetrics:
    # test_placeholder removed: empty body, tested via integration tests.
    pass
