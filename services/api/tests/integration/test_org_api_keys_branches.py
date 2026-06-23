"""Behavioral integration tests for the organization API-key router.

Targets uncovered branches in ``services/api/routers/org_api_keys.py`` and the
real ``services/api/services/org_api_key_service.py``.

**Async lane.** Every endpoint in ``org_api_keys.py`` moved to the async DB
lane (``Depends(get_async_db)``). Driving them with the sync ``TestClient`` +
sync ``test_db`` fails — the async engine binds to a different event loop than
TestClient's portal, and a sync call into an async handler poisons the shared
async connection pool (``RuntimeError: ... attached to a different loop``) so a
*combined* run regresses even though each test passes alone. These tests are
therefore driven with the ``async_test_client`` + ``async_test_db`` fixtures and
authenticate by overriding ``require_user`` (the handlers read
``current_user.id`` and re-query the async session for memberships) instead of
sending Bearer JWTs.

The suite still asserts the same behaviour as before:

  * permission helpers (``_require_org_exists`` / ``_require_org_admin`` /
    ``_require_org_member``) run against real ``OrganizationMembership`` rows,
  * ``set_org_api_key_async`` performs real Fernet encryption and inserts a real
    ``organization_api_keys`` row,

and each "persists" test asserts persisted state by querying
``OrganizationApiKey`` after.

Permission map seeded per test by ``_seed_org_and_users``:
  * superadmin    -> superadmin (manage + member, no membership row needed)
  * org_admin     -> ORG_ADMIN membership (manage)
  * annotator     -> ANNOTATOR membership (member only)
  * contributor   -> CONTRIBUTOR membership (member only)

Only the ``/test`` and ``/test-saved`` endpoints make a network validation
call; those patch ``user_api_key_service.validate_api_key`` to stay offline.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select

from models import (
    Organization,
    OrganizationApiKey,
    OrganizationMembership,
    OrganizationRole,
    User,
)

from auth_module.dependencies import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from main import app  # noqa: E402

VALID_OPENAI_KEY = "sk-org-openai-key-1234567890"
VALID_ANTHROPIC_KEY = "sk-ant-org-anthropic-key-1234567890"


def _uid() -> str:
    return str(uuid.uuid4())


class _SeededUser:
    """Plain snapshot of a seeded user's identity fields.

    Holding plain attribute values (rather than the live ORM instance) means
    ``_as_user`` never triggers a lazy attribute reload — important because the
    tests call ``expire_all()`` between requests, which would otherwise make a
    later ``db_user.id`` access fire a *sync* reload on the AsyncSession's
    underlying sync session and blow up under greenlet.
    """

    def __init__(self, db_user):
        self.id = db_user.id
        self.username = db_user.username
        self.email = db_user.email
        self.name = db_user.name
        self.is_superadmin = db_user.is_superadmin
        self.created_at = db_user.created_at


class _SeededOrg:
    """Plain snapshot of a seeded org's id (same ``expire_all`` rationale)."""

    def __init__(self, db_org):
        self.id = db_org.id


