"""
Unit tests for routers/evaluations/multi_field.py to increase branch coverage.
Covers run evaluation, available fields, and project evaluation results endpoints.
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


# ---------------------------------------------------------------------------
# Run Evaluation
# ---------------------------------------------------------------------------


class TestRunEvaluation:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/run",
                json={
                    "project_id": "nonexistent",
                    "evaluation_configs": [
                        {
                            "id": "c1",
                            "metric": "rouge_l",
                            "prediction_fields": ["answer"],
                            "reference_fields": ["gold"],
                        }
                    ],
                },
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_configs(self):
        client = TestClient(app)
        user = _make_user()
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
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                with patch("routers.evaluations.multi_field.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [],
                        },
                    )
                    assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_no_enabled_configs(self):
        client = TestClient(app)
        user = _make_user()
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
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                with patch("routers.evaluations.multi_field.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [
                                {
                                    "id": "c1",
                                    "metric": "rouge_l",
                                    "prediction_fields": ["answer"],
                                    "reference_fields": ["gold"],
                                    "enabled": False,
                                }
                            ],
                        },
                    )
                    assert resp.status_code == 400
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
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = False
                with patch("routers.evaluations.multi_field.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [
                                {
                                    "id": "c1",
                                    "metric": "rouge_l",
                                    "prediction_fields": ["answer"],
                                    "reference_fields": ["gold"],
                                }
                            ],
                        },
                    )
                    assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Available Fields
# ---------------------------------------------------------------------------


class TestAvailableFields:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/available-fields")
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
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = False
                resp = client.get("/api/evaluations/projects/p-1/available-fields")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()



# ---------------------------------------------------------------------------
# Project Evaluation Results
# ---------------------------------------------------------------------------


class TestProjectEvaluationResults:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/run/results/project/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_with_results(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.model_id = "gpt-4"
        eval_run.status = "completed"
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.completed_at = datetime.now(timezone.utc)
        eval_run.samples_evaluated = 10
        eval_run.error_message = None
        eval_run.eval_metadata = {
            "evaluation_type": "evaluation",
            "evaluation_configs": [{"id": "c1", "metric": "rouge_l"}],
            "samples_passed": 8,
            "samples_failed": 2,
            "samples_skipped": 0,
        }
        eval_run.metrics = {
            "c1:answer:gold:rouge_l": 0.85,
        }

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval_run]
        mock_q.count.return_value = 5
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/run/results/project/p-1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total_count"] == 1
                assert data["evaluations"][0]["model_id"] == "gpt-4"
        finally:
            app.dependency_overrides.clear()

    def test_latest_only_false(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        eval1 = Mock()
        eval1.id = "eval-1"
        eval1.model_id = "gpt-4"
        eval1.status = "completed"
        eval1.created_at = datetime.now(timezone.utc)
        eval1.completed_at = None
        eval1.samples_evaluated = 5
        eval1.error_message = None
        eval1.eval_metadata = {"evaluation_type": "evaluation", "configs": []}
        eval1.metrics = {}

        eval2 = Mock()
        eval2.id = "eval-2"
        eval2.model_id = "claude-3"
        eval2.status = "completed"
        eval2.created_at = datetime.now(timezone.utc)
        eval2.completed_at = None
        eval2.samples_evaluated = 3
        eval2.error_message = None
        eval2.eval_metadata = {"evaluation_type": "evaluation"}
        eval2.metrics = {}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval1, eval2]
        mock_q.count.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/run/results/project/p-1?latest_only=false")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total_count"] == 2
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Evaluation Run Results
# ---------------------------------------------------------------------------


class TestGetEvaluationRunResults:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/run/results/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_evaluation_run(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.eval_metadata = {"evaluation_type": "generation"}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = eval_run
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/run/results/eval-1")
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.status = "completed"
        eval_run.eval_metadata = {
            "evaluation_type": "evaluation",
            "evaluation_configs": [],
            "samples_passed": 5,
            "samples_failed": 1,
            "samples_skipped": 0,
        }
        eval_run.metrics = {"c1:answer:gold:rouge_l": 0.85}
        eval_run.samples_evaluated = 6
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.completed_at = datetime.now(timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = eval_run
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/run/results/eval-1")
                assert resp.status_code == 200
                data = resp.json()
                assert "results_by_config" in data
        finally:
            app.dependency_overrides.clear()
