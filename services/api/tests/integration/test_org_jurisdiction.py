"""Organization jurisdiction (core 2.41): ``settings.jurisdiction``.

``PUT /api/organizations/{id}/jurisdiction`` sets it for org admins and
superadmins (merging into the other settings keys), ``/auth/me/contexts``
reports it per organization (the wizard's jurisdiction-specific project
types read it there), and the generic org writes reject unknown values.

Groups override it (migration 120, ``organization_groups.jurisdiction``):
``PUT /api/organizations/{id}/groups/{gid}/jurisdiction`` sets or clears
the override for org admins and that group's admins, and the contexts list
each org's overrides as ``group_jurisdictions``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    User,
)
from org_jurisdiction import group_jurisdiction, org_jurisdiction, with_jurisdiction


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


async def _seed(db, *, settings=None):
    users = {}
    for role in ("ORG_ADMIN", "ANNOTATOR"):
        u = User(
            id=_uid(),
            username=f"juris-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="Juris User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(u)
        users[role] = u
    org = Organization(
        id=_uid(),
        name="Faculté",
        slug=f"faculte-{uuid.uuid4().hex[:8]}",
        display_name="Faculté de droit",
        is_active=True,
        settings=settings if settings is not None else {"require_private_keys": False},
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    for role, u in users.items():
        db.add(
            OrganizationMembership(
                id=_uid(), user_id=u.id, organization_id=org.id, role=role,
                is_active=True, joined_at=datetime.now(timezone.utc),
            )
        )
    await db.commit()
    return org, users


async def _stored_settings(db, org_id):
    db.expire_all()
    return (
        await db.execute(select(Organization.settings).where(Organization.id == org_id))
    ).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_sets_jurisdiction_and_keeps_other_settings(
    async_test_client, async_test_db
):
    org, users = await _seed(async_test_db)
    with _as_user(users["ORG_ADMIN"]):
        resp = await async_test_client.put(
            f"/api/organizations/{org.id}/jurisdiction", json={"jurisdiction": "FR"}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": org.id, "jurisdiction": "FR"}
    assert await _stored_settings(async_test_db, org.id) == {
        "require_private_keys": False,
        "jurisdiction": "FR",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_contexts_report_the_jurisdiction(async_test_client, async_test_db):
    org, users = await _seed(async_test_db, settings={"jurisdiction": "FR"})
    other, _ = await _seed(async_test_db, settings=None)
    with _as_user(users["ANNOTATOR"]):
        resp = await async_test_client.get("/api/auth/me/contexts")
    assert resp.status_code == 200, resp.text
    entries = {o["id"]: o for o in resp.json()["organizations"]}
    assert entries[org.id]["jurisdiction"] == "FR"
    assert other.id not in entries


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_annotator_cannot_change_it(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    with _as_user(users["ANNOTATOR"]):
        resp = await async_test_client.put(
            f"/api/organizations/{org.id}/jurisdiction", json={"jurisdiction": "FR"}
        )
    assert resp.status_code == 403
    assert "jurisdiction" not in await _stored_settings(async_test_db, org.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_values_are_rejected_on_every_write(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    with _as_user(users["ORG_ADMIN"]):
        dedicated = await async_test_client.put(
            f"/api/organizations/{org.id}/jurisdiction", json={"jurisdiction": "XX"}
        )
        generic = await async_test_client.put(
            f"/api/organizations/{org.id}", json={"settings": {"jurisdiction": "fr"}}
        )
    assert dedicated.status_code == 422
    assert generic.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_organization_is_404(async_test_client, async_test_db):
    _, users = await _seed(async_test_db)
    with _as_user(users["ORG_ADMIN"]):
        resp = await async_test_client.put(
            "/api/organizations/does-not-exist/jurisdiction", json={"jurisdiction": "FR"}
        )
    assert resp.status_code == 404


async def _seed_group(db, org, users):
    """A group in ``org`` with a CONTRIBUTOR-org-role group admin."""
    group = OrganizationGroup(id=_uid(), organization_id=org.id, name="Droit", is_active=True)
    db.add(group)
    admin = User(
        id=_uid(),
        username=f"juris-ga-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Group Admin",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(admin)
    await db.flush()
    db.add(
        OrganizationMembership(
            id=_uid(), user_id=admin.id, organization_id=org.id, role="CONTRIBUTOR",
            is_active=True, joined_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        OrganizationGroupMembership(
            id=_uid(), group_id=group.id, user_id=admin.id, role="ORG_ADMIN"
        )
    )
    await db.commit()
    return group, admin


async def _stored_group_jurisdiction(db, group_id):
    db.expire_all()
    return (
        await db.execute(
            select(OrganizationGroup.jurisdiction).where(OrganizationGroup.id == group_id)
        )
    ).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_sets_and_clears_a_group_jurisdiction(
    async_test_client, async_test_db
):
    org, users = await _seed(async_test_db)
    group, _ = await _seed_group(async_test_db, org, users)
    org_id, group_id = org.id, group.id
    url = f"/api/organizations/{org_id}/groups/{group_id}/jurisdiction"
    with _as_user(users["ORG_ADMIN"]):
        resp = await async_test_client.put(url, json={"jurisdiction": "FR"})
        listed = await async_test_client.get(f"/api/organizations/{org_id}/groups")
        cleared = await async_test_client.put(url, json={"jurisdiction": None})
        relisted = await async_test_client.get(f"/api/organizations/{org_id}/groups")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": group_id, "jurisdiction": "FR"}
    assert {g["id"]: g["jurisdiction"] for g in listed.json()}[group_id] == "FR"
    assert cleared.status_code == 200, cleared.text
    assert {g["id"]: g["jurisdiction"] for g in relisted.json()}[group_id] is None
    assert await _stored_group_jurisdiction(async_test_db, group_id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_may_set_it_annotator_may_not(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    group, group_admin = await _seed_group(async_test_db, org, users)
    group_id = group.id
    url = f"/api/organizations/{org.id}/groups/{group_id}/jurisdiction"
    with _as_user(users["ANNOTATOR"]):
        denied = await async_test_client.put(url, json={"jurisdiction": "FR"})
    with _as_user(group_admin):
        allowed = await async_test_client.put(url, json={"jurisdiction": "FR"})
    assert denied.status_code == 403
    assert allowed.status_code == 200, allowed.text
    assert await _stored_group_jurisdiction(async_test_db, group_id) == "FR"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_jurisdiction_rejects_unknown_values_and_groups(
    async_test_client, async_test_db
):
    org, users = await _seed(async_test_db)
    group, _ = await _seed_group(async_test_db, org, users)
    with _as_user(users["ORG_ADMIN"]):
        bad_value = await async_test_client.put(
            f"/api/organizations/{org.id}/groups/{group.id}/jurisdiction",
            json={"jurisdiction": "fr"},
        )
        missing = await async_test_client.put(
            f"/api/organizations/{org.id}/groups/does-not-exist/jurisdiction",
            json={"jurisdiction": "FR"},
        )
    assert bad_value.status_code == 422
    assert missing.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_contexts_report_group_overrides(async_test_client, async_test_db):
    org, users = await _seed(async_test_db)
    group, _ = await _seed_group(async_test_db, org, users)
    plain = OrganizationGroup(id=_uid(), organization_id=org.id, name="Zivil", is_active=True)
    async_test_db.add(plain)
    group.jurisdiction = "FR"
    await async_test_db.commit()

    # The annotator is in neither group: overrides are listed regardless.
    with _as_user(users["ANNOTATOR"]):
        resp = await async_test_client.get("/api/auth/me/contexts")
    assert resp.status_code == 200, resp.text
    entry = {o["id"]: o for o in resp.json()["organizations"]}[org.id]
    assert entry["jurisdiction"] == "DE"
    assert entry["group_jurisdictions"] == {group.id: "FR"}


class TestGroupHelper:
    @pytest.mark.parametrize(
        "settings, group_value, expected",
        [
            (None, None, "DE"),
            ({"jurisdiction": "FR"}, None, "FR"),
            ({"jurisdiction": "FR"}, "DE", "DE"),
            (None, "FR", "FR"),
            ({"jurisdiction": "FR"}, "ZZ", "FR"),
        ],
    )
    def test_group_jurisdiction(self, settings, group_value, expected):
        assert group_jurisdiction(settings, group_value) == expected


class TestHelpers:
    @pytest.mark.parametrize(
        "settings, expected",
        [(None, "DE"), ({}, "DE"), ({"jurisdiction": "FR"}, "FR"), ({"jurisdiction": "ZZ"}, "DE"), ("x", "DE")],
    )
    def test_org_jurisdiction(self, settings, expected):
        assert org_jurisdiction(settings) == expected

    def test_with_jurisdiction_copies(self):
        original = {"a": 1}
        assert with_jurisdiction(original, "FR") == {"a": 1, "jurisdiction": "FR"}
        assert original == {"a": 1}
        with pytest.raises(ValueError):
            with_jurisdiction(original, "XX")
