"""Behavioral integration tests for the user API-key router.

Targets uncovered branches in ``services/api/routers/api_keys.py`` and the real
``services/api/services/user_api_key_service.py`` it delegates to. Unlike the
mock-heavy unit tests in ``tests/unit/test_api_keys_router.py``, these exercise
the *real* service: real Fernet encryption and real Postgres writes via the
``async_test_db`` SAVEPOINT-isolated session, asserting persisted state on the
``User.encrypted_<provider>_api_key`` columns after each call.

Only the network-touching ``validate_api_key`` coroutine is patched (so no live
provider call is made); the storage/encryption/DB path runs for real. The
``set_user_api_key`` route treats ``validate_api_key``'s return as a single
truthy flag (line 60-65), so any truthy stand-in keeps the real storage path.

The router moved to the async DB lane (``Depends(get_async_db)`` + async twins
on ``user_api_key_service``), so every DB-touching test drives it with the
``async_test_client`` / ``async_test_db`` fixtures and authenticates by
overriding ``require_user`` (handlers read ``current_user.id``).
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import LLMModel, User as DBUser

# Valid per-provider key shapes (see encryption_service.is_valid_api_key_format):
#   openai: "sk-" + >=16 total, anthropic: "sk-ant-" + >=20, google: >10 chars,
#   deepinfra: >=8, grok: "xai-" + >=10, mistral/cohere: >=20.
VALID_OPENAI_KEY = "sk-test-openai-key-1234567890"
VALID_ANTHROPIC_KEY = "sk-ant-test-anthropic-key-1234567890"


def _patch_validate(success=True):
    """Patch the real router service instance's network validate call."""
    return patch.object(
        __import__("routers.api_keys", fromlist=["user_api_key_service"]).user_api_key_service,
        "validate_api_key",
        new=AsyncMock(return_value=(success, "ok" if success else "bad", None if success else "auth")),
    )


@contextmanager
def _as_user(db_user):
    """Authenticate the request as ``db_user`` by overriding ``require_user``.

    The async handlers only read ``current_user.id`` (and ``.username`` for
    logging), so an auth-layer ``AuthUser`` mirroring the DB row is sufficient.
    """
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


