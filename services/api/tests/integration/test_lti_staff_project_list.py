"""Staff find the LMS-linked private exams they may open (D13).

``check_project_accessible`` opens another user's private exam to the staff
of an org the exam is LMS-linked to (``org_groups.lti_staff_role``). The
project lists must agree: ``get_accessible_project_ids`` (and its async twin)
list such an exam in the private context for exactly those staff, and an org
context keeps a private project only for its creator and those staff. The
list endpoint then shows it with the full tier.

Annotators and students never see these exams in the generic lists, orgs
whose connections stay superadmin-run grant only their admins (fail closed),
and nothing changes for projects that are not LMS-linked private exams.
Real Postgres via the async fixtures; the sync twin runs on the same
transaction through ``run_sync``.
"""

import itertools
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from models import (
    LtiPlatformRegistration,
    LtiResourceLink,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from org_groups import lti_staff_role
from project_models import Project, ProjectOrganization, Task
from routers.projects.helpers import (
    _lti_staff_reach,
    _pick_lti_staff_projects,
    check_project_accessible,
    check_project_accessible_async,
    check_user_can_edit_project,
    check_user_can_edit_project_async,
    get_accessible_project_ids,
    get_accessible_project_ids_async,
    get_lti_staff_project_ids,
    get_lti_staff_project_ids_async,
)

pytestmark = [pytest.mark.integration]  # asyncio_mode = auto


# --------------------------------------------------------------------------- #
# Seed helpers
# --------------------------------------------------------------------------- #
def _hex() -> str:
    return uuid.uuid4().hex[:10]


async def _user(db) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"ltilist-{_hex()}",
        email=f"ltilist-{_hex()}@example.com",
        name="Person",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _org(db) -> Organization:
    slug = f"ltilist-{_hex()}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    db.add(org)
    await db.flush()
    return org


async def _member(db, user, org, role, *, active=True):
    db.add(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=active,
        )
    )
    await db.flush()


async def _group(db, org, *members) -> OrganizationGroup:
    """members: (user, is_group_admin) tuples."""
    group = OrganizationGroup(
        id=str(uuid.uuid4()), organization_id=org.id, name=f"G {_hex()}", is_active=True
    )
    db.add(group)
    await db.flush()
    for user, is_admin in members:
        db.add(
            OrganizationGroupMembership(
                id=str(uuid.uuid4()),
                group_id=group.id,
                user_id=user.id,
                is_group_admin=is_admin,
            )
        )
    await db.flush()
    return group


async def _project(
    db, owner, *, private=True, public=False, kind="exam", archived=False, deleted=False
) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Klausur {_hex()}",
        created_by=owner.id,
        is_private=private,
        is_public=public,
        public_role="ANNOTATOR" if public else None,
        is_archived=archived,
        kind=kind,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
        label_config='<View><Text name="sv" value="$sachverhalt"/></View>',
    )
    db.add(project)
    await db.flush()
    db.add(
        Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=1,
            data={"sachverhalt": "S", "musterloesung": "GEHEIM"},
            created_by=owner.id,
        )
    )
    await db.flush()
    return project


async def _activity(db, project, org) -> LtiResourceLink:
    """A connection of ``org`` with an activity linked to ``project``."""
    tag = _hex()
    registration = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name=f"LMS {tag}",
        issuer=f"https://lms-{tag}.example",
        client_id=f"client-{tag}",
        auth_login_url=f"https://lms-{tag}.example/auth",
        auth_token_url=f"https://lms-{tag}.example/token",
        jwks_uri=f"https://lms-{tag}.example/jwks",
    )
    db.add(registration)
    await db.flush()
    link = LtiResourceLink(
        id=str(uuid.uuid4()),
        registration_id=registration.id,
        deployment_id="1",
        resource_link_id=f"rl-{tag}",
        project_id=project.id,
    )
    db.add(link)
    await db.flush()
    return link


