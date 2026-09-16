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


# ---------------------------------------------------------------------------
# Exam carve-out (rubric leak): ANNOTATOR org members get no project-level
# permission on exams in EITHER mode. The async lane has no private fast
# path in front of the decider, so these tests exercise the decider itself.
# ---------------------------------------------------------------------------

READ_PERMISSIONS = (Permission.PROJECT_VIEW, Permission.TASK_VIEW)
BOTH_MODES = ("org", None)


def _ctx(mode, org):
    return org.id if mode == "org" else None


async def _make_group(db, org, *members):
    """members: (user, is_group_admin) tuples."""
    from models import OrganizationGroup, OrganizationGroupMembership

    g = OrganizationGroup(
        id=_uid(), organization_id=org.id, name=f"G-{_uid()[:6]}", is_active=True
    )
    db.add(g)
    await db.flush()
    for user, is_admin in members:
        db.add(
            OrganizationGroupMembership(
                id=_uid(), group_id=g.id, user_id=user.id, is_group_admin=is_admin
            )
        )
    await db.flush()
    return g


async def _attach(db, project, org, by, group=None):
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            group_id=group.id if group else None,
            assigned_by=by.id,
        )
    )
    await db.flush()


async def _allowed(db, user, project, permission, org_context):
    return await auth_service.check_project_access_async(
        _auth(user), project, permission, db, org_context=org_context
    )


def _allowed_sync(db, user, project, permission, org_context):
    return db.run_sync(
        lambda s: auth_service.check_project_access(
            _auth(user), project, permission, s, org_context=org_context
        )
    )


@pytest.mark.asyncio
async def test_async_org_annotator_denied_on_org_exam_both_modes(async_test_db):
    db = async_test_db
    owner = await _make_db_user(db)
    student = await _make_db_user(db)
    staff = await _make_db_user(db)
    org = await _make_org(db)
    exam = await _make_project(db, owner.id, org=org, kind="exam")
    await _add_membership(db, owner.id, org.id, role="CONTRIBUTOR")
    await _add_membership(db, student.id, org.id, role="ANNOTATOR")
    await _add_membership(db, staff.id, org.id, role="CONTRIBUTOR")
    await db.commit()

    for mode in BOTH_MODES:
        ctx = _ctx(mode, org)
        for permission in READ_PERMISSIONS:
            assert await _allowed(db, student, exam, permission, ctx) is False, (
                mode, permission,
            )
            # Sync lane: no fast path for a non-private exam, same decider.
            assert await _allowed_sync(db, student, exam, permission, ctx) is False
            # Staff keep the full tier on the same exam.
            assert await _allowed(db, staff, exam, permission, ctx) is True
            assert await _allowed_sync(db, staff, exam, permission, ctx) is True
        assert await _allowed(db, student, exam, Permission.ANNOTATION_VIEW, ctx) is False


@pytest.mark.asyncio
async def test_async_org_annotator_denied_on_private_org_exam_both_modes(async_test_db):
    db = async_test_db
    owner = await _make_db_user(db)
    student = await _make_db_user(db)
    org = await _make_org(db)
    exam = await _make_project(db, owner.id, org=org, kind="exam", is_private=True)
    await _add_membership(db, owner.id, org.id, role="CONTRIBUTOR")
    await _add_membership(db, student.id, org.id, role="ANNOTATOR")
    await db.commit()

    for mode in BOTH_MODES:
        ctx = _ctx(mode, org)
        for permission in READ_PERMISSIONS:
            assert await _allowed(db, student, exam, permission, ctx) is False, (
                mode, permission,
            )
            # The creator keeps their private exam in every mode.
            assert await _allowed(db, owner, exam, permission, ctx) is True


@pytest.mark.asyncio
async def test_async_private_org_project_is_creator_only_in_org_context(async_test_db):
    """The private rule now lives in the decider: even an org admin of the
    attachment gets nothing on a private project under that org's context
    (the sync lane always answered this way through its fast path)."""
    db = async_test_db
    owner = await _make_db_user(db)
    admin = await _make_db_user(db)
    org = await _make_org(db)
    project = await _make_project(db, owner.id, org=org, is_private=True)
    await _add_membership(db, admin.id, org.id, role="ORG_ADMIN")
    await db.commit()

    for mode in BOTH_MODES:
        ctx = _ctx(mode, org)
        assert await _allowed(db, admin, project, Permission.PROJECT_VIEW, ctx) is False
        assert await _allowed_sync(db, admin, project, Permission.PROJECT_VIEW, ctx) is False


