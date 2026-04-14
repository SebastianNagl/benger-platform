"""
Tests for API keys router.

Targets: routers/api_keys.py lines 38-75, 86-89, 99-104, 117-147, 162-195, 210-263
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


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

    def _setup(self, mock_user, mock_db=None):
        from database import get_db
        from auth_module.dependencies import require_user
        app.dependency_overrides[require_user] = lambda: mock_user
        if mock_db:
            app.dependency_overrides[get_db] = lambda: mock_db

    def test_set_api_key_missing_key(self, client, mock_user):
        """Test setting API key without providing the key."""
        self._setup(mock_user, Mock(spec=Session))
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
        self._setup(mock_user, Mock(spec=Session))
        try:
            response = client.post(
                "/api/users/api-keys/invalid_provider",
                json={"api_key": "test-key"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Unsupported provider" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_set_api_key_success(self, client, mock_user):
        """Test setting API key successfully."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.validate_api_key = AsyncMock(return_value=True)
            mock_svc.set_user_api_key.return_value = True

            try:
                response = client.post(
                    "/api/users/api-keys/openai",
                    json={"api_key": "sk-test-key-123"},
                )
                assert response.status_code == status.HTTP_200_OK
                assert "successfully" in response.json()["message"]
            finally:
                app.dependency_overrides.clear()

    def test_set_api_key_failure(self, client, mock_user):
        """Test setting API key when storage fails."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.validate_api_key = AsyncMock(return_value=True)
            mock_svc.set_user_api_key.return_value = False

            try:
                response = client.post(
                    "/api/users/api-keys/openai",
                    json={"api_key": "sk-test-key-123"},
                )
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_get_api_key_status(self, client, mock_user):
        """Test getting API key status."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.get_user_api_key_status.return_value = {"openai": True}
            mock_svc.get_user_available_providers.return_value = ["openai"]

            try:
                response = client.get("/api/users/api-keys/status")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "api_key_status" in data
                assert "available_providers" in data
            finally:
                app.dependency_overrides.clear()

    def test_remove_api_key_success(self, client, mock_user):
        """Test removing API key."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.remove_user_api_key.return_value = True

            try:
                response = client.delete("/api/users/api-keys/openai")
                assert response.status_code == status.HTTP_200_OK
                assert "removed" in response.json()["message"]
            finally:
                app.dependency_overrides.clear()

    def test_remove_api_key_failure(self, client, mock_user):
        """Test removing API key when it fails."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.remove_user_api_key.return_value = False

            try:
                response = client.delete("/api/users/api-keys/openai")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_test_api_key_success(self, client, mock_user):
        """Test testing API key successfully."""
        self._setup(mock_user)
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
        self._setup(mock_user)
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
        self._setup(mock_user)
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
        self._setup(mock_user)
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
        self._setup(mock_user)
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

    def test_test_saved_api_key_success(self, client, mock_user):
        """Test testing saved API key."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.get_user_api_key.return_value = "sk-saved-key"
            mock_svc.validate_api_key = AsyncMock(
                return_value=(True, "Connected", None)
            )

            try:
                response = client.post("/api/users/api-keys/openai/test-saved")
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["status"] == "success"
            finally:
                app.dependency_overrides.clear()

    def test_test_saved_api_key_not_found(self, client, mock_user):
        """Test testing saved API key when not found."""
        self._setup(mock_user, Mock(spec=Session))
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.get_user_api_key.return_value = None

            try:
                response = client.post("/api/users/api-keys/openai/test-saved")
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_test_saved_api_key_invalid_provider(self, client, mock_user):
        """Test testing saved key with invalid provider."""
        self._setup(mock_user, Mock(spec=Session))
        try:
            response = client.post("/api/users/api-keys/invalid/test-saved")
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_get_available_models(self, client, mock_user):
        """Test getting available models for user."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        self._setup(mock_user, mock_db)
        with patch("routers.api_keys.user_api_key_service") as mock_svc:
            mock_svc.get_user_available_providers.return_value = ["openai"]

            try:
                response = client.get("/api/users/api-keys/available-models")
                assert response.status_code == status.HTTP_200_OK
                assert isinstance(response.json(), list)
            finally:
                app.dependency_overrides.clear()

    def test_get_available_models_with_org_context(self, client, mock_user):
        """Test getting available models with org context."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        self._setup(mock_user, mock_db)
        with patch("org_api_key_service.org_api_key_service") as mock_org_svc:
            mock_org_svc.get_available_providers_for_context.return_value = ["openai"]

            try:
                response = client.get(
                    "/api/users/api-keys/available-models",
                    headers={"X-Organization-Context": "org-123"},
                )
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()