async def _attach(db, project, org, *, via="lti", group=None, linked=None):
    """Attach ``project`` to ``org``. A linking row (``via='lti'``) comes with
    a live activity of that org unless ``linked=False``."""
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org.id,
            group_id=group.id if group is not None else None,
            assigned_by=project.created_by,
            attached_via=via,
        )
    )
    await db.flush()
    if linked if linked is not None else via == "lti":
        await _activity(db, project, org)


def _principal(user):
    """The auth principal shape the helpers receive (no ORM relationships)."""
    return SimpleNamespace(id=user.id, is_superadmin=False)


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
        is_superadmin=False,
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


class _FakeExtended:
    COMPATIBLE_CORE_VERSIONS = ["2.20"]

    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _protect(monkeypatch, hook):
    import extensions

    monkeypatch.setattr(
        extensions, "_extended", _FakeExtended({"lti_protected_org_ids": hook})
    )


# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #
@dataclass
class World:
    uni: Organization
    foreign: Organization
    creator: User
    org_admin: User
    contributor: User
    contributor_in_group: User
    contributor_other_group: User
    annotator: User
    annotator_group_admin: User
    inactive_contributor: User
    foreign_admin: User
    foreign_contributor: User
    stranger: User
    exam_wide: Project  # private, live LMS row to uni (org-wide)
    exam_grouped: Project  # private, live LMS row to uni in group G
    exam_archived: Project  # private, archived, live LMS row to uni
    exam_stale: Project  # private, LMS row to uni whose link is gone
    exam_foreign: Project  # private, live LMS row to the foreign org
    exam_deleted: Project  # private, soft-deleted, live LMS row to uni
    exam_manual: Project  # private, MANUAL row to uni (legacy shape)
    exam_plain: Project  # private, no org row at all
    private_benchmark: Project  # private non-exam with a live LMS-shaped row
    exam_open: Project  # NOT private, live LMS row to uni
    org_project: Project  # plain org-visible project of uni (manual row)
    public_project: Project

    def lti_like(self):
        """Every private project of the world (the rows this change touches)."""
        return {
            p.id
            for p in (
                self.exam_wide,
                self.exam_grouped,
                self.exam_archived,
                self.exam_stale,
                self.exam_foreign,
                self.exam_deleted,
                self.exam_manual,
                self.exam_plain,
                self.private_benchmark,
            )
        }


async def _world(db) -> World:
    uni = await _org(db)
    foreign = await _org(db)
    creator = await _user(db)  # no membership anywhere
    org_admin = await _user(db)
    contributor = await _user(db)
    contributor_in_group = await _user(db)
    contributor_other_group = await _user(db)
    annotator = await _user(db)
    annotator_group_admin = await _user(db)
    inactive_contributor = await _user(db)
    foreign_admin = await _user(db)
    foreign_contributor = await _user(db)
    stranger = await _user(db)

    await _member(db, org_admin, uni, OrganizationRole.ORG_ADMIN)
    await _member(db, contributor, uni, OrganizationRole.CONTRIBUTOR)
    await _member(db, contributor_in_group, uni, OrganizationRole.CONTRIBUTOR)
    await _member(db, contributor_other_group, uni, OrganizationRole.CONTRIBUTOR)
    await _member(db, annotator, uni, OrganizationRole.ANNOTATOR)
    await _member(db, annotator_group_admin, uni, OrganizationRole.ANNOTATOR)
    await _member(db, inactive_contributor, uni, OrganizationRole.CONTRIBUTOR, active=False)
    await _member(db, foreign_admin, foreign, OrganizationRole.ORG_ADMIN)
    await _member(db, foreign_contributor, foreign, OrganizationRole.CONTRIBUTOR)
    # Staff of the foreign org may also be plain students of the university.
    await _member(db, foreign_contributor, uni, OrganizationRole.ANNOTATOR)

    group_g = await _group(
        db,
        uni,
        (contributor_in_group, False),
        (annotator, False),
        (annotator_group_admin, True),
    )
    await _group(db, uni, (contributor_other_group, False))

    exam_wide = await _project(db, creator)
    await _attach(db, exam_wide, uni)
    exam_grouped = await _project(db, creator)
    await _attach(db, exam_grouped, uni, group=group_g)
    exam_archived = await _project(db, creator, archived=True)
    await _attach(db, exam_archived, uni)
    exam_stale = await _project(db, creator)
    await _attach(db, exam_stale, uni, linked=False)
    exam_foreign = await _project(db, creator)
    await _attach(db, exam_foreign, foreign)
    exam_deleted = await _project(db, creator, deleted=True)
    await _attach(db, exam_deleted, uni)
    exam_manual = await _project(db, creator)
    await _attach(db, exam_manual, uni, via="manual")
    exam_plain = await _project(db, creator)
    private_benchmark = await _project(db, creator, kind="benchmark")
    await _attach(db, private_benchmark, uni)
    exam_open = await _project(db, creator, private=False)
    await _attach(db, exam_open, uni)
    org_project = await _project(db, creator, private=False, kind=None)
    await _attach(db, org_project, uni, via="manual")
    public_project = await _project(db, creator, private=False, public=True, kind=None)
    await db.commit()

    return World(
        uni=uni,
        foreign=foreign,
        creator=creator,
        org_admin=org_admin,
        contributor=contributor,
        contributor_in_group=contributor_in_group,
        contributor_other_group=contributor_other_group,
        annotator=annotator,
        annotator_group_admin=annotator_group_admin,
        inactive_contributor=inactive_contributor,
        foreign_admin=foreign_admin,
        foreign_contributor=foreign_contributor,
        stranger=stranger,
        exam_wide=exam_wide,
        exam_grouped=exam_grouped,
        exam_archived=exam_archived,
        exam_stale=exam_stale,
        exam_foreign=exam_foreign,
        exam_deleted=exam_deleted,
        exam_manual=exam_manual,
        exam_plain=exam_plain,
        private_benchmark=private_benchmark,
        exam_open=exam_open,
        org_project=org_project,
        public_project=public_project,
    )


