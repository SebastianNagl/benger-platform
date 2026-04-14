"""
Unit tests for routers/evaluations/metadata.py to increase coverage.
Tests evaluated models, configured methods, history, and significance endpoints.
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
    mock_q.distinct.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_q.scalar.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/evaluated-models
# ---------------------------------------------------------------------------


class TestGetEvaluatedModels:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/evaluated-models")
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_empty_models(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, list)
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/configured-methods
# ---------------------------------------------------------------------------


class TestGetConfiguredMethods:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/configured-methods")
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_no_config(self):
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_with_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu", "rouge_l"],
                    "human": [],
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/evaluation-history
# ---------------------------------------------------------------------------


class TestGetEvaluationHistory:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get(
                "/api/evaluations/projects/nonexistent/evaluation-history",
                params={"model_ids": ["gpt-4"], "metric": "bleu"},
            )
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history",
                    params={"model_ids": ["gpt-4"], "metric": "bleu"},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_empty_history(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history",
                    params={"model_ids": ["gpt-4"], "metric": "bleu"},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /significance/{project_id}
# ---------------------------------------------------------------------------


class TestGetSignificanceTests:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get(
                "/api/evaluations/significance/nonexistent",
                params={"model_ids": ["gpt-4", "claude"], "metrics": ["bleu"]},
            )
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
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get(
                    "/api/evaluations/significance/p-1",
                    params={"model_ids": ["gpt-4", "claude"], "metrics": ["bleu"]},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
