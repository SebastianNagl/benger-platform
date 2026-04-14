"""
Unit tests for org API key endpoints (Issue #1180)

Tests endpoint access control, settings toggle,
and key management operations.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from user_service import get_password_hash


@pytest.fixture
def setup_org_keys(test_db: Session):
    """Set up users, org, memberships, and feature flag for org API key tests."""
    # Users (must be created before feature flag for FK)
    admin = User(
        id="orgkey-admin",
        username="orgkeyadmin",
        email="orgkeyadmin@test.com",
        name="Org Key Admin",
        hashed_password=get_password_hash("admin123"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
    )
    member = User(
        id="orgkey-member",
        username="orgkeymember",
        email="orgkeymember@test.com",
        name="Org Key Member",
        hashed_password=get_password_hash("member123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )
    test_db.add_all([admin, member])
    test_db.flush()

    # Org
    org = Organization(
        id="orgkey-test-org",
        name="Test Org",
        display_name="Test Org",
        slug="test-org",
        settings={"require_private_keys": True},
    )
    test_db.add(org)
    test_db.flush()

    # Memberships
    admin_membership = OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=admin.id,
        organization_id=org.id,
        role="ORG_ADMIN",
        is_active=True,
    )
    member_membership = OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=member.id,
        organization_id=org.id,
        role="ANNOTATOR",
        is_active=True,
    )
    test_db.add_all([admin_membership, member_membership])
    test_db.commit()

    # Create auth tokens
    from auth_module import create_access_token

    admin_token = create_access_token(data={"user_id": admin.id})
    member_token = create_access_token(data={"user_id": member.id})

    return {
        "org": org,
        "admin": admin,
        "member": member,
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "member_headers": {"Authorization": f"Bearer {member_token}"},
    }


@pytest.mark.unit
class TestSettingsEndpoints:
    """Test GET/PUT settings for require_private_keys toggle."""

    def test_get_settings_returns_default(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["require_private_keys"] is True

    def test_member_can_read_settings(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            headers=data["member_headers"],
        )
        assert resp.status_code == 200

    def test_admin_can_toggle_settings(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["require_private_keys"] is False

        # Verify persisted
        resp2 = client.get(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            headers=data["admin_headers"],
        )
        assert resp2.json()["require_private_keys"] is False

    def test_member_cannot_toggle_settings(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=data["member_headers"],
        )
        assert resp.status_code == 403

    def test_toggle_missing_field_returns_400(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 400


@pytest.mark.unit
class TestKeyStatusEndpoint:
    """Test GET status endpoint."""

    def test_admin_gets_status(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            f"/api/organizations/{data['org'].id}/api-keys/status",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key_status" in body
        assert "available_providers" in body
        # All should be false initially
        assert all(v is False for v in body["api_key_status"].values())

    def test_member_cannot_get_status(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            f"/api/organizations/{data['org'].id}/api-keys/status",
            headers=data["member_headers"],
        )
        assert resp.status_code == 403


@pytest.mark.unit
class TestSetKeyEndpoint:
    """Test POST set key endpoint."""

    def test_admin_can_set_key_even_when_require_private_keys_true(self, client, setup_org_keys):
        """Admins can pre-configure org keys before toggling the setting."""
        data = setup_org_keys
        resp = client.post(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            json={"api_key": "sk-testapikey1234567890abcdef"},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200

    def test_admin_can_set_key_after_toggle(self, client, setup_org_keys):
        data = setup_org_keys
        # Toggle to org-pays mode
        client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=data["admin_headers"],
        )

        resp = client.post(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            json={"api_key": "sk-testapikey1234567890abcdef"},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200

    def test_member_cannot_set_key(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.post(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            json={"api_key": "sk-testapikey1234567890abcdef"},
            headers=data["member_headers"],
        )
        assert resp.status_code == 403

    def test_unsupported_provider_returns_400(self, client, setup_org_keys):
        data = setup_org_keys
        # Toggle to org-pays mode
        client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=data["admin_headers"],
        )

        resp = client.post(
            f"/api/organizations/{data['org'].id}/api-keys/unsupported",
            json={"api_key": "some-key"},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 400

    def test_missing_api_key_returns_400(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.post(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            json={},
            headers=data["admin_headers"],
        )
        assert resp.status_code == 400


@pytest.mark.unit
class TestRemoveKeyEndpoint:
    """Test DELETE key endpoint."""

    def test_admin_can_remove_key(self, client, setup_org_keys):
        data = setup_org_keys
        # Setup: toggle mode and set key
        client.put(
            f"/api/organizations/{data['org'].id}/api-keys/settings",
            json={"require_private_keys": False},
            headers=data["admin_headers"],
        )
        client.post(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            json={"api_key": "sk-testapikey1234567890abcdef"},
            headers=data["admin_headers"],
        )

        resp = client.delete(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 200

    def test_remove_nonexistent_returns_404(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.delete(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 404

    def test_member_cannot_remove_key(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.delete(
            f"/api/organizations/{data['org'].id}/api-keys/openai",
            headers=data["member_headers"],
        )
        assert resp.status_code == 403


@pytest.mark.unit
class TestNonexistentOrg:
    """Test requests to nonexistent org return 404."""

    def test_settings_nonexistent_org(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            "/api/organizations/nonexistent-org-id/api-keys/settings",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 404

    def test_status_nonexistent_org(self, client, setup_org_keys):
        data = setup_org_keys
        resp = client.get(
            "/api/organizations/nonexistent-org-id/api-keys/status",
            headers=data["admin_headers"],
        )
        assert resp.status_code == 404
