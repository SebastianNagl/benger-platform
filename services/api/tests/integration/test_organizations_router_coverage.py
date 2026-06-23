"""
Integration tests for organizations router handler bodies.

Targets: routers/organizations/* — list_organizations, create_organization,
         get_organization, get_organization_by_slug, update_organization,
         delete_organization, list_organization_members, update_member_role,
         remove_member, add_member.

These handlers were migrated to the async DB lane (``Depends(get_async_db)``),
so rows are seeded through ``async_test_db`` and the HTTP surface is driven via
``async_test_client``. The sync auth dependencies (``require_user`` /
``get_current_user``) can't see the async test transaction, so each test
overrides both via ``_as_user``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User


def _uid():
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


async def _make_user(db, *, is_superadmin=False, username_prefix="orguser") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Org User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Test Organization", slug=None) -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"test-org-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        description=f"Test organization: {name}",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user_id, org_id, role="ANNOTATOR"):
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
    """Replicates the legacy ``test_org`` fixture: an org with 4 members
    (admin/ORG_ADMIN superadmin, contributor, annotator, org_admin).

    Returns ``(org, users_by_role)`` where users_by_role maps
    "admin"/"contributor"/"annotator"/"org_admin" to the seeded User.
    """
    admin = await _make_user(db, is_superadmin=True, username_prefix="admin")
    contributor = await _make_user(db, username_prefix="contributor")
    annotator = await _make_user(db, username_prefix="annotator")
    org_admin = await _make_user(db, username_prefix="orgadmin")
    org = await _make_org(db)
    await _add_membership(db, admin.id, org.id, "ORG_ADMIN")
    await _add_membership(db, contributor.id, org.id, "CONTRIBUTOR")
    await _add_membership(db, annotator.id, org.id, "ANNOTATOR")
    await _add_membership(db, org_admin.id, org.id, "ORG_ADMIN")
    await db.commit()
    return org, {
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
        "org_admin": org_admin,
    }


# ---------------------------------------------------------------------------
# GET /api/organizations/
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_admin(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["admin"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_has_member_count(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["admin"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    body = resp.json()
    for org_obj in body:
        assert "member_count" in org_obj
        assert "id" in org_obj
        assert "name" in org_obj
        assert "slug" in org_obj


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_contributor(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["contributor"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_annotator(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["annotator"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_has_role(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    with _as_user(users["contributor"]):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    body = resp.json()
    if body:
        # Non-superadmin should have a role
        assert body[0].get("role") is not None


# ---------------------------------------------------------------------------
# GET /api/organizations/{organization_id}
# ---------------------------------------------------------------------------

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
    assert "member_count" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_contributor_access(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["contributor"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/organizations/by-slug/{slug}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_slug(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oslug = org.slug
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/by-slug/{oslug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == oslug


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_slug_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/by-slug/nonexistent-slug")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_invalid_slug(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/by-slug/INVALID_SLUG!")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/organizations/
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    slug = f"test-new-{uuid.uuid4().hex[:8]}"
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={
                "name": "New Test Org",
                "display_name": "New Test Org Display",
                "slug": slug,
                "description": "A new test org",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == slug
    assert body["name"] == "New Test Org"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_duplicate_slug(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oslug = org.slug
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={
                "name": "Duplicate Slug Org",
                "display_name": "Duplicate Slug Org Display",
                "slug": oslug,
                "description": "Should fail",
            },
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/organizations/{organization_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_name(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={"name": "Updated Org Name"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Org Name"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_description(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={"description": "Updated description"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated description"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            "/api/organizations/nonexistent-id",
            json={"name": "test"},
        )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_annotator_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["annotator"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={"name": "Annotator Update"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/organizations/{organization_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db, name="Delete Me")
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code == 200
    body = resp.json()
    assert "deleted" in body.get("message", "").lower() or "success" in body.get("message", "").lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete("/api/organizations/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org_non_admin(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["annotator"]):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/organizations/{organization_id}/members
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 4  # 4 seeded members


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members_has_user_info(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 200
    body = resp.json()
    if body:
        member = body[0]
        assert "user_id" in member
        assert "role" in member
        assert "is_active" in member


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/nonexistent-id/members")
    assert resp.status_code in (200, 404)
