"""Staff access to PRIVATE exams through LMS-linking attachments (D13).

Linking an exam to an LMS activity attaches it to the connection's org with
``attached_via='lti'``. On a private exam that row opens the full tier to the
org's eligible staff (CONTRIBUTOR / ORG_ADMIN, group-eligible; a group admin
of the attachment's group counts as ORG_ADMIN), whatever org context the
client sends. ANNOTATORs never get it, and the participant tier stays as it
was (private exams remain entitlement/share/creator-only for students).

Every rule runs through all three deciders on both lanes:
``check_project_accessible`` (+ the pure deciders), ``get_project_access_tier``
and ``AuthorizationService``; plus share management, which stays with the
creator after linking. Real Postgres via the async fixtures; the sync twins
run on the same transaction through ``run_sync``.
"""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.authorization import AuthorizationService, Permission
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
from org_groups import get_lti_attachment_map, get_lti_attachment_map_async, lti_staff_role
from project_models import MarketplaceEntitlement, Project, ProjectOrganization, Task
from routers.projects.helpers import (
    _decide_project_accessible_context_mode,
    _decide_project_accessible_legacy_mode,
    check_project_accessible,
    check_project_accessible_async,
    check_user_can_manage_shares,
    check_user_can_manage_shares_async,
    get_participant_project_ids_async,
    get_project_access_tier,
    get_project_access_tier_async,
)

pytestmark = [pytest.mark.integration]  # asyncio_mode = auto

FULL = "full"
PARTICIPANT = "participant"


# --------------------------------------------------------------------------- #
# Seed helpers
# --------------------------------------------------------------------------- #
def _hex() -> str:
    return uuid.uuid4().hex[:10]


async def _user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"ltiacc-{_hex()}",
        email=f"ltiacc-{_hex()}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _org(db) -> Organization:
    slug = f"ltiacc-{_hex()}"
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


async def _exam(db, owner, *, private=True, kind="exam", archived=False) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Klausur {_hex()}",
        created_by=owner.id,
        is_private=private,
        is_public=False,
        is_archived=archived,
        kind=kind,
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


async def _attach(db, project, org, *, via="lti", group=None, by=None, linked=None):
    """Attach ``project`` to ``org``. A linking row (``via='lti'``) comes with
    a connection of the org whose activity points at the project, unless
    ``linked=False`` (a row that outlived its link)."""
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org.id,
            group_id=group.id if group is not None else None,
            assigned_by=by.id if by is not None else project.created_by,
            attached_via=via,
        )
    )
    await db.flush()
    if linked if linked is not None else via == "lti":
        await _activity(db, project, org)


def _principal(user):
    """The auth principal shape the deciders receive (no ORM relationships)."""
    return SimpleNamespace(id=user.id, is_superadmin=user.is_superadmin)


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
    exam_wide: Project  # private, LTI row to uni (org-wide)
    exam_grouped: Project  # private, LTI row to uni scoped to group G
    exam_manual: Project  # private, MANUAL row to uni (not a linking row)
    exam_open: Project  # NOT private, LTI row to uni (org-wide)
    exam_foreign: Project  # private, LTI row to the foreign org
    private_benchmark: Project  # private non-exam with an LTI-shaped row


async def _world(db) -> World:
    uni = await _org(db)
    foreign = await _org(db)
    creator = await _user(db)  # no membership anywhere: pure creator arm
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

    exam_wide = await _exam(db, creator)
    await _attach(db, exam_wide, uni, by=creator)
    exam_grouped = await _exam(db, creator)
    await _attach(db, exam_grouped, uni, group=group_g, by=creator)
    exam_manual = await _exam(db, creator)
    await _attach(db, exam_manual, uni, via="manual", by=creator)
    exam_open = await _exam(db, creator, private=False)
    await _attach(db, exam_open, uni, by=creator)
    exam_foreign = await _exam(db, creator)
    await _attach(db, exam_foreign, foreign, by=creator)
    private_benchmark = await _exam(db, creator, kind="benchmark")
    await _attach(db, private_benchmark, uni, by=creator)
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
        exam_manual=exam_manual,
        exam_open=exam_open,
        exam_foreign=exam_foreign,
        private_benchmark=private_benchmark,
    )


def _contexts(w: World):
    """Every org context a client may send: none (legacy), the apex host's
    ``private``, the connection org, and an unrelated org."""
    return (None, "private", w.uni.id, w.foreign.id)


async def _full_tier_everywhere(db, user, project, contexts):
    """Collect every decider's answer on both lanes (one flat list)."""
    principal = _principal(user)
    svc = AuthorizationService()
    answers = []
    for ctx in contexts:
        answers.append(
            ("accessible/async", ctx,
             await check_project_accessible_async(db, principal, project.id, org_context=ctx))
        )
        answers.append(
            ("accessible/sync", ctx,
             await db.run_sync(
                 lambda s, c=ctx: check_project_accessible(
                     s, principal, project.id, org_context=c
                 )
             ))
        )
        answers.append(
            ("tier/async", ctx,
             await get_project_access_tier_async(db, principal, project.id, org_context=ctx) == FULL)
        )
        answers.append(
            ("tier/sync", ctx,
             await db.run_sync(
                 lambda s, c=ctx: get_project_access_tier(
                     s, principal, project.id, org_context=c
                 )
             ) == FULL)
        )
        answers.append(
            ("authz/async", ctx,
             await svc.check_project_access_async(
                 principal, project, Permission.PROJECT_VIEW, db, org_context=ctx
             ))
        )
        answers.append(
            ("authz/sync", ctx,
             await db.run_sync(
                 lambda s, c=ctx: svc.check_project_access(
                     principal, project, Permission.PROJECT_VIEW, s, org_context=c
                 )
             ))
        )
    return answers


