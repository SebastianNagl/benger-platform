"""Per-group roles (migration 111, core 2.28): the group role decides on a
group's projects, the org role on org-wide ones.

The reference case: a user who is org ANNOTATOR, ANNOTATOR in group A and
Admin (ORG_ADMIN) in group B. On A's exam they only reach the participant
tier; in B they create projects, assign tasks, edit settings and delete; they
stay refused org-wide project creation, group CRUD and org role changes. An
org CONTRIBUTOR who is a group ANNOTATOR is an ANNOTATOR on the group's
projects. A removed org member keeps no group-admin power.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from models import (
    ImportJob,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, ProjectOrganization, Task

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)
ADMIN, CONTRIB, ANNOT = (
    OrganizationRole.ORG_ADMIN,
    OrganizationRole.CONTRIBUTOR,
    OrganizationRole.ANNOTATOR,
)


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import get_current_user, require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _user(db, name="Person") -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name=name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _project(db, owner, *, kind=None, mode="open") -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=False,
        is_public=False,
        kind=kind,
        label_config=EXAM_CONFIG,
        assignment_mode=mode,
    )
    db.add(p)
    await db.flush()
    db.add(
        Task(
            id=str(uuid.uuid4()),
            project_id=p.id,
            inner_id=1,
            data={"sachverhalt": "Fall", "musterloesung": "GEHEIM"},
            created_by=owner.id,
        )
    )
    await db.flush()
    return p


async def _attach(db, project, org, by, group=None):
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org.id,
            group_id=group.id if group else None,
            assigned_by=by.id,
        )
    )
    await db.flush()


async def _world(db):
    """Org with groups A and B.

    niklas: org ANNOTATOR, A ANNOTATOR, B ORG_ADMIN. orgadmin: org ORG_ADMIN.
    author: org CONTRIBUTOR, CONTRIBUTOR in A and B. mixed: org CONTRIBUTOR,
    A ANNOTATOR. student: org ANNOTATOR, B ANNOTATOR.
    Projects by author: exam_a (exam, A), proj_a (A), proj_b (B, manual
    assignment).
    """
    niklas = await _user(db, "Niklas")
    orgadmin, author, mixed, student = [await _user(db) for _ in range(4)]
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    db.add(org)
    await db.flush()
    for user, role in (
        (niklas, ANNOT),
        (orgadmin, ADMIN),
        (author, CONTRIB),
        (mixed, CONTRIB),
        (student, ANNOT),
    ):
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
            )
        )
    groups = {}
    for name in ("A", "B"):
        groups[name] = OrganizationGroup(
            id=str(uuid.uuid4()), organization_id=org.id, name=f"LS {name}", is_active=True
        )
        db.add(groups[name])
    await db.flush()
    for user, name, role in (
        (niklas, "A", ANNOT),
        (niklas, "B", ADMIN),
        (author, "A", CONTRIB),
        (author, "B", CONTRIB),
        (mixed, "A", ANNOT),
        (student, "B", ANNOT),
    ):
        db.add(
            OrganizationGroupMembership(
                id=str(uuid.uuid4()), group_id=groups[name].id, user_id=user.id, role=role
            )
        )
    await db.flush()
    exam_a = await _project(db, author, kind="exam")
    await _attach(db, exam_a, org, author, groups["A"])
    proj_a = await _project(db, author)
    await _attach(db, proj_a, org, author, groups["A"])
    proj_b = await _project(db, author, mode="manual")
    await _attach(db, proj_b, org, author, groups["B"])
    await db.commit()
    return dict(
        org=org,
        a=groups["A"],
        b=groups["B"],
        niklas=niklas,
        orgadmin=orgadmin,
        author=author,
        mixed=mixed,
        student=student,
        exam_a=exam_a,
        proj_a=proj_a,
        proj_b=proj_b,
    )


async def test_group_annotator_gets_participant_tier_on_group_exam(async_test_db):
    from routers.projects.helpers import (
        TIER_PARTICIPANT,
        check_project_accessible_async,
        get_effective_project_role_async,
        get_project_access_tier_async,
        get_student_read_access_async,
    )

    db = async_test_db
    w = await _world(db)
    exam = w["exam_a"]
    assert await check_project_accessible_async(db, w["niklas"], exam.id) is False
    assert await get_student_read_access_async(db, w["niklas"], exam.id) is True
    assert await get_project_access_tier_async(db, w["niklas"], exam.id) == TIER_PARTICIPANT
    assert await get_effective_project_role_async(db, w["niklas"], exam) == "ANNOTATOR"
    # The org CONTRIBUTOR who is a group ANNOTATOR: participant too.
    assert await check_project_accessible_async(db, w["mixed"], exam.id) is False
    assert await get_project_access_tier_async(db, w["mixed"], exam.id) == TIER_PARTICIPANT
    # Org admins and group contributors keep the full tier.
    assert await check_project_accessible_async(db, w["orgadmin"], exam.id) is True


async def test_org_contributor_group_annotator_is_annotator_on_group_projects(
    async_test_db,
):
    from routers.projects.helpers import (
        check_user_can_edit_project_async,
        get_effective_project_role_async,
        resolve_project_roles_batch_async,
    )

    db = async_test_db
    w = await _world(db)
    proj = w["proj_a"]
    assert await get_effective_project_role_async(db, w["mixed"], proj) == "ANNOTATOR"
    assert await check_user_can_edit_project_async(db, w["mixed"], proj.id) is False
    loaded = (
        await db.execute(
            select(Project)
            .where(Project.id == proj.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    await db.refresh(loaded, ["project_organizations"])
    roles = await resolve_project_roles_batch_async(db, w["mixed"], [loaded])
    assert roles[proj.id] == ("ANNOTATOR", False)


async def test_group_admin_runs_group_projects(async_test_db):
    from routers.projects.helpers import (
        check_task_assigned_to_user,
        check_task_assigned_to_user_async,
        check_user_can_edit_project_async,
        check_user_can_edit_task_data_async,
        check_user_can_manage_shares_async,
        get_effective_project_role,
        get_effective_project_role_async,
        get_soft_deletable_project_ids_async,
    )

    db = async_test_db
    w = await _world(db)
    niklas, proj = w["niklas"], w["proj_b"]
    task_id = (
        await db.execute(select(Task.id).where(Task.project_id == proj.id))
    ).scalar_one()
    assert await get_effective_project_role_async(db, niklas, proj) == "ORG_ADMIN"
    # The sync lane (assign / remove assignment endpoints) agrees.
    assert await db.run_sync(lambda s: get_effective_project_role(s, niklas, proj)) == "ORG_ADMIN"
    assert await check_user_can_edit_project_async(db, niklas, proj.id) is True
    assert await check_user_can_edit_task_data_async(db, niklas, proj) is True
    assert await check_user_can_manage_shares_async(db, niklas, proj) is True
    assert proj.id in await get_soft_deletable_project_ids_async(db, niklas, [proj])
    # Manual assignment mode: the group Admin bypasses, the group's
    # annotator needs an assignment.
    assert await check_task_assigned_to_user_async(db, niklas, task_id, proj) is True
    assert (
        await db.run_sync(lambda s: check_task_assigned_to_user(s, niklas, task_id, proj))
        is True
    )
    assert await check_task_assigned_to_user_async(db, w["student"], task_id, proj) is False
    # Not on group A's project, where niklas is an annotator.
    assert w["proj_a"].id not in await get_soft_deletable_project_ids_async(
        db, niklas, [w["proj_a"]]
    )
    assert await check_user_can_edit_task_data_async(db, niklas, w["proj_a"]) is False


async def test_group_admin_http_surface(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id
    with _as_user(w["niklas"]):
        created = await async_test_client.post(
            "/api/projects/",
            json={
                "title": "Seminar B",
                "organization_id": org_id,
                "organization_group_id": w["b"].id,
            },
        )
        assert created.status_code == 200, created.text
        org_wide = await async_test_client.post(
            "/api/projects/", json={"title": "Org wide", "organization_id": org_id}
        )
        assert org_wide.status_code == 403
        in_a = await async_test_client.post(
            "/api/projects/",
            json={
                "title": "In A",
                "organization_id": org_id,
                "organization_group_id": w["a"].id,
            },
        )
        assert in_a.status_code == 403

        edited = await async_test_client.patch(
            f"/api/projects/{w['proj_b'].id}", json={"title": "Renamed by group admin"}
        )
        assert edited.status_code == 200, edited.text
        refused_edit = await async_test_client.patch(
            f"/api/projects/{w['proj_a'].id}", json={"title": "Nope"}
        )
        assert refused_edit.status_code == 403

        # Group CRUD and org roles stay with org admins.
        group_create = await async_test_client.post(
            f"/api/organizations/{org_id}/groups", json={"name": "LS C"}
        )
        assert group_create.status_code == 403
        role_change = await async_test_client.put(
            f"/api/organizations/{org_id}/members/{w['student'].id}/role",
            json={"role": "CONTRIBUTOR"},
        )
        assert role_change.status_code == 403

        # Member roles inside the own group: any role, admins included.
        promote = await async_test_client.patch(
            f"/api/organizations/{org_id}/groups/{w['b'].id}/members/{w['student'].id}",
            json={"role": "ORG_ADMIN"},
        )
        assert promote.status_code == 200, promote.text
        assert promote.json()["role"] == "ORG_ADMIN"
        demote = await async_test_client.patch(
            f"/api/organizations/{org_id}/groups/{w['b'].id}/members/{w['student'].id}",
            json={"role": "CONTRIBUTOR"},
        )
        assert demote.status_code == 200
        add = await async_test_client.post(
            f"/api/organizations/{org_id}/groups/{w['b'].id}/members",
            json={"user_id": w["mixed"].id},
        )
        assert add.status_code == 201, add.text
        assert add.json()["role"] == "ANNOTATOR"
        assert add.json()["org_role"] == "CONTRIBUTOR"
        members = await async_test_client.get(
            f"/api/organizations/{org_id}/groups/{w['b'].id}/members"
        )
        assert members.status_code == 200
        by_user = {m["user_id"]: m for m in members.json()}
        assert by_user[w["niklas"].id]["role"] == "ORG_ADMIN"
        assert by_user[w["niklas"].id]["org_role"] == "ANNOTATOR"
        assert "is_group_admin" not in by_user[w["niklas"].id]
        # Not in group A.
        foreign = await async_test_client.patch(
            f"/api/organizations/{org_id}/groups/{w['a'].id}/members/{w['mixed'].id}",
            json={"role": "ORG_ADMIN"},
        )
        assert foreign.status_code == 403

        groups = await async_test_client.get(f"/api/organizations/{org_id}/groups")
        mine = {g["name"]: g for g in groups.json()}
        assert mine["LS A"]["my_role"] == "ANNOTATOR"
        assert mine["LS B"]["my_role"] == "ORG_ADMIN"
        assert "is_group_admin" not in mine["LS A"]

        contexts = await async_test_client.get("/api/auth/me/contexts")
        assert contexts.status_code == 200, contexts.text
        org_ctx = next(o for o in contexts.json()["organizations"] if o["id"] == org_id)
        assert {g["name"]: g["role"] for g in org_ctx["groups"]} == {
            "LS A": "ANNOTATOR",
            "LS B": "ORG_ADMIN",
        }

        deleted = await async_test_client.delete(f"/api/projects/{w['proj_b'].id}")
        assert deleted.status_code in (200, 204), deleted.text

    with _as_user(w["orgadmin"]):
        roster = await async_test_client.get(f"/api/organizations/{org_id}/members")
        chips = {m["user_id"]: m["groups"] for m in roster.json()}
        assert {g["name"]: g["role"] for g in chips[w["niklas"].id]} == {
            "LS A": "ANNOTATOR",
            "LS B": "ORG_ADMIN",
        }
        project_roster = await async_test_client.get(
            f"/api/projects/{w['proj_a'].id}/members"
        )
        assert project_roster.status_code == 200, project_roster.text
        roles = {m["user_id"]: m["role"] for m in project_roster.json()}
        assert roles[w["mixed"].id] == "ANNOTATOR"
        assert roles[w["author"].id] == "CONTRIBUTOR"
        assert roles[w["orgadmin"].id] == "ORG_ADMIN"


async def test_removed_org_member_loses_group_admin_powers(
    async_test_client, async_test_db
):
    from org_groups import build_select_admin_group_ids

    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    async def admin_groups():
        return set(
            (await db.execute(build_select_admin_group_ids(w["niklas"].id))).scalars().all()
        )

    assert await admin_groups() == {w["b"].id}
    # A deactivated membership (leftover group row) grants nothing.
    membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == w["niklas"].id,
                OrganizationMembership.organization_id == org_id,
            )
        )
    ).scalar_one()
    membership.is_active = False
    await db.commit()
    assert await admin_groups() == set()
    with _as_user(w["niklas"]):
        r = await async_test_client.get(
            f"/api/organizations/{org_id}/groups/{w['b'].id}/members"
        )
        assert r.status_code == 403
    membership.is_active = True
    await db.commit()

    # Removing the member deletes their group rows in that org.
    with _as_user(w["orgadmin"]):
        r = await async_test_client.delete(
            f"/api/organizations/{org_id}/members/{w['niklas'].id}"
        )
        assert r.status_code == 200, r.text
    rows = (
        await db.execute(
            select(OrganizationGroupMembership.id).where(
                OrganizationGroupMembership.user_id == w["niklas"].id
            )
        )
    ).all()
    assert rows == []
    assert await admin_groups() == set()


async def test_grouped_project_notifications_reach_group_admins(async_test_db):
    from mailer.notification_service import NotificationService

    db = async_test_db
    w = await _world(db)
    recipients = await db.run_sync(
        lambda s: set(
            NotificationService.get_notification_recipients(
                s,
                "project_created",
                {"organization_id": w["org"].id, "project_id": w["proj_b"].id},
            )
        )
    )
    assert w["niklas"].id in recipients
    assert w["orgadmin"].id in recipients
    assert w["mixed"].id not in recipients
    invite = await db.run_sync(
        lambda s: set(
            NotificationService.get_notification_recipients(
                s,
                "organization_invitation_sent",
                {"organization_id": w["org"].id, "organization_group_id": w["b"].id},
            )
        )
    )
    assert invite == {w["orgadmin"].id, w["niklas"].id}


async def test_create_new_import_into_group(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    def body(user, **extra):
        return {
            "object_key": f"imports/2026/10/{user.id}/20261006_full.json",
            "organization_id": org_id,
            **extra,
        }

    fake = MagicMock()
    fake.id = "celery-import"
    with patch("routers.projects.import_export.send_task_safe", return_value=fake):
        with _as_user(w["niklas"]):
            ok = await async_test_client.post(
                "/api/projects/project-imports",
                json=body(w["niklas"], organization_group_id=w["b"].id),
            )
            assert ok.status_code == 202, ok.text
            org_wide = await async_test_client.post(
                "/api/projects/project-imports", json=body(w["niklas"])
            )
            assert org_wide.status_code == 403
            in_a = await async_test_client.post(
                "/api/projects/project-imports",
                json=body(w["niklas"], organization_group_id=w["a"].id),
            )
            assert in_a.status_code == 403
            no_org = await async_test_client.post(
                "/api/projects/project-imports",
                json={
                    "object_key": f"imports/2026/10/{w['niklas'].id}/x.json",
                    "organization_group_id": w["b"].id,
                },
            )
            assert no_org.status_code == 400
    job = (
        await db.execute(select(ImportJob).where(ImportJob.id == ok.json()["job_id"]))
    ).scalar_one()
    assert job.organization_id == org_id
    assert job.organization_group_id == w["b"].id

    # Worker side: the created project is attached through the group, and
    # the role is re-checked.
    from import_stream import (
        ImportValidationError,
        _create_imported_project,
        _FullImportContext,
    )

    def run(s, user, group_id):
        ctx = _FullImportContext(s, user.id)
        _create_imported_project(ctx, {"title": "Copy"}, "Copy", org_id, group_id)
        s.flush()
        return ctx.new_project_id

    new_id = await db.run_sync(lambda s: run(s, w["niklas"], w["b"].id))
    row = (
        await db.execute(
            select(ProjectOrganization).where(ProjectOrganization.project_id == new_id)
        )
    ).scalar_one()
    assert row.organization_id == org_id and row.group_id == w["b"].id

    def refused(s, user, group_id):
        try:
            run(s, user, group_id)
        except ImportValidationError as e:
            return e.status_code
        return None

    assert await db.run_sync(lambda s: refused(s, w["niklas"], w["a"].id)) == 403
    assert await db.run_sync(lambda s: refused(s, w["niklas"], None)) == 403
