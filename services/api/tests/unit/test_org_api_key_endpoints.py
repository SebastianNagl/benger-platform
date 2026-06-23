"""
Unit tests for org API key endpoints (Issue #1180)

Tests endpoint access control, settings toggle,
and key management operations.

Migrated to the async DB lane (2026-06-19): ``routers/org_api_keys.py`` now
runs entirely on ``Depends(get_async_db)`` — every handler and the private
permission helpers (``_require_org_exists`` / ``_require_org_admin`` /
``_require_org_member``) issue async ``select(...)`` queries against
``Organization`` / ``OrganizationMembership``. The old Bearer-token + sync
``test_db`` fixture path no longer reaches them, so these tests seed real rows
through ``async_test_db`` and drive the handlers via ``async_test_client``,
overriding ``require_user`` with an auth identity built from the seeded user.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

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
    slug = f"org-{_uid()[:8]}"
    o = Organization(
        id=_uid(),
        name=f"org-{_uid()[:6]}",
        display_name="Org",
        slug=slug,
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


async def _seed_org_with_members(async_test_db, *, org_settings=None):
    """Seed an org plus an ORG_ADMIN and an ANNOTATOR member.

    Returns ``(org, admin, member)``.
    """
    org = await _seed_org(async_test_db, settings=org_settings)
    admin = await _seed_user(async_test_db, is_superadmin=False)
    member = await _seed_user(async_test_db, is_superadmin=False)
    await _seed_member(async_test_db, admin, org, OrganizationRole.ORG_ADMIN)
    await _seed_member(async_test_db, member, org, OrganizationRole.ANNOTATOR)
    return org, admin, member


@pytest.mark.unit
class TestSettingsEndpoints:
    """Test GET/PUT settings for require_private_keys toggle."""

    @pytest.mark.asyncio
    async def test_get_settings_returns_default(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings"
            )
        assert resp.status_code == 200
        assert resp.json()["require_private_keys"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_member_can_read_settings(self, async_test_client, async_test_db):
        org, _, member = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(member):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_toggle_settings(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={"require_private_keys": False},
            )
            assert resp.status_code == 200
            assert resp.json()["require_private_keys"] == False  # noqa: E712

            # Verify persisted
            resp2 = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings"
            )
        assert resp2.json()["require_private_keys"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_member_cannot_toggle_settings(self, async_test_client, async_test_db):
        org, _, member = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(member):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={"require_private_keys": False},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_toggle_missing_field_returns_400(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={},
            )
        assert resp.status_code == 400


@pytest.mark.unit
class TestKeyStatusEndpoint:
    """Test GET status endpoint."""

    @pytest.mark.asyncio
    async def test_admin_gets_status(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key_status" in body
        assert "available_providers" in body
        # No keys seeded -> all providers report False
        assert all(v is False for v in body["api_key_status"].values())

    @pytest.mark.asyncio
    async def test_member_cannot_get_status(self, async_test_client, async_test_db):
        org, _, member = await _seed_org_with_members(async_test_db)
        with _as_user(member):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status"
            )
        assert resp.status_code == 403


@pytest.mark.unit
class TestSetKeyEndpoint:
    """Test POST set key endpoint."""

    @pytest.mark.asyncio
    async def test_admin_can_set_key_even_when_require_private_keys_true(
        self, async_test_client, async_test_db
    ):
        """Admins can pre-configure org keys before toggling the setting."""
        org, admin, _ = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.set_org_api_key_async",
            new=AsyncMock(return_value=True),
        ):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-testapikey1234567890abcdef"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_set_key_after_toggle(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(
            async_test_db, org_settings={"require_private_keys": True}
        )
        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.set_org_api_key_async",
            new=AsyncMock(return_value=True),
        ):
            # Toggle to org-pays mode
            await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={"require_private_keys": False},
            )
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-testapikey1234567890abcdef"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_set_key(self, async_test_client, async_test_db):
        org, _, member = await _seed_org_with_members(async_test_db)
        with _as_user(member):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-testapikey1234567890abcdef"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_400(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/unsupported",
                json={"api_key": "some-key"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_400(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={},
            )
        assert resp.status_code == 400


@pytest.mark.unit
class TestRemoveKeyEndpoint:
    """Test DELETE key endpoint."""

    @pytest.mark.asyncio
    async def test_admin_can_remove_key(self, async_test_client, async_test_db):
        org, admin, _ = await _seed_org_with_members(async_test_db)
        with _as_user(admin), patch(
            "routers.org_api_keys.org_api_key_service.remove_org_api_key_async",
            new=AsyncMock(return_value=True),
        ):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_404(self, async_test_client, async_test_db):
        # No key seeded -> the real async remove twin returns False -> 404.
        org, admin, _ = await _seed_org_with_members(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_member_cannot_remove_key(self, async_test_client, async_test_db):
        org, _, member = await _seed_org_with_members(async_test_db)
        with _as_user(member):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai"
            )
        assert resp.status_code == 403


@pytest.mark.unit
class TestNonexistentOrg:
    """Test requests to nonexistent org return 404."""

    @pytest.mark.asyncio
    async def test_settings_nonexistent_org(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/organizations/nonexistent-org-id/api-keys/settings"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_nonexistent_org(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/organizations/nonexistent-org-id/api-keys/status"
            )
        assert resp.status_code == 404