async def _assert_full(db, user, project, expected, contexts):
    for lane, ctx, got in await _full_tier_everywhere(db, user, project, contexts):
        assert got is expected, (lane, ctx, user.id, project.title, expected)


# --------------------------------------------------------------------------- #
# The staff grant, all deciders, both lanes, every context
# --------------------------------------------------------------------------- #
async def test_org_admin_and_contributor_get_the_full_tier_in_every_context(async_test_db):
    db = async_test_db
    w = await _world(db)
    for user in (w.org_admin, w.contributor):
        await _assert_full(db, user, w.exam_wide, True, _contexts(w))


async def test_group_scoped_attachment_follows_group_eligibility(async_test_db):
    db = async_test_db
    w = await _world(db)
    contexts = _contexts(w)
    # Group member contributor and the org admin (sees through groups): yes.
    await _assert_full(db, w.contributor_in_group, w.exam_grouped, True, contexts)
    await _assert_full(db, w.org_admin, w.exam_grouped, True, contexts)
    # A group admin counts as ORG_ADMIN, even with the ANNOTATOR org role.
    await _assert_full(db, w.annotator_group_admin, w.exam_grouped, True, contexts)
    # Contributors outside the group (none, or another group): no.
    await _assert_full(db, w.contributor, w.exam_grouped, False, contexts)
    await _assert_full(db, w.contributor_other_group, w.exam_grouped, False, contexts)


async def test_annotators_never_get_the_full_tier(async_test_db):
    db = async_test_db
    w = await _world(db)
    contexts = _contexts(w)
    # Plain LMS student, even inside the attachment's group.
    for exam in (w.exam_wide, w.exam_grouped):
        await _assert_full(db, w.annotator, exam, False, contexts)
    # A group admin is staff only for their own group's attachment.
    await _assert_full(db, w.annotator_group_admin, w.exam_wide, False, contexts)


async def test_foreign_inactive_and_unrelated_users_are_denied(async_test_db):
    db = async_test_db
    w = await _world(db)
    contexts = _contexts(w)
    for user in (
        w.foreign_admin,
        w.foreign_contributor,
        w.inactive_contributor,
        w.stranger,
    ):
        await _assert_full(db, user, w.exam_wide, False, contexts)
    # The foreign org's staff reach the exam linked to THEIR org, and the
    # university's staff do not.
    await _assert_full(db, w.foreign_admin, w.exam_foreign, True, contexts)
    await _assert_full(db, w.org_admin, w.exam_foreign, False, contexts)


async def test_creator_keeps_access_without_any_membership(async_test_db):
    db = async_test_db
    w = await _world(db)
    for exam in (w.exam_wide, w.exam_grouped, w.exam_manual, w.exam_foreign):
        await _assert_full(db, w.creator, exam, True, _contexts(w))


async def test_only_linking_rows_open_a_private_exam(async_test_db):
    db = async_test_db
    w = await _world(db)
    contexts = _contexts(w)
    # A manual org row on a private exam grants nobody but the creator.
    await _assert_full(db, w.org_admin, w.exam_manual, False, contexts)
    await _assert_full(db, w.contributor, w.exam_manual, False, contexts)
    # A private project that is not an exam stays creator-only too.
    await _assert_full(db, w.org_admin, w.private_benchmark, False, contexts)


async def test_permissions_follow_the_staff_role(async_test_db):
    db = async_test_db
    w = await _world(db)
    svc = AuthorizationService()

    async def allowed(user, permission, project=w.exam_wide, ctx="private"):
        principal = _principal(user)
        got_async = await svc.check_project_access_async(
            principal, project, permission, db, org_context=ctx
        )
        got_sync = await db.run_sync(
            lambda s: svc.check_project_access(
                principal, project, permission, s, org_context=ctx
            )
        )
        assert got_async is got_sync, (user.id, permission, ctx)
        return got_async

    assert await allowed(w.contributor, Permission.TASK_EDIT) is True
    assert await allowed(w.contributor, Permission.PROJECT_DELETE) is False
    assert await allowed(w.org_admin, Permission.PROJECT_DELETE) is True
    assert await allowed(w.annotator_group_admin, Permission.PROJECT_DELETE,
                         project=w.exam_grouped, ctx=w.foreign.id) is True
    assert await allowed(w.annotator, Permission.TASK_VIEW) is False
    assert await allowed(w.creator, Permission.PROJECT_DELETE) is True


async def test_soft_deleted_linked_exam_is_gone_for_staff(async_test_db):
    db = async_test_db
    w = await _world(db)
    w.exam_wide.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await _assert_full(db, w.org_admin, w.exam_wide, False, _contexts(w))


