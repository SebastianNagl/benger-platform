"""
Coverage boost tests for organization endpoints.

Targets specific branches in routers/organizations.py:
- list_organizations for superadmin vs regular user
- create_organization with various inputs
- get_organization
- update_organization
- delete_organization
- list/add/update/remove members
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User


def _make_org(db, name="Test Org", slug=None):
    org = Organization(
        id=str(uuid.uuid4()),
        name=name,
        slug=slug or f"test-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        description="test org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()
    return org


def _add_membership(db, user_id, org_id, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        joined_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()
    return m


class TestListOrganizations:
    """Test list_organizations endpoint."""

    def test_list_orgs_superadmin(self, client, auth_headers, test_db, test_users):
        _make_org(test_db, "Org A")
        _make_org(test_db, "Org B")

        resp = client.get("/api/organizations/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_list_orgs_regular_user(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "My Org")
        _add_membership(test_db, test_users[1].id, org.id, "CONTRIBUTOR")

        resp = client.get("/api/organizations/", headers=auth_headers["contributor"])
        assert resp.status_code == 200
        data = resp.json()
        names = [o["name"] for o in data]
        assert "My Org" in names

    def test_list_orgs_no_memberships(self, client, auth_headers, test_db, test_users):
        resp = client.get("/api/organizations/", headers=auth_headers["annotator"])
        assert resp.status_code == 200

    def test_list_orgs_superadmin_with_role(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Admin Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")

        resp = client.get("/api/organizations/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        admin_orgs = [o for o in data if o["name"] == "Admin Org"]
        assert len(admin_orgs) >= 1

    def test_list_orgs_member_counts(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Count Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")
        _add_membership(test_db, test_users[1].id, org.id, "CONTRIBUTOR")
        _add_membership(test_db, test_users[2].id, org.id, "ANNOTATOR")

        resp = client.get("/api/organizations/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        count_orgs = [o for o in data if o["name"] == "Count Org"]
        assert len(count_orgs) >= 1
        assert count_orgs[0]["member_count"] == 3


class TestCreateOrganization:
    """Test create_organization endpoint."""

    def test_create_org_superadmin(self, client, auth_headers):
        slug = f"new-org-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "New Organization",
                "display_name": "New Organization Display",
                "slug": slug,
                "description": "A brand new org",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Organization"
        assert data["slug"] == slug

    def test_create_org_with_settings(self, client, auth_headers):
        slug = f"settings-org-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Settings Org",
                "display_name": "Settings Org Display",
                "slug": slug,
                "settings": {"theme": "dark", "language": "de"},
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_org_duplicate_slug(self, client, auth_headers, test_db):
        slug = f"dup-slug-{uuid.uuid4().hex[:8]}"
        _make_org(test_db, "First", slug)

        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Second",
                "display_name": "Second Display",
                "slug": slug,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in [400, 409, 500]

    def test_create_org_invalid_slug(self, client, auth_headers):
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Invalid Slug",
                "display_name": "Invalid Slug Display",
                "slug": "INVALID SLUG WITH SPACES",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_create_org_annotator_forbidden(self, client, auth_headers):
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Forbidden",
                "display_name": "Forbidden Display",
                "slug": f"forbidden-{uuid.uuid4().hex[:8]}",
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


class TestGetOrganization:
    """Test get_organization endpoint."""

    def test_get_org_success(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Get Org")
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.get(f"/api/organizations/{org.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Org"

    def test_get_org_not_found(self, client, auth_headers):
        resp = client.get("/api/organizations/nonexistent", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_get_org_by_slug(self, client, auth_headers, test_db, test_users):
        slug = f"slug-get-{uuid.uuid4().hex[:8]}"
        org = _make_org(test_db, "Slug Org", slug)
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.get(f"/api/organizations/by-slug/{slug}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["slug"] == slug

    def test_get_org_by_slug_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/organizations/by-slug/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestUpdateOrganization:
    """Test update_organization endpoint."""

    def test_update_org_name(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Update Org")
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.put(
            f"/api/organizations/{org.id}",
            json={"name": "Updated Org"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Org"

    def test_update_org_description(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Desc Org")
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.put(
            f"/api/organizations/{org.id}",
            json={"description": "New description"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_org_settings(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Settings Update")
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.put(
            f"/api/organizations/{org.id}",
            json={"settings": {"key": "value"}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_org_not_found(self, client, auth_headers):
        resp = client.put(
            "/api/organizations/nonexistent",
            json={"name": "X"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_org_no_permission(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "No Perm Org")
        _add_membership(test_db, test_users[2].id, org.id, "ANNOTATOR")

        resp = client.put(
            f"/api/organizations/{org.id}",
            json={"name": "Hacked"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_deactivate_org(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Deactivate Org")
        _add_membership(test_db, test_users[0].id, org.id)

        resp = client.put(
            f"/api/organizations/{org.id}",
            json={"is_active": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


class TestDeleteOrganization:
    """Test delete_organization endpoint."""

    def test_delete_org_superadmin(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Delete Org")

        resp = client.delete(f"/api/organizations/{org.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_delete_org_not_found(self, client, auth_headers):
        resp = client.delete("/api/organizations/nonexistent", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_delete_org_not_superadmin(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "No Delete")
        _add_membership(test_db, test_users[1].id, org.id, "CONTRIBUTOR")

        resp = client.delete(f"/api/organizations/{org.id}", headers=auth_headers["contributor"])
        assert resp.status_code == 403


class TestListOrgMembers:
    """Test list_organization_members endpoint."""

    def test_list_members(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Members Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")
        _add_membership(test_db, test_users[1].id, org.id, "CONTRIBUTOR")
        _add_membership(test_db, test_users[2].id, org.id, "ANNOTATOR")

        resp = client.get(
            f"/api/organizations/{org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

    def test_list_members_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/organizations/nonexistent/members",
            headers=auth_headers["admin"],
        )
        # Superadmin may get empty list or 404 depending on implementation
        assert resp.status_code in [200, 404]


class TestAddOrgMember:
    """Test add_organization_member endpoint."""

    def test_add_member_as_admin(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Add Member Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")

        resp = client.post(
            f"/api/organizations/{org.id}/members",
            json={"user_id": test_users[1].id, "role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_add_member_org_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.post(
            "/api/organizations/nonexistent/members",
            json={"user_id": test_users[0].id, "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_add_member_user_not_found(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "No User Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")

        resp = client.post(
            f"/api/organizations/{org.id}/members",
            json={"user_id": "nonexistent-user-id", "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_add_duplicate_member(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Dup Member Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")
        _add_membership(test_db, test_users[1].id, org.id, "ANNOTATOR")

        resp = client.post(
            f"/api/organizations/{org.id}/members",
            json={"user_id": test_users[1].id, "role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in [400, 409]


class TestUpdateMemberRole:
    """Test update_member_role endpoint."""

    def test_update_role(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Update Role Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")
        _add_membership(test_db, test_users[1].id, org.id, "ANNOTATOR")

        resp = client.put(
            f"/api/organizations/{org.id}/members/{test_users[1].id}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_role_org_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.put(
            f"/api/organizations/nonexistent/members/{test_users[0].id}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestRemoveOrgMember:
    """Test remove_organization_member endpoint."""

    def test_remove_member(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "Remove Member Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")
        _add_membership(test_db, test_users[1].id, org.id, "ANNOTATOR")

        resp = client.delete(
            f"/api/organizations/{org.id}/members/{test_users[1].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_remove_member_not_found(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, "No Remove Org")
        _add_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")

        resp = client.delete(
            f"/api/organizations/{org.id}/members/nonexistent-user",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_remove_member_org_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.delete(
            f"/api/organizations/nonexistent/members/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
