"""Organization groups: the cross-group isolation matrix.

Org → group → user layer (shared/org_groups): a project attachment scoped to
a group is visible only to that group's members, the org's ORG_ADMINs, the
creator, and superadmins; group API keys are spent only for that group's
projects. These tests drive the SAME fixture world through every enforcement
surface — both decider lanes, the list arms (async lane + sync twin via
run_sync), the participant tier, the admin gates, the duplicate
authorization.py decider, the roster fan-in, the group management router,
the attachment endpoints, and key resolution — so a drift in any one of
them fails here.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from models import (
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, ProjectOrganization, Task

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
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
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _org(db, *members, settings=None) -> Organization:
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug,
        settings=settings or {},
    )
    db.add(org)
    await db.flush()
    for user, role in members:
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()), user_id=user.id, organization_id=org.id,
            role=role, is_active=True,
        ))
    await db.commit()
    return org


async def _group(db, org, name, *members) -> OrganizationGroup:
    """members: (user, is_group_admin) tuples."""
    g = OrganizationGroup(
        id=str(uuid.uuid4()), organization_id=org.id, name=name, is_active=True,
    )
    db.add(g)
    await db.flush()
    for user, is_admin in members:
        db.add(OrganizationGroupMembership(
            id=str(uuid.uuid4()), group_id=g.id, user_id=user.id,
            is_group_admin=is_admin,
        ))
    await db.commit()
    return g


async def _project(db, owner, *, private=False, kind=None, tasks=1) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=private,
        is_public=False,
        kind=kind,
        label_config=EXAM_CONFIG,
        assignment_mode="open",
    )
    db.add(p)
    await db.flush()
    for i in range(tasks):
        db.add(Task(
            id=str(uuid.uuid4()), project_id=p.id, inner_id=i + 1,
            data={"sachverhalt": f"Fall {i}", "musterloesung": "GEHEIM"},
            created_by=owner.id,
        ))
    await db.commit()
    return p


async def _attach(db, project, org, by, group=None):
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()), project_id=project.id, organization_id=org.id,
        group_id=group.id if group else None, assigned_by=by.id,
    ))
    await db.commit()


async def _world(db):
    """One org, two groups (A/B), the standard cast, three projects.

    Cast: orgadmin (ORG_ADMIN, no group), contrib_a/contrib_b (CONTRIBUTOR in
    group A/B), gadmin_a (CONTRIBUTOR + group-admin of A), annot_a/annot_b
    (ANNOTATOR in group A/B), loose (CONTRIBUTOR, no group).
    Projects (owner = contrib_b for p_a → creator arm is exercised across
    group lines): p_a (grouped→A), p_org (org-wide), exam_a (exam, grouped→A).
    """
    orgadmin, contrib_a, contrib_b, gadmin_a, annot_a, annot_b, loose = [
        await _user(db) for _ in range(7)
    ]
    org = await _org(
        db,
        (orgadmin, OrganizationRole.ORG_ADMIN),
        (contrib_a, OrganizationRole.CONTRIBUTOR),
        (contrib_b, OrganizationRole.CONTRIBUTOR),
        (gadmin_a, OrganizationRole.CONTRIBUTOR),
        (annot_a, OrganizationRole.ANNOTATOR),
        (annot_b, OrganizationRole.ANNOTATOR),
        (loose, OrganizationRole.CONTRIBUTOR),
    )
    group_a = await _group(db, org, "LS A", (contrib_a, False), (gadmin_a, True), (annot_a, False))
    group_b = await _group(db, org, "LS B", (contrib_b, False), (annot_b, False))

    p_a = await _project(db, contrib_b)
    await _attach(db, p_a, org, orgadmin, group=group_a)
    p_org = await _project(db, contrib_a)
    await _attach(db, p_org, org, orgadmin)
    exam_a = await _project(db, gadmin_a, kind="exam")
    await _attach(db, exam_a, org, orgadmin, group=group_a)

    return {
        "org": org, "group_a": group_a, "group_b": group_b,
        "orgadmin": orgadmin, "contrib_a": contrib_a, "contrib_b": contrib_b,
        "gadmin_a": gadmin_a, "annot_a": annot_a, "annot_b": annot_b,
        "loose": loose, "p_a": p_a, "p_org": p_org, "exam_a": exam_a,
    }


# ------------------------------------------------------------- list arms ----


async def test_accessible_ids_group_matrix_both_lanes(async_test_db):
    from routers.projects.helpers import (
        get_accessible_project_ids,
        get_accessible_project_ids_async,
    )

    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    async def ids_async(user):
        return set(await get_accessible_project_ids_async(db, user, org_id) or [])

    def ids_sync(user):
        return lambda sync_db: set(
            get_accessible_project_ids(sync_db, user, org_id) or []
        )

    expectations = [
        # (user, sees p_a, sees p_org)
        (w["contrib_a"], True, True),
        (w["contrib_b"], True, True),   # creator of p_a — never loses it
        (w["loose"], False, True),
        (w["orgadmin"], True, True),    # org admin sees through groups
        (w["gadmin_a"], True, True),
    ]
    for user, sees_pa, sees_porg in expectations:
        got = await ids_async(user)
        assert (w["p_a"].id in got) is sees_pa, (user.id, "async p_a")
        assert (w["p_org"].id in got) is sees_porg, (user.id, "async p_org")
        got_sync = await db.run_sync(ids_sync(user))
        assert got == got_sync, f"sync/async twin drift for {user.id}"

    # Cross-group CONTRIBUTOR never sees the other group's project.
    got_b_view = await ids_async(w["loose"])
    assert w["exam_a"].id not in got_b_view

    # ANNOTATOR exam-strip keeps exams out of the generic browser — except
    # for a group admin of the attachment's group.
    annot_a_ids = await ids_async(w["annot_a"])
    assert w["exam_a"].id not in annot_a_ids
    gadmin_ids = await ids_async(w["gadmin_a"])
    assert w["exam_a"].id in gadmin_ids


async def test_per_project_deciders_both_modes_and_lanes(async_test_db):
    from routers.projects.helpers import (
        check_project_accessible,
        check_project_accessible_async,
    )

    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    cases = [
        # (user, project, expected)
        (w["contrib_a"], w["p_a"], True),
        (w["loose"], w["p_a"], False),
        (w["annot_b"], w["p_a"], False),
        (w["orgadmin"], w["p_a"], True),
        (w["contrib_b"], w["p_a"], True),  # creator
        (w["loose"], w["p_org"], True),
    ]
    for user, project, expected in cases:
        for ctx in (org_id, None):  # context mode + legacy mode
            got = await check_project_accessible_async(
                db, user, project.id, org_context=ctx
            )
            assert got is expected, (user.id, project.id, ctx, "async")
            got_sync = await db.run_sync(
                lambda s, u=user, p=project, c=ctx: check_project_accessible(
                    s, u, p.id, org_context=c
                )
            )
            assert got_sync is expected, (user.id, project.id, ctx, "sync")


async def test_participant_tier_grouped_exam(async_test_db):
    from routers.projects.helpers import (
        get_participant_project_ids_async,
        get_project_access_tier_async,
    )

    db = async_test_db
    w = await _world(db)

    # Group A annotator reaches the group exam via the narrow tier;
    # group B annotator has NO standing at all.
    assert await get_project_access_tier_async(db, w["annot_a"], w["exam_a"].id) == "participant"
    assert await get_project_access_tier_async(db, w["annot_b"], w["exam_a"].id) is None
    # Org admin and the group admin hold the full tier.
    assert await get_project_access_tier_async(db, w["orgadmin"], w["exam_a"].id) == "full"
    assert await get_project_access_tier_async(db, w["gadmin_a"], w["exam_a"].id) == "full"

    # Batch twin (project list tagging) agrees with the per-project arm.
    tagged_a = await get_participant_project_ids_async(db, w["annot_a"].id)
    assert tagged_a.get(w["exam_a"].id) == "org_exam"
    tagged_b = await get_participant_project_ids_async(db, w["annot_b"].id)
    assert w["exam_a"].id not in tagged_b


async def test_admin_gates_group_admin_scope(async_test_db):
    from routers.projects.helpers import (
        check_user_can_edit_project_async,
        check_user_can_edit_task_data_async,
        check_user_can_manage_shares_async,
        get_effective_project_role_async,
    )

    db = async_test_db
    w = await _world(db)

    # Effective role: group admin ⇒ ORG_ADMIN on the group's project only.
    assert await get_effective_project_role_async(db, w["gadmin_a"], w["p_a"]) == "ORG_ADMIN"
    assert await get_effective_project_role_async(db, w["gadmin_a"], w["p_org"]) == OrganizationRole.CONTRIBUTOR
    assert await get_effective_project_role_async(db, w["loose"], w["p_a"]) is None

    # Musterlösung edit + share management: ORG_ADMIN-only gates open for
    # the attachment group's admin, closed for plain group members.
    for gate in (check_user_can_edit_task_data_async, check_user_can_manage_shares_async):
        assert await gate(db, w["gadmin_a"], w["p_a"]) is True
        assert await gate(db, w["contrib_a"], w["p_a"]) is False
        assert await gate(db, w["orgadmin"], w["p_a"]) is True

    # Edit: eligible CONTRIBUTOR yes, cross-group CONTRIBUTOR no.
    assert await check_user_can_edit_project_async(db, w["contrib_a"], w["p_a"].id) is True
    assert await check_user_can_edit_project_async(db, w["loose"], w["p_a"].id) is False


async def test_authorization_duplicate_decider_both_lanes(async_test_db):
    from types import SimpleNamespace

    from app.core.authorization import AuthorizationService, Permission

    db = async_test_db
    w = await _world(db)
    svc = AuthorizationService()
    org_id = w["org"].id

    def principal(u):
        # The service receives the AUTH principal (no ORM relationships) —
        # passing the ORM row would lazy-load memberships in async context.
        return SimpleNamespace(id=u.id, is_superadmin=u.is_superadmin)

    for ctx in (org_id, None):
        assert await svc.check_project_access_async(
            principal(w["contrib_a"]), w["p_a"], Permission.PROJECT_VIEW, db, org_context=ctx
        ) is True
        assert await svc.check_project_access_async(
            principal(w["loose"]), w["p_a"], Permission.PROJECT_VIEW, db, org_context=ctx
        ) is False
        got_sync = await db.run_sync(
            lambda s, c=ctx: svc.check_project_access(
                principal(w["loose"]), w["p_a"], Permission.PROJECT_VIEW, s, org_context=c
            )
        )
        assert got_sync is False
    # Group admin gets admin-level permissions on the group project.
    assert await svc.check_project_access_async(
        principal(w["gadmin_a"]), w["p_a"], Permission.PROJECT_EDIT, db, org_context=org_id
    ) is True


# --------------------------------------------------------- HTTP surfaces ----


async def test_list_endpoint_and_members_fan_in(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id
    headers = {"X-Organization-Context": org_id}

    with _as_user(w["loose"]):
        r = await async_test_client.get("/api/projects/", headers=headers)
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["items"]}
        assert w["p_org"].id in ids
        assert w["p_a"].id not in ids

    with _as_user(w["contrib_a"]):
        r = await async_test_client.get("/api/projects/", headers=headers)
        ids = {p["id"] for p in r.json()["items"]}
        assert w["p_a"].id in ids

        # Roster fan-in: group A project lists group A members + org admins,
        # never group B / loose members.
        r = await async_test_client.get(
            f"/api/projects/{w['p_a'].id}/members", headers=headers
        )
        assert r.status_code == 200
        member_ids = {m["user_id"] for m in r.json()}
        assert w["contrib_a"].id in member_ids
        assert w["gadmin_a"].id in member_ids
        assert w["orgadmin"].id in member_ids
        assert w["annot_b"].id not in member_ids
        assert w["loose"].id not in member_ids


async def test_groups_router_crud_and_gates(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    # Create: org admin 201, contributor 403, duplicate 409.
    with _as_user(w["orgadmin"]):
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups", json={"name": "LS C"}
        )
        assert r.status_code == 201, r.text
        group_c = r.json()
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups", json={"name": "LS C"}
        )
        assert r.status_code == 409
    with _as_user(w["contrib_a"]):
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups", json={"name": "LS D"}
        )
        assert r.status_code == 403

    # List: any member; ANNOTATORs get no member counts.
    with _as_user(w["annot_a"]):
        r = await async_test_client.get(f"/api/organizations/{org_id}/groups")
        assert r.status_code == 200
        by_name = {g["name"]: g for g in r.json()}
        assert by_name["LS A"]["member_count"] is None
        assert by_name["LS A"]["is_member"] is True
        assert by_name["LS B"]["is_member"] is False
    with _as_user(w["contrib_a"]):
        r = await async_test_client.get(f"/api/organizations/{org_id}/groups")
        assert {g["name"] for g in r.json()} >= {"LS A", "LS B", "LS C"}
        assert all(g["member_count"] is not None for g in r.json())

    # Member management: the group's admin may manage ITS members, not B's.
    with _as_user(w["gadmin_a"]):
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups/{w['group_a'].id}/members",
            json={"user_id": w["loose"].id, "is_group_admin": False},
        )
        assert r.status_code == 201, r.text
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups/{w['group_b'].id}/members",
            json={"user_id": w["loose"].id, "is_group_admin": False},
        )
        assert r.status_code == 403
        # Non-org-member target is rejected.
        outsider = await _user(db)
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups/{w['group_a'].id}/members",
            json={"user_id": outsider.id, "is_group_admin": False},
        )
        assert r.status_code == 400
        r = await async_test_client.delete(
            f"/api/organizations/{org_id}/groups/{w['group_a'].id}/members/{w['loose'].id}"
        )
        assert r.status_code == 200

    # Delete: 409 while attachments reference the group; a group WITH
    # members but no attachments deletes cleanly (the memberships go with
    # it via the DB cascade — regression: an ORM delete without
    # passive_deletes tried to NULL the NOT-NULL group_id and 500'd).
    with _as_user(w["orgadmin"]):
        r = await async_test_client.delete(
            f"/api/organizations/{org_id}/groups/{w['group_a'].id}"
        )
        assert r.status_code == 409
        r = await async_test_client.post(
            f"/api/organizations/{org_id}/groups/{group_c['id']}/members",
            json={"user_id": w["loose"].id, "is_group_admin": False},
        )
        assert r.status_code == 201
        r = await async_test_client.delete(
            f"/api/organizations/{org_id}/groups/{group_c['id']}"
        )
        assert r.status_code == 200, r.text
        member_rows = await db.run_sync(
            lambda s: s.query(OrganizationGroupMembership)
            .filter(OrganizationGroupMembership.group_id == group_c["id"])
            .count()
        )
        assert member_rows == 0


async def test_attachment_endpoints_group_scope(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id
    headers = {"X-Organization-Context": org_id}

    # create_project with organization_group_id stamps the attachment.
    with _as_user(w["contrib_a"]):
        r = await async_test_client.post(
            "/api/projects/",
            headers=headers,
            json={
                "title": "Grouped via create",
                "organization_group_id": w["group_a"].id,
            },
        )
        assert r.status_code == 200, r.text
        new_id = r.json()["id"]
        row = await db.run_sync(
            lambda s: s.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == new_id)
            .first()
        )
        assert row is not None and row.group_id == w["group_a"].id

        # Scoping to a group the caller doesn't belong to is rejected.
        r = await async_test_client.post(
            "/api/projects/",
            headers=headers,
            json={
                "title": "Foreign group",
                "organization_group_id": w["group_b"].id,
            },
        )
        assert r.status_code == 403

    # update_project_visibility with organization_attachments re-scopes.
    with _as_user(w["contrib_b"]):  # creator of p_a
        r = await async_test_client.patch(
            f"/api/projects/{w['p_a'].id}/visibility",
            headers=headers,
            json={
                "is_private": False,
                "organization_attachments": [
                    {"organization_id": org_id, "group_id": w["group_b"].id}
                ],
            },
        )
        assert r.status_code == 200, r.text
        row = await db.run_sync(
            lambda s: s.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == w["p_a"].id)
            .first()
        )
        assert row.group_id == w["group_b"].id


# ------------------------------------------------------- invitations gate ----


async def test_invitation_gate_and_group_validation(async_test_db):
    from routers.invitations import _authorize_invitation
    from fastapi import HTTPException

    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    def run(user, role, group_id):
        def _inner(s):
            db_user = s.query(User).filter(User.id == user.id).first()
            try:
                _authorize_invitation(s, db_user, org_id, role, group_id)
                return None
            except HTTPException as e:
                return e.status_code
        return _inner

    # Org admin: free rein, with or without group.
    assert await db.run_sync(run(w["orgadmin"], OrganizationRole.ANNOTATOR, None)) is None
    assert await db.run_sync(run(w["orgadmin"], OrganizationRole.ORG_ADMIN, w["group_a"].id)) is None
    # Group admin: only into their own group, never as ORG_ADMIN.
    assert await db.run_sync(run(w["gadmin_a"], OrganizationRole.CONTRIBUTOR, w["group_a"].id)) is None
    assert await db.run_sync(run(w["gadmin_a"], OrganizationRole.ORG_ADMIN, w["group_a"].id)) == 403
    assert await db.run_sync(run(w["gadmin_a"], OrganizationRole.ANNOTATOR, w["group_b"].id)) == 403
    assert await db.run_sync(run(w["gadmin_a"], OrganizationRole.ANNOTATOR, None)) == 403
    # Plain members: nothing.
    assert await db.run_sync(run(w["contrib_a"], OrganizationRole.ANNOTATOR, w["group_a"].id)) == 403


# ------------------------------------------------------- notification fan ----


async def test_project_notification_fan_out_respects_groups(async_test_db):
    """PROJECT_* events on a group-attached project reach the group's
    members + org admins + superadmins — never the other groups."""
    from mailer.notification_service import NotificationService

    db = async_test_db
    w = await _world(db)

    def recipients(s, project):
        return set(
            NotificationService.get_notification_recipients(
                s,
                "project_created",
                {"organization_id": w["org"].id, "project_id": project.id},
            )
        )

    grouped = await db.run_sync(lambda s: recipients(s, w["p_a"]))
    assert w["contrib_a"].id in grouped
    assert w["gadmin_a"].id in grouped
    assert w["annot_a"].id in grouped
    assert w["orgadmin"].id in grouped
    assert w["contrib_b"].id not in grouped
    assert w["annot_b"].id not in grouped
    assert w["loose"].id not in grouped

    org_wide = await db.run_sync(lambda s: recipients(s, w["p_org"]))
    for member in ("contrib_a", "contrib_b", "annot_a", "annot_b", "loose", "orgadmin"):
        assert w[member].id in org_wide


# --------------------------------------------------------- key resolution ----


async def test_group_key_resolution_matrix(async_test_db):
    from services.org_api_key_service import org_api_key_service

    assert org_api_key_service is not None, "encryption service missing in test env"

    db = async_test_db
    w = await _world(db)
    org_id = w["org"].id

    # Org pays; the org holds an org-wide openai key AND a group-A key.
    org_row = await db.get(Organization, org_id)
    org_row.settings = {"require_private_keys": False}
    await db.commit()

    org_key = "sk-orgwide-" + "x" * 24
    group_key = "sk-group-a-" + "y" * 24

    def seed_keys(s):
        assert org_api_key_service.set_org_api_key(
            s, org_id, "openai", org_key, w["orgadmin"].id
        )
        assert org_api_key_service.set_org_api_key(
            s, org_id, "openai", group_key, w["orgadmin"].id, group_id=w["group_a"].id
        )

    await db.run_sync(seed_keys)

    def resolve(s, user, project_id):
        return org_api_key_service.resolve_api_key(
            s, user.id, org_id, "openai", project_id=project_id
        )

    # Group project spends the GROUP key; org-wide project the org key;
    # no project context = org-wide row only.
    assert await db.run_sync(lambda s: resolve(s, w["contrib_a"], w["p_a"].id)) == group_key
    assert await db.run_sync(lambda s: resolve(s, w["contrib_a"], w["p_org"].id)) == org_key
    assert await db.run_sync(lambda s: resolve(s, w["contrib_a"], None)) == org_key
    # The key follows the PROJECT: an org admin (not in group A) grading the
    # group project still spends group A's key.
    assert await db.run_sync(lambda s: resolve(s, w["orgadmin"], w["p_a"].id)) == group_key

    # Cross-contamination guards: org-wide reads/writes never touch the
    # group row and vice versa.
    def scope_checks(s):
        assert org_api_key_service.get_org_api_key(s, org_id, "openai") == org_key
        assert (
            org_api_key_service.get_org_api_key(
                s, org_id, "openai", group_id=w["group_a"].id
            )
            == group_key
        )
        # Org-wide upsert must not clobber the group row.
        new_org_key = "sk-orgwide2-" + "z" * 24
        assert org_api_key_service.set_org_api_key(
            s, org_id, "openai", new_org_key, w["orgadmin"].id
        )
        assert (
            org_api_key_service.get_org_api_key(
                s, org_id, "openai", group_id=w["group_a"].id
            )
            == group_key
        )
        # Per-scope status.
        assert org_api_key_service.get_org_api_key_status(s, org_id)["openai"] is True
        assert (
            org_api_key_service.get_org_api_key_status(
                s, org_id, group_id=w["group_b"].id
            )["openai"]
            is False
        )
        # Removing the group key falls resolution back to the org-wide row.
        assert org_api_key_service.remove_org_api_key(
            s, org_id, "openai", group_id=w["group_a"].id
        )
        assert resolve(s, w["contrib_a"], w["p_a"].id) == new_org_key

    await db.run_sync(scope_checks)

    # The worker twin agrees (lockstep contract).
    from shared_org_api_key_service import org_api_key_service as worker_svc

    assert worker_svc is not None
    got = await db.run_sync(
        lambda s: worker_svc.resolve_api_key(
            s, w["contrib_a"].id, org_id, "openai", project_id=w["p_org"].id
        )
    )
    assert got == "sk-orgwide2-" + "z" * 24