# ---------------------------------------------------------------------------
# Async-lane helpers (mirror tests/integration/test_invitations_branches.py)
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB user row."""
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


async def _aseed_user(db, email, name="Org Key User", *, is_superadmin=False):
    """Seed a User row on the async session and return it."""
    user = User(
        id=_uid(),
        username=email,
        email=email,
        name=name,
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _aseed_org(db, *, name="Org-Key Test Org", slug=None):
    org = Organization(
        id=_uid(),
        name=name,
        display_name=f"{name} Display",
        slug=slug or f"orgkey-org-{uuid.uuid4().hex[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _aseed_membership(db, user_id, org_id, role=OrganizationRole.ANNOTATOR, is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
    )
    db.add(m)
    await db.flush()
    return m


async def _seed_org_and_users(db):
    """Seed one org plus the four permission-level users.

    Returns ``(org, users)`` where ``users`` is a dict with keys
    ``superadmin`` / ``org_admin`` / ``contributor`` / ``annotator``. The
    superadmin holds no membership row (superadmin short-circuits both the
    admin and member checks). Commits so the handlers (running on the same
    SAVEPOINT-isolated transaction) can read the rows.
    """
    org = await _aseed_org(db)

    superadmin = await _aseed_user(db, "orgkey-super@example.com", is_superadmin=True)
    org_admin = await _aseed_user(db, "orgkey-orgadmin@example.com")
    contributor = await _aseed_user(db, "orgkey-contributor@example.com")
    annotator = await _aseed_user(db, "orgkey-annotator@example.com")

    await _aseed_membership(db, org_admin.id, org.id, role=OrganizationRole.ORG_ADMIN)
    await _aseed_membership(db, contributor.id, org.id, role=OrganizationRole.CONTRIBUTOR)
    await _aseed_membership(db, annotator.id, org.id, role=OrganizationRole.ANNOTATOR)

    await db.commit()
    return _SeededOrg(org), {
        "superadmin": _SeededUser(superadmin),
        "org_admin": _SeededUser(org_admin),
        "contributor": _SeededUser(contributor),
        "annotator": _SeededUser(annotator),
    }


async def _get_org_key(db, org_id, provider):
    """Fetch the OrganizationApiKey row for (org, provider), or None.

    Expires identity-map state first so a row written by the handler (on the
    same connection/transaction) is re-read from the DB rather than served
    stale from the session cache.
    """
    db.expire_all()
    result = await db.execute(
        select(OrganizationApiKey).where(
            OrganizationApiKey.organization_id == org_id,
            OrganizationApiKey.provider == provider,
        )
    )
    return result.scalar_one_or_none()


def _patch_validate(success=True):
    # The router resolves ``from services.user_api_key_service import
    # user_api_key_service`` — a *different* module object than the
    # ``/shared`` ``user_api_key_service`` (both exist on sys.path). Patch the
    # singleton the handler actually calls, else the real provider network
    # call fires (401 from OpenAI) and the assertion flips success->error.
    return patch(
        "services.user_api_key_service.user_api_key_service.validate_api_key",
        new=AsyncMock(
            return_value=(success, "ok" if success else "bad", None if success else "auth")
        ),
    )


@pytest.mark.integration
class TestSetOrgApiKeyBehavioral:
    """POST /{org_id}/api-keys/{provider} — real row insert + encryption."""

    @pytest.mark.asyncio
    async def test_set_org_key_persists_row(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)
        assert await _get_org_key(async_test_db, org.id, "openai") is None

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert "openai set successfully" in resp.json()["message"]

        row = await _get_org_key(async_test_db, org.id, "openai")
        assert row is not None
        assert row.provider == "openai"
        assert row.organization_id == org.id
        assert row.created_by == users["org_admin"].id
        assert row.encrypted_key and VALID_OPENAI_KEY not in row.encrypted_key

    @pytest.mark.asyncio
    async def test_set_org_key_as_superadmin(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["superadmin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/anthropic",
                json={"api_key": VALID_ANTHROPIC_KEY},
            )
        assert resp.status_code == status.HTTP_200_OK
        row = await _get_org_key(async_test_db, org.id, "anthropic")
        assert row is not None and row.created_by == users["superadmin"].id

    @pytest.mark.asyncio
    async def test_set_org_key_upsert_updates_existing_row(
        self, async_test_client, async_test_db
    ):
        """Setting the same provider twice updates the existing row, not a 2nd insert."""
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        first = await _get_org_key(async_test_db, org.id, "openai")
        first_id, first_cipher = first.id, first.encrypted_key

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "sk-org-openai-key-DIFFERENT-99999"},
            )
        assert resp.status_code == status.HTTP_200_OK

        # Still exactly one row, same id, but re-encrypted (different ciphertext).
        async_test_db.expire_all()
        rows = (
            await async_test_db.execute(
                select(OrganizationApiKey).where(
                    OrganizationApiKey.organization_id == org.id,
                    OrganizationApiKey.provider == "openai",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == first_id
        assert rows[0].encrypted_key != first_cipher

    @pytest.mark.asyncio
    async def test_set_org_key_missing_api_key_400(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "api_key is required" in resp.json()["detail"]
        assert await _get_org_key(async_test_db, org.id, "openai") is None

    @pytest.mark.asyncio
    async def test_set_org_key_unsupported_provider_400(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/notaprovider",
                json={"api_key": "sk-whatever-1234567890"},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported provider" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_org_key_bad_format_500_no_row(self, async_test_client, async_test_db):
        """Valid provider but malformed key -> service returns False -> 500, no row."""
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": "no-sk-prefix"},
            )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert await _get_org_key(async_test_db, org.id, "openai") is None

    @pytest.mark.asyncio
    async def test_set_org_key_org_not_found_404(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["superadmin"]):
            resp = await async_test_client.post(
                "/api/organizations/does-not-exist/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "Organization not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_org_key_non_admin_member_403(self, async_test_client, async_test_db):
        """An annotator is a member but not an org-admin -> 403, no row written."""
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["annotator"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in resp.json()["detail"].lower()
        assert await _get_org_key(async_test_db, org.id, "openai") is None


@pytest.mark.integration
class TestOrgApiKeyStatusBehavioral:
    """GET /{org_id}/api-keys/status — reflects real rows."""

    @pytest.mark.asyncio
    async def test_status_reflects_stored_keys(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status",
            )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["api_key_status"]["openai"] is True
        assert data["api_key_status"]["anthropic"] is False
        assert "OpenAI" in data["available_providers"]

    @pytest.mark.asyncio
    async def test_status_non_admin_403(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["contributor"]):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status",
            )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.integration
class TestRemoveOrgApiKeyBehavioral:
    """DELETE /{org_id}/api-keys/{provider} — deletes the real row."""

    @pytest.mark.asyncio
    async def test_remove_deletes_row(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert await _get_org_key(async_test_db, org.id, "openai") is not None

        with _as_user(users["org_admin"]):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai",
            )
        assert resp.status_code == status.HTTP_200_OK
        assert "removed successfully" in resp.json()["message"]
        assert await _get_org_key(async_test_db, org.id, "openai") is None

    @pytest.mark.asyncio
    async def test_remove_missing_key_404(self, async_test_client, async_test_db):
        """No row for provider -> service returns False -> route raises 404."""
        org, users = await _seed_org_and_users(async_test_db)
        assert await _get_org_key(async_test_db, org.id, "cohere") is None

        with _as_user(users["org_admin"]):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/cohere",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_remove_non_admin_403(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["annotator"]):
            resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/openai",
            )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_remove_org_not_found_404(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["superadmin"]):
            resp = await async_test_client.delete(
                "/api/organizations/does-not-exist/api-keys/openai",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "Organization not found" in resp.json()["detail"]


@pytest.mark.integration
class TestOrgKeyLifecycle:
    """Full set -> status -> remove lifecycle with DB-level assertions."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        # set
        with _as_user(users["org_admin"]):
            await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/mistral",
                json={"api_key": "mistral-org-key-abcdefghij1234567890"},
            )
        assert await _get_org_key(async_test_db, org.id, "mistral") is not None

        # status reflects it
        with _as_user(users["org_admin"]):
            r_status = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/status",
            )
        assert r_status.json()["api_key_status"]["mistral"] is True

        # remove
        with _as_user(users["org_admin"]):
            r_del = await async_test_client.delete(
                f"/api/organizations/{org.id}/api-keys/mistral",
            )
        assert r_del.status_code == status.HTTP_200_OK
        assert await _get_org_key(async_test_db, org.id, "mistral") is None