async def test_archived_linked_exam_stays_open_to_staff_only(async_test_db):
    db = async_test_db
    w = await _world(db)
    w.exam_wide.is_archived = True
    await db.commit()
    await _assert_full(db, w.contributor, w.exam_wide, True, _contexts(w))
    await _assert_full(db, w.annotator, w.exam_wide, False, _contexts(w))


# --------------------------------------------------------------------------- #
# Non-private exams and the participant tier stay as they were
# --------------------------------------------------------------------------- #
async def test_non_private_linked_exam_keeps_the_generic_rules(async_test_db):
    db = async_test_db
    w = await _world(db)
    # Staff: full in legacy mode and in the org's context (today's rules),
    # and under the private context the LMS landing pages send (the linked
    # org's staff, D13/D14). A foreign org context still gives nothing.
    for ctx in (None, w.uni.id, "private"):
        await _assert_full(db, w.contributor, w.exam_open, True, (ctx,))
    await _assert_full(db, w.contributor, w.exam_open, False, (w.foreign.id,))
    # Org students keep the participant tier on the org-visible exam (D13).
    for ctx in _contexts(w):
        assert await get_project_access_tier_async(
            db, _principal(w.annotator), w.exam_open.id, org_context=ctx
        ) == PARTICIPANT
    tagged = await get_participant_project_ids_async(db, w.annotator.id)
    assert tagged.get(w.exam_open.id) == "org_exam"


async def test_participant_tier_unchanged_for_org_annotators_on_private_exams(
    async_test_db,
):
    db = async_test_db
    w = await _world(db)
    principal = _principal(w.annotator)
    for exam in (w.exam_wide, w.exam_grouped):
        for ctx in _contexts(w):
            assert await get_project_access_tier_async(
                db, principal, exam.id, org_context=ctx
            ) is None
            assert await db.run_sync(
                lambda s, e=exam, c=ctx: get_project_access_tier(
                    s, principal, e.id, org_context=c
                )
            ) is None
    tagged = await get_participant_project_ids_async(db, w.annotator.id)
    assert w.exam_wide.id not in tagged
    assert w.exam_grouped.id not in tagged

    # The LMS path itself is unchanged: an LMS entitlement is the narrow tier.
    db.add(
        MarketplaceEntitlement(
            id=str(uuid.uuid4()),
            user_id=w.annotator.id,
            project_id=w.exam_wide.id,
            source="lti",
        )
    )
    await db.commit()
    for ctx in _contexts(w):
        assert await get_project_access_tier_async(
            db, principal, w.exam_wide.id, org_context=ctx
        ) == PARTICIPANT
        assert await db.run_sync(
            lambda s, c=ctx: get_project_access_tier(
                s, principal, w.exam_wide.id, org_context=c
            )
        ) == PARTICIPANT
    tagged = await get_participant_project_ids_async(db, w.annotator.id)
    assert tagged.get(w.exam_wide.id) == "entitlement"


# --------------------------------------------------------------------------- #
# Share management stays with the creator after linking
# --------------------------------------------------------------------------- #
async def _can_manage(db, user, project):
    principal = _principal(user)
    got_async = await check_user_can_manage_shares_async(db, principal, project)
    got_sync = await db.run_sync(
        lambda s: check_user_can_manage_shares(s, principal, project)
    )
    assert got_async is got_sync, (user.id, project.title)
    return got_async


async def test_share_management_after_linking(async_test_db):
    db = async_test_db
    w = await _world(db)
    # Only linking rows: the creator keeps it; the connection org's admins
    # and the attachment group's admins have it too; staff below admin not.
    assert await _can_manage(db, w.creator, w.exam_wide) is True
    assert await _can_manage(db, w.org_admin, w.exam_wide) is True
    assert await _can_manage(db, w.contributor, w.exam_wide) is False
    assert await _can_manage(db, w.annotator, w.exam_wide) is False
    assert await _can_manage(db, w.foreign_admin, w.exam_wide) is False
    assert await _can_manage(db, w.creator, w.exam_grouped) is True
    assert await _can_manage(db, w.annotator_group_admin, w.exam_grouped) is True
    assert await _can_manage(db, w.creator, w.exam_open) is True
    # A manual org row still takes it over (unchanged rule).
    assert await _can_manage(db, w.creator, w.exam_manual) is False
    assert await _can_manage(db, w.org_admin, w.exam_manual) is True


async def test_manual_row_next_to_a_linking_row_still_takes_share_management(
    async_test_db,
):
    db = async_test_db
    w = await _world(db)
    await _attach(db, w.exam_wide, w.foreign, via="manual", by=w.creator)
    await db.commit()
    assert await _can_manage(db, w.creator, w.exam_wide) is False
    assert await _can_manage(db, w.foreign_admin, w.exam_wide) is True
    assert await _can_manage(db, w.org_admin, w.exam_wide) is True


