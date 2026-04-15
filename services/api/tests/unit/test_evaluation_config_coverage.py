"""
Unit tests for routers/evaluations/config.py to increase branch coverage.
Covers evaluation config CRUD, detect answer types, field types, and helper functions.
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
from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods


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
# _derive_evaluation_configs_from_selected_methods
# ---------------------------------------------------------------------------


class TestDeriveEvaluationConfigs:
    def test_empty_methods(self):
        result = _derive_evaluation_configs_from_selected_methods({})
        assert result == []

    def test_non_dict_selections(self):
        result = _derive_evaluation_configs_from_selected_methods({"field": "not_a_dict"})
        assert result == []

    def test_string_metrics(self):
        selected = {
            "answer": {
                "automated": ["rouge_l", "bleu"],
                "field_mapping": {
                    "prediction_field": "answer",
                    "reference_field": "gold",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 2
        assert result[0]["metric"] == "rouge_l"
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["gold"]

    def test_dict_metrics_with_parameters(self):
        selected = {
            "answer": {
                "automated": [
                    {"name": "llm_judge_custom", "parameters": {"criteria": "accuracy"}},
                    {"name": ""},  # empty name, should be skipped
                ],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["metric"] == "llm_judge_custom"
        assert "metric_parameters" in result[0]

    def test_no_field_mapping(self):
        selected = {
            "answer": {
                "automated": ["rouge_l"],
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["answer"]


# ---------------------------------------------------------------------------
# Get Project Evaluation Config
# ---------------------------------------------------------------------------


class TestGetProjectEvaluationConfig:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/evaluation-config")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
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
            with patch("routers.evaluations.config.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = False
                resp = client.get("/api/evaluations/projects/p-1/evaluation-config")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_no_label_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None
        project.label_config = None
        project.label_config_version = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/projects/p-1/evaluation-config")
                assert resp.status_code == 200
                data = resp.json()
                assert data["detected_answer_types"] == []
        finally:
            app.dependency_overrides.clear()

    def test_existing_config_returned(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        existing_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {"answer": {"available_metrics": ["rouge_l"]}},
            "selected_methods": {},
            "label_config_version": "v1",
        }

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = existing_config
        project.label_config = "<View><TextArea name='answer'/></View>"
        project.label_config_version = "v1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/projects/p-1/evaluation-config")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()



# ---------------------------------------------------------------------------
# Update Project Evaluation Config
# ---------------------------------------------------------------------------


class TestUpdateProjectEvaluationConfig:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.put(
                "/api/evaluations/projects/nonexistent/evaluation-config",
                json={"selected_methods": {}},
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
        project.label_config_version = "v1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=False):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={"selected_methods": {}},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_invalid_field(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config_version = "v1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {
                            "nonexistent_field": {"automated": ["rouge_l"]}
                        },
                        "available_methods": {
                            "answer": {"available_metrics": ["rouge_l"], "available_human": []}
                        },
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()



# ---------------------------------------------------------------------------
# Detect Answer Types
# ---------------------------------------------------------------------------


class TestDetectAnswerTypes:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/detect-answer-types")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_label_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = None
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/detect-answer-types")
                assert resp.status_code == 200
                assert resp.json()["detected_types"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_label_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer'/></View>"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True), \
                 patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
                mock_gen.return_value = {
                    "detected_answer_types": [{"name": "answer", "type": "text"}],
                    "available_methods": {"answer": {"available_metrics": ["rouge_l"]}},
                }
                resp = client.get("/api/evaluations/projects/p-1/detect-answer-types")
                assert resp.status_code == 200
                assert len(resp.json()["detected_types"]) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Field Types for LLM Judge
# ---------------------------------------------------------------------------


class TestGetFieldTypes:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/field-types")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_label_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = None
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/field-types")
                assert resp.status_code == 200
                assert resp.json()["field_types"] == {}
        finally:
            app.dependency_overrides.clear()

    def test_with_field_types(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer'/></View>"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True), \
                 patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
                mock_gen.return_value = {
                    "available_methods": {
                        "answer": {
                            "type": "text",
                            "tag": "TextArea",
                            "llm_judge_criteria": ["correctness", "completeness"],
                        }
                    }
                }
                resp = client.get("/api/evaluations/projects/p-1/field-types")
                assert resp.status_code == 200
                data = resp.json()
                assert "answer" in data["field_types"]
                assert data["field_types"]["answer"]["type"] == "text"
        finally:
            app.dependency_overrides.clear()
