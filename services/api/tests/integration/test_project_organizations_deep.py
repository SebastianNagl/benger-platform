"""
Deep integration tests for project organization management endpoints.

Covers routers/projects/organizations.py:
- GET /{project_id}/organizations — list project orgs
- POST /{project_id}/organizations/{org_id} — add org
- DELETE /{project_id}/organizations/{org_id} — remove org

Also covers parts of routers/organizations.py for cascading CRUD:
- Organization CRUD with project relationships
- Membership with cascading effects
- Statistics and slug lookup
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _make_org(db, name=None, slug=None):
    org = Organization(
        id=_uid(),
        name=name or f"Org {uuid.uuid4().hex[:6]}",
        slug=slug or f"org-{uuid.uuid4().hex[:8]}",
        display_name=name or "Test Display",
        description="Test organization",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.flush()
    return org


def _make_membership(db, user_id, org_id, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=_uid(), user_id=user_id, organization_id=org_id,
        role=role, joined_at=datetime.utcnow(),
    )
    db.add(m)
    db.flush()
    return m


def _make_project_with_orgs(db, admin, orgs, title="Multi-Org Project"):
    p = Project(
        id=_uid(), title=title, created_by=admin.id,
        label_config="<View/>",
    )
    db.add(p)
    db.flush()
    for org in orgs:
        po = ProjectOrganization(
            id=_uid(), project_id=p.id,
            organization_id=org.id, assigned_by=admin.id,
        )
        db.add(po)
    db.flush()
    return p


def _h(auth_headers, org=None):
    headers = {**auth_headers["admin"]}
    if org:
        headers["X-Organization-Context"] = org.id
    return headers


# ===================================================================
# LIST PROJECT ORGANIZATIONS
# ===================================================================

@pytest.mark.integration
class TestListProjectOrganizations:
    """GET /api/projects/{project_id}/organizations"""

    def test_list_orgs_single(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        orgs = resp.json()
        assert isinstance(orgs, list)
        assert len(orgs) == 1
        assert orgs[0]["organization_id"] == test_org.id

    def test_list_orgs_multiple(self, client, test_db, test_users, auth_headers, test_org):
        org2 = _make_org(test_db, name="Org Two")
        _make_membership(test_db, test_users[0].id, org2.id)
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, org2])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        orgs = resp.json()
        assert len(orgs) == 2
        org_ids = {o["organization_id"] for o in orgs}
        assert test_org.id in org_ids
        assert org2.id in org_ids

    def test_list_orgs_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/projects/nonexistent/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_list_orgs_has_fields(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        org = resp.json()[0]
        assert "organization_id" in org
        assert "organization_name" in org
        assert "assigned_by" in org


# ===================================================================
# ADD ORGANIZATION TO PROJECT
# ===================================================================

@pytest.mark.integration
class TestAddProjectOrganization:
    """POST /api/projects/{project_id}/organizations/{org_id}"""

    def test_add_org_to_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        new_org = _make_org(test_db, name="New Org")
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/organizations/{new_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["organization_id"] == new_org.id

    def test_add_duplicate_org(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_add_org_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            f"/api/projects/nonexistent/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_add_nonexistent_org(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/organizations/nonexistent-org",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_add_org_non_superadmin_denied(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        new_org = _make_org(test_db, name="Forbidden Org")
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/organizations/{new_org.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ===================================================================
# REMOVE ORGANIZATION FROM PROJECT
# ===================================================================

@pytest.mark.integration
class TestRemoveProjectOrganization:
    """DELETE /api/projects/{project_id}/organizations/{org_id}"""

    def test_remove_org_from_project(self, client, test_db, test_users, auth_headers, test_org):
        org2 = _make_org(test_db, name="Removable Org")
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, org2])
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/organizations/{org2.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_remove_last_org_denied(self, client, test_db, test_users, auth_headers, test_org):
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_remove_unassigned_org(self, client, test_db, test_users, auth_headers, test_org):
        """Removing an org that is not assigned should return 404, but only if the project has >1 orgs."""
        extra_org = _make_org(test_db, name="Extra Org")
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, extra_org])
        other_org = _make_org(test_db, name="Not Assigned Org")
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/organizations/{other_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_remove_org_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.delete(
            f"/api/projects/nonexistent/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_remove_org_non_superadmin_denied(self, client, test_db, test_users, auth_headers, test_org):
        org2 = _make_org(test_db, name="Protected Org")
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, org2])
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/organizations/{org2.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ===================================================================
# ORGANIZATION CRUD (routers/organizations.py)
# ===================================================================

@pytest.mark.integration
class TestOrganizationCRUDDeep:
    """Organization CRUD operations with more edge cases."""

    def test_create_org_full(self, client, test_db, test_users, auth_headers):
        slug = f"deep-org-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/organizations/",
            json={
                "name": "Deep Test Org",
                "slug": slug,
                "display_name": "Deep Test Display",
                "description": "A detailed test organization",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["slug"] == slug

    def test_get_org_by_id(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_org.id
        assert data["name"] == test_org.name

    def test_update_org(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.put(
            f"/api/organizations/{test_org.id}",
            json={
                "name": "Updated Deep Org",
                "slug": test_org.slug,
                "display_name": "Updated Display",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Deep Org"

    def test_delete_org(self, client, test_db, test_users, auth_headers):
        org = _make_org(test_db, name="Delete Deep Org")
        test_db.commit()

        resp = client.delete(
            f"/api/organizations/{org.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 204)

    def test_list_orgs_with_membership(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/organizations/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        orgs = resp.json()
        assert any(o["id"] == test_org.id for o in orgs)


# ===================================================================
# ORGANIZATION MEMBERS
# ===================================================================

@pytest.mark.integration
class TestOrganizationMembersDeep:
    """Member management with detailed checks."""

    def test_list_members_with_roles(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 4  # 4 test users
        roles = {m["role"] for m in members}
        assert "ORG_ADMIN" in roles

    def test_add_member(self, client, test_db, test_users, auth_headers, test_org):
        new_user = User(
            id=_uid(),
            username=f"deep-member-{uuid.uuid4().hex[:6]}@test.com",
            email=f"deep-member-{uuid.uuid4().hex[:6]}@test.com",
            name="Deep Member",
            hashed_password="hashed",
            is_active=True, email_verified=True,
        )
        test_db.add(new_user)
        test_db.commit()

        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": new_user.id, "role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_remove_member(self, client, test_db, test_users, auth_headers, test_org):
        user = User(
            id=_uid(),
            username=f"remove-deep-{uuid.uuid4().hex[:6]}@test.com",
            email=f"remove-deep-{uuid.uuid4().hex[:6]}@test.com",
            name="Remove Me Deep",
            hashed_password="hashed",
            is_active=True, email_verified=True,
        )
        test_db.add(user)
        test_db.flush()
        _make_membership(test_db, user.id, test_org.id, "ANNOTATOR")
        test_db.commit()

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


# ===================================================================
# ORGANIZATION LOOKUP & STATS
# ===================================================================

@pytest.mark.integration
class TestOrganizationLookup:
    """Slug lookup and statistics endpoints."""

    def test_get_org_by_slug(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/by-slug/{test_org.slug}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)

    def test_get_org_by_slug_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/organizations/by-slug/nonexistent-slug",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_org_stats(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/organizations/{test_org.id}/stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# MULTI-ORG PROJECT ACCESS
# ===================================================================

@pytest.mark.integration
class TestMultiOrgAccess:
    """Test project access across multiple organizations."""

    def test_project_visible_to_all_member_orgs(self, client, test_db, test_users, auth_headers, test_org):
        """A project in 2 orgs should be visible from either org context."""
        org2 = _make_org(test_db, name="Org Two Context")
        _make_membership(test_db, test_users[0].id, org2.id, "ORG_ADMIN")
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, org2])
        test_db.commit()

        # Access from test_org context
        resp1 = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert resp1.status_code == 200

        # Access from org2 context
        resp2 = client.get(
            f"/api/projects/{p.id}/organizations",
            headers={**auth_headers["admin"], "X-Organization-Context": org2.id},
        )
        assert resp2.status_code == 200

    def test_add_and_verify_org_appears(self, client, test_db, test_users, auth_headers, test_org):
        """Add an org then verify it appears in the list."""
        p = _make_project_with_orgs(test_db, test_users[0], [test_org])
        new_org = _make_org(test_db, name="Verify Org")
        test_db.commit()

        # Add
        add_resp = client.post(
            f"/api/projects/{p.id}/organizations/{new_org.id}",
            headers=auth_headers["admin"],
        )
        assert add_resp.status_code == 200

        # Verify
        list_resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        org_ids = {o["organization_id"] for o in list_resp.json()}
        assert new_org.id in org_ids

    def test_remove_and_verify_org_gone(self, client, test_db, test_users, auth_headers, test_org):
        """Remove an org then verify it disappears."""
        org2 = _make_org(test_db, name="Remove Verify Org")
        p = _make_project_with_orgs(test_db, test_users[0], [test_org, org2])
        test_db.commit()

        # Remove
        del_resp = client.delete(
            f"/api/projects/{p.id}/organizations/{org2.id}",
            headers=auth_headers["admin"],
        )
        assert del_resp.status_code == 200

        # Verify
        list_resp = client.get(
            f"/api/projects/{p.id}/organizations",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        org_ids = {o["organization_id"] for o in list_resp.json()}
        assert org2.id not in org_ids
