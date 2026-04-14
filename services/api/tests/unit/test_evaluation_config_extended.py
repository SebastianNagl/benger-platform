"""
Unit tests for routers/evaluations/config.py to increase coverage.
Tests evaluation config CRUD, answer type detection, and field types.
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
# get_project_evaluation_config
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

    def test_existing_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer'/></View>"
        project.label_config_version = "v1"
        project.evaluation_config = {
            "detected_answer_types": [{"name": "answer", "type": "text"}],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
        }

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

    def test_force_regenerate(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer' toName='text'/></View>"
        project.label_config_version = "v2"
        project.evaluation_config = {
            "label_config_version": "v1",
        }

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.auth_service") as mock_auth, \
                 patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
                mock_auth.check_project_access.return_value = True
                mock_gen.return_value = {
                    "detected_answer_types": [],
                    "available_methods": {},
                    "selected_methods": {},
                    "label_config_version": "v2",
                }
                resp = client.get("/api/evaluations/projects/p-1/evaluation-config?force_regenerate=true")
                assert resp.status_code == 200
                mock_gen.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    def test_lazy_migration_derive_configs(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer'/></View>"
        project.label_config_version = "v1"
        project.evaluation_config = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {
                "answer": {
                    "automated": ["bleu"],
                    "field_mapping": {"prediction_field": "pred", "reference_field": "ref"},
                }
            },
            "label_config_version": "v1",
        }

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.auth_service") as mock_auth, \
                 patch("sqlalchemy.orm.attributes.flag_modified"):
                mock_auth.check_project_access.return_value = True
                resp = client.get("/api/evaluations/projects/p-1/evaluation-config")
                assert resp.status_code == 200
                data = resp.json()
                assert "evaluation_configs" in data
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# update_project_evaluation_config
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

    def test_invalid_field_in_selected_methods(self):
        client = TestClient(app)
        user = _make_user()
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
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {"nonexistent_field": {}},
                        "available_methods": {"answer": {"available_metrics": ["bleu"], "available_human": []}},
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_invalid_metric(self):
        client = TestClient(app)
        user = _make_user()
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
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {
                            "answer": {
                                "automated": ["nonexistent_metric"],
                            }
                        },
                        "available_methods": {
                            "answer": {
                                "available_metrics": ["bleu"],
                                "available_human": [],
                            }
                        },
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_successful_update(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config_version = "v1"
        project.evaluation_config = {}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True), \
                 patch("sqlalchemy.orm.attributes.flag_modified"):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {
                            "answer": {"automated": ["bleu"]}
                        },
                        "available_methods": {
                            "answer": {
                                "available_metrics": ["bleu"],
                                "available_human": [],
                            }
                        },
                    },
                )
                assert resp.status_code == 200
                assert "message" in resp.json()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# detect_answer_types
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
                data = resp.json()
                assert data["detected_types"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_label_config(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View><TextArea name='answer' toName='text'/></View>"
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
                    "available_methods": {"answer": {"available_metrics": ["bleu"]}},
                }
                resp = client.get("/api/evaluations/projects/p-1/detect-answer-types")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["detected_types"]) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_field_types_for_llm_judge
# ---------------------------------------------------------------------------


class TestGetFieldTypesForLLMJudge:
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
                data = resp.json()
                assert data["field_types"] == {}
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

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config = "<View/>"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/projects/p-1/field-types")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
