"""
Unit tests for routers/evaluations/status.py to increase coverage.
Tests evaluation status, SSE streaming, evaluation types, and supported metrics.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user, require_superadmin


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
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# get_evaluation_status
# ---------------------------------------------------------------------------


class TestGetEvaluationStatus:
    def test_evaluation_not_found(self):
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

    def test_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        evaluation = Mock()
        evaluation.id = "eval-1"
        evaluation.project_id = "p-1"
        evaluation.status = "completed"
        evaluation.error_message = "Done"

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
                data = resp.json()
                assert data["id"] == "eval-1"
                assert data["status"] == "completed"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_evaluations (list all)
# ---------------------------------------------------------------------------


class TestGetEvaluations:
    def test_empty_list(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=None):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_results(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"bleu": 0.8}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.status = "completed"
        eval_run.eval_metadata = {"key": "value"}
        eval_run.samples_evaluated = 10

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=None):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 1
                assert data[0]["id"] == "eval-1"
        finally:
            app.dependency_overrides.clear()

    def test_no_accessible_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=[]):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_org_scoped_results(self):
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
        eval_run.eval_metadata = {}
        eval_run.samples_evaluated = 5

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=["p-1"]):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_evaluation_types
# ---------------------------------------------------------------------------


class TestGetEvaluationTypes:
    def test_empty_types(self):
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
            resp = client.get("/api/evaluations/evaluation-types")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_types(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "bleu"
        eval_type.name = "BLEU Score"
        eval_type.description = "Bilingual Evaluation Understudy"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {"min": 0, "max": 1}
        eval_type.applicable_project_types = ["text_generation"]
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
            data = resp.json()
            assert len(data) == 1
            assert data[0]["id"] == "bleu"
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_category(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "bleu"
        eval_type.name = "BLEU"
        eval_type.description = "bleu"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {}
        eval_type.applicable_project_types = []
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_type]
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
                resp = client.get("/api/evaluations/evaluation-types?task_type_id=text_gen")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_evaluation_type (single)
# ---------------------------------------------------------------------------


class TestGetEvaluationType:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "bleu"
        eval_type.name = "BLEU"
        eval_type.description = "BLEU score"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {"min": 0, "max": 1}
        eval_type.applicable_project_types = []
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = eval_type
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types/bleu")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "bleu"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_supported_metrics
# ---------------------------------------------------------------------------


class TestDeriveEvaluationConfigs:
    """Test the _derive_evaluation_configs_from_selected_methods helper."""

    def test_empty_selected_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({})
        assert result == []

    def test_non_dict_selections(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({"field1": "not_a_dict"})
        assert result == []

    def test_with_string_metrics(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu", "rouge_l"],
                "field_mapping": {
                    "prediction_field": "pred_answer",
                    "reference_field": "ref_answer",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 2
        assert result[0]["metric"] == "bleu"
        assert result[0]["prediction_fields"] == ["pred_answer"]
        assert result[0]["reference_fields"] == ["ref_answer"]
        assert result[1]["metric"] == "rouge_l"

    def test_with_dict_metrics_and_parameters(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "text": {
                "automated": [
                    {"name": "llm_judge", "parameters": {"model": "gpt-4"}}
                ],
                "field_mapping": {
                    "prediction_field": "pred",
                    "reference_field": "ref",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["metric"] == "llm_judge"
        assert result[0]["metric_parameters"] == {"model": "gpt-4"}

    def test_with_no_field_mapping(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu"],
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        # Should use field_name as default for both pred and ref
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["answer"]

    def test_with_empty_metric_name(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": [{"name": ""}],
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result == []  # Empty name should be skipped
