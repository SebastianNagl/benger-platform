"""Org admin scope (``auth_module/org_scope.py``) on real Postgres.

Every case runs on both lanes: the async helpers with ``async_test_db`` and
the sync twins with ``test_db``, seeded with the same small world.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from auth_module.org_scope import (
    OrgAdminScope,
    load_org_admin_scope,
    load_org_admin_scope_sync,
    require_scope_admin,
    require_scope_admin_sync,
)
from models import (
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _world():
    """Objects to insert plus the ids and auth users the tests use."""
    ids = {
        "org": _id("org"),
        "inactive_org": _id("org-off"),
        "other_org": _id("org-b"),
        "group": _id("grp"),
        "inactive_group": _id("grp-off"),
        "other_group": _id("grp-b"),
    }
    orgs = [
        Organization(
            id=ids["org"], name="Uni", display_name="Uni", slug=ids["org"], is_active=True
        ),
        Organization(
            id=ids["inactive_org"],
            name="Gone",
            display_name="Gone",
            slug=ids["inactive_org"],
            is_active=False,
        ),
        Organization(
            id=ids["other_org"],
            name="Other",
            display_name="Other",
            slug=ids["other_org"],
            is_active=True,
        ),
    ]
    groups = [
        OrganizationGroup(id=ids["group"], organization_id=ids["org"], name="Chair A"),
        OrganizationGroup(
            id=ids["inactive_group"],
            organization_id=ids["org"],
            name="Chair Old",
            is_active=False,
        ),
        OrganizationGroup(
            id=ids["other_group"], organization_id=ids["other_org"], name="Chair B"
        ),
    ]
    users = {}
    rows = []

    def user(key, *, superadmin=False):
        uid = _id(key)
        users[key] = SimpleNamespace(id=uid, is_superadmin=superadmin)
        rows.append(
            User(
                id=uid,
                username=uid,
                email=f"{uid}@example.com",
                name=key,
                is_superadmin=superadmin,
            )
        )
        return uid

    def member(uid, org, role, active=True):
        rows.append(
            OrganizationMembership(
                id=_id("m"),
                user_id=uid,
                organization_id=org,
                role=role,
                is_active=active,
            )
        )

    def group_member(uid, group, admin):
        rows.append(
            OrganizationGroupMembership(
                id=_id("gm"), group_id=group, user_id=uid, is_group_admin=admin
            )
        )

    user("superadmin", superadmin=True)
    org_admin = user("org_admin")
    member(org_admin, ids["org"], OrganizationRole.ORG_ADMIN)
    group_admin = user("group_admin")
    member(group_admin, ids["org"], OrganizationRole.ANNOTATOR)
    group_member(group_admin, ids["group"], True)
    group_member(group_admin, ids["inactive_group"], True)
    group_member(group_admin, ids["other_group"], True)
    former = user("former_member")
    member(former, ids["org"], OrganizationRole.CONTRIBUTOR, active=False)
    group_member(former, ids["group"], True)
    contributor = user("contributor")
    member(contributor, ids["org"], OrganizationRole.CONTRIBUTOR)
    group_member(contributor, ids["group"], False)
    user("stranger")
    inactive_admin = user("inactive_org_admin")
    member(inactive_admin, ids["inactive_org"], OrganizationRole.ORG_ADMIN)

    return ids, users, [*orgs, *groups], rows


class _Lane:
    """One API over the async and the sync helpers."""

    def __init__(self, kind, session):
        self.kind = kind
        self.session = session

    async def seed(self):
        ids, users, parents, rows = _world()
        self.session.add_all(parents)
        if self.kind == "async":
            await self.session.flush()
        else:
            self.session.flush()
        self.session.add_all(rows)
        if self.kind == "async":
            await self.session.flush()
        else:
            self.session.flush()
        return ids, users

    async def load(self, user, org_id):
        if self.kind == "async":
            return await load_org_admin_scope(self.session, user, org_id)
        return load_org_admin_scope_sync(self.session, user, org_id)

    async def require(self, user, org_id, group_id=None, **kwargs):
        if self.kind == "async":
            return await require_scope_admin(
                self.session, user, org_id, group_id, **kwargs
            )
        return require_scope_admin_sync(self.session, user, org_id, group_id, **kwargs)


@pytest_asyncio.fixture(params=["async", "sync"])
async def lane(request, async_test_db, test_db):
    if request.param == "async":
        return _Lane("async", async_test_db)
    return _Lane("sync", test_db)


async def _denied(coro, status_code, code):
    with pytest.raises(HTTPException) as exc:
        await coro
    assert exc.value.status_code == status_code
    assert exc.value.detail["code"] == code
    assert exc.value.detail["message"]


class TestOrgAdminScopeValue:
    def test_group_scope_rules(self):
        scope = OrgAdminScope(org_id="o", admin_group_ids=frozenset({"g1"}))
        assert scope.covers("g1") and not scope.covers("g2")
        assert not scope.covers(None)
        assert scope.is_admin and not scope.org_wide
        assert not scope.sees_real_names

    def test_org_wide_scopes(self):
        for scope in (
            OrgAdminScope(org_id="o", is_org_admin=True),
            OrgAdminScope(org_id="o", is_superadmin=True),
        ):
            assert scope.covers(None) and scope.covers("any-group")
            assert scope.org_wide and scope.is_admin and scope.sees_real_names

    def test_empty_scope(self):
        scope = OrgAdminScope(org_id="o")
        assert not scope.is_admin
        assert not scope.covers(None) and not scope.covers("g1")


class TestLoadAndRequire:
    async def test_superadmin_covers_everything(self, lane):
        ids, users = await lane.seed()
        sa = users["superadmin"]

        scope = await lane.load(sa, ids["org"])
        assert scope == OrgAdminScope(org_id=ids["org"], is_superadmin=True)
        assert (await lane.require(sa, ids["org"])).sees_real_names
        assert (await lane.require(sa, ids["org"], ids["inactive_group"])).covers(
            ids["inactive_group"]
        )
        # Deactivated orgs stay reachable for superadmins.
        assert (await lane.require(sa, ids["inactive_org"])).is_superadmin
        await _denied(lane.load(sa, _id("missing")), 404, "organization_not_found")
        await _denied(
            lane.require(sa, ids["org"], ids["other_group"]), 404, "group_not_found"
        )

    async def test_org_admin_covers_the_org_and_its_groups(self, lane):
        ids, users = await lane.seed()
        admin = users["org_admin"]

        scope = await lane.require(admin, ids["org"])
        assert scope.is_org_admin and not scope.is_superadmin
        assert scope.sees_real_names
        assert (await lane.require(admin, ids["org"], ids["group"])).org_wide
        assert (await lane.require(admin, ids["org"], ids["inactive_group"])).org_wide
        # No power in another org.
        await _denied(lane.require(admin, ids["other_org"]), 403, "scope_admin_required")
        await _denied(
            lane.require(admin, ids["org"], ids["other_group"]), 404, "group_not_found"
        )

    async def test_group_admin_covers_only_active_groups(self, lane):
        ids, users = await lane.seed()
        admin = users["group_admin"]

        scope = await lane.load(admin, ids["org"])
        assert scope.admin_group_ids == frozenset({ids["group"]})
        assert not scope.is_org_admin and not scope.sees_real_names

        assert (await lane.require(admin, ids["org"], ids["group"])).covers(ids["group"])
        await _denied(lane.require(admin, ids["org"]), 403, "scope_admin_required")
        await _denied(
            lane.require(admin, ids["org"], ids["inactive_group"]),
            403,
            "scope_admin_required",
        )
        await _denied(
            lane.require(admin, ids["org"], _id("missing")), 404, "group_not_found"
        )
        # List endpoints: any group admin may ask for the org-wide list.
        listed = await lane.require(admin, ids["org"], any_group=True)
        assert listed.admin_group_ids == frozenset({ids["group"]})
        # A group of another org is never theirs, even with an admin row there
        # (they are no member of that org).
        other = await lane.load(admin, ids["other_org"])
        assert not other.is_admin

    async def test_deactivated_member_loses_group_admin(self, lane):
        ids, users = await lane.seed()
        former = users["former_member"]

        scope = await lane.load(former, ids["org"])
        assert scope == OrgAdminScope(org_id=ids["org"])
        await _denied(
            lane.require(former, ids["org"], ids["group"]), 403, "scope_admin_required"
        )
        await _denied(
            lane.require(former, ids["org"], any_group=True),
            403,
            "scope_admin_required",
        )

    @pytest.mark.parametrize("who", ["contributor", "stranger"])
    async def test_non_admins_are_refused(self, lane, who):
        ids, users = await lane.seed()
        user = users[who]

        assert not (await lane.load(user, ids["org"])).is_admin
        for group_id in (None, ids["group"]):
            await _denied(
                lane.require(user, ids["org"], group_id), 403, "scope_admin_required"
            )
        await _denied(
            lane.require(user, ids["org"], any_group=True), 403, "scope_admin_required"
        )

    async def test_inactive_org_is_hidden_from_its_admins(self, lane):
        ids, users = await lane.seed()
        admin = users["inactive_org_admin"]

        await _denied(
            lane.load(admin, ids["inactive_org"]), 404, "organization_not_found"
        )
        await _denied(
            lane.require(admin, ids["inactive_org"]), 404, "organization_not_found"
        )
        # Same answer as for an org that does not exist.
        await _denied(lane.require(admin, _id("missing")), 404, "organization_not_found")