@pytest.mark.integration
class TestOrgKeySettingsBehavioral:
    """GET/PUT /{org_id}/api-keys/settings — settings persist on Organization.settings."""

    @pytest.mark.asyncio
    async def test_get_settings_defaults_true(self, async_test_client, async_test_db):
        """No settings stored -> require_private_keys defaults to True; member-readable."""
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["annotator"]):  # plain member may read
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings",
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["require_private_keys"] is True

    @pytest.mark.asyncio
    async def test_update_settings_persists(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={"require_private_keys": False},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["require_private_keys"] is False

        # Persisted on the Organization.settings JSON, and re-readable via GET.
        async_test_db.expire_all()
        stored = (
            await async_test_db.execute(
                select(Organization).where(Organization.id == org.id)
            )
        ).scalar_one_or_none()
        assert stored.settings.get("require_private_keys") is False

        with _as_user(users["org_admin"]):
            r_get = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/settings",
            )
        assert r_get.json()["require_private_keys"] is False

    @pytest.mark.asyncio
    async def test_update_settings_missing_field_400(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "require_private_keys is required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_settings_non_admin_403(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["annotator"]):
            resp = await async_test_client.put(
                f"/api/organizations/{org.id}/api-keys/settings",
                json={"require_private_keys": True},
            )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.integration
class TestTestSavedOrgKeyBehavioral:
    """POST /{org_id}/api-keys/{provider}/test-saved — reads the real stored key."""

    @pytest.mark.asyncio
    async def test_test_saved_no_key_404(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai/test-saved",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_test_saved_with_stored_key_success(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        with _patch_validate(success=True):
            with _as_user(users["org_admin"]):
                resp = await async_test_client.post(
                    f"/api/organizations/{org.id}/api-keys/openai/test-saved",
                )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"


@pytest.mark.integration
class TestTestOrgKeyBehavioral:
    """POST /{org_id}/api-keys/{provider}/test — unsaved key, network patched."""

    @pytest.mark.asyncio
    async def test_test_unsaved_key_success(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _patch_validate(success=True):
            with _as_user(users["org_admin"]):
                resp = await async_test_client.post(
                    f"/api/organizations/{org.id}/api-keys/openai/test",
                    json={"api_key": VALID_OPENAI_KEY},
                )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"

    @pytest.mark.asyncio
    async def test_test_unsaved_key_missing_400(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["org_admin"]):
            resp = await async_test_client.post(
                f"/api/organizations/{org.id}/api-keys/openai/test",
                json={},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_test_unsaved_key_invalid_returns_error(
        self, async_test_client, async_test_db
    ):
        org, users = await _seed_org_and_users(async_test_db)

        with _patch_validate(success=False):
            with _as_user(users["org_admin"]):
                resp = await async_test_client.post(
                    f"/api/organizations/{org.id}/api-keys/openai/test",
                    json={"api_key": VALID_OPENAI_KEY},
                )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "error"


@pytest.mark.integration
class TestOrgAvailableModelsBehavioral:
    """GET /{org_id}/api-keys/available-models — member-readable, returns a list."""

    @pytest.mark.asyncio
    async def test_available_models_member_ok(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["annotator"]):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/available-models",
            )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_available_models_org_not_found_404(self, async_test_client, async_test_db):
        org, users = await _seed_org_and_users(async_test_db)

        with _as_user(users["superadmin"]):
            resp = await async_test_client.get(
                "/api/organizations/does-not-exist/api-keys/available-models",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
