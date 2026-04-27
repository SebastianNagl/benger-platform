"""
Unit tests for routers/evaluations/results.py to increase coverage.
Tests score extraction, per-sample results, export, and comparison endpoints.
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
    mock_q.order_by.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# _extract_primary_score helper
# ---------------------------------------------------------------------------


class TestExtractPrimaryScore:
    def test_none_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score({}) is None

    def test_llm_judge_custom(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 0.8}
        assert _extract_primary_score(metrics) == 0.8

    def test_score_key(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0.9}
        assert _extract_primary_score(metrics) == 0.9

    def test_overall_score_key(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"overall_score": 0.85}
        assert _extract_primary_score(metrics) == 0.85

    def test_llm_judge_arbitrary(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_accuracy": 0.7}
        assert _extract_primary_score(metrics) == 0.7

    def test_ignores_non_numeric(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": "not_a_number"}
        result = _extract_primary_score(metrics)
        assert result is None or isinstance(result, (int, float))

    def test_priority_order(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_custom": 0.5,
            "score": 0.3,
        }
        assert _extract_primary_score(metrics) == 0.5


# ---------------------------------------------------------------------------
# GET /evaluations/results/{project_id} - list evaluation results
# ---------------------------------------------------------------------------


class TestGetProjectEvaluationResults:
    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/results/p-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_returns_ok_for_accessible_project(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/results/p-1")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /evaluations/{evaluation_id}/samples
# ---------------------------------------------------------------------------


class TestGetEvaluationSamples:
    def test_evaluation_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/nonexistent/samples")
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

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = evaluation
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/eval-1/samples")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /evaluations/{evaluation_id}/confusion-matrix
# ---------------------------------------------------------------------------


class TestGetMetricDistribution:
    def test_evaluation_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/nonexistent/metrics/bleu/distribution")
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

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = evaluation
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/eval-1/metrics/bleu/distribution")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /evaluations/export/{project_id}
# ---------------------------------------------------------------------------


class TestExportEvaluations:
    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=False):
                resp = client.post("/api/evaluations/export/p-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /{evaluation_id}/results/by-task-model
# ---------------------------------------------------------------------------


class TestResultsByTaskModel:
    def test_evaluation_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/nonexistent/results/by-task-model")
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

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = evaluation
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.results.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/eval-1/results/by-task-model")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
