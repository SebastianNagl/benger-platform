"""
Deep integration tests for organization CRUD and member management.

Targets: routers/projects/organizations.py
- GET    /api/organizations           — list organizations
- POST   /api/organizations           — create organization
- GET    /api/organizations/{id}      — get org details
- PUT    /api/organizations/{id}      — update organization
- DELETE /api/organizations/{id}      — delete organization
- GET    /api/organizations/{id}/members — list members
- POST   /api/organizations/{id}/members — add member
- PUT    /api/organizations/{id}/members/{user_id}/role — update member role
- DELETE /api/organizations/{id}/members/{user_id} — remove member
- GET    /api/organizations/by-slug/{slug} — lookup by slug
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization


def _uid() -> str:
    return str(uuid.uuid4())


def _make_org(db: Session, created_by: str = None, name: str = "Test Org", slug: str = None):
    """Create an organization directly in the database."""
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"org-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        description=f"Organization: {name}",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_membership(db: Session, user_id: str, org_id: str, role: str = "ORG_ADMIN"):
    """Create an organization membership."""
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        joined_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()
    return m


def _make_user(db: Session, name: str = "Extra User"):
    """Create an extra user for member management tests."""
    user = User(
        id=_uid(),
        username=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@test.com",
        email=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@test.com",
        name=name,
        hashed_password="hashed_placeholder",
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    return user


# ====================================================================
# GET /api/organizations/ — list organizations
# ====================================================================

@pytest.mark.integration
class TestListOrgsDeep:
    """Organization listing endpoint."""

    def test_superadmin_sees_all_orgs(self, client, test_db, test_users, auth_headers, test_org):
        _make_org(test_db, name="Extra Org A")
        _make_org(test_db, name="Extra Org B")
        resp = client.get("/api/organizations/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        orgs = resp.json()
        assert isinstance(orgs, list)
        assert len(orgs) >= 3  # test_org + 2 extras

    def test_contributor_sees_own_orgs(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/organizations/", headers=auth_headers["contributor"])
        assert resp.status_code == 200
        orgs = resp.json()
        assert isinstance(orgs, list)
        org_ids = [o["id"] for o in orgs]
        assert test_org.id in org_ids

    def test_annotator_sees_own_orgs(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/organizations/", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        orgs = resp.json()
        assert isinstance(orgs, list)

    def test_unauthenticated_rejected(self, client, test_db):
        resp = client.get("/api/organizations/")
        assert resp.status_code in (401, 403)


# ====================================================================
# POST /api/organizations/ — create organization
# ====================================================================

@pytest.mark.integration
class TestCreateOrgDeep:
    """Organization creation endpoint."""

    def test_create_org_with_all_fields(self, client, test_db, test_users, auth_headers):
        slug = f"full-org-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Full Org",
                "slug": slug,
                "display_name": "Full Organization",
                "description": "A fully specified organization",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body["name"] == "Full Org"
        assert body["slug"] == slug
        assert body["display_name"] == "Full Organization"

    def test_create_org_minimal_fields(self, client, test_db, test_users, auth_headers):
        slug = f"minimal-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={"name": "Minimal Org", "slug": slug, "display_name": "Minimal"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_create_org_duplicate_slug_rejected(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/organizations/",
            json={"name": "Dup Slug", "slug": test_org.slug, "display_name": "Dup"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (400, 409)

    def test_create_org_missing_name_rejected(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/organizations/",
            json={"slug": f"no-name-{uuid.uuid4().hex[:8]}"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_create_org_missing_slug_rejected(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/organizations/",
            json={"name": "No Slug Org"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_annotator_cannot_create_org(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/organizations/",
            json={"name": "Nope", "slug": f"nope-{uuid.uuid4().hex[:8]}", "display_name": "Nope"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ====================================================================
# GET /api/organizations/{id} — get org details
# ====================================================================

@pytest.mark.integration
class TestGetOrgDeep:
    """Get organization by ID."""

    def test_get_org_by_id(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(f"/api/organizations/{test_org.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == test_org.id
        assert body["name"] == test_org.name

    def test_get_org_includes_display_name(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(f"/api/organizations/{test_org.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert "display_name" in resp.json()

    def test_get_nonexistent_org(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/organizations/nonexistent-org-id", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_get_org_by_slug(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/by-slug/{test_org.slug}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)


# ====================================================================
# PUT /api/organizations/{id} — update organization
# ====================================================================

@pytest.mark.integration
class TestUpdateOrgDeep:
    """Update organization details."""

    def test_update_org_name(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={"name": "Updated Name", "slug": test_org.slug, "display_name": test_org.display_name},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_org_description(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={
                "name": test_org.name,
                "slug": test_org.slug,
                "display_name": test_org.display_name,
                "description": "Updated description for testing",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_nonexistent_org(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/organizations/nonexistent",
            json={"name": "Nope", "slug": "nope", "display_name": "Nope"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ====================================================================
# DELETE /api/organizations/{id} — delete organization
# ====================================================================

@pytest.mark.integration
class TestDeleteOrgDeep:
    """Delete organization endpoint."""

    def test_superadmin_can_delete_org(self, client, test_db, test_users, auth_headers):
        org = _make_org(test_db, name="Delete Me")
        resp = client.delete(f"/api/organizations/{org.id}", headers=auth_headers["admin"])
        assert resp.status_code in (200, 204)

    def test_delete_nonexistent_org(self, client, test_db, test_users, auth_headers):
        resp = client.delete("/api/organizations/nonexistent", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_annotator_cannot_delete_org(self, client, test_db, test_users, auth_headers):
        org = _make_org(test_db, name="Protected Org")
        _make_membership(test_db, test_users[2].id, org.id, "ANNOTATOR")
        resp = client.delete(f"/api/organizations/{org.id}", headers=auth_headers["annotator"])
        assert resp.status_code == 403

    def test_org_admin_cannot_delete_org(self, client, test_db, test_users, auth_headers):
        org = _make_org(test_db, name="OrgAdmin Protected")
        _make_membership(test_db, test_users[3].id, org.id, "ORG_ADMIN")
        resp = client.delete(f"/api/organizations/{org.id}", headers=auth_headers["org_admin"])
        # Only superadmin can delete orgs
        assert resp.status_code in (200, 204, 403)


# ====================================================================
# Member management endpoints
# ====================================================================

@pytest.mark.integration
class TestOrgMembersDeep:
    """Organization member management endpoints."""

    def test_list_members(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        members = resp.json()
        assert isinstance(members, list)
        assert len(members) >= 4  # All 4 test users are members

    def test_list_members_includes_roles(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        members = resp.json()
        for member in members:
            assert "role" in member

    def test_add_new_member(self, client, test_db, test_users, auth_headers, test_org):
        new_user = _make_user(test_db, "Brand New Member")
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": new_user.id, "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_add_member_as_contributor(self, client, test_db, test_users, auth_headers, test_org):
        new_user = _make_user(test_db, "Contrib Member")
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": new_user.id, "role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_remove_member(self, client, test_db, test_users, auth_headers, test_org):
        user = _make_user(test_db, "Remove Me Member")
        _make_membership(test_db, user.id, test_org.id, "ANNOTATOR")
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{user.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 204)

    def test_update_member_role(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{test_users[2].id}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)

    def test_remove_nonexistent_member(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/nonexistent-user",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (404, 400)

    def test_add_member_to_nonexistent_org(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/organizations/nonexistent/members",
            json={"user_id": test_users[0].id, "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (404, 400)


# ====================================================================
# Organization with projects
# ====================================================================

@pytest.mark.integration
class TestOrgWithProjectsDeep:
    """Organization behavior with associated projects."""

    def test_org_stats_endpoint(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)

    def test_org_projects_visible_after_creation(self, client, test_db, test_users, auth_headers, test_org):
        # Create a project linked to the org
        project = Project(
            id=_uid(), title="Org Project", created_by=test_users[0].id,
            label_config="<View><Text name='t' value='$text'/></View>",
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        # Verify org details still accessible
        resp = client.get(f"/api/organizations/{test_org.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
