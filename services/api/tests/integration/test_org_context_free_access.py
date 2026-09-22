"""The selected organization is not a read boundary (core 2.21).

The LMU shape of 2026-09-22: an exam attached to the org through a group,
with a started window; a CONTRIBUTOR invited into that group; an ANNOTATOR of
the same group. Whatever ``X-Organization-Context`` the client sends (the
org's id, another org's id, the literal ``private`` of the apex host, or no
header), the contributor holds the full tier with the Korrektur-relevant role
and the annotator stays a participant. The project list is the union over
every membership and never refuses a context.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

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
from routers.projects.helpers import (
    TIER_FULL,
    TIER_PARTICIPANT,
    get_accessible_project_ids,
    get_accessible_project_ids_async,
    get_project_access_tier,
    get_project_access_tier_async,
)

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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


def _principal(db_user):
    from auth_module.models import User as AuthUser

    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


async def _user(db) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _org(db, *members) -> Organization:
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug, settings={}
    )
    db.add(org)
    await db.flush()
    for user, role in members:
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
            )
        )
    await db.commit()
    return org


async def _group(db, org, *members) -> OrganizationGroup:
    g = OrganizationGroup(
        id=str(uuid.uuid4()), organization_id=org.id, name="Heidebach", is_active=True
    )
    db.add(g)
    await db.flush()
    for user, is_admin in members:
        db.add(
            OrganizationGroupMembership(
                id=str(uuid.uuid4()),
                group_id=g.id,
                user_id=user.id,
                is_group_admin=is_admin,
            )
        )
    await db.commit()
    return g


async def _project(db, owner, *, kind=None, window_started=False) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=False,
        is_public=False,
        kind=kind,
        label_config=EXAM_CONFIG,
        assignment_mode="open",
        korrektur_enabled=kind == "exam",
        window_start_at=(
            datetime.now(timezone.utc) - timedelta(days=1) if window_started else None
        ),
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
    await db.commit()
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
    await db.commit()


async def _world(db):
    """LMU: creator (ORG_ADMIN), contributor and annotator in the group, a
    member of two orgs (CONTRIBUTOR in both) and an outsider org."""
    creator, contributor, annotator, two_orgs, stranger = [
        await _user(db) for _ in range(5)
    ]
    lmu = await _org(
        db,
        (creator, OrganizationRole.ORG_ADMIN),
        (contributor, OrganizationRole.CONTRIBUTOR),
        (annotator, OrganizationRole.ANNOTATOR),
        (two_orgs, OrganizationRole.CONTRIBUTOR),
    )
    other = await _org(db, (two_orgs, OrganizationRole.CONTRIBUTOR))
    group = await _group(db, lmu, (contributor, False), (annotator, False), (two_orgs, False))
    exam = await _project(db, creator, kind="exam", window_started=True)
    await _attach(db, exam, lmu, creator, group=group)
    other_project = await _project(db, two_orgs)
    await _attach(db, other_project, other, two_orgs)
    return {
        "lmu": lmu,
        "other": other,
        "group": group,
        "creator": creator,
        "contributor": contributor,
        "annotator": annotator,
        "two_orgs": two_orgs,
        "stranger": stranger,
        "exam": exam,
        "other_project": other_project,
    }


def _contexts(w):
    return ("private", w["lmu"].id, w["other"].id, None)


def _headers(ctx):
    return {} if ctx is None else {"X-Organization-Context": ctx}


async def _tier_both_lanes(db, user, project, ctx):
    principal = _principal(user)
    got_async = await get_project_access_tier_async(db, principal, project.id, ctx)
    got_sync = await db.run_sync(
        lambda s: get_project_access_tier(s, principal, project.id, ctx)
    )
    assert got_async == got_sync, (user.id, ctx, got_async, got_sync)
    return got_async


async def test_group_contributor_holds_the_full_tier_in_every_context(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _world(db)
    for ctx in _contexts(w):
        assert await _tier_both_lanes(db, w["contributor"], w["exam"], ctx) == TIER_FULL
        with _as_user(w["contributor"]):
            r = await async_test_client.get(
                f"/api/projects/{w['exam'].id}", headers=_headers(ctx)
            )
        assert r.status_code == 200, (ctx, r.text)
        body = r.json()
        assert body["access_tier"] == "full", ctx
        assert body["effective_role"] == "CONTRIBUTOR", ctx
        assert body["can_edit"] is True, ctx
        # The full-tier gate of the project data (the Musterloesung stays).
        assert body.get("label_config"), ctx


async def test_group_annotator_stays_a_participant_in_every_context(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _world(db)
    for ctx in _contexts(w):
        assert (
            await _tier_both_lanes(db, w["annotator"], w["exam"], ctx) == TIER_PARTICIPANT
        )
        with _as_user(w["annotator"]):
            r = await async_test_client.get(
                f"/api/projects/{w['exam'].id}", headers=_headers(ctx)
            )
            assert r.status_code == 200, (ctx, r.text)
            body = r.json()
            assert body["access_tier"] == "participant", ctx
            assert body["effective_role"] == "ANNOTATOR", ctx
            assert body["can_edit"] is False, ctx
            # A write the full tier would allow stays refused.
            r = await async_test_client.patch(
                f"/api/projects/{w['exam'].id}",
                json={"title": "renamed"},
                headers=_headers(ctx),
            )
            assert r.status_code == 403, (ctx, r.text)


async def test_creator_and_stranger_are_unchanged(async_test_db):
    db = async_test_db
    w = await _world(db)
    for ctx in _contexts(w):
        assert await _tier_both_lanes(db, w["creator"], w["exam"], ctx) == TIER_FULL
        assert await _tier_both_lanes(db, w["stranger"], w["exam"], ctx) is None


async def test_list_is_the_union_over_every_membership(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)

    async def listed(user, ctx):
        with _as_user(user):
            r = await async_test_client.get(
                "/api/projects/?page_size=500", headers=_headers(ctx)
            )
        assert r.status_code == 200, (ctx, r.text)
        return {p["id"]: p for p in r.json()["items"]}

    for ctx in _contexts(w):
        rows = await listed(w["two_orgs"], ctx)
        assert {w["exam"].id, w["other_project"].id} <= set(rows), ctx
        assert rows[w["exam"].id]["access_tier"] == "full"
        assert rows[w["exam"].id]["effective_role"] == "CONTRIBUTOR"
        assert rows[w["exam"].id]["can_edit"] is True
        assert rows[w["other_project"].id]["effective_role"] == "ORG_ADMIN"
        assert rows[w["other_project"].id]["can_edit"] is True

        rows = await listed(w["contributor"], ctx)
        assert w["exam"].id in rows and w["other_project"].id not in rows, ctx
        assert rows[w["exam"].id]["can_edit"] is True

        rows = await listed(w["annotator"], ctx)
        assert w["exam"].id in rows, ctx
        assert rows[w["exam"].id]["access_tier"] == "participant"
        assert rows[w["exam"].id]["effective_role"] == "ANNOTATOR"
        assert rows[w["exam"].id]["can_edit"] is False

        # A context the caller never joined is no error, just no extra rows.
        rows = await listed(w["stranger"], ctx)
        assert w["exam"].id not in rows and w["other_project"].id not in rows, ctx


async def test_id_helper_ignores_the_context_on_both_lanes(async_test_db):
    db = async_test_db
    w = await _world(db)
    principal = _principal(w["two_orgs"])
    expected = None
    for ctx in _contexts(w):
        got_async = set(await get_accessible_project_ids_async(db, principal, ctx))
        got_sync = set(
            await db.run_sync(lambda s, c=ctx: get_accessible_project_ids(s, principal, c))
        )
        assert got_async == got_sync, ctx
        assert {w["exam"].id, w["other_project"].id} <= got_async, ctx
        if expected is None:
            expected = got_async
        assert got_async == expected, ctx
    # The annotator's org list carries no exam (the participant arm does).
    annotator_ids = set(
        await get_accessible_project_ids_async(db, _principal(w["annotator"]), None)
    )
    assert w["exam"].id not in annotator_ids


async def test_creator_holds_org_admin_permissions_without_a_membership(async_test_db):
    from app.core.authorization import AuthorizationService, Permission

    db = async_test_db
    creator = await _user(db)
    org_admin = await _user(db)
    org = await _org(db, (org_admin, OrganizationRole.ORG_ADMIN))
    project = await _project(db, creator, kind="exam")
    await _attach(db, project, org, org_admin)
    svc = AuthorizationService()
    principal = _principal(creator)
    for ctx in ("private", org.id, "elsewhere", None):
        for perm in (Permission.TASK_VIEW, Permission.PROJECT_EDIT, Permission.PROJECT_DELETE):
            assert await svc.check_project_access_async(
                principal, project, perm, db, org_context=ctx
            ) is True, (ctx, perm)
            assert await db.run_sync(
                lambda s, c=ctx, p=perm: svc.check_project_access(
                    principal, project, p, s, org_context=c
                )
            ) is True, (ctx, perm)
