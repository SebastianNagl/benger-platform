"""
Tests for org API keys router.

Targets: routers/org_api_keys.py — the async permission helpers
(``_require_org_admin`` / ``_require_org_member`` / ``_require_org_exists``)
and the GET/POST/DELETE endpoints under ``/api/organizations/{org_id}/api-keys``.

Migrated to the async DB lane (2026-06-19): the router and its private
permission helpers now run ``await db.execute(select(...))`` against
``Organization`` / ``OrganizationMembership`` via ``Depends(get_async_db)``.
The previous ``app.dependency_overrides[get_db] = lambda: mock_db`` + sync
service mocks no longer reach the handlers, so these tests:

- exercise the helpers directly with a real ``async_test_db`` AsyncSession, and
- drive the endpoints through ``async_test_client`` with a seeded superadmin
  identity (superadmin bypasses every org membership check), patching the
  specific async service twins where a deterministic result is needed.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User as DBUser,
)


@contextmanager
def _as_user(db_user):
    """Override require_user with an auth identity built from a seeded DB row."""
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


def _uid():
    return str(uuid.uuid4())


async def _seed_user(db, *, is_superadmin=False):
    u = DBUser(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_org(db, *, settings=None):
    o = Organization(
        id=_uid(),
        name=f"org-{_uid()[:6]}",
        display_name="Org",
        slug=f"org-{_uid()[:8]}",
        is_active=True,
        settings=settings if settings is not None else {},
    )
    db.add(o)
    await db.flush()
    return o


async def _seed_member(db, user, org, role):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
    )
    db.add(m)
    await db.flush()
    return m


class TestOrgApiKeysHelpers:
    """Test the async permission helper functions directly.

    These helpers now hit the DB, so they are exercised with a real
    ``async_test_db`` AsyncSession + seeded rows rather than a mock session.
    """

    @pytest.mark.asyncio
    async def test_require_org_admin_denied(self, async_test_db):
        """A plain member (non-admin) is rejected with 403."""
        from routers.org_api_keys import _require_org_admin

        org = await _seed_org(async_test_db)
        member = await _seed_user(async_test_db, is_superadmin=False)
        await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)

        au = AuthUser(
            id=member.id,
            username=member.username,
            email=member.email,
            name=member.name,
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(HTTPException) as exc_info:
            await _require_org_admin(au, org.id, async_test_db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_org_member_superadmin(self, async_test_db):
        """A superadmin passes the member check without any membership row."""
        from routers.org_api_keys import _require_org_member

        org = await _seed_org(async_test_db)
        au = AuthUser(
            id=_uid(),
            username="super",
            email="super@e.com",
            name="Super",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        # Should not raise
        await _require_org_member(au, org.id, async_test_db)

    @pytest.mark.asyncio
    async def test_require_org_member_denied(self, async_test_db):
        """A non-superadmin with no membership is rejected with 403."""
        from routers.org_api_keys import _require_org_member

        org = await _seed_org(async_test_db)
        outsider = await _seed_user(async_test_db, is_superadmin=False)

        au = AuthUser(
            id=outsider.id,
            username=outsider.username,
            email=outsider.email,
            name=outsider.name,
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(HTTPException) as exc_info:
            await _require_org_member(au, org.id, async_test_db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_org_exists_not_found(self, async_test_db):
        """A missing org raises 404."""
        from routers.org_api_keys import _require_org_exists

        with pytest.raises(HTTPException) as exc_info:
            await _require_org_exists("nonexistent", async_test_db)
        assert exc_info.value.status_code == 404


class TestOrgApiKeysEndpoints:
    """Test org API key management endpoints (driven as a superadmin).

    Superadmin bypasses the org membership checks, so a seeded org plus a
    superadmin identity is enough to reach each handler. Service results are
    pinned by patching the specific async twin on the singleton.
    """

    @pytest.mark.asyncio
    async def test_get_org_api_key_status(self, async_test_client, async_test_db):
        """Test getting org API key status."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.get_org_api_key_status_async",
            new=AsyncMock(return_value={"openai": True}),
        ), patch(
            "routers.org_api_keys.org_api_key_service.get_org_available_providers_async",
            new=AsyncMock(return_value=["openai"]),
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "api_key_status" in data

    @pytest.mark.asyncio
    async def test_set_org_api_key_success(self, async_test_client, async_test_db):
        """Test setting org API key."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.set_org_api_key_async",
            new=AsyncMock(return_value=True),
        ):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-test"},
            )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_set_org_api_key_missing(self, async_test_client, async_test_db):
        """Test setting org API key without api_key."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_set_org_api_key_invalid_provider(self, async_test_client, async_test_db):
        """Test setting org API key for invalid provider."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/invalid",
                json={"api_key": "test"},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_set_org_api_key_failure(self, async_test_client, async_test_db):
        """Test setting org API key when storage fails."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.set_org_api_key_async",
            new=AsyncMock(return_value=False),
        ):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-test"},
            )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_remove_org_api_key_success(self, async_test_client, async_test_db):
        """Test removing org API key."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.remove_org_api_key_async",
            new=AsyncMock(return_value=True),
        ):
            response = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai"
            )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_remove_org_api_key_not_found(self, async_test_client, async_test_db):
        """Test removing non-existent org API key."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.remove_org_api_key_async",
            new=AsyncMock(return_value=False),
        ):
            response = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_test_org_api_key_success(self, async_test_client, async_test_db):
        """Test testing an unsaved org API key."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "services.user_api_key_service.user_api_key_service.validate_api_key",
            new=AsyncMock(return_value=(True, "OK", None)),
        ):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai/test",
                json={"api_key": "sk-test"},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "success"

    @pytest.mark.asyncio
    async def test_test_saved_org_api_key_not_found(self, async_test_client, async_test_db):
        """Test testing a saved org API key when none is stored."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.get_org_api_key_async",
            new=AsyncMock(return_value=None),
        ):
            response = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai/test-saved"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_org_api_key_settings(self, async_test_client, async_test_db):
        """Test getting org API key settings."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service._get_org_setting_require_private_keys_async",
            new=AsyncMock(return_value=False),
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "require_private_keys" in data

    @pytest.mark.asyncio
    async def test_get_org_available_models(self, async_test_client, async_test_db):
        """Test getting available models for org."""
        org = await _seed_org(async_test_db)
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.get_available_providers_for_context_async",
            new=AsyncMock(return_value=[]),
        ):
            response = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/available-models"
            )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
