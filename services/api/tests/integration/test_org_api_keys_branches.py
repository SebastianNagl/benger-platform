"""Behavioral integration tests for the organization API-key router.

Targets uncovered branches in ``services/api/routers/org_api_keys.py`` and the
real ``services/api/services/org_api_key_service.py``. These use the real
``client`` + ``test_db`` + ``test_org`` fixtures (no mocked DB) so that:

  * permission helpers (``_require_org_exists`` / ``_require_org_admin`` /
    ``_require_org_member``) run against real memberships,
  * ``set_org_api_key`` performs real Fernet encryption and inserts a real
    ``organization_api_keys`` row,

and each test asserts persisted state by querying ``OrganizationApiKey`` after.

Permission map under the ``test_org`` fixture:
  * test_users[0] / auth_headers["admin"]      -> superadmin (manage + member)
  * test_users[3] / auth_headers["org_admin"]  -> ORG_ADMIN member (manage)
  * test_users[2] / auth_headers["annotator"]  -> ANNOTATOR member (member only)
  * test_users[1] / auth_headers["contributor"]-> CONTRIBUTOR member (member only)

Only the ``/test`` and ``/test-saved`` endpoints make a network validation
call; those patch ``user_api_key_service.validate_api_key`` to stay offline.
"""

from unittest.mock import AsyncMock, patch

from fastapi import status

from models import OrganizationApiKey

VALID_OPENAI_KEY = "sk-org-openai-key-1234567890"
VALID_ANTHROPIC_KEY = "sk-ant-org-anthropic-key-1234567890"


def _get_org_key(test_db, org_id, provider):
    test_db.expire_all()
    return (
        test_db.query(OrganizationApiKey)
        .filter(
            OrganizationApiKey.organization_id == org_id,
            OrganizationApiKey.provider == provider,
        )
        .first()
    )


def _patch_validate(success=True):
    return patch(
        "user_api_key_service.user_api_key_service.validate_api_key",
        new=AsyncMock(
            return_value=(success, "ok" if success else "bad", None if success else "auth")
        ),
    )


