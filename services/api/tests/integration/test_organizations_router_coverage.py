"""
Integration tests for organizations router handler bodies.

Targets: routers/organizations.py — list_organizations, create_organization,
         get_organization, get_organization_by_slug, update_organization,
         delete_organization, list_organization_members, update_member_role,
         remove_member, add_member
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User


def _uid():
    return str(uuid.uuid4())


@pytest.mark.integration
class TestListOrganizations:
    """GET /api/organizations/"""

    def test_list_orgs_admin(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/organizations/",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_list_orgs_has_member_count(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/organizations/",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        for org in body:
            assert "member_count" in org
            assert "id" in org
            assert "name" in org
            assert "slug" in org

    def test_list_orgs_contributor(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/organizations/",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_list_orgs_annotator(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/organizations/",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_list_orgs_has_role(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/organizations/",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        body = resp.json()
        if body:
            # Non-superadmin should have a role
            assert body[0].get("role") is not None


@pytest.mark.integration
class TestGetOrganization:
    """GET /api/organizations/{organization_id}"""

    def test_get_org_by_id(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == test_org.id
        assert body["name"] == test_org.name
        assert "member_count" in body

    def test_get_org_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/organizations/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_org_contributor_access(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestGetOrganizationBySlug:
    """GET /api/organizations/by-slug/{slug}"""

    def test_get_org_by_slug(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/by-slug/{test_org.slug}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == test_org.slug

    def test_get_org_by_slug_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/organizations/by-slug/nonexistent-slug",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_org_by_invalid_slug(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/organizations/by-slug/INVALID_SLUG!",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400


@pytest.mark.integration
class TestCreateOrganization:
    """POST /api/organizations/"""

    def test_create_org(self, client, test_db, test_users, auth_headers):
        slug = f"test-new-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "New Test Org",
                "display_name": "New Test Org Display",
                "slug": slug,
                "description": "A new test org",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == slug
        assert body["name"] == "New Test Org"

    def test_create_org_duplicate_slug(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Duplicate Slug Org",
                "display_name": "Duplicate Slug Org Display",
                "slug": test_org.slug,
                "description": "Should fail",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400


@pytest.mark.integration
class TestUpdateOrganization:
    """PUT /api/organizations/{organization_id}"""

    def test_update_org_name(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={"name": "Updated Org Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Updated Org Name"

    def test_update_org_description(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={"description": "Updated description"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == "Updated description"

    def test_update_org_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/organizations/nonexistent-id",
            json={"name": "test"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_org_annotator_forbidden(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={"name": "Annotator Update"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestDeleteOrganization:
    """DELETE /api/organizations/{organization_id}"""

    def test_delete_org(self, client, test_db, test_users, auth_headers):
        # Create a disposable org
        org = Organization(
            id=_uid(), name="Delete Me", slug=f"delete-{uuid.uuid4().hex[:8]}",
            display_name="Delete Me Display",
            created_at=datetime.utcnow(),
        )
        test_db.add(org)
        test_db.commit()

        resp = client.delete(
            f"/api/organizations/{org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "deleted" in body.get("message", "").lower() or "success" in body.get("message", "").lower()

    def test_delete_org_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            "/api/organizations/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_delete_org_non_admin(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.delete(
            f"/api/organizations/{test_org.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestListOrganizationMembers:
    """GET /api/organizations/{organization_id}/members"""

    def test_list_members(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 4  # 4 test users

    def test_list_members_has_user_info(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        if body:
            member = body[0]
            assert "user_id" in member
            assert "role" in member
            assert "is_active" in member

    def test_list_members_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/organizations/nonexistent-id/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)
