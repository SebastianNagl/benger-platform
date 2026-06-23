"""Behavioral branch-coverage integration tests for the organizations router.

Targets the error / permission / edge paths in
``services/api/routers/organizations/*`` that the happy-path suites
(``test_organizations_integration.py`` / ``_deep.py`` / ``_router_coverage.py``)
either skip or assert too loosely (``in (200, 404)``) to actually exercise.

Most handlers here were migrated to the async DB lane
(``Depends(get_async_db)``), so their tests seed via ``async_test_db`` and drive
the HTTP surface through ``async_test_client``, overriding both auth
dependencies per-test via ``_as_user`` (the sync auth deps can't see the async
test transaction). DB state is asserted by re-querying ``async_test_db`` by id
AFTER the HTTP call (the ORM objects are expired across the await boundary).

The one exception is ``delete_user`` (``DELETE /manage/users/{id}``), which is
deliberately kept SYNC (it is dominated by the self-committing, sync-only
``auth_module.user_service.delete_user`` orchestration). Its tests therefore
keep the legacy sync ``client`` + ``test_db`` fixtures unchanged.

Endpoints covered here:

- ``get_organization_by_slug``  : non-member 403.   [async]
- ``list_organization_members`` : non-member 403.   [async]
- ``update_member_role``        : org-admin success + persisted role, annotator
  403, member-not-found 404, own-role guard 400, superadmin-modifies-own-role
  allowed.   [async]
- ``remove_member``             : org-admin success + soft-delete state, annotator
  403, member-not-found 404, self-removal guard 400, superadmin self-removal
  allowed.   [async]
- ``add_user_to_organization``  : org-admin success + persisted row, user-not-found
  404, already-active-member 400, reactivate-previously-removed branch, annotator
  403.   [async]
- ``verify_member_email``       : success + persisted verification fields,
  already-verified short-circuit, non-member 404 (org-admin path), annotator 403.
  [async]
- ``bulk_verify_member_emails`` : mixed success/skip/error tally + persisted state.
  [async]
- ``list_all_users`` (manage)   : superadmin sees all, non-superadmin org-scoped,
  ``search`` ILIKE filter, no-org non-superadmin empty list.   [async]
- ``update_user_superadmin_status`` : promote success + persisted flag, non-admin
  403, user-not-found 404.   [async]
- ``delete_user`` (manage)      : non-superadmin 403, user-not-found 404,
  self-delete guard 400, superadmin success.   [SYNC — handler stays sync]
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, OrganizationRole, User


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


# --- async seed helpers -----------------------------------------------------

async def _make_user(
    db, name="Extra User", *, is_superadmin=False, email_verified=False
) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=_uid(),
        username=f"user-{suffix}@test.com",
        email=f"user-{suffix}@test.com",
        name=name,
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=email_verified,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_org(db, name="Branch Org", slug=None) -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"branch-{uuid.uuid4().hex[:8]}",
        display_name=name,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _membership(db, user_id, org_id, role="ANNOTATOR", is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _seed_org_with_members(db):
    """Org + the 4 canonical members. Returns ``(org, users_by_role)``:
    admin (superadmin/ORG_ADMIN), contributor, annotator, org_admin (ORG_ADMIN).
    """
    admin = await _make_user(db, "Test Admin", is_superadmin=True, email_verified=True)
    contributor = await _make_user(db, "Test Contributor", email_verified=True)
    annotator = await _make_user(db, "Test Annotator", email_verified=True)
    org_admin = await _make_user(db, "Test Org Admin", email_verified=True)
    org = await _make_org(db, name="Test Organization")
    await _membership(db, admin.id, org.id, "ORG_ADMIN")
    await _membership(db, contributor.id, org.id, "CONTRIBUTOR")
    await _membership(db, annotator.id, org.id, "ANNOTATOR")
    await _membership(db, org_admin.id, org.id, "ORG_ADMIN")
    await db.commit()
    return org, {
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
        "org_admin": org_admin,
    }


async def _get_membership(db, user_id, org_id):
    # `async_test_db` uses expire_on_commit=False and is the SAME session the
    # handler wrote through, so a bare select() would return the cached
    # identity-map row (assertion would pass even if nothing persisted).
    # expire_all() forces a real DB round-trip — matches the sync HEAD pattern.
    db.expire_all()
    return (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()


async def _get_user(db, user_id):
    # See _get_membership: force a real round-trip so persistence assertions
    # (role / is_active / email_verified / is_superadmin) can't pass on a
    # stale identity-map object.
    db.expire_all()
    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# get_organization_by_slug / list_organization_members — access 403 branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_by_slug_non_member_forbidden(async_test_client, async_test_db):
    """A user with no membership on the org gets 403 from the by-slug route."""
    annotator = await _make_user(async_test_db, "Outsider")
    org = await _make_org(async_test_db, name="Slug Outsider Org")
    oslug = org.slug
    await async_test_db.commit()
    with _as_user(annotator):
        resp = await async_test_client.get(f"/api/organizations/by-slug/{oslug}")
    assert resp.status_code == 403
    assert "Not a member" in resp.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_members_non_member_forbidden(async_test_client, async_test_db):
    contributor = await _make_user(async_test_db, "Outsider")
    org = await _make_org(async_test_db, name="Members Outsider Org")
    oid = org.id
    await async_test_db.commit()
    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/organizations/{oid}/members")
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# update_member_role — permission + guard branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_updates_role_persists(async_test_client, async_test_db):
    """org_admin (non-superadmin) promotes the annotator -> persisted role."""
    org, users = await _seed_org_with_members(async_test_db)
    oid, annotator_id = org.id, users["annotator"].id
    with _as_user(users["org_admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{annotator_id}/role",
            json={"role": "CONTRIBUTOR"},
        )
    assert resp.status_code == 200
    assert "updated successfully" in resp.json()["message"]

    m = await _get_membership(async_test_db, annotator_id, oid)
    assert m is not None
    assert m.role == OrganizationRole.CONTRIBUTOR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_update_role_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, contributor_id = org.id, users["contributor"].id
    with _as_user(users["annotator"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{contributor_id}/role",
            json={"role": "ORG_ADMIN"},
        )
    assert resp.status_code == 403
    assert "Only organization admins" in resp.json()["detail"]

    m = await _get_membership(async_test_db, contributor_id, oid)
    assert m.role == OrganizationRole.CONTRIBUTOR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_member_not_found_returns_404(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{_uid()}/role",
            json={"role": "CONTRIBUTOR"},
        )
    assert resp.status_code == 404
    assert "Member not found" in resp.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_cannot_modify_own_role(async_test_client, async_test_db):
    """Non-superadmin modifying their own role -> 400 own-role guard."""
    org, users = await _seed_org_with_members(async_test_db)
    oid, org_admin_id = org.id, users["org_admin"].id
    with _as_user(users["org_admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{org_admin_id}/role",
            json={"role": "ANNOTATOR"},
        )
    assert resp.status_code == 400
    assert "Cannot modify your own role" in resp.json()["detail"]

    m = await _get_membership(async_test_db, org_admin_id, oid)
    assert m.role == OrganizationRole.ORG_ADMIN


@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_can_modify_own_role(async_test_client, async_test_db):
    """Superadmin is exempt from the own-role guard -> persisted change."""
    org, users = await _seed_org_with_members(async_test_db)
    oid, admin_id = org.id, users["admin"].id
    with _as_user(users["admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/{oid}/members/{admin_id}/role",
            json={"role": "CONTRIBUTOR"},
        )
    assert resp.status_code == 200

    m = await _get_membership(async_test_db, admin_id, oid)
    assert m.role == OrganizationRole.CONTRIBUTOR


# ---------------------------------------------------------------------------
# remove_member — permission + guard + soft-delete branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_removes_member_soft_deletes(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    target = await _make_user(async_test_db, "Target Member")
    await _membership(async_test_db, target.id, org.id, "ANNOTATOR")
    oid, target_id = org.id, target.id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/{target_id}"
        )
    assert resp.status_code == 200
    assert "removed" in resp.json()["message"].lower()

    m = await _get_membership(async_test_db, target_id, oid)
    assert m is not None
    assert m.is_active is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_remove_member_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, contributor_id = org.id, users["contributor"].id
    with _as_user(users["annotator"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/{contributor_id}"
        )
    assert resp.status_code == 403
    assert "Only organization admins" in resp.json()["detail"]

    m = await _get_membership(async_test_db, contributor_id, oid)
    assert m.is_active is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_nonexistent_member_404(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/{_uid()}"
        )
    assert resp.status_code == 404
    assert "Member not found" in resp.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_cannot_remove_self(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, org_admin_id = org.id, users["org_admin"].id
    with _as_user(users["org_admin"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/{org_admin_id}"
        )
    assert resp.status_code == 400
    assert "Cannot remove yourself" in resp.json()["detail"]

    m = await _get_membership(async_test_db, org_admin_id, oid)
    assert m.is_active is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_can_remove_self(async_test_client, async_test_db):
    """Superadmin is exempt from the self-removal guard."""
    org, users = await _seed_org_with_members(async_test_db)
    oid, admin_id = org.id, users["admin"].id
    with _as_user(users["admin"]):
        resp = await async_test_client.delete(
            f"/api/organizations/{oid}/members/{admin_id}"
        )
    assert resp.status_code == 200

    m = await _get_membership(async_test_db, admin_id, oid)
    assert m.is_active is False


# ---------------------------------------------------------------------------
# add_user_to_organization — create / reactivate / guard branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_adds_new_member_persists(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    new_user = await _make_user(async_test_db, "Fresh Add")
    oid, new_uid = org.id, new_user.id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": new_uid, "role": "CONTRIBUTOR"},
        )
    assert resp.status_code == 200
    assert "added" in resp.json()["message"].lower()

    m = await _get_membership(async_test_db, new_uid, oid)
    assert m is not None
    assert m.is_active is True
    assert m.role == OrganizationRole.CONTRIBUTOR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_user_not_found_404(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid = org.id
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": _uid(), "role": "ANNOTATOR"},
        )
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_already_active_member_400(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, contributor_id = org.id, users["contributor"].id
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": contributor_id, "role": "ANNOTATOR"},
        )
    assert resp.status_code == 400
    assert "already a member" in resp.json()["detail"]

    m = await _get_membership(async_test_db, contributor_id, oid)
    assert m.role == OrganizationRole.CONTRIBUTOR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_reactivates_previously_removed_member(async_test_client, async_test_db):
    """A prior inactive membership is reactivated (not a 2nd row), with the
    new role applied."""
    org, users = await _seed_org_with_members(async_test_db)
    target = await _make_user(async_test_db, "Returning Member")
    await _membership(async_test_db, target.id, org.id, "ANNOTATOR", is_active=False)
    oid, target_id = org.id, target.id
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": target_id, "role": "CONTRIBUTOR"},
        )
    assert resp.status_code == 200

    rows = (
        await async_test_db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == target_id,
                OrganizationMembership.organization_id == oid,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].is_active is True
    assert rows[0].role == OrganizationRole.CONTRIBUTOR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_add_member_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    new_user = await _make_user(async_test_db, "Denied Add")
    oid, new_uid = org.id, new_user.id
    await async_test_db.commit()
    with _as_user(users["annotator"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members",
            json={"user_id": new_uid, "role": "ANNOTATOR"},
        )
    assert resp.status_code == 403
    assert "Only organization admins" in resp.json()["detail"]

    assert await _get_membership(async_test_db, new_uid, oid) is None


# ---------------------------------------------------------------------------
# verify_member_email — single verification branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_verifies_member_persists(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    target = await _make_user(async_test_db, "Unverified Member", email_verified=False)
    await _membership(async_test_db, target.id, org.id, "ANNOTATOR")
    oid, target_id, org_admin_id = org.id, target.id, users["org_admin"].id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/{target_id}/verify-email",
            json={"reason": "manual check"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification_method"] == "admin"

    refreshed = await _get_user(async_test_db, target_id)
    assert refreshed.email_verified is True
    assert refreshed.email_verification_method == "admin"
    assert refreshed.email_verified_by_id == org_admin_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_already_verified_short_circuits(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    target = await _make_user(async_test_db, "Already Verified", email_verified=True)
    await _membership(async_test_db, target.id, org.id, "ANNOTATOR")
    oid, target_id = org.id, target.id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/{target_id}/verify-email",
            json={},
        )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Email already verified"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_non_member_404_for_org_admin(async_test_client, async_test_db):
    """org_admin path checks org membership of the target -> 404 if absent."""
    org, users = await _seed_org_with_members(async_test_db)
    outsider = await _make_user(async_test_db, "Org Outsider", email_verified=False)
    oid, outsider_id = org.id, outsider.id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/{outsider_id}/verify-email",
            json={},
        )
    assert resp.status_code == 404
    assert "not a member" in resp.json()["detail"].lower()

    refreshed = await _get_user(async_test_db, outsider_id)
    assert refreshed.email_verified is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_annotator_cannot_verify_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    target = await _make_user(async_test_db, "Verify Target", email_verified=False)
    await _membership(async_test_db, target.id, org.id, "ANNOTATOR")
    oid, target_id = org.id, target.id
    await async_test_db.commit()
    with _as_user(users["annotator"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/{target_id}/verify-email",
            json={},
        )
    assert resp.status_code == 403
    assert "Only organization admins" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# bulk_verify_member_emails — mixed-result tally branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_verify_mixed_results(async_test_client, async_test_db):
    """One unverified member (success), one already-verified member (skipped),
    one non-member (error) -> tally + persisted state for the success."""
    org, users = await _seed_org_with_members(async_test_db)
    unverified = await _make_user(async_test_db, "Bulk Unverified", email_verified=False)
    await _membership(async_test_db, unverified.id, org.id, "ANNOTATOR")
    verified = await _make_user(async_test_db, "Bulk Verified", email_verified=True)
    await _membership(async_test_db, verified.id, org.id, "ANNOTATOR")
    outsider = await _make_user(async_test_db, "Bulk Outsider", email_verified=False)
    oid = org.id
    unverified_id, verified_id, outsider_id = unverified.id, verified.id, outsider.id
    await async_test_db.commit()
    with _as_user(users["org_admin"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/verify-emails",
            json={"user_ids": [unverified_id, verified_id, outsider_id]},
        )
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert summary["total"] == 3
    assert summary["success"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1

    assert (await _get_user(async_test_db, unverified_id)).email_verified is True
    # The non-member was never touched.
    assert (await _get_user(async_test_db, outsider_id)).email_verified is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_verify_annotator_forbidden(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    oid, contributor_id = org.id, users["contributor"].id
    with _as_user(users["annotator"]):
        resp = await async_test_client.post(
            f"/api/organizations/{oid}/members/verify-emails",
            json={"user_ids": [contributor_id]},
        )
    assert resp.status_code == 403
    assert "Only organization admins" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# list_all_users (manage/users) — scope + search branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_sees_all_users(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    seeded_ids = {u.id for u in users.values()}
    with _as_user(users["admin"]):
        resp = await async_test_client.get("/api/organizations/manage/users")
    assert resp.status_code == 200
    body = resp.json()
    ids = {u["id"] for u in body}
    # All 4 seeded users are active and visible to the superadmin.
    assert seeded_ids.issubset(ids)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_superadmin_scoped_to_own_org(async_test_client, async_test_db):
    """A contributor only sees members of their shared org. A user in a
    different org is excluded.

    Note: ``list_all_users`` derives the caller's orgs from the auth User's
    ``organizations`` attribute, so the overridden auth User must carry that
    list. We build the contributor AuthUser with the seeded org attached.
    """
    org, users = await _seed_org_with_members(async_test_db)
    other_org = await _make_org(async_test_db, name="Disjoint Org")
    stranger = await _make_user(async_test_db, "Stranger")
    await _membership(async_test_db, stranger.id, other_org.id, "ANNOTATOR")
    oid, annotator_id, stranger_id = org.id, users["annotator"].id, stranger.id
    await async_test_db.commit()

    contributor = users["contributor"]
    auth_user = AuthUser(
        id=contributor.id,
        username=contributor.username,
        email=contributor.email,
        name=contributor.name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=contributor.created_at or datetime.now(timezone.utc),
        organizations=[{"id": oid, "role": "CONTRIBUTOR"}],
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        resp = await async_test_client.get("/api/organizations/manage/users")
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    ids = {u["id"] for u in resp.json()}
    # Sees co-members of the shared org...
    assert annotator_id in ids
    # ...but not the stranger in the disjoint org.
    assert stranger_id not in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_filter_narrows(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    # The seeded annotator email isn't deterministic, so seed one we can match.
    annot = await _make_user(async_test_db, "Searchable")
    annot.email = f"annotator-{uuid.uuid4().hex[:6]}@test.com"
    annot.username = annot.email
    await async_test_db.flush()
    await async_test_db.commit()
    with _as_user(users["admin"]):
        resp = await async_test_client.get(
            "/api/organizations/manage/users?search=annotator-"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert all("annotator-" in u["email"].lower() for u in body)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_superadmin_no_org_returns_empty(async_test_client, async_test_db):
    """A non-superadmin with no org memberships sees an empty list — the
    early-return branch when user_org_ids is empty."""
    user = await _make_user(async_test_db, "Orgless")
    await async_test_db.commit()
    auth_user = AuthUser(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=user.created_at or datetime.now(timezone.utc),
        organizations=[],
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        resp = await async_test_client.get("/api/organizations/manage/users")
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# update_user_superadmin_status — promote / permission branches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_promotes_user_persists(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    target = await _make_user(async_test_db, "Promote Me")
    target_id = target.id
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            f"/api/organizations/manage/users/{target_id}/superadmin",
            json={"is_superadmin": True},
        )
    assert resp.status_code == 200
    assert resp.json()["is_superadmin"] is True

    refreshed = await _get_user(async_test_db, target_id)
    assert refreshed.is_superadmin is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_superadmin_cannot_promote_403(async_test_client, async_test_db):
    org, users = await _seed_org_with_members(async_test_db)
    annotator_id = users["annotator"].id
    with _as_user(users["org_admin"]):
        resp = await async_test_client.put(
            f"/api/organizations/manage/users/{annotator_id}/superadmin",
            json={"is_superadmin": True},
        )
    assert resp.status_code == 403
    assert "Only superadmins" in resp.json()["detail"]

    refreshed = await _get_user(async_test_db, annotator_id)
    assert refreshed.is_superadmin is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_promote_user_not_found_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, "Admin", is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put(
            f"/api/organizations/manage/users/{_uid()}/superadmin",
            json={"is_superadmin": True},
        )
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# delete_user (manage/users) — permission + guard branches
#
# NOTE: delete_user stays SYNC (handler depends on the self-committing sync-only
# user_service.delete_user). These tests keep the legacy sync client + test_db
# fixtures unchanged — they still drive the real sync handler.
# ---------------------------------------------------------------------------

def _sync_make_user(test_db, name="Extra User", *, is_superadmin=False):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=_uid(),
        username=f"user-{suffix}@test.com",
        email=f"user-{suffix}@test.com",
        name=name,
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=False,
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.mark.integration
class TestDeleteUser:
    def test_non_superadmin_cannot_delete_403(
        self, client, test_db, test_users, auth_headers
    ):
        target = _sync_make_user(test_db, "Delete Denied")
        resp = client.delete(
            f"/api/organizations/manage/users/{target.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403
        assert "Only superadmins" in resp.json()["detail"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == target.id).first() is not None

    def test_delete_user_not_found_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"/api/organizations/manage/users/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]

    def test_cannot_delete_self_400(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"/api/organizations/manage/users/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "your own account" in resp.json()["detail"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == test_users[0].id).first() is not None

    def test_superadmin_deletes_non_superadmin_success(
        self, client, test_db, test_users, auth_headers
    ):
        """Full delete-user success path: a second superadmin acts as the
        reassignment-fallback target, and a plain user is deleted.

        ``delete_user_service`` requires another superadmin to exist (to reassign
        authored content to), so ``test_users[0]`` alone is not enough — we add a
        second superadmin first. The deleted row is gone afterward.
        """
        # Fallback superadmin so reassignment in delete_user_service is possible.
        _sync_make_user(test_db, "Fallback Admin", is_superadmin=True)

        target = _sync_make_user(test_db, "Doomed User")
        resp = client.delete(
            f"/api/organizations/manage/users/{target.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "deleted successfully" in resp.json()["message"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == target.id).first() is None