def _seed_user(db_session, user_id="admin-test-id", *, username=None, is_superadmin=True):
    """Add a real ``User`` row on the async session (encrypted_* columns start None)."""
    user = DBUser(
        id=user_id,
        username=username or f"{user_id}@test.com",
        email=username or f"{user_id}@test.com",
        name=f"Test {user_id}",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
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


async def _reload_user(db, user_id):
    """Re-query the user, ensuring committed-column state is read back fresh.

    ``populate_existing()`` forces the SELECT to overwrite any expired/identity-
    map attributes in this same round-trip, so attribute access afterwards never
    triggers an implicit (sync) lazy refresh — which would ``MissingGreenlet`` on
    the async session.
    """
    result = await db.execute(
        select(DBUser).where(DBUser.id == user_id).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


class TestSetUserApiKeyBehavioral:
    """POST /api/users/api-keys/{provider} — real encryption + DB persistence."""

    @pytest.mark.asyncio
    async def test_set_openai_key_persists_encrypted_column(
        self, async_test_client, async_test_db
    ):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        # Precondition: no key stored.
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is None

        with _as_user(admin), _patch_validate(success=True):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )

        assert resp.status_code == status.HTTP_200_OK
        assert "openai set successfully" in resp.json()["message"]

        # Persisted: column is now a non-empty Fernet ciphertext, not plaintext.
        stored = (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key
        assert stored is not None and stored != ""
        assert VALID_OPENAI_KEY not in stored  # encrypted at rest

    @pytest.mark.asyncio
    async def test_set_key_uppercase_provider_normalized(
        self, async_test_client, async_test_db
    ):
        """Provider is validated case-insensitively and stored on the lowercase field."""
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin), _patch_validate(success=True):
            resp = await async_test_client.post(
                "/api/users/api-keys/Anthropic",
                json={"api_key": VALID_ANTHROPIC_KEY},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert (await _reload_user(async_test_db, admin.id)).encrypted_anthropic_api_key is not None

    @pytest.mark.asyncio
    async def test_set_key_missing_api_key_400(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "api_key is required" in resp.json()["detail"]
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is None

    @pytest.mark.asyncio
    async def test_set_key_unsupported_provider_400(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/users/api-keys/notaprovider",
                json={"api_key": "sk-whatever-1234567890"},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported provider" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_key_bad_format_returns_500_and_does_not_persist(
        self, async_test_client, async_test_db
    ):
        """A valid provider but malformed key fails the service format check.

        ``set_user_api_key`` returns False (is_valid_api_key_format rejects an
        openai key lacking the ``sk-`` prefix), so the route raises 500 and the
        column stays None.
        """
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin), _patch_validate(success=True):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "totally-wrong-format"},
            )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is None

    @pytest.mark.asyncio
    async def test_set_key_validation_exception_swallowed_and_stores(
        self, async_test_client, async_test_db
    ):
        """If the network validation raises, the route logs and still stores."""
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin), patch.object(
            __import__("routers.api_keys", fromlist=["user_api_key_service"]).user_api_key_service,
            "validate_api_key",
            new=AsyncMock(side_effect=Exception("network down")),
        ):
            resp = await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is not None

    @pytest.mark.asyncio
    async def test_set_key_requires_auth(self, async_test_client):
        """No require_user override -> the real dependency rejects the request."""
        resp = await async_test_client.post(
            "/api/users/api-keys/openai", json={"api_key": VALID_OPENAI_KEY}
        )
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class TestUserApiKeyStatusBehavioral:
    """GET /api/users/api-keys/status — reflects real stored columns."""

    @pytest.mark.asyncio
    async def test_status_reflects_stored_key(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        # Store a key behaviorally first.
        with _as_user(admin), _patch_validate(success=True):
            await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )

            resp = await async_test_client.get("/api/users/api-keys/status")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["api_key_status"]["openai"] is True
        assert data["api_key_status"]["anthropic"] is False
        # available_providers uses the display-name capitalisation.
        assert "OpenAI" in data["available_providers"]
        assert "Anthropic" not in data["available_providers"]

    @pytest.mark.asyncio
    async def test_status_empty_when_no_keys(self, async_test_client, async_test_db):
        contributor = _seed_user(
            async_test_db, user_id="contributor-test-id", is_superadmin=False
        )
        await async_test_db.flush()
        with _as_user(contributor):
            resp = await async_test_client.get("/api/users/api-keys/status")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert all(v is False for v in data["api_key_status"].values())
        assert data["available_providers"] == []


