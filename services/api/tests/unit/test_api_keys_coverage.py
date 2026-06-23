"""
Unit tests for routers/api_keys.py (user API key management) to increase branch coverage.
Covers set, get status, remove, test, test-saved, and available-models endpoints.

The router runs on the async DB lane (`Depends(get_async_db)` + async twins on
`user_api_key_service`). DB-touching tests use the real `async_test_client` /
`async_test_db` fixtures and patch the specific async twins with `AsyncMock`.
Validate-only `/test` and 400-before-DB paths never reach the DB, so those keep
the lightweight TestClient + require_user override.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import LLMModel, User as DBUser


def _make_user(is_superadmin=False, user_id="user-123"):
    """Auth-layer user object for the require_user override (no DB row needed
    for endpoints that don't read the DB)."""
    return AuthUser(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _seed_user(db_session, user_id="user-123"):
    user = DBUser(
        id=user_id,
        username=f"testuser-{user_id}",
        email=f"{user_id}@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    return user


def _seed_model(db_session, model_id, provider, name=None):
    model = LLMModel(
        id=model_id,
        name=name or model_id,
        description=f"{provider} model",
        provider=provider,
        model_type="llm",
        capabilities=["text"],
        config_schema={},
        default_config={},
        input_cost_per_million=30.0,
        output_cost_per_million=60.0,
        parameter_constraints=None,
        recommended_parameters=None,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(model)
    return model


class TestSetUserApiKey:
    def test_missing_api_key(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
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
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = client.post(
                "/api/users/api-keys/invalid_provider",
                json={"api_key": "sk-test123"},
            )
            assert resp.status_code == 400
            assert "Unsupported provider" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_set_key_success(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=True)), \
             patch("routers.api_keys.user_api_key_service.set_user_api_key_async",
                   new=AsyncMock(return_value=True)):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "sk-test123"},
            )
        assert resp.status_code == 200
        assert "successfully" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_set_key_store_failure(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=True)), \
             patch("routers.api_keys.user_api_key_service.set_user_api_key_async",
                   new=AsyncMock(return_value=False)):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "sk-test123"},
            )
        assert resp.status_code == 500


class TestGetApiKeyStatus:
    @pytest.mark.asyncio
    async def test_get_status(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_status_async",
                   new=AsyncMock(return_value={"openai": True})), \
             patch("routers.api_keys.user_api_key_service.get_user_available_providers_async",
                   new=AsyncMock(return_value=["openai"])):
            resp = await async_test_client.get("/api/users/api-keys/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key_status" in data
        assert "available_providers" in data


class TestRemoveApiKey:
    @pytest.mark.asyncio
    async def test_remove_success(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.remove_user_api_key_async",
                   new=AsyncMock(return_value=True)):
            resp = await async_test_client.delete("/api/users/api-keys/openai")
        assert resp.status_code == 200
        assert "removed" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_remove_failure(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.remove_user_api_key_async",
                   new=AsyncMock(return_value=False)):
            resp = await async_test_client.delete("/api/users/api-keys/openai")
        assert resp.status_code == 500


class TestTestApiKey:
    """`/test` is validate-only (no DB) — keeps the lightweight TestClient."""

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
        """Validate-only 400 (provider rejected before the DB lookup)."""
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = client.post("/api/users/api-keys/invalid/test-saved")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_no_saved_key(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_async",
                   new=AsyncMock(return_value=None)):
            resp = await async_test_client.post("/api/users/api-keys/openai/test-saved")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_saved_key_valid(self, async_test_client, async_test_db):
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_async",
                   new=AsyncMock(return_value="sk-saved")), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=(True, "Valid", None))):
            resp = await async_test_client.post("/api/users/api-keys/openai/test-saved")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


class TestAvailableModels:
    @pytest.mark.asyncio
    async def test_private_context(self, async_test_client, async_test_db):
        """User with an openai key sees only the openai model."""
        user = _seed_user(async_test_db)
        _seed_model(async_test_db, "gpt-4", "openai", name="GPT-4")
        _seed_model(async_test_db, "claude-x", "anthropic", name="Claude")
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_available_providers_async",
                   new=AsyncMock(return_value=["openai"])):
            resp = await async_test_client.get("/api/users/api-keys/available-models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_org_context(self, async_test_client, async_test_db):
        """Org context with no providers yields no models."""
        user = _seed_user(async_test_db)
        _seed_model(async_test_db, "gpt-4", "openai", name="GPT-4")
        await async_test_db.flush()
        with _as_user(user), \
             patch(
                 "services.org_api_key_service.org_api_key_service."
                 "get_available_providers_for_context_async",
                 new=AsyncMock(return_value=[]),
             ):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": "org-1"},
            )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_no_models_available(self, async_test_client, async_test_db):
        """User with no providers sees no models even when models exist."""
        user = _seed_user(async_test_db)
        _seed_model(async_test_db, "gpt-4", "openai", name="GPT-4")
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_available_providers_async",
                   new=AsyncMock(return_value=[])):
            resp = await async_test_client.get("/api/users/api-keys/available-models")
        assert resp.status_code == 200
        assert resp.json() == []
