"""
Unit tests for routers/api_keys.py (user API key management) to increase branch coverage.
Covers set, get status, remove, test, test-saved, and available-models endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user


def _make_user(is_superadmin=False, user_id="user-123"):
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


class TestSetUserApiKey:
    def test_missing_api_key(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/users/api-keys/openai",
                json={},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_invalid_provider(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/users/api-keys/invalid_provider",
                json={"api_key": "sk-test123"},
            )
            assert resp.status_code == 400
            assert "Unsupported provider" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_set_key_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.validate_api_key = AsyncMock(return_value=True)
                mock_svc.set_user_api_key.return_value = True
                resp = client.post(
                    "/api/users/api-keys/openai",
                    json={"api_key": "sk-test123"},
                )
                assert resp.status_code == 200
                assert "successfully" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()

    def test_set_key_store_failure(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.validate_api_key = AsyncMock(return_value=True)
                mock_svc.set_user_api_key.return_value = False
                resp = client.post(
                    "/api/users/api-keys/openai",
                    json={"api_key": "sk-test123"},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestGetApiKeyStatus:
    def test_get_status(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.get_user_api_key_status.return_value = {"openai": True}
                mock_svc.get_user_available_providers.return_value = ["openai"]
                resp = client.get("/api/users/api-keys/status")
                assert resp.status_code == 200
                data = resp.json()
                assert "api_key_status" in data
                assert "available_providers" in data
        finally:
            app.dependency_overrides.clear()


class TestRemoveApiKey:
    def test_remove_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.remove_user_api_key.return_value = True
                resp = client.delete("/api/users/api-keys/openai")
                assert resp.status_code == 200
                assert "removed" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()

    def test_remove_failure(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.remove_user_api_key.return_value = False
                resp = client.delete("/api/users/api-keys/openai")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestTestApiKey:
    def test_missing_key(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = client.post(
                "/api/users/api-keys/openai/test",
                json={},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_invalid_provider(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = client.post(
                "/api/users/api-keys/invalid/test",
                json={"api_key": "sk-test"},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_valid_key(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.validate_api_key = AsyncMock(return_value=(True, "Valid", None))
                resp = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "sk-test"},
                )
                assert resp.status_code == 200
                assert resp.json()["status"] == "success"
        finally:
            app.dependency_overrides.clear()

    def test_invalid_key(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.validate_api_key = AsyncMock(return_value=(False, "Invalid", "auth_error"))
                resp = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "sk-bad"},
                )
                assert resp.status_code == 200
                assert resp.json()["status"] == "error"
        finally:
            app.dependency_overrides.clear()

    def test_exception(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.validate_api_key = AsyncMock(side_effect=Exception("Timeout"))
                resp = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "sk-test"},
                )
                assert resp.status_code == 200
                assert resp.json()["status"] == "error"
        finally:
            app.dependency_overrides.clear()


class TestTestSavedApiKey:
    def test_invalid_provider(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post("/api/users/api-keys/invalid/test-saved")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_no_saved_key(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.get_user_api_key.return_value = None
                resp = client.post("/api/users/api-keys/openai/test-saved")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_saved_key_valid(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.get_user_api_key.return_value = "sk-saved"
                mock_svc.validate_api_key = AsyncMock(return_value=(True, "Valid", None))
                resp = client.post("/api/users/api-keys/openai/test-saved")
                assert resp.status_code == 200
                assert resp.json()["status"] == "success"
        finally:
            app.dependency_overrides.clear()


class TestAvailableModels:
    def test_private_context(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        model = Mock()
        model.id = "gpt-4"
        model.name = "GPT-4"
        model.description = "OpenAI GPT-4"
        model.provider = "openai"
        model.model_type = "llm"
        model.capabilities = ["text"]
        model.config_schema = {}
        model.default_config = {}
        model.input_cost_per_million = 30.0
        model.output_cost_per_million = 60.0
        model.is_active = True
        model.parameter_constraints = None
        model.created_at = datetime.now(timezone.utc)
        model.updated_at = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [model]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.get_user_available_providers.return_value = ["openai"]
                resp = client.get("/api/users/api-keys/available-models")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 1
                assert data[0]["id"] == "gpt-4"
        finally:
            app.dependency_overrides.clear()

    def test_org_context(self):
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
            with patch("org_api_key_service.org_api_key_service") as mock_org_svc:
                mock_org_svc.get_available_providers_for_context.return_value = []
                resp = client.get(
                    "/api/users/api-keys/available-models",
                    headers={"X-Organization-Context": "org-1"},
                )
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_no_models_available(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        model = Mock()
        model.id = "gpt-4"
        model.provider = "openai"
        model.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [model]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.api_keys.user_api_key_service") as mock_svc:
                mock_svc.get_user_available_providers.return_value = []  # No providers
                resp = client.get("/api/users/api-keys/available-models")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()