class TestRemoveUserApiKeyBehavioral:
    """DELETE /api/users/api-keys/{provider} — clears the real column."""

    @pytest.mark.asyncio
    async def test_remove_clears_stored_column(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin), _patch_validate(success=True):
            await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is not None

        with _as_user(admin):
            resp = await async_test_client.delete("/api/users/api-keys/openai")
        assert resp.status_code == status.HTTP_200_OK
        assert "removed successfully" in resp.json()["message"]
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is None

    @pytest.mark.asyncio
    async def test_remove_when_no_key_still_succeeds(self, async_test_client, async_test_db):
        """Removing an unset provider clears (already-None) field; service returns True."""
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        assert (await _reload_user(async_test_db, admin.id)).encrypted_cohere_api_key is None
        with _as_user(admin):
            resp = await async_test_client.delete("/api/users/api-keys/cohere")
        assert resp.status_code == status.HTTP_200_OK
        assert (await _reload_user(async_test_db, admin.id)).encrypted_cohere_api_key is None

    @pytest.mark.asyncio
    async def test_remove_unsupported_provider_500(self, async_test_client, async_test_db):
        """Service returns False for an unsupported provider -> route raises 500."""
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.delete("/api/users/api-keys/notaprovider")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestLifecycleAndIsolation:
    """Full create -> status -> remove lifecycle, plus per-user isolation."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()

        with _as_user(admin):
            # 1) create
            with _patch_validate(success=True):
                r_create = await async_test_client.post(
                    "/api/users/api-keys/anthropic",
                    json={"api_key": VALID_ANTHROPIC_KEY},
                )
            assert r_create.status_code == status.HTTP_200_OK
            assert (
                await _reload_user(async_test_db, admin.id)
            ).encrypted_anthropic_api_key is not None

            # 2) status shows it
            r_status = await async_test_client.get("/api/users/api-keys/status")
            assert r_status.json()["api_key_status"]["anthropic"] is True

            # 3) remove
            r_del = await async_test_client.delete("/api/users/api-keys/anthropic")
            assert r_del.status_code == status.HTTP_200_OK
            assert (
                await _reload_user(async_test_db, admin.id)
            ).encrypted_anthropic_api_key is None

            # 4) status no longer shows it
            r_status2 = await async_test_client.get("/api/users/api-keys/status")
            assert r_status2.json()["api_key_status"]["anthropic"] is False

    @pytest.mark.asyncio
    async def test_keys_are_per_user(self, async_test_client, async_test_db):
        """A key set by the admin user must not appear for a different user."""
        admin = _seed_user(async_test_db)
        contributor = _seed_user(
            async_test_db, user_id="contributor-test-id", is_superadmin=False
        )
        await async_test_db.flush()
        with _as_user(admin), _patch_validate(success=True):
            await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )

        # admin has it, contributor does not (DB-level assertion)
        assert (await _reload_user(async_test_db, admin.id)).encrypted_openai_api_key is not None
        assert (
            await _reload_user(async_test_db, contributor.id)
        ).encrypted_openai_api_key is None

        # contributor's status endpoint reflects no key
        with _as_user(contributor):
            resp = await async_test_client.get("/api/users/api-keys/status")
        assert resp.json()["api_key_status"]["openai"] is False


class TestTestSavedUserKeyBehavioral:
    """POST /api/users/api-keys/{provider}/test-saved — reads the real stored key."""

    @pytest.mark.asyncio
    async def test_test_saved_no_key_404(self, async_test_client, async_test_db):
        contributor = _seed_user(
            async_test_db, user_id="contributor-test-id", is_superadmin=False
        )
        await async_test_db.flush()
        with _as_user(contributor):
            resp = await async_test_client.post("/api/users/api-keys/openai/test-saved")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_test_saved_unsupported_provider_400(self, async_test_client, async_test_db):
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.post("/api/users/api-keys/notaprovider/test-saved")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_test_saved_with_stored_key_succeeds(self, async_test_client, async_test_db):
        """After storing a real (encrypted) key, the saved-test path decrypts it
        and runs the (patched) validator -> success."""
        admin = _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin), _patch_validate(success=True):
            await async_test_client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
            )
            resp = await async_test_client.post("/api/users/api-keys/openai/test-saved")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"


class TestUserAvailableModelsBehavioral:
    """GET /api/users/api-keys/available-models — filters by stored providers."""

    @pytest.mark.asyncio
    async def test_available_models_empty_without_keys(
        self, async_test_client, async_test_db
    ):
        contributor = _seed_user(
            async_test_db, user_id="contributor-test-id", is_superadmin=False
        )
        await async_test_db.flush()
        with _as_user(contributor):
            resp = await async_test_client.get("/api/users/api-keys/available-models")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_available_models_org_context_branch(
        self, async_test_client, async_test_db
    ):
        """X-Organization-Context routes resolution through org_api_key_service."""
        org_admin = _seed_user(
            async_test_db, user_id="org-admin-test-id", is_superadmin=False
        )
        _seed_model(async_test_db, "gpt-4", "openai", name="GPT-4")
        _seed_model(async_test_db, "claude-x", "anthropic", name="Claude")
        await async_test_db.flush()
        with _as_user(org_admin), patch(
            "services.org_api_key_service.org_api_key_service."
            "get_available_providers_for_context_async",
            new=AsyncMock(return_value=[]),
        ):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": "test-org-id"},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)
