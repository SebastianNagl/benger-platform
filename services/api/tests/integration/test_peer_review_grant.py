"""Peer review grant: who reviews a project's submissions.

``services.peer_review.review_role`` answers "staff", "peer" or None per user,
``peer_candidate_ids`` lists the peers of a whole project, and the two must
agree. The project switch ``peer_review_enabled`` is changed through
``PATCH /projects/{id}`` by an effective role of ORG_ADMIN only, and every
single-project response tells the caller their ``viewer_review_role``.
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
from project_models import (
    Annotation,
    MarketplaceEntitlement,
    Project,
    ProjectOrganization,
    ProjectShareLink,
    ProjectShareMember,
    Task,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)
NOW = datetime.now(timezone.utc)


def _user(*, superadmin=False, service=False, active=True) -> User:
    return User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_service_account=service,
        is_active=active,
        email_verified=True,
        created_at=NOW,
    )


def _project(owner, *, enabled=True, private=False, kind=None, archived=False,
             window_start=None, public_role=None) -> Project:
    return Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=private,
        is_public=public_role is not None,
        public_role=public_role,
        kind=kind,
        is_archived=archived,
        label_config=CONFIG,
        peer_review_enabled=enabled,
        window_start_at=window_start,
        window_end_at=(window_start + timedelta(hours=4)) if window_start else None,
    )


def _org(*members):
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    rows = [
        OrganizationMembership(
            id=str(uuid.uuid4()), user_id=user.id, organization_id=org.id,
            role=role, is_active=active,
        )
        for user, role, active in members
    ]
    return org, rows


def _attach(project, org, by, group=None) -> ProjectOrganization:
    return ProjectOrganization(
        id=str(uuid.uuid4()), project_id=project.id, organization_id=org.id,
        assigned_by=by.id, group_id=group.id if group is not None else None,
    )


def _share(project, owner, member, *, consent=True):
    link = ProjectShareLink(
        id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=project.id,
        created_by=owner.id, password_hash="x", is_listed=False,
    )
    membership = ProjectShareMember(
        id=str(uuid.uuid4()), share_link_id=link.id, project_id=project.id,
        user_id=member.id, attempts=0,
        gdpr_consent_at=NOW if consent else None, consent_version="1",
    )
    return link, membership


def _entitlement(project, user, *, revoked=False):
    return MarketplaceEntitlement(
        id=str(uuid.uuid4()), user_id=user.id, project_id=project.id,
        source="discovered", revoked_at=NOW if revoked else None,
    )


def _submission(project, owner, user):
    task = Task(
        id=str(uuid.uuid4()), project_id=project.id, inner_id=1,
        data={"sachverhalt": "Fall"}, created_by=owner.id,
    )
    return task, Annotation(
        id=str(uuid.uuid4()), task_id=task.id, project_id=project.id,
        completed_by=user.id, result=[{"v": 1}], was_cancelled=False,
    )


async def _add_all(db, *rows):
    for r in rows:
        db.add(r)
        await db.flush()
    await db.commit()


async def _role_both(db, user, project):
    """Resolve the review role on both lanes and assert they agree."""
    from services.peer_review import review_role, review_role_async

    got_async = await review_role_async(db, user, project)
    got_sync = await db.run_sync(lambda s: review_role(s, user, project))
    assert got_async == got_sync, (got_async, got_sync)
    return got_async


async def _candidates_both(db, project, user_ids=None):
    from services.peer_review import peer_candidate_ids, peer_candidate_ids_async

    got_async = await peer_candidate_ids_async(db, project, user_ids)
    got_sync = await db.run_sync(lambda s: peer_candidate_ids(s, project, user_ids))
    assert got_async == got_sync, (got_async, got_sync)
    return got_async


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
        created_at=db_user.created_at or NOW,
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


# ------------------------------------------------------------- the world ----


async def _world(db, **project_kwargs):
    """One project with every kind of person around it."""
    people = {
        name: _user()
        for name in (
            "owner", "org_admin", "contributor", "annotator", "inactive_member",
            "group_annotator", "group_outsider", "group_contributor",
            "sharer", "unconsented", "entitled", "revoked", "outsider",
        )
    }
    people["superadmin"] = _user(superadmin=True)
    people["service"] = _user(service=True)
    await _add_all(db, *people.values())

    project = _project(people["owner"], **project_kwargs)
    org, org_rows = _org(
        (people["org_admin"], OrganizationRole.ORG_ADMIN, True),
        (people["contributor"], OrganizationRole.CONTRIBUTOR, True),
        (people["annotator"], OrganizationRole.ANNOTATOR, True),
        (people["inactive_member"], OrganizationRole.ANNOTATOR, False),
        (people["service"], OrganizationRole.ANNOTATOR, True),
    )
    # A grouped attachment of a second org: its group's members take part
    # (with their group role), the org's other members do not.
    gorg, gorg_rows = _org(
        (people["group_annotator"], OrganizationRole.CONTRIBUTOR, True),
        (people["group_outsider"], OrganizationRole.ANNOTATOR, True),
        (people["group_contributor"], OrganizationRole.ANNOTATOR, True),
    )
    group = OrganizationGroup(id=str(uuid.uuid4()), organization_id=gorg.id, name="Kurs A")
    await _add_all(db, project, org, *org_rows, gorg, *gorg_rows, group)
    link_s, member_s = _share(project, people["owner"], people["sharer"])
    link_u, member_u = _share(project, people["owner"], people["unconsented"], consent=False)
    await _add_all(
        db,
        _attach(project, org, people["owner"]),
        _attach(project, gorg, people["owner"], group=group),
        OrganizationGroupMembership(
            id=str(uuid.uuid4()), group_id=group.id,
            user_id=people["group_annotator"].id, role=OrganizationRole.ANNOTATOR,
        ),
        OrganizationGroupMembership(
            id=str(uuid.uuid4()), group_id=group.id,
            user_id=people["group_contributor"].id, role=OrganizationRole.CONTRIBUTOR,
        ),
        link_s, member_s, link_u, member_u,
        _entitlement(project, people["entitled"]),
        _entitlement(project, people["revoked"], revoked=True),
    )
    return project, people


EXPECTED = {
    "owner": "staff",
    "superadmin": "staff",
    "org_admin": "staff",
    "contributor": "staff",
    "group_contributor": "staff",
    "annotator": "peer",
    "group_annotator": "peer",
    "sharer": "peer",
    "entitled": "peer",
    "service": None,
    "inactive_member": None,
    "group_outsider": None,
    "unconsented": None,
    "revoked": None,
    "outsider": None,
}


async def test_roles_and_candidates_agree_on_a_project_with_peer_review(async_test_db):
    db = async_test_db
    project, people = await _world(db)

    roles = {name: await _role_both(db, user, project) for name, user in people.items()}
    assert roles == EXPECTED

    candidates = await _candidates_both(db, project)
    assert candidates == {people[n].id for n, role in EXPECTED.items() if role == "peer"}

    # Narrowed to some people: only the peers among them.
    some = [people["annotator"].id, people["contributor"].id, people["outsider"].id]
    assert await _candidates_both(db, project, some) == {people["annotator"].id}
    assert await _candidates_both(db, project, []) == set()


async def test_switch_off_leaves_only_staff(async_test_db):
    db = async_test_db
    project, people = await _world(db, enabled=False)

    roles = {name: await _role_both(db, user, project) for name, user in people.items()}
    assert roles == {
        name: ("staff" if role == "staff" else None) for name, role in EXPECTED.items()
    }
    assert await _candidates_both(db, project) == set()


async def test_an_archived_project_has_no_peers(async_test_db):
    db = async_test_db
    project, people = await _world(db, archived=True)

    assert await _role_both(db, people["annotator"], project) is None
    assert await _role_both(db, people["sharer"], project) is None
    assert await _role_both(db, people["owner"], project) == "staff"
    assert await _candidates_both(db, project) == set()


async def test_an_exam_before_its_window_reaches_no_org_member(async_test_db):
    db = async_test_db
    project, people = await _world(
        db, kind="exam", window_start=NOW + timedelta(hours=2)
    )

    # Org annotators reach an exam only once its window has started; the
    # share member and the entitled student came through their own channel.
    assert await _role_both(db, people["annotator"], project) is None
    assert await _role_both(db, people["group_annotator"], project) is None
    assert await _role_both(db, people["sharer"], project) == "peer"
    assert await _role_both(db, people["entitled"], project) == "peer"
    assert await _candidates_both(db, project) == {
        people["sharer"].id,
        people["entitled"].id,
    }

    project.window_start_at = NOW - timedelta(hours=1)
    project.window_end_at = NOW + timedelta(hours=1)
    await db.commit()
    assert await _role_both(db, people["annotator"], project) == "peer"
    assert people["annotator"].id in await _candidates_both(db, project)


async def test_a_private_project_reaches_only_its_explicit_participants(async_test_db):
    db = async_test_db
    project, people = await _world(db, private=True, kind="exam")

    assert await _role_both(db, people["annotator"], project) is None
    assert await _role_both(db, people["sharer"], project) == "peer"
    assert await _candidates_both(db, project) == {
        people["sharer"].id,
        people["entitled"].id,
    }


async def test_on_a_public_project_the_people_who_handed_in_are_peers(async_test_db):
    db = async_test_db
    owner, submitter, visitor = _user(), _user(), _user()
    await _add_all(db, owner, submitter, visitor)
    project = _project(owner, public_role="ANNOTATOR")
    await _add_all(db, project)
    task, annotation = _submission(project, owner, submitter)
    await _add_all(db, task, annotation)

    assert await _role_both(db, submitter, project) == "peer"
    # A visitor who never handed in may grade too, but nobody lists them.
    assert await _role_both(db, visitor, project) == "peer"
    assert await _candidates_both(db, project) == {submitter.id}


async def test_a_deactivated_account_is_never_listed(async_test_db):
    db = async_test_db
    project, people = await _world(db)
    people["annotator"].is_active = False
    await db.commit()

    assert people["annotator"].id not in await _candidates_both(db, project)


# ------------------------------------------------------------ the API ----


async def test_project_response_tells_the_caller_their_review_role(
    async_test_db, async_test_client
):
    db = async_test_db
    project, people = await _world(db)

    for name in ("owner", "contributor", "annotator", "sharer"):
        with _as_user(people[name]):
            r = await async_test_client.get(f"/api/projects/{project.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["peer_review_enabled"] is True
        assert body["viewer_review_role"] == EXPECTED[name], name

    project.peer_review_enabled = False
    await db.commit()
    with _as_user(people["annotator"]):
        r = await async_test_client.get(f"/api/projects/{project.id}")
    assert r.status_code == 200, r.text
    assert r.json()["viewer_review_role"] is None


@pytest.mark.parametrize(
    "who, allowed", [("owner", True), ("org_admin", True), ("superadmin", True),
                     ("contributor", False)],
)
async def test_only_a_project_admin_switches_peer_review(
    async_test_db, async_test_client, who, allowed
):
    db = async_test_db
    project, people = await _world(db, enabled=False)

    with _as_user(people[who]):
        r = await async_test_client.patch(
            f"/api/projects/{project.id}", json={"peer_review_enabled": True}
        )

    await db.refresh(project)
    if allowed:
        assert r.status_code == 200, r.text
        assert r.json()["peer_review_enabled"] is True
        assert project.peer_review_enabled is True
    else:
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "peer_review_admin_only"
        assert project.peer_review_enabled is False


async def test_a_contributor_may_echo_the_stored_value_and_edit_the_rest(
    async_test_db, async_test_client
):
    db = async_test_db
    project, people = await _world(db, enabled=True)

    with _as_user(people["contributor"]):
        r = await async_test_client.patch(
            f"/api/projects/{project.id}",
            json={"peer_review_enabled": True, "description": "Neu"},
        )
        assert r.status_code == 200, r.text
        # An explicit null leaves the switch as it is.
        r = await async_test_client.patch(
            f"/api/projects/{project.id}", json={"peer_review_enabled": None}
        )
        assert r.status_code == 200, r.text

    await db.refresh(project)
    assert project.peer_review_enabled is True
    assert project.description == "Neu"


async def test_a_group_admin_switches_peer_review_on_their_groups_project(
    async_test_db, async_test_client
):
    db = async_test_db
    owner, group_admin = _user(), _user()
    await _add_all(db, owner, group_admin)
    org, org_rows = _org((group_admin, OrganizationRole.ANNOTATOR, True))
    group = OrganizationGroup(id=str(uuid.uuid4()), organization_id=org.id, name="Kurs B")
    project = _project(owner, enabled=False)
    await _add_all(db, org, *org_rows, group, project)
    await _add_all(
        db,
        _attach(project, org, owner, group=group),
        OrganizationGroupMembership(
            id=str(uuid.uuid4()), group_id=group.id, user_id=group_admin.id,
            role=OrganizationRole.ORG_ADMIN,
        ),
    )

    with _as_user(group_admin):
        r = await async_test_client.patch(
            f"/api/projects/{project.id}", json={"peer_review_enabled": True}
        )
    assert r.status_code == 200, r.text
    await db.refresh(project)
    assert project.peer_review_enabled is True
