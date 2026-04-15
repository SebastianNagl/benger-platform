"""
Unit tests for routers/evaluations/metadata.py to increase branch coverage.
Covers evaluated-models, configured-methods, evaluation-history, significance,
and statistics endpoints.
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
    mock_q.group_by.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


def _setup_overrides(user=None, mock_db=None):
    if user is None:
        user = _make_user()
    if mock_db is None:
        mock_db = _mock_db()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db
    return user, mock_db


# ---------------------------------------------------------------------------
# Evaluated Models
# ---------------------------------------------------------------------------


class TestEvaluatedModels:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/evaluated-models")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_project_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_no_models_returns_empty(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_q.order_by.return_value = mock_q
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()



# ---------------------------------------------------------------------------
# Configured Methods
# ---------------------------------------------------------------------------


class TestConfiguredMethods:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/configured-methods")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_eval_config(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                assert resp.json()["fields"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_selected_methods(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {
            "selected_methods": {
                "answer": {
                    "automated": ["rouge_l", {"name": "llm_judge_custom", "parameters": {"criteria": "accuracy"}}],
                    "human": ["likert_scale"],
                    "field_mapping": {"prediction_field": "answer", "reference_field": "answer"},
                }
            },
            "available_methods": {
                "answer": {"type": "text", "to_name": "answer"}
            },
        }

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.status = "completed"
        eval_run.metrics = {"rouge_l": 0.75}
        eval_run.completed_at = datetime.now(timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["fields"]) == 1
                assert data["fields"][0]["field_name"] == "answer"
        finally:
            app.dependency_overrides.clear()

    def test_empty_selected_methods(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {"selected_methods": {}}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                assert resp.json()["fields"] == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Evaluation History
# ---------------------------------------------------------------------------


class TestEvaluationHistory:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get(
                "/api/evaluations/projects/nonexistent/evaluation-history?model_ids=m1&metric=accuracy"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history?model_ids=m1&metric=accuracy"
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_with_results(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"accuracy": 0.85}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.eval_metadata = {}
        eval_run.samples_evaluated = 10

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history?model_ids=gpt-4&metric=accuracy"
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["metric"] == "accuracy"
                assert len(data["data"]) == 1
        finally:
            app.dependency_overrides.clear()

    def test_with_date_filters(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history"
                    "?model_ids=gpt-4&metric=accuracy"
                    "&start_date=2025-01-01T00:00:00"
                    "&end_date=2025-12-31T23:59:59"
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_with_ci_in_metadata(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"accuracy": 0.85}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.eval_metadata = {
            "confidence_intervals": {
                "accuracy": {"lower": 0.8, "upper": 0.9}
            }
        }
        eval_run.samples_evaluated = 10

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history?model_ids=gpt-4&metric=accuracy"
                )
                assert resp.status_code == 200
                data = resp.json()["data"][0]
                assert data["ci_lower"] == 0.8
                assert data["ci_upper"] == 0.9
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Significance Tests
# ---------------------------------------------------------------------------


class TestSignificanceTests:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get(
                "/api/evaluations/significance/nonexistent?model_ids=m1&model_ids=m2&metrics=accuracy"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_scipy_not_available(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True), \
                 patch("routers.leaderboards.STATS_AVAILABLE", False):
                resp = client.get(
                    "/api/evaluations/significance/p-1?model_ids=m1&model_ids=m2&metrics=accuracy"
                )
                assert resp.status_code == 200
                assert "not available" in resp.json().get("message", "")
        finally:
            app.dependency_overrides.clear()

    def test_insufficient_data(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True), \
                 patch("routers.leaderboards.STATS_AVAILABLE", True):
                resp = client.get(
                    "/api/evaluations/significance/p-1?model_ids=m1&model_ids=m2&metrics=accuracy"
                )
                assert resp.status_code == 200
                comps = resp.json()["comparisons"]
                assert len(comps) == 1
                assert comps[0]["significant"] is False
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.post(
                "/api/evaluations/projects/nonexistent/statistics",
                json={"metrics": ["accuracy"]},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_evaluations(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.post(
                    "/api/evaluations/projects/p-1/statistics",
                    json={"metrics": ["accuracy"]},
                )
                assert resp.status_code == 404
                assert "No completed evaluations" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()




    def test_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.post(
                    "/api/evaluations/projects/p-1/statistics",
                    json={"metrics": ["accuracy"]},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
