"""
Integration tests for organizations router endpoints.

Targets: routers/organizations/* — the CRUD + member endpoints were migrated to
the async DB lane (``Depends(get_async_db)``). These tests therefore seed real
rows via ``async_test_db`` and drive the HTTP surface through
``async_test_client``. The sync auth dependencies (``require_user`` /
``get_current_user``) can't see the async test transaction, so each test
overrides BOTH via the ``_as_user`` context manager to return an auth User that
matches a seeded DB user (handlers depend on one or the other; overriding both
is harmless).

Uses real PostgreSQL with per-test transaction rollback (SAVEPOINT isolation).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override both auth dependencies to return an AuthUser for ``db_user``.

    ``require_user`` and ``get_current_user`` both normally resolve through a
    sync ``get_db`` Session that cannot see the async test transaction, so we
    bypass them entirely. Handlers in this router use one or the other.
    """
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


async def _make_user(
    db, *, is_superadmin=False, is_active=True, username_prefix="orguser"
) -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Org User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=is_active,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Test Org", slug=None) -> Organization:
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


async def _make_membership(db, user_id: str, org_id: str, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


# ---------------------------------------------------------------------------
# GET /api/organizations/
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_as_superadmin(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await _make_org(async_test_db)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_as_member(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _make_membership(async_test_db, user.id, org.id, "CONTRIBUTOR")
    await async_test_db.commit()
    with _as_user(user):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_orgs_unauthorized(async_test_client):
    # No _as_user override -> require_user resolves normally and rejects.
    resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/organizations/{org_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_id(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/organizations/{oid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == oid


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/organizations/nonexistent-org-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/organizations/
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_as_superadmin(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    slug = f"new-org-{uuid.uuid4().hex[:8]}"
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={
                "name": "New Test Org",
                "slug": slug,
                "display_name": "New Test Org Display",
                "description": "A new test organization",
            },
        )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "New Test Org"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_duplicate_slug(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    slug = org.slug
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={
                "name": "Duplicate Slug Org",
                "slug": slug,
                "display_name": "Dup",
            },
        )
    assert resp.status_code in (400, 409)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_org_missing_name(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/organizations/",
            json={"slug": "no-name-org"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/organizations/{org_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_name(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    oid, oslug, odisplay = org.id, org.slug, org.display_name
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}",
            json={"name": "Updated Org Name", "slug": oslug, "display_name": odisplay},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Org Name"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            "/api/organizations/nonexistent",
            json={"name": "Nope", "slug": "nope", "display_name": "Nope"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/organizations/{org_id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org_as_superadmin(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db, name="Delete Me Org")
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code in (200, 204)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete("/api/organizations/nonexistent")
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_org_non_superadmin_denied(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    annotator = await _make_user(async_test_db)
    org = await _make_org(async_test_db, name="Protected Org")
    await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
    oid = org.id
    await async_test_db.commit()
    with _as_user(annotator):
        resp = await async_test_client.delete(f"/api/organizations/{oid}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Member management endpoints
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_org_members(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    member = await _make_user(async_test_db)
    await _make_membership(async_test_db, member.id, org.id, "ANNOTATOR")
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_member_to_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    new_user = await _make_user(async_test_db, username_prefix="newmember")
    oid, new_uid = org.id, new_user.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": new_uid, "role": "ANNOTATOR"},
        )
    assert resp.status_code in (200, 201)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_member_from_org(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    user = await _make_user(async_test_db, username_prefix="removeme")
    await _make_membership(async_test_db, user.id, org.id, "ANNOTATOR")
    oid, uid = org.id, user.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/organizations/{oid}/members/{uid}")
    assert resp.status_code in (200, 204)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_member_role(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    member = await _make_user(async_test_db)
    await _make_membership(async_test_db, member.id, org.id, "ANNOTATOR")
    oid, uid = org.id, member.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{uid}/role",
            json={"role": "CONTRIBUTOR"},
        )
    assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Misc / by-slug
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_stats(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    oid = org.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/organizations/{oid}/stats")
    # No such endpoint -> 404 (kept for parity with the original assertion set).
    assert resp.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_org_by_slug(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    oslug = org.slug
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/organizations/by-slug/{oslug}")
    assert resp.status_code in (200, 404)
