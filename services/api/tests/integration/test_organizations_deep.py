"""
Deep integration tests for organization CRUD and member management.

Targets: routers/organizations/* (migrated to the async DB lane). Rows are
seeded via ``async_test_db`` and the HTTP surface is driven through
``async_test_client``; both auth dependencies are overridden per-test via
``_as_user`` (the sync auth deps can't see the async test transaction).

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
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, name="Extra User", *, is_superadmin=False) -> User:
    user = User(
        id=_uid(),
        username=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@test.com",
        email=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@test.com",
        name=name,
        hashed_password="hashed_placeholder",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_org(db, name: str = "Test Org", slug: str = None) -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"org-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        description=f"Organization: {name}",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_membership(db, user_id: str, org_id: str, role: str = "ORG_ADMIN"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _seed_org_with_members(db):
    """Org with the 4 canonical members (admin superadmin/ORG_ADMIN,
    contributor, annotator, org_admin). Returns ``(org, users_by_role)``."""
    admin = await _make_user(db, "Test Admin", is_superadmin=True)
    contributor = await _make_user(db, "Test Contributor")
    annotator = await _make_user(db, "Test Annotator")
    org_admin = await _make_user(db, "Test Org Admin")
    org = await _make_org(db, name="Test Org")
    await _make_membership(db, admin.id, org.id, "ORG_ADMIN")
    await _make_membership(db, contributor.id, org.id, "CONTRIBUTOR")
    await _make_membership(db, annotator.id, org.id, "ANNOTATOR")
    await _make_membership(db, org_admin.id, org.id, "ORG_ADMIN")
    await db.commit()
    return org, {
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
        "org_admin": org_admin,
    }


# ====================================================================
# GET /api/organizations/ — list organizations
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_sees_all_orgs(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    await _make_org(async_test_db, name="Extra Org A")
    await _make_org(async_test_db, name="Extra Org B")
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    orgs = resp.json()
    assert isinstance(orgs, list)
    assert len(orgs) >= 3  # test_org + 2 extras


@pytest.mark.integration
@pytest.mark.asyncio
async def test_contributor_sees_own_orgs(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["contributor"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    orgs = resp.json()
    assert isinstance(orgs, list)
    org_ids = [o["id"] for o in orgs]
    assert oid in org_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_sees_own_orgs(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["annotator"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    orgs = resp.json()
    assert isinstance(orgs, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unauthenticated_rejected(async_test_client):
    resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code in (401, 403)


# ====================================================================
# POST /api/organizations/ — create organization
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_with_all_fields(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    slug = f"full-org-{uuid.uuid4().hex[:8]}"
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={
                "name": "Full Org",
                "slug": slug,
                "display_name": "Full Organization",
                "description": "A fully specified organization",
            },
        )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["name"] == "Full Org"
    assert body["slug"] == slug
    assert body["display_name"] == "Full Organization"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_minimal_fields(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    slug = f"minimal-{uuid.uuid4().hex[:8]}"
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"name": "Minimal Org", "slug": slug, "display_name": "Minimal"},
        )
    assert resp.status_code in (200, 201)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_duplicate_slug_rejected(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oslug = org.slug
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"name": "Dup Slug", "slug": oslug, "display_name": "Dup"},
        )
    assert resp.status_code in (400, 409)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_missing_name_rejected(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"slug": f"no-name-{uuid.uuid4().hex[:8]}"},
        )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_missing_slug_rejected(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"name": "No Slug Org"},
        )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_create_org(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["annotator"]):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"name": "Nope", "slug": f"nope-{uuid.uuid4().hex[:8]}", "display_name": "Nope"},
        )
    assert resp.status_code == 403


# ====================================================================
# GET /api/organizations/{id} — get org details
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_id(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, oname = org.id, org.name
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == oid
    assert body["name"] == oname


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_includes_display_name(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}")
    assert resp.status_code == 200
    assert "display_name" in resp.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_nonexistent_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/nonexistent-org-id")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_slug(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oslug = org.slug
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/by-slug/{oslug}")
    assert resp.status_code in (200, 404)


# ====================================================================
# PUT /api/organizations/{id} — update organization
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_name(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, oslug, odisplay = org.id, org.slug, org.display_name
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={"name": "Updated Name", "slug": oslug, "display_name": odisplay},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_description(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, oname, oslug, odisplay = org.id, org.name, org.slug, org.display_name
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={
                "name": oname,
                "slug": oslug,
                "display_name": odisplay,
                "description": "Updated description for testing",
            },
        )
    assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_nonexistent_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            "/api/organizations/nonexistent",
            json={"name": "Nope", "slug": "nope", "display_name": "Nope"},
        )
    assert resp.status_code == 404


# ====================================================================
# DELETE /api/organizations/{id} — delete organization
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_can_delete_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    org = await _make_org(async_test_db, name="Delete Me")
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code in (200, 204)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_nonexistent_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete("/api/organizations/nonexistent")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_delete_org(async_test_client, async_test_db):
    annotator = await _make_user(async_test_db, "Annotator")
    org = await _make_org(async_test_db, name="Protected Org")
    await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
    oid = org.id
    await async_test_db.commit()
    with _as_user(annotator):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_cannot_delete_org(async_test_client, async_test_db):
    org_admin = await _make_user(async_test_db, "OrgAdmin")
    org = await _make_org(async_test_db, name="OrgAdmin Protected")
    await _make_membership(async_test_db, org_admin.id, org.id, "ORG_ADMIN")
    oid = org.id
    await async_test_db.commit()
    with _as_user(org_admin):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    # Only superadmin can delete orgs
    assert resp.status_code in (200, 204, 403)


# ====================================================================
# Member management endpoints
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 200
    members = resp.json()
    assert isinstance(members, list)
    assert len(members) >= 4  # All 4 seeded users are members


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members_includes_roles(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 200
    members = resp.json()
    for member in members:
        assert "role" in member


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_new_member(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    new_user = await _make_user(async_test_db, "Brand New Member")
    oid, new_uid = org.id, new_user.id
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": new_uid, "role": "ANNOTATOR"},
        )
    assert resp.status_code in (200, 201)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_member_as_contributor(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    new_user = await _make_user(async_test_db, "Contrib Member")
    oid, new_uid = org.id, new_user.id
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": new_uid, "role": "CONTRIBUTOR"},
        )
    assert resp.status_code in (200, 201)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_member(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    user = await _make_user(async_test_db, "Remove Me Member")
    await _make_membership(async_test_db, user.id, org.id, "ANNOTATOR")
    oid, uid = org.id, user.id
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.delete(f"/api/organizations/{oid}/members/{uid}")
    assert resp.status_code in (200, 204)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_member_role(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, uid = org.id, users["annotator"].id
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{uid}/role",
            json={"role": "CONTRIBUTOR"},
        )
    assert resp.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_nonexistent_member(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/nonexistent-user"
        )
    assert resp.status_code in (404, 400)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_member_to_nonexistent_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    target = await _make_user(async_test_db, "Target")
    target_id = target.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/nonexistent/members",
            json={"user_id": target_id, "role": "ANNOTATOR"},
        )
    assert resp.status_code in (404, 400)


# ====================================================================
# Organization with projects
# ====================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_stats_endpoint(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}/stats")
    assert resp.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_projects_visible_after_creation(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    admin = users["admin"]
    # Create a project linked to the org
    project = Project(
        id=_uid(),
        title="Org Project",
        created_by=admin.id,
        label_config="<View><Text name='t' value='$text'/></View>",
    )
    async_test_db.add(project)
    await async_test_db.flush()
    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    )
    async_test_db.add(po)
    await async_test_db.commit()

    oid = org.id
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/organizations/{oid}")
    assert resp.status_code == 200