async def _ids(db, user, ctx):
    """Both lanes of the list helper; asserts they agree and returns the set.
    ``None`` when the helper refuses the context (403) on both lanes."""
    principal = _principal(user)
    try:
        got_async = await get_accessible_project_ids_async(db, principal, ctx)
    except HTTPException as exc:
        assert exc.status_code == 403
        got_async = None
    try:
        got_sync = await db.run_sync(
            lambda s: get_accessible_project_ids(s, principal, ctx)
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        got_sync = None
    if got_async is None or got_sync is None:
        assert got_async is None and got_sync is None, (user.id, ctx)
        return None
    assert got_async == got_sync, f"sync/async drift for {user.id} in {ctx}"
    return set(got_async)


async def _listed_private(db, w, user, ctx):
    ids = await _ids(db, user, ctx)
    return None if ids is None else ids & w.lti_like()


def _names(w, ids):
    """Readable assertion messages: project ids back to World field names."""
    by_id = {getattr(w, f).id: f for f in World.__dataclass_fields__
             if isinstance(getattr(w, f), Project)}
    return sorted(by_id.get(i, i) for i in ids)


async def _assert_listed(db, w, user, contexts, expected):
    want = {p.id for p in expected}
    for ctx in contexts:
        got = await _listed_private(db, w, user, ctx)
        assert got is not None, (user.id, ctx, "unexpected 403")
        assert got == want, (ctx, _names(w, got), _names(w, want))


# --------------------------------------------------------------------------- #
# The list helper, both lanes
# --------------------------------------------------------------------------- #
async def test_org_admin_finds_every_linked_exam_of_the_org(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _assert_listed(
        db, w, w.org_admin, (None, "private", w.uni.id),
        {w.exam_wide, w.exam_grouped, w.exam_archived},
    )


async def test_contributors_follow_group_eligibility(async_test_db):
    db = async_test_db
    w = await _world(db)
    contexts = (None, "private", w.uni.id)
    await _assert_listed(
        db, w, w.contributor, contexts, {w.exam_wide, w.exam_archived}
    )
    await _assert_listed(
        db, w, w.contributor_in_group, contexts,
        {w.exam_wide, w.exam_grouped, w.exam_archived},
    )
    await _assert_listed(
        db, w, w.contributor_other_group, contexts, {w.exam_wide, w.exam_archived}
    )


async def test_group_admin_finds_only_the_group_exam(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _assert_listed(
        db, w, w.annotator_group_admin, (None, "private", w.uni.id), {w.exam_grouped}
    )


async def test_annotators_students_and_outsiders_find_nothing(async_test_db):
    db = async_test_db
    w = await _world(db)
    # Plain LMS student (also a member of the exam's group) and a foreign
    # contributor who is a student of the university.
    await _assert_listed(db, w, w.annotator, (None, "private", w.uni.id), set())
    for user in (w.inactive_contributor, w.stranger):
        await _assert_listed(db, w, user, (None, "private"), set())
        # Not an active member: the org context stays refused.
        assert await _ids(db, user, w.uni.id) is None


async def test_foreign_org_staff_find_only_their_own_linked_exam(async_test_db):
    db = async_test_db
    w = await _world(db)
    for user in (w.foreign_admin, w.foreign_contributor):
        await _assert_listed(
            db, w, user, (None, "private", w.foreign.id), {w.exam_foreign}
        )
    # The foreign contributor is only a student of the university.
    await _assert_listed(db, w, w.foreign_contributor, (w.uni.id,), set())


async def test_creator_keeps_all_own_private_projects(async_test_db):
    db = async_test_db
    w = await _world(db)
    own = w.lti_like() - {w.exam_deleted.id}
    for ctx in (None, "private"):
        assert await _listed_private(db, w, w.creator, ctx) == own


async def test_unlinked_stale_deleted_and_non_exam_private_projects_stay_hidden(
    async_test_db,
):
    db = async_test_db
    w = await _world(db)
    hidden = {
        w.exam_stale.id,
        w.exam_deleted.id,
        w.exam_manual.id,
        w.exam_plain.id,
        w.private_benchmark.id,
    }
    for user in (
        w.org_admin,
        w.contributor,
        w.contributor_in_group,
        w.annotator,
        w.annotator_group_admin,
    ):
        for ctx in (None, "private", w.uni.id):
            got = await _listed_private(db, w, user, ctx)
            assert not got & hidden, (user.id, ctx, _names(w, got & hidden))


async def test_lists_match_the_per_project_decider(async_test_db):
    """A listed private project always opens; an openable one attached to the
    org (or any, in the private context) is always listed."""
    db = async_test_db
    w = await _world(db)
    attached_to_uni = w.lti_like() - {w.exam_plain.id, w.exam_foreign.id}
    users = (
        w.org_admin,
        w.contributor,
        w.contributor_in_group,
        w.contributor_other_group,
        w.annotator,
        w.annotator_group_admin,
        w.foreign_admin,
        w.foreign_contributor,
        w.stranger,
    )
    for user in users:
        principal = _principal(user)
        for ctx, candidates in ((None, w.lti_like()), ("private", w.lti_like()),
                                (w.uni.id, attached_to_uni)):
            listed = await _listed_private(db, w, user, ctx)
            if listed is None:
                continue
            for pid in candidates:
                opens = await check_project_accessible_async(
                    db, principal, pid, org_context=ctx
                )
                opens_sync = await db.run_sync(
                    lambda s, u=principal, p=pid, c=ctx: check_project_accessible(
                        s, u, p, org_context=c
                    )
                )
                assert opens is opens_sync
                assert (pid in listed) is opens, (
                    user.id, ctx, _names(w, {pid}), opens
                )


async def test_staff_project_ids_both_lanes(async_test_db):
    db = async_test_db
    w = await _world(db)
    expected = {
        w.org_admin: {w.exam_wide, w.exam_grouped, w.exam_archived},
        w.contributor: {w.exam_wide, w.exam_archived},
        w.annotator_group_admin: {w.exam_grouped},
        w.annotator: set(),
        w.foreign_contributor: {w.exam_foreign},
        w.creator: set(),  # own exams come from the creator arm, not this one
        w.stranger: set(),
    }
    for user, projects in expected.items():
        principal = _principal(user)
        want = {p.id for p in projects}
        assert await get_lti_staff_project_ids_async(db, principal) == want
        assert await db.run_sync(
            lambda s, u=principal: get_lti_staff_project_ids(s, u)
        ) == want


# --------------------------------------------------------------------------- #
# Orgs whose connections stay superadmin-run
# --------------------------------------------------------------------------- #
async def test_protected_org_lists_only_for_its_admins(async_test_db, monkeypatch):
    db = async_test_db
    w = await _world(db)
    _protect(monkeypatch, lambda _db: {w.uni.id})
    contexts = (None, "private", w.uni.id)
    for user in (w.contributor, w.contributor_in_group):
        await _assert_listed(db, w, user, contexts, set())
    await _assert_listed(
        db, w, w.org_admin, contexts,
        {w.exam_wide, w.exam_grouped, w.exam_archived},
    )
    await _assert_listed(db, w, w.annotator_group_admin, contexts, {w.exam_grouped})
    # Other orgs are unaffected.
    await _assert_listed(
        db, w, w.foreign_contributor, (None, "private", w.foreign.id), {w.exam_foreign}
    )


async def test_protected_org_lookup_fails_closed(async_test_db, monkeypatch):
    db = async_test_db
    w = await _world(db)

    def _boom(_db):
        raise RuntimeError("hook down")

    _protect(monkeypatch, _boom)
    await _assert_listed(db, w, w.contributor, (None, "private", w.uni.id), set())
    await _assert_listed(
        db, w, w.foreign_contributor, (None, "private", w.foreign.id), set()
    )
    await _assert_listed(
        db, w, w.org_admin, (None, "private", w.uni.id),
        {w.exam_wide, w.exam_grouped, w.exam_archived},
    )


# --------------------------------------------------------------------------- #
# Nothing else changes
# --------------------------------------------------------------------------- #
async def test_non_private_and_public_projects_keep_their_rules(async_test_db):
    db = async_test_db
    w = await _world(db)
    for user in (w.contributor, w.org_admin):
        in_private = await _ids(db, user, "private")
        in_org = await _ids(db, user, w.uni.id)
        # Non-private org projects (LMS-linked or not) belong to the org list.
        assert w.exam_open.id not in in_private
        assert w.org_project.id not in in_private
        assert {w.exam_open.id, w.org_project.id} <= in_org
        assert w.public_project.id in in_private and w.public_project.id in in_org
    # Org students still get no exams in the generic org list, but keep the
    # org's other projects.
    annotator_ids = await _ids(db, w.annotator, w.uni.id)
    assert w.exam_open.id not in annotator_ids
    assert w.org_project.id in annotator_ids


async def test_users_without_a_staff_role_see_the_old_private_list(async_test_db):
    db = async_test_db
    w = await _world(db)
    own = await _project(db, w.annotator)
    await db.commit()
    for ctx in (None, "private"):
        ids = await _ids(db, w.annotator, ctx)
        assert own.id in ids
        assert ids & w.lti_like() == set()
        assert w.public_project.id in ids
        assert w.exam_open.id not in ids


# --------------------------------------------------------------------------- #
# The project list endpoint
# --------------------------------------------------------------------------- #
async def test_list_endpoint_shows_the_linked_exam_to_staff(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _world(db)

    async def listed(user, ctx):
        with _as_user(user):
            r = await async_test_client.get(
                "/api/projects/?page_size=500",
                headers={"X-Organization-Context": ctx},
            )
        assert r.status_code == 200, r.text
        return {p["id"]: p for p in r.json()["items"]}

    for ctx in ("private", w.uni.id):
        items = await listed(w.contributor, ctx)
        assert w.exam_wide.id in items
        assert items[w.exam_wide.id]["access_tier"] == "full"
        assert w.exam_grouped.id not in items
        assert w.exam_stale.id not in items
        assert w.exam_manual.id not in items

        items = await listed(w.org_admin, ctx)
        assert {w.exam_wide.id, w.exam_grouped.id} <= set(items)

        items = await listed(w.annotator_group_admin, ctx)
        assert w.exam_grouped.id in items
        assert items[w.exam_grouped.id]["access_tier"] == "full"
        assert w.exam_wide.id not in items

        items = await listed(w.annotator, ctx)
        assert not set(items) & w.lti_like()

    # Archived linked exams sit behind the archive filter like any project.
    with _as_user(w.contributor):
        r = await async_test_client.get(
            "/api/projects/?page_size=500&is_archived=true",
            headers={"X-Organization-Context": "private"},
        )
    assert r.status_code == 200
    assert w.exam_archived.id in {p["id"] for p in r.json()["items"]}

    # The detail page opens what the list shows.
    with _as_user(w.contributor):
        r = await async_test_client.get(
            f"/api/projects/{w.exam_wide.id}",
            headers={"X-Organization-Context": "private"},
        )
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# The edit check applies the private rule itself
# --------------------------------------------------------------------------- #
async def _can_edit(db, user, project, allowed_roles=("ORG_ADMIN", "CONTRIBUTOR")):
    """Both lanes of the edit check; asserts they agree."""
    principal = _principal(user)
    got_async = await check_user_can_edit_project_async(
        db, principal, project.id, allowed_roles
    )
    got_sync = await db.run_sync(
        lambda s: check_user_can_edit_project(s, principal, project.id, allowed_roles)
    )
    assert got_async is got_sync, (user.id, project.id)
    return got_async


async def test_edit_check_on_private_projects_equals_access(async_test_db):
    """Callers such as the student exam editor, the rubric editor and the
    grading feedback view call the edit check without the access check.
    On a private project it must never grant more than the access check:
    stale, manual and non-exam rows grant nothing to plain org staff."""
    db = async_test_db
    w = await _world(db)
    projects = {
        getattr(w, f)
        for f in World.__dataclass_fields__
        if isinstance(getattr(w, f), Project) and getattr(w, f).is_private
    }
    users = (
        w.org_admin,
        w.contributor,
        w.contributor_in_group,
        w.contributor_other_group,
        w.annotator,
        w.annotator_group_admin,
        w.inactive_contributor,
        w.foreign_admin,
        w.foreign_contributor,
        w.stranger,
    )
    for user in users:
        for project in projects:
            opens = await check_project_accessible_async(
                db, _principal(user), project.id, org_context=None
            )
            assert await _can_edit(db, user, project) is opens, (
                user.id, _names(w, {project.id}), opens
            )
    # The gap this closes: plain contributors of an attached org.
    for project in (w.exam_stale, w.exam_manual, w.private_benchmark):
        assert await _can_edit(db, w.contributor, project) is False
        assert await _can_edit(db, w.org_admin, project) is False
    # The creator keeps every own private project (soft delete ends it).
    for project in projects:
        assert await _can_edit(db, w.creator, project) is (project is not w.exam_deleted)
    # The allowed roles still apply to the LMS grant.
    assert await _can_edit(db, w.contributor, w.exam_wide) is True
    assert await _can_edit(db, w.contributor, w.exam_wide, ("ORG_ADMIN",)) is False
    assert await _can_edit(db, w.org_admin, w.exam_wide, ("ORG_ADMIN",)) is True
    assert (
        await _can_edit(db, w.annotator_group_admin, w.exam_grouped, ("ORG_ADMIN",))
        is True
    )


async def test_edit_check_on_protected_org_counts_only_admins(
    async_test_db, monkeypatch
):
    db = async_test_db
    w = await _world(db)
    _protect(monkeypatch, lambda _db: {w.uni.id})
    for user in (w.contributor, w.contributor_in_group):
        for project in (w.exam_wide, w.exam_grouped, w.exam_archived):
            assert await _can_edit(db, user, project) is False
    assert await _can_edit(db, w.org_admin, w.exam_wide) is True
    assert await _can_edit(db, w.annotator_group_admin, w.exam_grouped) is True

    def _boom(_db):
        raise RuntimeError("hook down")

    _protect(monkeypatch, _boom)
    assert await _can_edit(db, w.contributor, w.exam_wide) is False
    assert await _can_edit(db, w.foreign_contributor, w.exam_foreign) is False
    assert await _can_edit(db, w.org_admin, w.exam_wide) is True


async def test_only_the_creator_deletes_a_linked_private_exam(
    async_test_client, async_test_db
):
    """Staff open and grade the linked exam, but it stays the creator's:
    an org admin of the linked org cannot delete it, alone or in bulk."""
    db = async_test_db
    w = await _world(db)
    for user in (w.org_admin, w.contributor, w.annotator_group_admin):
        with _as_user(user):
            r = await async_test_client.delete(f"/api/projects/{w.exam_wide.id}")
            assert r.status_code == 403, (user.id, r.text)
            r = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": [w.exam_grouped.id]}
            )
            assert r.status_code == 200 and r.json()["deleted"] == 0, r.text
    # Legacy manual rows on a private project do not count either.
    with _as_user(w.org_admin):
        r = await async_test_client.delete(f"/api/projects/{w.exam_manual.id}")
        assert r.status_code == 403, r.text
    # A non-private linked exam keeps the org admin rule.
    with _as_user(w.org_admin):
        r = await async_test_client.delete(f"/api/projects/{w.exam_open.id}")
        assert r.status_code == 200, r.text
    with _as_user(w.creator):
        r = await async_test_client.delete(f"/api/projects/{w.exam_wide.id}")
        assert r.status_code == 200, r.text


async def test_edit_check_on_non_private_projects_is_unchanged(async_test_db):
    db = async_test_db
    w = await _world(db)
    assert await _can_edit(db, w.contributor, w.exam_open) is True
    assert await _can_edit(db, w.contributor_other_group, w.org_project) is True
    assert await _can_edit(db, w.annotator, w.exam_open) is False
    assert await _can_edit(db, w.inactive_contributor, w.org_project) is False
    assert await _can_edit(db, w.stranger, w.org_project) is False


# --------------------------------------------------------------------------- #
# The bulk pre-filter never changes the decider's answer (pure)
# --------------------------------------------------------------------------- #
class _M:
    def __init__(self, org_id, role, is_active=True):
        self.organization_id = org_id
        self.role = role
        self.is_active = is_active


_GROUP_OF = {"o1": "g1", "o2": "g2"}


def _configs():
    roles = (None, "ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR")
    group_states = (None, False, True)  # not a member / member / group admin
    for r1, active1, r2, g1, g2 in itertools.product(
        roles, (True, False), roles, group_states, group_states
    ):
        memberships = []
        if r1 is not None:
            memberships.append(_M("o1", r1, active1))
        if r2 is not None:
            memberships.append(_M("o2", r2))
        user_groups = {}
        if g1 is not None:
            user_groups["g1"] = g1
        if g2 is not None:
            user_groups["g2"] = g2
        yield memberships, user_groups


def _attachment_maps():
    for a1, a2 in itertools.product(("absent", "wide", "group"), repeat=2):
        lti = {}
        for org, state in (("o1", a1), ("o2", a2)):
            if state == "wide":
                lti[org] = None
            elif state == "group":
                lti[org] = _GROUP_OF[org]
        if lti:
            yield lti


def test_prefiltered_pick_equals_lti_staff_role():
    checked = 0
    for memberships, user_groups in _configs():
        active = [m for m in memberships if m.is_active]
        staff_orgs, admin_groups = _lti_staff_reach(active, user_groups)
        for lti in _attachment_maps():
            rows = [
                ("p", org, group)
                for org, group in lti.items()
                if org in staff_orgs or group in admin_groups
            ]
            for protected in (set(), {"o1"}, {"o1", "o2"}):
                expected = (
                    lti_staff_role(
                        "exam", memberships, lti, user_groups,
                        protected_org_ids=protected,
                    )
                    is not None
                )
                got = "p" in _pick_lti_staff_projects(
                    rows, active, user_groups, protected
                )
                assert got is expected, (
                    [(m.organization_id, m.role, m.is_active) for m in memberships],
                    user_groups, lti, protected,
                )
                checked += 1
    assert checked > 5000