# --------------------------------------------------------------------------- #
# Loaders and pure deciders
# --------------------------------------------------------------------------- #
async def test_lti_attachment_map_lists_only_linking_rows(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _attach(db, w.exam_grouped, w.foreign, via="manual", by=w.creator)
    await db.commit()
    got_async = await get_lti_attachment_map_async(db, w.exam_grouped.id)
    got_sync = await db.run_sync(lambda s: get_lti_attachment_map(s, w.exam_grouped.id))
    assert got_async == got_sync
    assert list(got_async) == [w.uni.id]
    assert got_async[w.uni.id] is not None  # the group scope
    assert await get_lti_attachment_map_async(db, w.exam_manual.id) == {}


async def test_linking_row_without_a_live_link_grants_nothing(async_test_db):
    db = async_test_db
    w = await _world(db)
    stale = await _exam(db, w.creator)
    await _attach(db, stale, w.uni, by=w.creator, linked=False)
    # Another org's activity on the exam does not revive the uni's row.
    await _activity(db, stale, w.foreign)
    await db.commit()
    assert await get_lti_attachment_map_async(db, stale.id) == {}
    assert await db.run_sync(lambda s: get_lti_attachment_map(s, stale.id)) == {}
    for user in (w.org_admin, w.contributor):
        await _assert_full(db, user, stale, False, _contexts(w))
    await _assert_full(db, w.creator, stale, True, _contexts(w))

    # An activity of the uni's connection pointing at the exam again: open.
    await _activity(db, stale, w.uni)
    await db.commit()
    await _assert_full(db, w.contributor, stale, True, _contexts(w))


# --------------------------------------------------------------------------- #
# Orgs whose connections stay superadmin-run (the Vertretbar org)
# --------------------------------------------------------------------------- #
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


async def test_protected_org_grants_only_its_admins(async_test_db, monkeypatch):
    db = async_test_db
    w = await _world(db)
    _protect(monkeypatch, lambda _db: {w.uni.id})
    contexts = _contexts(w)
    # Every LMS teacher is a contributor of such an org: nothing for them,
    # in or out of the attachment's group.
    for user in (w.contributor, w.contributor_in_group):
        await _assert_full(db, user, w.exam_wide, False, contexts)
    await _assert_full(db, w.contributor_in_group, w.exam_grouped, False, contexts)
    # Its org admins and the attachment group's admins keep the grant.
    await _assert_full(db, w.org_admin, w.exam_wide, True, contexts)
    await _assert_full(db, w.annotator_group_admin, w.exam_grouped, True, contexts)
    # Other orgs are unaffected, and the creator always keeps access.
    await _assert_full(db, w.foreign_contributor, w.exam_foreign, True, contexts)
    await _assert_full(db, w.creator, w.exam_wide, True, contexts)

    svc = AuthorizationService()
    principal = _principal(w.contributor)
    assert await svc.check_project_access_async(
        principal, w.exam_wide, Permission.TASK_VIEW, db, org_context=w.uni.id
    ) is False


async def test_protected_org_lookup_fails_closed(async_test_db, monkeypatch):
    db = async_test_db
    w = await _world(db)

    def _boom(_db):
        raise RuntimeError("hook down")

    _protect(monkeypatch, _boom)
    contexts = _contexts(w)
    # Every linked org counts as protected: contributors lose the grant,
    # org admins keep it.
    await _assert_full(db, w.contributor, w.exam_wide, False, contexts)
    await _assert_full(db, w.foreign_contributor, w.exam_foreign, False, contexts)
    await _assert_full(db, w.org_admin, w.exam_wide, True, contexts)


def test_lti_staff_role_on_protected_orgs():
    lti = {"vtr": None, "chair": "g1"}
    protected = {"vtr", "chair"}
    contributor = [_M("vtr", "CONTRIBUTOR")]
    assert lti_staff_role("exam", contributor, lti) == "CONTRIBUTOR"
    assert lti_staff_role("exam", contributor, lti, protected_org_ids=protected) is None
    assert lti_staff_role(
        "exam", [_M("vtr", "ORG_ADMIN")], lti, protected_org_ids=protected
    ) == "ORG_ADMIN"
    # A group admin of the attachment's group counts as ORG_ADMIN there.
    assert lti_staff_role(
        "exam", [_M("chair", "CONTRIBUTOR")], lti, {"g1": True},
        protected_org_ids=protected,
    ) == "ORG_ADMIN"
    assert lti_staff_role(
        "exam", [_M("chair", "CONTRIBUTOR")], lti, {"g1": False},
        protected_org_ids=protected,
    ) is None
    # The protected set only affects its own orgs.
    assert lti_staff_role(
        "exam", [_M("uni", "CONTRIBUTOR")], {"uni": None},
        protected_org_ids=protected,
    ) == "CONTRIBUTOR"


class _M:
    def __init__(self, org_id, role, is_active=True):
        self.organization_id = org_id
        self.role = role
        self.is_active = is_active


class _Memberships:
    def __init__(self, *memberships):
        self.organization_memberships = list(memberships)


def test_lti_staff_role_matrix():
    lti = {"uni": None, "chair": "g1"}
    assert lti_staff_role("exam", [_M("uni", OrganizationRole.CONTRIBUTOR)], lti) == "CONTRIBUTOR"
    assert lti_staff_role("exam", [_M("uni", "ORG_ADMIN")], lti) == "ORG_ADMIN"
    assert lti_staff_role("exam", [_M("uni", OrganizationRole.ANNOTATOR)], lti) is None
    assert lti_staff_role("exam", [_M("uni", "CONTRIBUTOR", is_active=False)], lti) is None
    assert lti_staff_role("exam", [_M("other", "ORG_ADMIN")], lti) is None
    # Group axis: member contributor yes, outsider no, org admin yes,
    # group-admin annotator counts as ORG_ADMIN.
    assert lti_staff_role("exam", [_M("chair", "CONTRIBUTOR")], lti, {"g1": False}) == "CONTRIBUTOR"
    assert lti_staff_role("exam", [_M("chair", "CONTRIBUTOR")], lti, {"g2": True}) is None
    assert lti_staff_role("exam", [_M("chair", "ORG_ADMIN")], lti, {}) == "ORG_ADMIN"
    assert lti_staff_role("exam", [_M("chair", "ANNOTATOR")], lti, {"g1": True}) == "ORG_ADMIN"
    assert lti_staff_role("exam", [_M("chair", "ANNOTATOR")], lti, {"g1": False}) is None
    # The best role over all memberships wins.
    both = [_M("uni", "CONTRIBUTOR"), _M("chair", "CONTRIBUTOR")]
    assert lti_staff_role("exam", both, lti, {"g1": True}) == "ORG_ADMIN"
    # Only exams, only with linking rows; the org context never matters.
    assert lti_staff_role("benchmark", [_M("uni", "ORG_ADMIN")], lti) is None
    assert lti_staff_role("exam", [_M("uni", "ORG_ADMIN")], {}) is None
    assert lti_staff_role("exam", [_M("uni", "ORG_ADMIN")], None) is None
    assert lti_staff_role("exam", None, lti) is None
    for ctx in (None, "private", "uni", "elsewhere"):
        assert lti_staff_role(
            "exam", [_M("uni", "CONTRIBUTOR")], lti, org_context=ctx
        ) == "CONTRIBUTOR"


def test_pure_deciders_without_the_map_keep_private_creator_only():
    project = SimpleNamespace(kind="exam", is_private=True, created_by="creator")
    staff = _Memberships(_M("uni", "CONTRIBUTOR"))
    user = SimpleNamespace(id="colleague")
    lti = {"uni": None}
    for ctx in ("private", "uni", "elsewhere"):
        assert _decide_project_accessible_context_mode(
            user, project, ctx, ["uni"], staff
        ) is False
        assert _decide_project_accessible_context_mode(
            user, project, ctx, ["uni"], staff, lti_attachments=lti
        ) is True
    assert _decide_project_accessible_legacy_mode(user, project, ["uni"], staff) is False
    assert _decide_project_accessible_legacy_mode(
        user, project, ["uni"], staff, lti_attachments=lti
    ) is True
    # No memberships at all: nothing to grant.
    assert _decide_project_accessible_legacy_mode(
        user, project, ["uni"], None, lti_attachments=lti
    ) is False
    assert _decide_project_accessible_context_mode(
        SimpleNamespace(id="creator"), project, "elsewhere", [], None
    ) is True


# --------------------------------------------------------------------------- #
# HTTP: the apex host (private context) and share links
# --------------------------------------------------------------------------- #
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


PRIVATE_CONTEXT = {"X-Organization-Context": "private"}


async def test_staff_open_the_linked_exam_from_the_apex_host(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _world(db)
    url = f"/api/projects/{w.exam_wide.id}"
    for user in (w.org_admin, w.contributor, w.creator):
        with _as_user(user):
            response = await async_test_client.get(url, headers=PRIVATE_CONTEXT)
        assert response.status_code == 200, (user.id, response.text)
    for user in (w.annotator, w.foreign_admin, w.stranger):
        with _as_user(user):
            response = await async_test_client.get(url, headers=PRIVATE_CONTEXT)
        assert response.status_code == 403, (user.id, response.text)


async def test_creator_keeps_share_links_on_a_linked_exam(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _world(db)
    url = f"/api/projects/{w.exam_wide.id}"

    with _as_user(w.creator):
        detail = await async_test_client.get(url, headers=PRIVATE_CONTEXT)
        created = await async_test_client.post(
            f"{url}/shares", json={"password": "abcdefgh"}, headers=PRIVATE_CONTEXT
        )
    assert detail.json()["can_manage_shares"] is True
    assert created.status_code == 201, created.text

    # Staff below org admin see the exam but cannot let outsiders in.
    with _as_user(w.contributor):
        detail = await async_test_client.get(url, headers=PRIVATE_CONTEXT)
        refused = await async_test_client.post(
            f"{url}/shares", json={"password": "abcdefgh"}, headers=PRIVATE_CONTEXT
        )
    assert detail.status_code == 200
    assert detail.json()["can_manage_shares"] is False
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "share_admin_only"

    with _as_user(w.org_admin):
        created = await async_test_client.post(
            f"{url}/shares", json={"password": "abcdefgh"}, headers=PRIVATE_CONTEXT
        )
    assert created.status_code == 201, created.text


# --------------------------------------------------------------------------- #
# The protected-org rule on non-private exams
# --------------------------------------------------------------------------- #
from routers.projects.helpers import (  # noqa: E402
    check_project_write_access,
    check_project_write_access_async,
    check_user_can_edit_project,
    check_user_can_edit_project_async,
    get_accessible_project_ids_async,
    get_effective_project_role,
    get_effective_project_role_async,
)
from routers.projects.tasks.blinding import (  # noqa: E402
    annotator_bound_fields_or_none_async,
)


async def _roles(db, user, project):
    """Effective role, edit check and write check on both lanes."""
    principal = _principal(user)
    role = await get_effective_project_role_async(db, principal, project)
    assert role == await db.run_sync(
        lambda s: get_effective_project_role(s, principal, project)
    ), (user.id, project.title)
    edit = await check_user_can_edit_project_async(db, principal, project.id)
    assert edit is await db.run_sync(
        lambda s: check_user_can_edit_project(s, principal, project.id)
    )
    write = await check_project_write_access_async(db, principal, project.id)
    assert write is await db.run_sync(
        lambda s: check_project_write_access(s, principal, project.id)
    )
    return role, edit, write


async def _listed(db, user, org):
    ids = await get_accessible_project_ids_async(db, _principal(user), org_context=org.id)
    return set(ids or ())


async def _open_exams(db, w):
    """Non-private exams of the creator linked to uni: org-wide, in group G,
    and one the creator shared with uni by hand."""
    from sqlalchemy import select

    group_g = (
        await db.execute(
            select(OrganizationGroupMembership.group_id).where(
                OrganizationGroupMembership.user_id == w.annotator_group_admin.id
            )
        )
    ).scalar_one()
    open_grouped = await _exam(db, w.creator, private=False)
    await _attach(db, open_grouped, w.uni, by=w.creator, group=SimpleNamespace(id=group_g))
    open_manual = await _exam(db, w.creator, private=False)
    await _attach(db, open_manual, w.uni, via="manual", by=w.creator)
    await db.commit()
    return open_grouped, open_manual


async def test_protected_org_counts_only_admins_on_non_private_exams(
    async_test_db, monkeypatch
):
    db = async_test_db
    w = await _world(db)
    open_grouped, open_manual = await _open_exams(db, w)
    _protect(monkeypatch, lambda _db: {w.uni.id})
    contexts = (None, w.uni.id)

    for user in (w.contributor, w.contributor_in_group):
        await _assert_full(db, user, w.exam_open, False, contexts)
        # Org members keep the participant tier on an org-visible exam
        # (D13): a blinded ANNOTATOR, never staff.
        role, edit, write = await _roles(db, user, w.exam_open)
        assert (role, edit, write) == ("ANNOTATOR", False, False), user.id
        assert await annotator_bound_fields_or_none_async(
            db, _principal(user), w.exam_open
        ) is not None
        assert w.exam_open.id not in await _listed(db, user, w.uni)
        assert await AuthorizationService().check_project_access_async(
            _principal(user), w.exam_open, Permission.TASK_VIEW, db, org_context=w.uni.id
        ) is False
    await _assert_full(db, w.contributor_in_group, open_grouped, False, contexts)
    assert (await _roles(db, w.contributor_in_group, open_grouped))[1] is False
    assert open_grouped.id not in await _listed(db, w.contributor_in_group, w.uni)

    # Its org admins and the attachment group's admins keep everything.
    await _assert_full(db, w.org_admin, w.exam_open, True, contexts)
    assert await _roles(db, w.org_admin, w.exam_open) == ("ORG_ADMIN", True, True)
    assert w.exam_open.id in await _listed(db, w.org_admin, w.uni)
    await _assert_full(db, w.annotator_group_admin, open_grouped, True, contexts)
    assert await _roles(db, w.annotator_group_admin, open_grouped) == (
        "ORG_ADMIN",
        True,
        True,
    )
    assert open_grouped.id in await _listed(db, w.annotator_group_admin, w.uni)

    # A share the author made by hand keeps the generic rules.
    await _assert_full(db, w.contributor, open_manual, True, contexts)
    assert await _roles(db, w.contributor, open_manual) == ("CONTRIBUTOR", True, True)
    assert open_manual.id in await _listed(db, w.contributor, w.uni)

    # Org students keep the participant tier on the org-visible exam (D13).
    assert await get_project_access_tier_async(
        db, _principal(w.annotator), w.exam_open.id, org_context=w.uni.id
    ) == PARTICIPANT
    # The creator keeps the exam.
    assert await _roles(db, w.creator, w.exam_open) == ("ORG_ADMIN", True, True)


async def test_protected_rule_on_non_private_exams_fails_closed(
    async_test_db, monkeypatch
):
    db = async_test_db
    w = await _world(db)

    def _boom(_db):
        raise RuntimeError("hook down")

    _protect(monkeypatch, _boom)
    await _assert_full(db, w.contributor, w.exam_open, False, (None, w.uni.id))
    assert (await _roles(db, w.contributor, w.exam_open))[1] is False
    await _assert_full(db, w.org_admin, w.exam_open, True, (None, w.uni.id))


async def test_unprotected_org_keeps_the_generic_rules_on_open_exams(async_test_db):
    db = async_test_db
    w = await _world(db)
    assert await _roles(db, w.contributor, w.exam_open) == ("CONTRIBUTOR", True, True)
    assert w.exam_open.id in await _listed(db, w.contributor, w.uni)


async def test_visibility_patch_keeps_the_protected_rule(
    async_test_client, async_test_db, monkeypatch
):
    """A linked private exam switched to org-visible keeps its LMS row; the
    protected org's contributors still get nothing from it."""
    db = async_test_db
    w = await _world(db)
    url = f"/api/projects/{w.exam_wide.id}/visibility"
    with _as_user(w.creator):
        response = await async_test_client.patch(
            url,
            json={"is_private": False, "organization_ids": [w.foreign.id]},
            headers=PRIVATE_CONTEXT,
        )
    assert response.status_code == 200, response.text
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(ProjectOrganization.organization_id, ProjectOrganization.attached_via)
            .where(ProjectOrganization.project_id == w.exam_wide.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert (w.uni.id, "lti") in {(str(o), v) for o, v in rows}
    exam = (
        await db.execute(
            select(Project)
            .where(Project.id == w.exam_wide.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert exam.is_private is False

    _protect(monkeypatch, lambda _db: {w.uni.id})
    await _assert_full(db, w.contributor, exam, False, (None, w.uni.id))
    assert (await _roles(db, w.contributor, exam))[1] is False
    await _assert_full(db, w.org_admin, exam, True, (None, w.uni.id))


# --------------------------------------------------------------------------- #
# The effective role follows the private rule
# --------------------------------------------------------------------------- #
async def test_effective_role_on_private_exams_needs_a_live_unprotected_link(
    async_test_db, monkeypatch
):
    """Stale, manual and protected rows give no role on someone else's
    private exam, so imports, blinding and the other role-only gates refuse
    what the access check refuses."""
    db = async_test_db
    w = await _world(db)
    stale = await _exam(db, w.creator)
    await _attach(db, stale, w.uni, by=w.creator, linked=False)
    await db.commit()

    for project in (stale, w.exam_manual):
        assert await _roles(db, w.contributor, project) == (None, False, False)
        assert await _roles(db, w.org_admin, project) == (None, False, False)
        fields = await annotator_bound_fields_or_none_async(
            db, _principal(w.contributor), project
        )
        assert fields is not None  # blinded

    # A live link: staff roles as the access check grants them.
    assert await _roles(db, w.contributor, w.exam_wide) == ("CONTRIBUTOR", True, True)
    assert await _roles(db, w.org_admin, w.exam_wide) == ("ORG_ADMIN", True, True)
    assert await _roles(db, w.annotator, w.exam_wide) == (None, False, False)

    _protect(monkeypatch, lambda _db: {w.uni.id})
    assert await _roles(db, w.contributor, w.exam_wide) == (None, False, False)
    assert await _roles(db, w.org_admin, w.exam_wide) == ("ORG_ADMIN", True, True)
    assert await _roles(db, w.annotator_group_admin, w.exam_grouped) == (
        "ORG_ADMIN",
        True,
        True,
    )
    assert await annotator_bound_fields_or_none_async(
        db, _principal(w.contributor), w.exam_wide
    ) is not None

    def _boom(_db):
        raise RuntimeError("hook down")

    _protect(monkeypatch, _boom)
    assert await _roles(db, w.contributor, w.exam_wide) == (None, False, False)


async def test_protected_contributor_with_an_lms_grant_is_a_blinded_participant(
    async_test_client, async_test_db, monkeypatch
):
    """A pilot teacher who also launched as a learner holds an LMS
    entitlement: that is the participant tier (ANNOTATOR), never the
    unblinded staff view, and no import rights."""
    from sqlalchemy import select

    db = async_test_db
    w = await _world(db)
    stale = await _exam(db, w.creator)
    await _attach(db, stale, w.uni, by=w.creator, linked=False)
    for project in (w.exam_wide, stale):
        db.add(
            MarketplaceEntitlement(
                id=str(uuid.uuid4()),
                user_id=w.contributor.id,
                project_id=project.id,
                source="lti",
            )
        )
    await db.commit()
    _protect(monkeypatch, lambda _db: {w.uni.id})

    for project in (w.exam_wide, stale):
        assert await _roles(db, w.contributor, project) == ("ANNOTATOR", False, False)
        task_id = (
            await db.execute(select(Task.id).where(Task.project_id == project.id))
        ).scalar_one()
        with _as_user(w.contributor):
            task = await async_test_client.get(
                f"/api/projects/tasks/{task_id}", headers=PRIVATE_CONTEXT
            )
            upload = await async_test_client.post(
                f"/api/projects/{project.id}/imports/upload-url",
                headers=PRIVATE_CONTEXT,
            )
            job = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": f"imports/x/{project.id}/a.json"},
                headers=PRIVATE_CONTEXT,
            )
        assert task.status_code == 200, task.text
        assert "musterloesung" not in task.json()["data"]
        assert upload.status_code == 403, upload.text
        assert job.status_code == 403, job.text

    # The org admin keeps the full view on the live link.
    task_id = (
        await db.execute(select(Task.id).where(Task.project_id == w.exam_wide.id))
    ).scalar_one()
    with _as_user(w.org_admin):
        task = await async_test_client.get(
            f"/api/projects/tasks/{task_id}", headers=PRIVATE_CONTEXT
        )
    assert task.status_code == 200, task.text
    assert task.json()["data"]["musterloesung"] == "GEHEIM"


# --------------------------------------------------------------------------- #
# Someone else's NON-private exam under the private context (teacher view)
# --------------------------------------------------------------------------- #
async def _open_exam_linked_through(db, w, *, via, group=None):
    """An org-visible exam of the creator, attached to the university with a
    row of kind ``via`` and linked through a university connection."""
    exam = await _exam(db, w.creator, private=False)
    await _attach(db, exam, w.uni, via=via, group=group, by=w.creator, linked=True)
    await db.commit()
    return exam


@pytest.mark.parametrize("via", ["manual", "lti"])
async def test_linked_org_staff_reach_an_open_exam_from_the_private_context(
    async_test_db, via
):
    """Linking keeps a row the author made by hand, so a manual row of the
    linking org counts as well as a linking row."""
    db = async_test_db
    w = await _world(db)
    exam = await _open_exam_linked_through(db, w, via=via)
    private = ("private",)
    for user in (w.org_admin, w.contributor):
        await _assert_full(db, user, exam, True, private)
    # Students keep the participant tier only; foreign staff (also plain
    # students of the university) and inactive members get nothing more.
    for user in (w.annotator, w.foreign_contributor, w.inactive_contributor, w.stranger):
        await _assert_full(db, user, exam, False, private)
    assert await get_project_access_tier_async(
        db, _principal(w.annotator), exam.id, org_context="private"
    ) == PARTICIPANT


async def test_private_context_follows_the_attachment_group(async_test_db):
    db = async_test_db
    w = await _world(db)
    group = await _group(db, w.uni, (w.contributor_in_group, False))
    exam = await _open_exam_linked_through(db, w, via="manual", group=group)
    private = ("private",)
    await _assert_full(db, w.contributor_in_group, exam, True, private)
    await _assert_full(db, w.org_admin, exam, True, private)
    await _assert_full(db, w.contributor, exam, False, private)


async def test_unlinked_open_exam_stays_creator_only_in_the_private_context(
    async_test_db,
):
    db = async_test_db
    w = await _world(db)
    # Shared with the university by hand, but the only LMS link belongs to
    # the foreign org: the university's staff are not linking staff.
    exam = await _exam(db, w.creator, private=False)
    await _attach(db, exam, w.uni, via="manual", by=w.creator)
    await _activity(db, exam, w.foreign)
    await db.commit()
    private = ("private",)
    for user in (w.org_admin, w.contributor):
        await _assert_full(db, user, exam, False, private)
    await _assert_full(db, w.creator, exam, True, private)
    # The foreign org has no attachment row: nothing to grant there either.
    await _assert_full(db, w.foreign_admin, exam, False, private)
    # Not an exam: the private context stays creator-only.
    benchmark = await _exam(db, w.creator, private=False, kind="benchmark")
    await _attach(db, benchmark, w.uni, via="manual", by=w.creator, linked=True)
    await db.commit()
    await _assert_full(db, w.org_admin, benchmark, False, private)


async def test_private_context_permissions_follow_the_staff_role(async_test_db):
    db = async_test_db
    w = await _world(db)
    exam = await _open_exam_linked_through(db, w, via="manual")
    svc = AuthorizationService()

    async def allowed(user, permission):
        principal = _principal(user)
        got_async = await svc.check_project_access_async(
            principal, exam, permission, db, org_context="private"
        )
        got_sync = await db.run_sync(
            lambda s: svc.check_project_access(
                principal, exam, permission, s, org_context="private"
            )
        )
        assert got_async is got_sync, (user.id, permission)
        return got_async

    assert await allowed(w.contributor, Permission.TASK_EDIT) is True
    assert await allowed(w.contributor, Permission.PROJECT_DELETE) is False
    assert await allowed(w.org_admin, Permission.PROJECT_DELETE) is True
    assert await allowed(w.annotator, Permission.TASK_VIEW) is False
    assert await allowed(w.foreign_contributor, Permission.TASK_VIEW) is False


async def test_teacher_view_calls_work_with_the_private_header(
    async_test_client, async_test_db
):
    """What the Korrektur page and the exam page load, sent the way the LMS
    landing page sends it (``X-Organization-Context: private``)."""
    from tests.integration.test_group_visibility import _as_user

    db = async_test_db
    w = await _world(db)
    exam = await _open_exam_linked_through(db, w, via="manual")
    headers = {"X-Organization-Context": "private"}
    client = async_test_client

    with _as_user(w.contributor):
        project = await client.get(f"/api/projects/{exam.id}", headers=headers)
        config = await client.get(
            f"/api/evaluations/projects/{exam.id}/evaluation-config", headers=headers
        )
    assert project.status_code == 200, project.text
    assert project.json()["access_tier"] == FULL
    assert config.status_code == 200, config.text

    with _as_user(w.annotator):
        project = await client.get(f"/api/projects/{exam.id}", headers=headers)
        config = await client.get(
            f"/api/evaluations/projects/{exam.id}/evaluation-config", headers=headers
        )
    assert project.status_code == 200, project.text
    assert project.json()["access_tier"] == PARTICIPANT
    assert config.status_code == 403, config.text