@pytest.mark.asyncio
async def test_async_org_annotator_allowed_on_non_exam_org_project(async_test_db):
    db = async_test_db
    owner = await _make_db_user(db)
    annotator = await _make_db_user(db)
    org = await _make_org(db)
    plain = await _make_project(db, owner.id, org=org)
    deck = await _make_project(db, owner.id, org=org, kind="flashcard_collection")
    await _add_membership(db, annotator.id, org.id, role="ANNOTATOR")
    await db.commit()

    for project in (plain, deck):
        for mode in BOTH_MODES:
            ctx = _ctx(mode, org)
            for permission in READ_PERMISSIONS + (Permission.ANNOTATION_CREATE,):
                assert await _allowed(db, annotator, project, permission, ctx) is True, (
                    project.kind, mode, permission,
                )
            assert await _allowed(db, annotator, project, Permission.PROJECT_EDIT, ctx) is False


@pytest.mark.asyncio
async def test_async_group_admin_annotator_allowed_on_group_exam(async_test_db):
    db = async_test_db
    owner = await _make_db_user(db)
    gadmin = await _make_db_user(db)
    gmember = await _make_db_user(db)
    org = await _make_org(db)
    await _add_membership(db, owner.id, org.id, role="CONTRIBUTOR")
    await _add_membership(db, gadmin.id, org.id, role="ANNOTATOR")
    await _add_membership(db, gmember.id, org.id, role="ANNOTATOR")
    group = await _make_group(db, org, (gadmin, True), (gmember, False))
    exam = await _make_project(db, owner.id, kind="exam")
    await _attach(db, exam, org, owner, group=group)
    await db.commit()

    for mode in BOTH_MODES:
        ctx = _ctx(mode, org)
        for permission in READ_PERMISSIONS:
            # Group admin of the attachment = staff on the group's exams.
            assert await _allowed(db, gadmin, exam, permission, ctx) is True, (mode, permission)
            assert await _allowed_sync(db, gadmin, exam, permission, ctx) is True
            # A plain (non-admin) ANNOTATOR group member is still a student.
            assert await _allowed(db, gmember, exam, permission, ctx) is False, (mode, permission)
        # The group-admin upgrade is ORG_ADMIN, so edit is granted too.
        assert await _allowed(db, gadmin, exam, Permission.PROJECT_EDIT, ctx) is True


@pytest.mark.asyncio
async def test_async_inactive_member_denied_both_modes(async_test_db):
    db = async_test_db
    owner = await _make_db_user(db)
    removed = await _make_db_user(db)
    org = await _make_org(db)
    project = await _make_project(db, owner.id, org=org)
    exam = await _make_project(db, owner.id, org=org, kind="exam")
    await _add_membership(db, removed.id, org.id, role="CONTRIBUTOR", is_active=False)
    await db.commit()

    for target in (project, exam):
        for mode in BOTH_MODES:
            ctx = _ctx(mode, org)
            for permission in READ_PERMISSIONS + (Permission.PROJECT_EDIT,):
                assert await _allowed(db, removed, target, permission, ctx) is False, (
                    target.kind, mode, permission,
                )
                assert await _allowed_sync(db, removed, target, permission, ctx) is False


@pytest.mark.asyncio
async def test_async_annotator_creator_keeps_own_org_exam(async_test_db):
    """A student who authored an org-visible exam keeps reading its rubric
    (the creator already may edit it via check_user_can_edit_project)."""
    db = async_test_db
    creator = await _make_db_user(db)
    org = await _make_org(db)
    exam = await _make_project(db, creator.id, org=org, kind="exam")
    await _add_membership(db, creator.id, org.id, role="ANNOTATOR")
    await db.commit()

    for mode in BOTH_MODES:
        ctx = _ctx(mode, org)
        for permission in READ_PERMISSIONS:
            assert await _allowed(db, creator, exam, permission, ctx) is True, (mode, permission)


@pytest.mark.asyncio
async def test_async_legacy_exam_staff_membership_in_second_org_grants(async_test_db):
    """Legacy mode skips the ANNOTATOR attachment and keeps looking: staff
    status through another attached org still grants."""
    db = async_test_db
    owner = await _make_db_user(db)
    user = await _make_db_user(db)
    org_a = await _make_org(db, "A")
    org_b = await _make_org(db, "B")
    exam = await _make_project(db, owner.id, org=org_a, kind="exam")
    await _attach(db, exam, org_b, owner)
    await _add_membership(db, user.id, org_a.id, role="ANNOTATOR")
    await _add_membership(db, user.id, org_b.id, role="CONTRIBUTOR")
    await db.commit()

    assert await _allowed(db, user, exam, Permission.TASK_VIEW, None) is True
    assert await _allowed_sync(db, user, exam, Permission.TASK_VIEW, None) is True
    # Context mode is pinned to the named org.
    assert await _allowed(db, user, exam, Permission.TASK_VIEW, org_a.id) is False
    assert await _allowed(db, user, exam, Permission.TASK_VIEW, org_b.id) is True
