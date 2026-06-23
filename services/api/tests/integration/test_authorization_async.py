"""Integration tests for the async twin of AuthorizationService.check_project_access.

Covers ``check_project_access_async`` (added for the async DB lane) end-to-end
against the real SAVEPOINT-isolated AsyncSession. The sync ``check_project_access``
keeps its own extensive Mock-based unit coverage in
``tests/unit/test_authorization_service*.py``; this module is the async-lane
mirror, asserting the two reads (project org ids + memberships) and the shared
``_decide_project_access`` decision run correctly under asyncpg.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.authorization import Permission, auth_service
from auth_module.models import User as AuthUser
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization


def _uid() -> str:
    return str(uuid.uuid4())


async def _make_db_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"authz-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Authz User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


def _auth(db_user):
    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at,
    )


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
        title="Authz Project",
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


@pytest.mark.asyncio
async def test_async_superadmin_always_true(async_test_db):
    admin = await _make_db_user(async_test_db, is_superadmin=True)
    owner = await _make_db_user(async_test_db)
    project = await _make_project(async_test_db, owner.id)
    await async_test_db.commit()

    assert await auth_service.check_project_access_async(
        _auth(admin), project, Permission.PROJECT_DELETE, async_test_db
    ) is True


@pytest.mark.asyncio
async def test_async_private_creator_view(async_test_db):
    creator = await _make_db_user(async_test_db)
    project = await _make_project(async_test_db, creator.id, is_private=True)
    await async_test_db.commit()

    assert await auth_service.check_project_access_async(
        _auth(creator), project, Permission.PROJECT_VIEW, async_test_db,
        org_context="private",
    ) is True


@pytest.mark.asyncio
async def test_async_private_non_owner_denied(async_test_db):
    creator = await _make_db_user(async_test_db)
    other = await _make_db_user(async_test_db)
    project = await _make_project(async_test_db, creator.id, is_private=True)
    await async_test_db.commit()

    assert await auth_service.check_project_access_async(
        _auth(other), project, Permission.PROJECT_VIEW, async_test_db,
        org_context="private",
    ) is False


@pytest.mark.asyncio
async def test_async_org_contributor_can_edit(async_test_db):
    owner = await _make_db_user(async_test_db)
    member = await _make_db_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="CONTRIBUTOR")
    await async_test_db.commit()

    assert await auth_service.check_project_access_async(
        _auth(member), project, Permission.PROJECT_EDIT, async_test_db,
        org_context=org.id,
    ) is True


@pytest.mark.asyncio
async def test_async_org_annotator_cannot_edit(async_test_db):
    owner = await _make_db_user(async_test_db)
    member = await _make_db_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="ANNOTATOR")
    await async_test_db.commit()

    # Annotator has VIEW but not EDIT.
    assert await auth_service.check_project_access_async(
        _auth(member), project, Permission.PROJECT_VIEW, async_test_db,
        org_context=org.id,
    ) is True
    assert await auth_service.check_project_access_async(
        _auth(member), project, Permission.PROJECT_EDIT, async_test_db,
        org_context=org.id,
    ) is False


@pytest.mark.asyncio
async def test_async_public_visitor_view_only(async_test_db):
    owner = await _make_db_user(async_test_db)
    visitor = await _make_db_user(async_test_db)
    project = await _make_project(
        async_test_db, owner.id, is_public=True, public_role="ANNOTATOR"
    )
    await async_test_db.commit()

    # Public annotator-tier visitor can view but never edit.
    assert await auth_service.check_project_access_async(
        _auth(visitor), project, Permission.PROJECT_VIEW, async_test_db
    ) is True
    assert await auth_service.check_project_access_async(
        _auth(visitor), project, Permission.PROJECT_EDIT, async_test_db
    ) is False


@pytest.mark.asyncio
async def test_async_legacy_member_matches_sync(async_test_db):
    owner = await _make_db_user(async_test_db)
    member = await _make_db_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _make_project(async_test_db, owner.id, org=org)
    await _add_membership(async_test_db, member.id, org.id, role="CONTRIBUTOR")
    await async_test_db.commit()

    # Legacy mode (org_context=None): any active membership in a project org.
    assert await auth_service.check_project_access_async(
        _auth(member), project, Permission.PROJECT_EDIT, async_test_db,
        org_context=None,
    ) is True
