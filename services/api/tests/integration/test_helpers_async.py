"""Integration tests for the async (asyncpg) twins of the project-access helpers.

Covers the dual-mode additions in ``routers/projects/helpers.py``:
  - get_user_with_memberships_async
  - get_effective_project_role_async
  - check_project_accessible_async

These exercise the real SAVEPOINT-isolated AsyncSession (async_test_db) so the
``select(...)`` SQL, the joinedload eager-load (no MissingGreenlet), and the
membership/org-context decision logic run end-to-end against PostgreSQL — the
exact surface the migrated async handlers depend on.

The sync twins keep their own ``db.query`` mock-based unit-test coverage in
tests/unit/test_project_helpers_*.py; these tests are the async-lane mirror.
"""

import uuid
from datetime import datetime, timezone

import pytest

from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization
from routers.projects.helpers import (
    check_project_accessible_async,
    get_effective_project_role_async,
    get_user_with_memberships_async,
)


def _uid():
    return str(uuid.uuid4())


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Test User",
        is_superadmin=is_superadmin,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name="Org"):
    o = Organization(
        id=_uid(),
        name=f"{name}-{_uid()[:8]}",
        slug=f"{name.lower()}-{_uid()[:8]}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(o)
    await db.flush()
    return o


async def _make_project(db, creator_id, *, org=None, **kwargs):
    p = Project(
        id=_uid(),
        title="Async Helper Project",
        created_by=creator_id,
        label_config='<View><Text name="text" value="$text"/></View>',
        **kwargs,
    )
    db.add(p)
    await db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator_id,
            )
        )
        await db.flush()
    return p


async def _add_membership(db, user_id, org_id, role="CONTRIBUTOR", is_active=True):
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


# ── get_user_with_memberships_async ────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_user_with_memberships_async_eager_loads(async_test_db):
    user = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, user.id, org.id, role="ORG_ADMIN")
    await async_test_db.commit()

    loaded = await get_user_with_memberships_async(async_test_db, user.id)
    assert loaded is not None
    # The joinedload populated memberships without a lazy load (would raise
    # MissingGreenlet under asyncpg otherwise).
    assert [m.organization_id for m in loaded.organization_memberships] == [org.id]


@pytest.mark.asyncio
async def test_get_user_with_memberships_async_missing(async_test_db):
    assert await get_user_with_memberships_async(async_test_db, "no-such-user") is None


# ── get_effective_project_role_async ───────────────────────────────────────
@pytest.mark.asyncio
async def test_role_async_creator_is_org_admin(async_test_db):
    creator = await _make_user(async_test_db)
    project = await _make_project(async_test_db, creator.id)
    await async_test_db.commit()

    role = await get_effective_project_role_async(async_test_db, creator, project)
    assert role == "ORG_ADMIN"


@pytest.mark.asyncio
async def test_role_async_active_member_role(async_test_db):
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="CONTRIBUTOR")
    await async_test_db.commit()

    role = await get_effective_project_role_async(async_test_db, member, project)
    assert role == "CONTRIBUTOR"


@pytest.mark.asyncio
async def test_role_async_no_claim_is_none(async_test_db):
    owner = await _make_user(async_test_db)
    outsider = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await async_test_db.commit()

    assert await get_effective_project_role_async(async_test_db, outsider, project) is None


# ── check_project_accessible_async ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_access_async_superadmin_always_true(async_test_db):
    superadmin = await _make_user(async_test_db, is_superadmin=True)
    owner = await _make_user(async_test_db)
    project = await _make_project(async_test_db, owner.id)
    await async_test_db.commit()

    assert await check_project_accessible_async(
        async_test_db, superadmin, project.id
    ) is True


@pytest.mark.asyncio
async def test_access_async_private_creator_in_org_context(async_test_db):
    creator = await _make_user(async_test_db)
    project = await _make_project(async_test_db, creator.id, is_private=True)
    await async_test_db.commit()

    # Org context set, but the creator of a private project keeps access.
    assert await check_project_accessible_async(
        async_test_db, creator, project.id, org_context="some-org"
    ) is True


@pytest.mark.asyncio
async def test_access_async_private_non_owner_denied(async_test_db):
    creator = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _make_project(async_test_db, creator.id, is_private=True)
    await async_test_db.commit()

    assert await check_project_accessible_async(
        async_test_db, other, project.id, org_context="private"
    ) is False


@pytest.mark.asyncio
async def test_access_async_org_member_active(async_test_db):
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="CONTRIBUTOR")
    await async_test_db.commit()

    assert await check_project_accessible_async(
        async_test_db, member, project.id, org_context=org.id
    ) is True


@pytest.mark.asyncio
async def test_access_async_org_member_inactive_denied(async_test_db):
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(
        async_test_db, member.id, org.id, role="CONTRIBUTOR", is_active=False
    )
    await async_test_db.commit()

    assert await check_project_accessible_async(
        async_test_db, member, project.id, org_context=org.id
    ) is False


@pytest.mark.asyncio
async def test_access_async_legacy_org_member(async_test_db):
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="ANNOTATOR")
    await async_test_db.commit()

    # Legacy mode (org_context=None) — any active membership in a project org.
    assert await check_project_accessible_async(
        async_test_db, member, project.id, org_context=None
    ) is True


@pytest.mark.asyncio
async def test_access_async_archived_annotator_denied(async_test_db):
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(
        async_test_db, owner.id, org=org, is_archived=True
    )
    await _add_membership(async_test_db, member.id, org.id, role="ANNOTATOR")
    await async_test_db.commit()

    # Archived project is read-only to annotators → access revoked.
    assert await check_project_accessible_async(
        async_test_db, member, project.id, org_context=org.id
    ) is False


@pytest.mark.asyncio
async def test_access_async_missing_project(async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()

    assert await check_project_accessible_async(
        async_test_db, user, "no-such-project"
    ) is False
