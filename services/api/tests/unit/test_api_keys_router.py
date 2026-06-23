"""
Tests for API keys router.

Targets: routers/api_keys.py lines 38-75, 86-89, 99-104, 117-147, 162-195, 210-263

The router was migrated to the async DB lane (`Depends(get_async_db)` + async
twins on `user_api_key_service`). DB-touching tests use the real
`async_test_client` / `async_test_db` fixtures and patch the specific async
twins with `AsyncMock`. Validate-only `/test` and 400-before-DB paths never
reach the DB, so those keep the lightweight TestClient + require_user override.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User


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


def _seed_user(db_session, user_id="ak-user"):
    user = User(
        id=user_id,
        username=f"akuser-{user_id}",
        email=f"{user_id}@test.com",
        name="AK User",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    return user


class TestApiKeysRouter:
    """Test user API key management endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="ak-user",
            username="akuser",
            email="ak@test.com",
            name="AK User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    # ---- 400-before-DB paths (validate-only / no DB) — unchanged ----------

    def test_set_api_key_missing_key(self, client, mock_user):
        """Test setting API key without providing the key."""
        app.dependency_overrides[require_user] = lambda: mock_user
        try:
            response = client.post(
                "/api/users/api-keys/openai",
                json={},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "api_key is required" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_set_api_key_invalid_provider(self, client, mock_user):
        """Test setting API key for unsupported provider."""
        app.dependency_overrides[require_user] = lambda: mock_user
        try:
            response = client.post(
                "/api/users/api-keys/invalid_provider",
                json={"api_key": "test-key"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Unsupported provider" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    # ---- DB-touching paths (async lane) ----------------------------------

    @pytest.mark.asyncio
    async def test_set_api_key_success(self, async_test_client, async_test_db):
        """Test setting API key successfully."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=True)), \
             patch("routers.api_keys.user_api_key_service.set_user_api_key_async",
                   new=AsyncMock(return_value=True)):
            response = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "sk-test-key-123"},
            )
        assert response.status_code == status.HTTP_200_OK
        assert "successfully" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_set_api_key_failure(self, async_test_client, async_test_db):
        """Test setting API key when storage fails."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=True)), \
             patch("routers.api_keys.user_api_key_service.set_user_api_key_async",
                   new=AsyncMock(return_value=False)):
            response = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "sk-test-key-123"},
            )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_get_api_key_status(self, async_test_client, async_test_db):
        """Test getting API key status."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_status_async",
                   new=AsyncMock(return_value={"openai": True})), \
             patch("routers.api_keys.user_api_key_service.get_user_available_providers_async",
                   new=AsyncMock(return_value=["openai"])):
            response = await async_test_client.get("/api/users/api-keys/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "api_key_status" in data
        assert "available_providers" in data

    @pytest.mark.asyncio
    async def test_remove_api_key_success(self, async_test_client, async_test_db):
        """Test removing API key."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.remove_user_api_key_async",
                   new=AsyncMock(return_value=True)):
            response = await async_test_client.delete("/api/users/api-keys/openai")
        assert response.status_code == status.HTTP_200_OK
        assert "removed" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_remove_api_key_failure(self, async_test_client, async_test_db):
        """Test removing API key when it fails."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.remove_user_api_key_async",
                   new=AsyncMock(return_value=False)):
            response = await async_test_client.delete("/api/users/api-keys/openai")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---- /test (validate-only, no DB) — unchanged ------------------------

    def test_test_api_key_success(self, client, mock_user):
        """Test testing API key successfully."""
        app.dependency_overrides[require_user] = lambda: mock_user
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.validate_api_key = AsyncMock(
                return_value=(True, "Connection successful", None)
            )

            try:
                response = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "sk-test"},
                )
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["status"] == "success"
            finally:
                app.dependency_overrides.clear()

    def test_test_api_key_invalid(self, client, mock_user):
        """Test testing invalid API key."""
        app.dependency_overrides[require_user] = lambda: mock_user
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.validate_api_key = AsyncMock(
                return_value=(False, "Invalid key", "auth_error")
            )

            try:
                response = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "invalid"},
                )
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["status"] == "error"
            finally:
                app.dependency_overrides.clear()

    def test_test_api_key_missing(self, client, mock_user):
        """Test testing without API key."""
        app.dependency_overrides[require_user] = lambda: mock_user
        try:
            response = client.post(
                "/api/users/api-keys/openai/test",
                json={},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_test_api_key_invalid_provider(self, client, mock_user):
        """Test testing with invalid provider."""
        app.dependency_overrides[require_user] = lambda: mock_user
        try:
            response = client.post(
                "/api/users/api-keys/invalid/test",
                json={"api_key": "test"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_test_api_key_exception(self, client, mock_user):
        """Test testing API key with exception."""
        app.dependency_overrides[require_user] = lambda: mock_user
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.validate_api_key = AsyncMock(side_effect=Exception("Network error"))

            try:
                response = client.post(
                    "/api/users/api-keys/openai/test",
                    json={"api_key": "sk-test"},
                )
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["status"] == "error"
            finally:
                app.dependency_overrides.clear()

    # ---- /test-saved (async DB lookup of saved key) ----------------------

    @pytest.mark.asyncio
    async def test_test_saved_api_key_success(self, async_test_client, async_test_db):
        """Test testing saved API key."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_async",
                   new=AsyncMock(return_value="sk-saved-key")), \
             patch("routers.api_keys.user_api_key_service.validate_api_key",
                   new=AsyncMock(return_value=(True, "Connected", None))):
            response = await async_test_client.post(
                "/api/users/api-keys/openai/test-saved"
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "success"

    @pytest.mark.asyncio
    async def test_test_saved_api_key_not_found(self, async_test_client, async_test_db):
        """Test testing saved API key when not found."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_api_key_async",
                   new=AsyncMock(return_value=None)):
            response = await async_test_client.post(
                "/api/users/api-keys/openai/test-saved"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_test_saved_api_key_invalid_provider(self, client, mock_user):
        """Test testing saved key with invalid provider (400 before DB)."""
        app.dependency_overrides[require_user] = lambda: mock_user
        try:
            response = client.post("/api/users/api-keys/invalid/test-saved")
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    # ---- available-models (async select over llm_models) -----------------

    @pytest.mark.asyncio
    async def test_get_available_models(self, async_test_client, async_test_db):
        """Test getting available models for user (no matching providers)."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch("routers.api_keys.user_api_key_service.get_user_available_providers_async",
                   new=AsyncMock(return_value=["openai"])):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_available_models_with_org_context(
        self, async_test_client, async_test_db
    ):
        """Test getting available models with org context."""
        user = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch(
                 "services.org_api_key_service.org_api_key_service."
                 "get_available_providers_for_context_async",
                 new=AsyncMock(return_value=["openai"]),
             ):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": "org-123"},
            )
        assert response.status_code == status.HTTP_200_OK
