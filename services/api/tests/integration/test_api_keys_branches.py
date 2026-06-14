"""Behavioral integration tests for the user API-key router.

Targets uncovered branches in ``services/api/routers/api_keys.py`` and the real
``services/api/services/user_api_key_service.py`` it delegates to. Unlike the
mock-heavy unit tests in ``tests/unit/test_api_keys_router.py``, these exercise
the *real* service: real Fernet encryption and real Postgres writes via the
``test_db`` SAVEPOINT-isolated session, asserting persisted state on the
``User.encrypted_<provider>_api_key`` columns after each call.

Only the network-touching ``validate_api_key`` coroutine is patched (so no live
provider call is made); the storage/encryption/DB path runs for real. The
``set_user_api_key`` route treats ``validate_api_key``'s return as a single
truthy flag (line 60-65), so any truthy stand-in keeps the real storage path.
"""

from unittest.mock import AsyncMock, patch

from fastapi import status

from models import User

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


def _get_user(test_db, user_id):
    test_db.expire_all()
    return test_db.query(User).filter(User.id == user_id).first()


class TestSetUserApiKeyBehavioral:
    """POST /api/users/api-keys/{provider} — real encryption + DB persistence."""

    def test_set_openai_key_persists_encrypted_column(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        # Precondition: no key stored.
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is None

        with _patch_validate(success=True):
            resp = client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )

        assert resp.status_code == status.HTTP_200_OK
        assert "openai set successfully" in resp.json()["message"]

        # Persisted: column is now a non-empty Fernet ciphertext, not plaintext.
        stored = _get_user(test_db, admin.id).encrypted_openai_api_key
        assert stored is not None and stored != ""
        assert VALID_OPENAI_KEY not in stored  # encrypted at rest

    def test_set_key_uppercase_provider_normalized(
        self, client, test_db, test_users, auth_headers
    ):
        """Provider is validated case-insensitively and stored on the lowercase field."""
        admin = test_users[0]
        with _patch_validate(success=True):
            resp = client.post(
                "/api/users/api-keys/Anthropic",
                json={"api_key": VALID_ANTHROPIC_KEY},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert _get_user(test_db, admin.id).encrypted_anthropic_api_key is not None

    def test_set_key_missing_api_key_400(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        resp = client.post(
            "/api/users/api-keys/openai",
            json={},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "api_key is required" in resp.json()["detail"]
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is None

    def test_set_key_unsupported_provider_400(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/users/api-keys/notaprovider",
            json={"api_key": "sk-whatever-1234567890"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported provider" in resp.json()["detail"]

    def test_set_key_bad_format_returns_500_and_does_not_persist(
        self, client, test_db, test_users, auth_headers
    ):
        """A valid provider but malformed key fails the service format check.

        ``set_user_api_key`` returns False (is_valid_api_key_format rejects an
        openai key lacking the ``sk-`` prefix), so the route raises 500 and the
        column stays None.
        """
        admin = test_users[0]
        with _patch_validate(success=True):
            resp = client.post(
                "/api/users/api-keys/openai",
                json={"api_key": "totally-wrong-format"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is None

    def test_set_key_validation_exception_swallowed_and_stores(
        self, client, test_db, test_users, auth_headers
    ):
        """If the network validation raises, the route logs and still stores."""
        admin = test_users[0]
        with patch.object(
            __import__("routers.api_keys", fromlist=["user_api_key_service"]).user_api_key_service,
            "validate_api_key",
            new=AsyncMock(side_effect=Exception("network down")),
        ):
            resp = client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is not None

    def test_set_key_requires_auth(self, client):
        resp = client.post("/api/users/api-keys/openai", json={"api_key": VALID_OPENAI_KEY})
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class TestUserApiKeyStatusBehavioral:
    """GET /api/users/api-keys/status — reflects real stored columns."""

    def test_status_reflects_stored_key(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        # Store a key behaviorally first.
        with _patch_validate(success=True):
            client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )

        resp = client.get("/api/users/api-keys/status", headers=auth_headers["admin"])
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["api_key_status"]["openai"] is True
        assert data["api_key_status"]["anthropic"] is False
        # available_providers uses the display-name capitalisation.
        assert "OpenAI" in data["available_providers"]
        assert "Anthropic" not in data["available_providers"]

    def test_status_empty_when_no_keys(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/users/api-keys/status", headers=auth_headers["contributor"])
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert all(v is False for v in data["api_key_status"].values())
        assert data["available_providers"] == []


class TestRemoveUserApiKeyBehavioral:
    """DELETE /api/users/api-keys/{provider} — clears the real column."""

    def test_remove_clears_stored_column(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        with _patch_validate(success=True):
            client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is not None

        resp = client.delete("/api/users/api-keys/openai", headers=auth_headers["admin"])
        assert resp.status_code == status.HTTP_200_OK
        assert "removed successfully" in resp.json()["message"]
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is None

    def test_remove_when_no_key_still_succeeds(self, client, test_db, test_users, auth_headers):
        """Removing an unset provider clears (already-None) field; service returns True."""
        admin = test_users[0]
        assert _get_user(test_db, admin.id).encrypted_cohere_api_key is None
        resp = client.delete("/api/users/api-keys/cohere", headers=auth_headers["admin"])
        assert resp.status_code == status.HTTP_200_OK
        assert _get_user(test_db, admin.id).encrypted_cohere_api_key is None

    def test_remove_unsupported_provider_500(self, client, test_db, test_users, auth_headers):
        """Service returns False for an unsupported provider -> route raises 500."""
        resp = client.delete("/api/users/api-keys/notaprovider", headers=auth_headers["admin"])
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestLifecycleAndIsolation:
    """Full create -> status -> remove lifecycle, plus per-user isolation."""

    def test_full_lifecycle(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]

        # 1) create
        with _patch_validate(success=True):
            r_create = client.post(
                "/api/users/api-keys/anthropic",
                json={"api_key": VALID_ANTHROPIC_KEY},
                headers=auth_headers["admin"],
            )
        assert r_create.status_code == status.HTTP_200_OK
        assert _get_user(test_db, admin.id).encrypted_anthropic_api_key is not None

        # 2) status shows it
        r_status = client.get("/api/users/api-keys/status", headers=auth_headers["admin"])
        assert r_status.json()["api_key_status"]["anthropic"] is True

        # 3) remove
        r_del = client.delete("/api/users/api-keys/anthropic", headers=auth_headers["admin"])
        assert r_del.status_code == status.HTTP_200_OK
        assert _get_user(test_db, admin.id).encrypted_anthropic_api_key is None

        # 4) status no longer shows it
        r_status2 = client.get("/api/users/api-keys/status", headers=auth_headers["admin"])
        assert r_status2.json()["api_key_status"]["anthropic"] is False

    def test_keys_are_per_user(self, client, test_db, test_users, auth_headers):
        """A key set by the admin user must not appear for a different user."""
        admin = test_users[0]
        contributor = test_users[1]
        with _patch_validate(success=True):
            client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )

        # admin has it, contributor does not (DB-level assertion)
        assert _get_user(test_db, admin.id).encrypted_openai_api_key is not None
        assert _get_user(test_db, contributor.id).encrypted_openai_api_key is None

        # contributor's status endpoint reflects no key
        resp = client.get("/api/users/api-keys/status", headers=auth_headers["contributor"])
        assert resp.json()["api_key_status"]["openai"] is False


class TestTestSavedUserKeyBehavioral:
    """POST /api/users/api-keys/{provider}/test-saved — reads the real stored key."""

    def test_test_saved_no_key_404(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/users/api-keys/openai/test-saved",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    def test_test_saved_unsupported_provider_400(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/users/api-keys/notaprovider/test-saved",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_test_saved_with_stored_key_succeeds(
        self, client, test_db, test_users, auth_headers
    ):
        """After storing a real (encrypted) key, the saved-test path decrypts it
        and runs the (patched) validator -> success."""
        with _patch_validate(success=True):
            client.post(
                "/api/users/api-keys/openai",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["admin"],
            )
            resp = client.post(
                "/api/users/api-keys/openai/test-saved",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"


class TestUserAvailableModelsBehavioral:
    """GET /api/users/api-keys/available-models — filters by stored providers."""

    def test_available_models_empty_without_keys(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.get(
            "/api/users/api-keys/available-models",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    def test_available_models_org_context_branch(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """X-Organization-Context routes resolution through org_api_key_service."""
        resp = client.get(
            "/api/users/api-keys/available-models",
            headers={
                **auth_headers["org_admin"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)
