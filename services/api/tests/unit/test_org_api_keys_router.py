"""
Tests for org API keys router.

Targets: routers/org_api_keys.py lines 24-27, 35-49, 57-59, 75-81, 93-114, 128-136, 151-179, 194-216, 233-237, 248-270, 286-316
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestOrgApiKeysHelpers:
    """Test helper functions for org API key management."""

    def test_require_org_admin_denied(self):
        from routers.org_api_keys import _require_org_admin
        from fastapi import HTTPException

        mock_user = Mock()
        mock_db = Mock(spec=Session)

        with patch("routers.organizations.can_manage_organization") as mock_can:
            mock_can.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                _require_org_admin(mock_user, "org-1", mock_db)
            assert exc_info.value.status_code == 403

    def test_require_org_member_superadmin(self):
        from routers.org_api_keys import _require_org_member
        mock_user = Mock()
        mock_user.is_superadmin = True
        mock_db = Mock(spec=Session)
        # Should not raise
        _require_org_member(mock_user, "org-1", mock_db)

    def test_require_org_member_denied(self):
        from routers.org_api_keys import _require_org_member
        from fastapi import HTTPException

        mock_user = Mock()
        mock_user.is_superadmin = False
        mock_user.id = "user-1"

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            _require_org_member(mock_user, "org-1", mock_db)
        assert exc_info.value.status_code == 403

    def test_require_org_exists_not_found(self):
        from routers.org_api_keys import _require_org_exists
        from fastapi import HTTPException

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            _require_org_exists("nonexistent", mock_db)
        assert exc_info.value.status_code == 404


class TestOrgApiKeysEndpoints:
    """Test org API key management endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="org-ak-admin",
            username="orgakadmin",
            email="orgak@test.com",
            name="Org AK Admin",
            hashed_password="hashed",
            is_superadmin=True,
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

    def _mock_db_with_org(self):
        """Return mock_db that finds an organization."""
        mock_db = Mock(spec=Session)
        mock_org = Mock()
        mock_org.id = "org-1"
        mock_org.settings = {}

        # query().filter().first() returns the org
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_org
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        return mock_db, mock_org

    def test_get_org_api_key_status(self, client, mock_superadmin):
        """Test getting org API key status."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.get_org_api_key_status.return_value = {"openai": True}
            mock_svc.get_org_available_providers.return_value = ["openai"]

            try:
                response = client.get("/api/organizations/org-1/api-keys/status")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "api_key_status" in data
            finally:
                app.dependency_overrides.clear()

    def test_set_org_api_key_success(self, client, mock_superadmin):
        """Test setting org API key."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.SUPPORTED_PROVIDERS = ["openai", "anthropic", "google"]
            mock_svc.set_org_api_key.return_value = True

            try:
                response = client.post(
                    "/api/organizations/org-1/api-keys/openai",
                    json={"api_key": "sk-test"},
                )
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_set_org_api_key_missing(self, client, mock_superadmin):
        """Test setting org API key without api_key."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.organizations.can_manage_organization", return_value=True):
            try:
                response = client.post(
                    "/api/organizations/org-1/api-keys/openai",
                    json={},
                )
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_set_org_api_key_invalid_provider(self, client, mock_superadmin):
        """Test setting org API key for invalid provider."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.SUPPORTED_PROVIDERS = ["openai"]

            try:
                response = client.post(
                    "/api/organizations/org-1/api-keys/invalid",
                    json={"api_key": "test"},
                )
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_set_org_api_key_failure(self, client, mock_superadmin):
        """Test setting org API key when storage fails."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.SUPPORTED_PROVIDERS = ["openai"]
            mock_svc.set_org_api_key.return_value = False

            try:
                response = client.post(
                    "/api/organizations/org-1/api-keys/openai",
                    json={"api_key": "sk-test"},
                )
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_remove_org_api_key_success(self, client, mock_superadmin):
        """Test removing org API key."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.remove_org_api_key.return_value = True

            try:
                response = client.delete("/api/organizations/org-1/api-keys/openai")
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_remove_org_api_key_not_found(self, client, mock_superadmin):
        """Test removing non-existent org API key."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.remove_org_api_key.return_value = False

            try:
                response = client.delete("/api/organizations/org-1/api-keys/openai")
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_test_org_api_key_success(self, client, mock_superadmin):
        """Test testing org API key."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.SUPPORTED_PROVIDERS = ["openai"]

            with patch("user_api_key_service.user_api_key_service") as mock_uak:
                mock_uak.validate_api_key = AsyncMock(
                    return_value=(True, "OK", None)
                )
                try:
                    response = client.post(
                        "/api/organizations/org-1/api-keys/openai/test",
                        json={"api_key": "sk-test"},
                    )
                    assert response.status_code == status.HTTP_200_OK
                    assert response.json()["status"] == "success"
                finally:
                    app.dependency_overrides.clear()

    def test_test_saved_org_api_key_not_found(self, client, mock_superadmin):
        """Test testing saved org API key when not found."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc, \
             patch("routers.organizations.can_manage_organization", return_value=True):
            mock_svc.get_org_api_key.return_value = None

            try:
                response = client.post(
                    "/api/organizations/org-1/api-keys/openai/test-saved"
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_get_org_api_key_settings(self, client, mock_superadmin):
        """Test getting org API key settings."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc:
            mock_svc._get_org_setting_require_private_keys.return_value = False

            try:
                response = client.get("/api/organizations/org-1/api-keys/settings")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "require_private_keys" in data
            finally:
                app.dependency_overrides.clear()

    def test_get_org_available_models(self, client, mock_superadmin):
        """Test getting available models for org."""
        mock_db, _ = self._mock_db_with_org()
        self._setup(mock_superadmin, mock_db)

        with patch("routers.org_api_keys.org_api_key_service") as mock_svc:
            mock_svc.get_available_providers_for_context.return_value = []

            try:
                response = client.get("/api/organizations/org-1/api-keys/available-models")
                assert response.status_code == status.HTTP_200_OK
                assert isinstance(response.json(), list)
            finally:
                app.dependency_overrides.clear()