class TestSetOrgApiKeyBehavioral:
    """POST /{org_id}/api-keys/{provider} — real row insert + encryption."""

    def test_set_org_key_persists_row(self, client, test_db, test_users, auth_headers, test_org):
        assert _get_org_key(test_db, test_org.id, "openai") is None

        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "openai set successfully" in resp.json()["message"]

        row = _get_org_key(test_db, test_org.id, "openai")
        assert row is not None
        assert row.provider == "openai"
        assert row.organization_id == test_org.id
        assert row.created_by == test_users[3].id  # the org_admin user
        assert row.encrypted_key and VALID_OPENAI_KEY not in row.encrypted_key

    def test_set_org_key_as_superadmin(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/anthropic",
            json={"api_key": VALID_ANTHROPIC_KEY},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_200_OK
        row = _get_org_key(test_db, test_org.id, "anthropic")
        assert row is not None and row.created_by == test_users[0].id

    def test_set_org_key_upsert_updates_existing_row(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Setting the same provider twice updates the existing row, not a 2nd insert."""
        client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["org_admin"],
        )
        first = _get_org_key(test_db, test_org.id, "openai")
        first_id, first_cipher = first.id, first.encrypted_key

        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": "sk-org-openai-key-DIFFERENT-99999"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_200_OK

        # Still exactly one row, same id, but re-encrypted (different ciphertext).
        rows = (
            test_db.query(OrganizationApiKey)
            .filter(
                OrganizationApiKey.organization_id == test_org.id,
                OrganizationApiKey.provider == "openai",
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].id == first_id
        assert rows[0].encrypted_key != first_cipher

    def test_set_org_key_missing_api_key_400(self, client, test_db, auth_headers, test_org):
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "api_key is required" in resp.json()["detail"]
        assert _get_org_key(test_db, test_org.id, "openai") is None

    def test_set_org_key_unsupported_provider_400(self, client, test_db, auth_headers, test_org):
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/notaprovider",
            json={"api_key": "sk-whatever-1234567890"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported provider" in resp.json()["detail"]

    def test_set_org_key_bad_format_500_no_row(self, client, test_db, auth_headers, test_org):
        """Valid provider but malformed key -> service returns False -> 500, no row."""
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": "no-sk-prefix"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert _get_org_key(test_db, test_org.id, "openai") is None

    def test_set_org_key_org_not_found_404(self, client, test_db, auth_headers):
        resp = client.post(
            "/api/organizations/does-not-exist/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "Organization not found" in resp.json()["detail"]

    def test_set_org_key_non_admin_member_403(self, client, test_db, auth_headers, test_org):
        """An annotator is a member but not an org-admin -> 403, no row written."""
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in resp.json()["detail"].lower()
        assert _get_org_key(test_db, test_org.id, "openai") is None


class TestOrgApiKeyStatusBehavioral:
    """GET /{org_id}/api-keys/status — reflects real rows."""

    def test_status_reflects_stored_keys(self, client, test_db, auth_headers, test_org):
        client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["org_admin"],
        )
        resp = client.get(
            f"/api/organizations/{test_org.id}/api-keys/status",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["api_key_status"]["openai"] is True
        assert data["api_key_status"]["anthropic"] is False
        assert "OpenAI" in data["available_providers"]

    def test_status_non_admin_403(self, client, test_db, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/api-keys/status",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestRemoveOrgApiKeyBehavioral:
    """DELETE /{org_id}/api-keys/{provider} — deletes the real row."""

    def test_remove_deletes_row(self, client, test_db, auth_headers, test_org):
        client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["org_admin"],
        )
        assert _get_org_key(test_db, test_org.id, "openai") is not None

        resp = client.delete(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "removed successfully" in resp.json()["message"]
        assert _get_org_key(test_db, test_org.id, "openai") is None

    def test_remove_missing_key_404(self, client, test_db, auth_headers, test_org):
        """No row for provider -> service returns False -> route raises 404."""
        assert _get_org_key(test_db, test_org.id, "cohere") is None
        resp = client.delete(
            f"/api/organizations/{test_org.id}/api-keys/cohere",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    def test_remove_non_admin_403(self, client, test_db, auth_headers, test_org):
        resp = client.delete(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_remove_org_not_found_404(self, client, test_db, auth_headers):
        resp = client.delete(
            "/api/organizations/does-not-exist/api-keys/openai",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "Organization not found" in resp.json()["detail"]


class TestOrgKeyLifecycle:
    """Full set -> status -> remove lifecycle with DB-level assertions."""

    def test_full_lifecycle(self, client, test_db, auth_headers, test_org):
        # set
        client.post(
            f"/api/organizations/{test_org.id}/api-keys/mistral",
            json={"api_key": "mistral-org-key-abcdefghij1234567890"},
            headers=auth_headers["org_admin"],
        )
        assert _get_org_key(test_db, test_org.id, "mistral") is not None

        # status reflects it
        r_status = client.get(
            f"/api/organizations/{test_org.id}/api-keys/status",
            headers=auth_headers["org_admin"],
        )
        assert r_status.json()["api_key_status"]["mistral"] is True

        # remove
        r_del = client.delete(
            f"/api/organizations/{test_org.id}/api-keys/mistral",
            headers=auth_headers["org_admin"],
        )
        assert r_del.status_code == status.HTTP_200_OK
        assert _get_org_key(test_db, test_org.id, "mistral") is None


class TestOrgKeySettingsBehavioral:
    """GET/PUT /{org_id}/api-keys/settings — settings persist on Organization.settings."""

    def test_get_settings_defaults_true(self, client, test_db, auth_headers, test_org):
        """No settings stored -> require_private_keys defaults to True; member-readable."""
        resp = client.get(
            f"/api/organizations/{test_org.id}/api-keys/settings",
            headers=auth_headers["annotator"],  # plain member may read
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["require_private_keys"] is True

    def test_update_settings_persists(self, client, test_db, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["require_private_keys"] is False

        # Persisted on the Organization.settings JSON, and re-readable via GET.
        from models import Organization

        test_db.expire_all()
        org = test_db.query(Organization).filter(Organization.id == test_org.id).first()
        assert org.settings.get("require_private_keys") is False

        r_get = client.get(
            f"/api/organizations/{test_org.id}/api-keys/settings",
            headers=auth_headers["org_admin"],
        )
        assert r_get.json()["require_private_keys"] is False

    def test_update_settings_missing_field_400(self, client, test_db, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}/api-keys/settings",
            json={},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "require_private_keys is required" in resp.json()["detail"]

    def test_update_settings_non_admin_403(self, client, test_db, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}/api-keys/settings",
            json={"require_private_keys": True},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestTestSavedOrgKeyBehavioral:
    """POST /{org_id}/api-keys/{provider}/test-saved — reads the real stored key."""

    def test_test_saved_no_key_404(self, client, test_db, auth_headers, test_org):
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai/test-saved",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "No API key found" in resp.json()["detail"]

    def test_test_saved_with_stored_key_success(self, client, test_db, auth_headers, test_org):
        client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai",
            json={"api_key": VALID_OPENAI_KEY},
            headers=auth_headers["org_admin"],
        )
        with _patch_validate(success=True):
            resp = client.post(
                f"/api/organizations/{test_org.id}/api-keys/openai/test-saved",
                headers=auth_headers["org_admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"


class TestTestOrgKeyBehavioral:
    """POST /{org_id}/api-keys/{provider}/test — unsaved key, network patched."""

    def test_test_unsaved_key_success(self, client, test_db, auth_headers, test_org):
        with _patch_validate(success=True):
            resp = client.post(
                f"/api/organizations/{test_org.id}/api-keys/openai/test",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["org_admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"

    def test_test_unsaved_key_missing_400(self, client, test_db, auth_headers, test_org):
        resp = client.post(
            f"/api/organizations/{test_org.id}/api-keys/openai/test",
            json={},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_test_unsaved_key_invalid_returns_error(self, client, test_db, auth_headers, test_org):
        with _patch_validate(success=False):
            resp = client.post(
                f"/api/organizations/{test_org.id}/api-keys/openai/test",
                json={"api_key": VALID_OPENAI_KEY},
                headers=auth_headers["org_admin"],
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "error"


class TestOrgAvailableModelsBehavioral:
    """GET /{org_id}/api-keys/available-models — member-readable, returns a list."""

    def test_available_models_member_ok(self, client, test_db, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/api-keys/available-models",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    def test_available_models_org_not_found_404(self, client, test_db, auth_headers):
        resp = client.get(
            "/api/organizations/does-not-exist/api-keys/available-models",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
