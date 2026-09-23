"""Attempted access tier: an own submission keeps read access.

Once a user holds a non-cancelled annotation on a project they keep READ
access to that submission (their tasks, their annotations, the participation
read, the project row) whatever happens to the window, the archive flag,
privacy, org membership / group, the share roster or their own enrollment.
Only the project's soft delete removes it. The tier never writes: annotation
create/update, drafts, checkpoints, skips and questionnaire submits refuse it
with a coded 403. Precedence: full > participant > attempted.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

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
    TaskAssignment,
)

EXAM_CONFIG = (
    '<View><Text name="sv" value="$sachverhalt"/>'
    '<TextArea name="loesung" toName="sv"/></View>'
)

NOW = datetime.now(timezone.utc)
UPCOMING = (NOW + timedelta(hours=1), NOW + timedelta(hours=3))
CLOSED = (NOW - timedelta(hours=3), NOW - timedelta(hours=1))
OPEN = (NOW - timedelta(hours=1), NOW + timedelta(hours=1))


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


# ------------------------------------------------------------ builders ----
# Plain constructors so the same shapes serve the async (async_test_db) and
# the sync (test_db) sessions — the sync solver endpoints (annotation POST,
# draft PUT, my-tasks) run on the sync lane and need the sync fixture.


def _new_user(*, superadmin=False) -> User:
    return User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _new_project(owner, *, private=True, kind=None, archived=False, window=None,
                 assignment_mode="open") -> Project:
    start, end = window or (None, None)
    return Project(
        id=str(uuid.uuid4()),
        title=f"P {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        is_private=private,
        is_public=False,
        kind=kind,
        is_archived=archived,
        label_config=EXAM_CONFIG,
        assignment_mode=assignment_mode,
        evaluation_config={"judge": "secret-prompt"},
        window_start_at=start,
        window_end_at=end,
    )


def _new_task(project, owner, i=0) -> Task:
    return Task(
        id=str(uuid.uuid4()), project_id=project.id, inner_id=i + 1,
        data={"sachverhalt": f"Fall {i}", "musterloesung": "GEHEIM"},
        created_by=owner.id,
    )


def _new_annotation(task, user, *, cancelled=False) -> Annotation:
    return Annotation(
        id=str(uuid.uuid4()), task_id=task.id, project_id=task.project_id,
        completed_by=user.id, result=[{"v": user.id}], was_cancelled=cancelled,
    )


def _new_share(project, owner, member, *, consent=True):
    link = ProjectShareLink(
        id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=project.id,
        created_by=owner.id, password_hash="x", is_listed=False,
    )
    membership = ProjectShareMember(
        id=str(uuid.uuid4()), share_link_id=link.id, project_id=project.id,
        user_id=member.id, attempts=0,
        gdpr_consent_at=datetime.now(timezone.utc) if consent else None,
        consent_version="1",
    )
    return link, membership


def _new_org(*members):
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(id=str(uuid.uuid4()), name=slug, display_name=slug, slug=slug)
    rows = [
        OrganizationMembership(
            id=str(uuid.uuid4()), user_id=user.id, organization_id=org.id,
            role=role, is_active=True,
        )
        for user, role in members
    ]
    return org, rows


def _attach(project, org, by, group=None) -> ProjectOrganization:
    return ProjectOrganization(
        id=str(uuid.uuid4()), project_id=project.id, organization_id=org.id,
        assigned_by=by.id, group_id=group.id if group is not None else None,
    )


async def _add_all(db, *rows):
    for r in rows:
        db.add(r)
        await db.flush()
    await db.commit()


async def _tier_both(db, user, project_id):
    """Resolve the tier on both lanes and assert they agree."""
    from routers.projects.helpers import (
        get_project_access_tier,
        get_project_access_tier_async,
    )

    got_async = await get_project_access_tier_async(db, user, project_id)
    got_sync = await db.run_sync(
        lambda s: get_project_access_tier(s, user, project_id)
    )
    assert got_async == got_sync, (got_async, got_sync)
    return got_async


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# --------------------------------------------------------- tier matrix ----


async def test_tier_matrix_own_submission_survives_every_revocation(async_test_db):
    from routers.projects.helpers import TIER_ATTEMPTED, TIER_FULL, TIER_PARTICIPANT

    db = async_test_db
    owner, member = _new_user(), _new_user()
    await _add_all(db, owner, member)

    # --- share member: roster eviction, link deletion, archive, leave ---------
    evicted = _new_project(owner)
    t_evicted = _new_task(evicted, owner)
    link_e, mem_e = _new_share(evicted, owner, member)
    await _add_all(db, evicted, t_evicted, link_e, mem_e, _new_annotation(t_evicted, member))
    assert await _tier_both(db, member, evicted.id) == TIER_PARTICIPANT  # participant beats attempted
    await db.delete(mem_e)
    await db.commit()
    assert await _tier_both(db, member, evicted.id) == TIER_ATTEMPTED

    revoked = _new_project(owner)
    t_revoked = _new_task(revoked, owner)
    link_r, mem_r = _new_share(revoked, owner, member)
    await _add_all(db, revoked, t_revoked, link_r, mem_r, _new_annotation(t_revoked, member))
    assert await _tier_both(db, member, revoked.id) == TIER_PARTICIPANT
    await db.delete(link_r)  # link deletion cascades the roster row
    await db.commit()
    assert await _tier_both(db, member, revoked.id) == TIER_ATTEMPTED

    archived = _new_project(owner)
    t_archived = _new_task(archived, owner)
    link_a, mem_a = _new_share(archived, owner, member)
    await _add_all(db, archived, t_archived, link_a, mem_a, _new_annotation(t_archived, member))
    archived.is_archived = True
    await db.commit()
    assert await _tier_both(db, member, archived.id) == TIER_ATTEMPTED

    # --- org exam: upcoming window, closed window, private flip, membership,
    #     group move -------------------------------------------------------------
    annot = _new_user()
    org, org_rows = _new_org((annot, OrganizationRole.ANNOTATOR))
    await _add_all(db, annot, org, *org_rows)

    moved = _new_project(owner, private=False, kind="exam", window=OPEN)
    t_moved = _new_task(moved, owner)
    await _add_all(db, moved, t_moved, _attach(moved, org, owner), _new_annotation(t_moved, annot))
    assert await _tier_both(db, annot, moved.id) == TIER_PARTICIPANT
    # The teacher moves the window into the future after the submission.
    moved.window_start_at, moved.window_end_at = UPCOMING
    await db.commit()
    assert await _tier_both(db, annot, moved.id) == TIER_ATTEMPTED

    closed = _new_project(owner, private=False, kind="exam", window=CLOSED)
    t_closed = _new_task(closed, owner)
    await _add_all(db, closed, t_closed, _attach(closed, org, owner), _new_annotation(t_closed, annot))
    # A closed window keeps the org-exam participant grant (participant beats
    # attempted); the read-only state comes from the window itself.
    assert await _tier_both(db, annot, closed.id) == TIER_PARTICIPANT

    flipped = _new_project(owner, private=False, kind="exam")
    t_flipped = _new_task(flipped, owner)
    await _add_all(db, flipped, t_flipped, _attach(flipped, org, owner), _new_annotation(t_flipped, annot))
    assert await _tier_both(db, annot, flipped.id) == TIER_PARTICIPANT
    flipped.is_private = True
    await db.commit()
    assert await _tier_both(db, annot, flipped.id) == TIER_ATTEMPTED

    group_a = OrganizationGroup(id=str(uuid.uuid4()), organization_id=org.id, name="A")
    group_b = OrganizationGroup(id=str(uuid.uuid4()), organization_id=org.id, name="B")
    gm = OrganizationGroupMembership(id=str(uuid.uuid4()), group_id=group_a.id, user_id=annot.id)
    grouped = _new_project(owner, private=False, kind="exam")
    t_grouped = _new_task(grouped, owner)
    await _add_all(
        db, group_a, group_b, gm, grouped, t_grouped,
        _attach(grouped, org, owner, group=group_a), _new_annotation(t_grouped, annot),
    )
    assert await _tier_both(db, annot, grouped.id) == TIER_PARTICIPANT
    gm.group_id = group_b.id  # moved to the other group
    await db.commit()
    assert await _tier_both(db, annot, grouped.id) == TIER_ATTEMPTED

    # Membership deactivation drops BOTH the closed and the grouped exam to attempted.
    org_rows[0].is_active = False
    await db.commit()
    assert await _tier_both(db, annot, closed.id) == TIER_ATTEMPTED
    assert await _tier_both(db, annot, grouped.id) == TIER_ATTEMPTED

    # --- full beats both; a cancelled annotation is no submission; soft
    #     delete removes everything ----------------------------------------------
    own = _new_project(owner)
    t_own = _new_task(own, owner)
    await _add_all(db, own, t_own, _new_annotation(t_own, owner))
    assert await _tier_both(db, owner, own.id) == TIER_FULL

    cancelled = _new_project(owner)
    t_cancelled = _new_task(cancelled, owner)
    await _add_all(db, cancelled, t_cancelled, _new_annotation(t_cancelled, member, cancelled=True))
    assert await _tier_both(db, member, cancelled.id) is None

    evicted.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    assert await _tier_both(db, member, evicted.id) is None
    superadmin = _new_user(superadmin=True)
    await _add_all(db, superadmin)
    assert await _tier_both(db, superadmin, evicted.id) == TIER_FULL


async def test_leaving_keeps_the_submission(async_test_client, async_test_db):
    """DELETE participation removes the enrollment; the own submission stays
    readable (contrast: without a submission the project 403s after leaving)."""
    db = async_test_db
    owner, member, other = _new_user(), _new_user(), _new_user()
    p = _new_project(owner)
    t = _new_task(p, owner)
    await _add_all(db, owner, member, other, p, t)
    await _add_all(db, MarketplaceEntitlement(id=str(uuid.uuid4()), user_id=member.id,
                                              project_id=p.id, source="discovered"))
    await _add_all(db, MarketplaceEntitlement(id=str(uuid.uuid4()), user_id=other.id,
                                              project_id=p.id, source="discovered"))
    await _add_all(db, _new_annotation(t, member))

    with _as_user(member):
        r = await async_test_client.delete(f"/api/projects/{p.id}/participation")
        assert r.status_code == 204, r.text
        r = await async_test_client.get(f"/api/projects/{p.id}")
        assert r.status_code == 200, r.text
        assert r.json()["access_tier"] == "attempted"
        r = await async_test_client.get(f"/api/projects/{p.id}/participation")
        assert r.status_code == 200
        assert r.json()["tier"] == "attempted"
        assert r.json()["via"] == "attempted"
        assert r.json()["can_leave"] is False
        assert r.json()["cannot_leave_reason"] == "attempted"
    with _as_user(other):
        r = await async_test_client.delete(f"/api/projects/{p.id}/participation")
        assert r.status_code == 204
        r = await async_test_client.get(f"/api/projects/{p.id}")
        assert r.status_code == 403


# ---------------------------------------------------- helper twins ----


async def test_attempted_project_ids_twins(async_test_db):
    from routers.projects.helpers import (
        get_attempted_project_ids,
        get_attempted_project_ids_async,
        get_participant_project_ids_async,
        user_attempted_project,
        user_attempted_project_async,
    )

    db = async_test_db
    owner, u = _new_user(), _new_user()
    await _add_all(db, owner, u)
    archived = _new_project(owner, archived=True)
    private_exam = _new_project(owner, kind="exam")
    deleted = _new_project(owner)
    cancelled_only = _new_project(owner)
    untouched = _new_project(owner)
    tasks = {p.id: _new_task(p, owner) for p in (archived, private_exam, deleted, cancelled_only, untouched)}
    await _add_all(db, archived, private_exam, deleted, cancelled_only, untouched, *tasks.values())
    await _add_all(
        db,
        _new_annotation(tasks[archived.id], u),
        _new_annotation(tasks[private_exam.id], u),
        _new_annotation(tasks[deleted.id], u),
        _new_annotation(tasks[cancelled_only.id], u, cancelled=True),
    )
    deleted.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    expected = {archived.id, private_exam.id}
    got_async = await get_attempted_project_ids_async(db, u.id)
    got_sync = await db.run_sync(lambda s: get_attempted_project_ids(s, u.id))
    assert got_async == expected
    assert got_sync == expected  # lockstep twins
    # The participant batch stays untouched by submissions.
    assert await get_participant_project_ids_async(db, u.id) == {}

    for pid in (archived.id, private_exam.id):
        assert await user_attempted_project_async(db, u.id, pid) is True
        assert await db.run_sync(lambda s, pid=pid: user_attempted_project(s, u.id, pid)) is True
    assert await user_attempted_project_async(db, u.id, cancelled_only.id) is False
    assert await db.run_sync(lambda s: user_attempted_project(s, u.id, untouched.id)) is False
    # Soft delete is filtered by the batch, not by the per-project predicate
    # (the tier resolver handles deleted_at before it asks).
    assert await user_attempted_project_async(db, u.id, deleted.id) is True


async def test_write_tier_helpers():
    from routers.projects.helpers import (
        TIER_ATTEMPTED,
        TIER_FULL,
        TIER_PARTICIPANT,
        require_write_tier,
        tier_allows_writes,
    )

    assert tier_allows_writes(TIER_FULL) and tier_allows_writes(TIER_PARTICIPANT)
    assert not tier_allows_writes(TIER_ATTEMPTED) and not tier_allows_writes(None)
    require_write_tier(TIER_FULL)
    require_write_tier(TIER_PARTICIPANT)
    with pytest.raises(HTTPException) as e:
        require_write_tier(None)
    assert e.value.status_code == 403 and e.value.detail == "Access denied"
    with pytest.raises(HTTPException) as e:
        require_write_tier(TIER_ATTEMPTED)
    assert e.value.status_code == 403 and e.value.detail["code"] == "attempted_read_only"


async def test_own_annotation_counts_as_assigned(async_test_db):
    from routers.projects.helpers import (
        check_task_assigned_to_user,
        check_task_assigned_to_user_async,
    )

    db = async_test_db
    owner, annot, other = _new_user(), _new_user(), _new_user()
    org, org_rows = _new_org((annot, OrganizationRole.ANNOTATOR), (other, OrganizationRole.ANNOTATOR))
    p = _new_project(owner, private=False, assignment_mode="manual")
    t = _new_task(p, owner)
    await _add_all(db, owner, annot, other, org, *org_rows, p, t, _attach(p, org, owner))
    await _add_all(db, TaskAssignment(id=str(uuid.uuid4()), task_id=t.id, user_id=annot.id,
                                      assigned_by=owner.id, status="completed"))
    await _add_all(db, _new_annotation(t, annot))
    assert await check_task_assigned_to_user_async(db, annot, t.id, p) is True
    assert await check_task_assigned_to_user_async(db, other, t.id, p) is False
    # The assignment row is removed after the fact: the submission still counts.
    row = (await db.execute(select(TaskAssignment).where(TaskAssignment.task_id == t.id))).scalar_one()
    await db.delete(row)
    await db.commit()
    assert await check_task_assigned_to_user_async(db, annot, t.id, p) is True
    assert await db.run_sync(lambda s: check_task_assigned_to_user(s, annot, t.id, p)) is True
    assert await db.run_sync(lambda s: check_task_assigned_to_user(s, other, t.id, p)) is False


# ------------------------------------------------------ read window ----


async def test_read_window_exempts_attempted(async_test_db, async_test_client):
    from routers.projects.helpers import (
        TIER_ATTEMPTED,
        TIER_PARTICIPANT,
        enforce_project_read_window,
        enforce_project_read_window_async,
    )

    db = async_test_db
    owner, member, stranger = _new_user(), _new_user(), _new_user()
    p = _new_project(owner, window=UPCOMING)
    t = _new_task(p, owner)
    link, mem = _new_share(p, owner, member)
    link2, mem2 = _new_share(p, owner, stranger)
    await _add_all(db, owner, member, stranger, p, t, link, mem, link2, mem2, _new_annotation(t, member))

    # Explicit tier: attempted passes, participant is gated.
    await enforce_project_read_window_async(db, member, p, tier=TIER_ATTEMPTED)
    await db.run_sync(lambda s: enforce_project_read_window(s, member, p, tier=TIER_ATTEMPTED))
    with pytest.raises(HTTPException) as e:
        await enforce_project_read_window_async(db, stranger, p, tier=TIER_PARTICIPANT)
    assert e.value.detail["code"] == "project_window_upcoming"
    # No tier passed (old call sites): the predicate is re-checked.
    await enforce_project_read_window_async(db, member, p)
    await db.run_sync(lambda s: enforce_project_read_window(s, member, p))
    with pytest.raises(HTTPException):
        await enforce_project_read_window_async(db, stranger, p)
    with pytest.raises(HTTPException):
        await db.run_sync(lambda s: enforce_project_read_window(s, stranger, p))

    # Wired into the handlers: the member (still a share member, so the
    # participant tier — window-gated for new tasks) reads their own task
    # through the escape because the resolver-free path re-checks the predicate
    # only when no tier is given. Evict them so the tier is attempted.
    await db.delete(mem)
    await db.commit()
    with _as_user(member):
        r = await async_test_client.get(f"/api/projects/tasks/{t.id}")
        assert r.status_code == 200, r.text
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert r.status_code == 200, r.text
        r = await async_test_client.get(f"/api/projects/tasks/{t.id}/annotations")
        assert r.status_code == 200, r.text
        assert {a["completed_by"] for a in r.json()} == {member.id}
    with _as_user(stranger):
        r = await async_test_client.get(f"/api/projects/tasks/{t.id}")
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "project_window_upcoming"


# ------------------------------------------------- async endpoints ----


async def test_task_endpoints_scoped_to_own_submission(async_test_client, async_test_db):
    db = async_test_db
    owner, member, other = _new_user(), _new_user(), _new_user()
    p = _new_project(owner)
    mine, not_mine = _new_task(p, owner, 0), _new_task(p, owner, 1)
    link, mem = _new_share(p, owner, member)
    link2, mem2 = _new_share(p, owner, other)
    await _add_all(db, owner, member, other, p, mine, not_mine, link, mem, link2, mem2)
    own_ann = _new_annotation(mine, member)
    await _add_all(db, own_ann, _new_annotation(mine, other), _new_annotation(not_mine, other))
    await db.delete(mem)  # evicted -> attempted
    await db.commit()

    with _as_user(member):
        r = await async_test_client.get(f"/api/projects/{p.id}")
        assert r.status_code == 200, r.text
        assert r.json()["access_tier"] == "attempted"
        assert r.json()["participant_via"] is None
        assert r.json()["evaluation_config"] is None
        assert r.json()["can_manage_shares"] is False

        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert r.status_code == 200, r.text
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        assert [t["id"] for t in items] == [mine.id]
        # Blinding: the own submission reveals nothing beyond the bound fields
        # unless the project opts in (annotator_full_visibility_after_submit).
        assert "musterloesung" not in items[0]["data"]
        assert {a["id"] for a in items[0]["annotators"]} <= {member.id}

        r = await async_test_client.get(f"/api/projects/tasks/{mine.id}")
        assert r.status_code == 200, r.text
        r = await async_test_client.get(f"/api/projects/tasks/{not_mine.id}")
        assert r.status_code == 404

        r = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is None

        r = await async_test_client.get(
            f"/api/projects/tasks/{mine.id}/annotations", params={"all_users": "true"}
        )
        assert r.status_code == 200, r.text
        assert {a["completed_by"] for a in r.json()} == {member.id}
        r = await async_test_client.get(f"/api/projects/tasks/{not_mine.id}/annotations")
        assert r.status_code == 404

        r = await async_test_client.get(f"/api/projects/{p.id}/participation")
        assert r.status_code == 200
        assert r.json()["via"] == "attempted" and r.json()["can_leave"] is False
        assert r.json()["cannot_leave_reason"] == "attempted"

        r = await async_test_client.get(f"/api/projects/{p.id}/cohort-leaderboard")
        assert r.status_code == 200, r.text

        # Writes: coded read-only 403, nothing changes.
        r = await async_test_client.patch(
            f"/api/projects/annotations/{own_ann.id}", json={"result": [{"v": "edited"}]}
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "attempted_read_only"
        r = await async_test_client.post(f"/api/projects/{p.id}/tasks/{mine.id}/skip", json={})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "attempted_read_only"
        p.questionnaire_enabled = True
        await db.commit()
        r = await async_test_client.post(
            f"/api/projects/{p.id}/tasks/{mine.id}/questionnaire-response",
            json={"annotation_id": own_ann.id, "result": []},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "attempted_read_only"
        # Editor surfaces stay closed.
        for path in (f"/api/projects/{p.id}/shares", f"/api/projects/{p.id}/shares/roster"):
            assert (await async_test_client.get(path)).status_code in (403, 404)
        assert (await async_test_client.patch(f"/api/projects/{p.id}", json={"title": "x"})).status_code in (403, 404)

    await db.refresh(own_ann)
    assert own_ann.result == [{"v": member.id}]

    # The other share member keeps the participant tier and sees both tasks.
    with _as_user(other):
        r = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        assert {t["id"] for t in items} == {mine.id, not_mine.id}


async def test_project_list_carries_attempted_rows(async_test_client, async_test_db):
    db = async_test_db
    owner, member = _new_user(), _new_user()
    org, org_rows = _new_org((member, OrganizationRole.ANNOTATOR), (owner, OrganizationRole.ORG_ADMIN))
    await _add_all(db, owner, member, org, *org_rows)

    evicted = _new_project(owner)
    t1 = _new_task(evicted, owner)
    link, mem = _new_share(evicted, owner, member)
    joined = _new_project(owner)
    t2 = _new_task(joined, owner)
    link2, mem2 = _new_share(joined, owner, member)
    mine = _new_project(member)
    archived_org = _new_project(owner, private=False, kind="exam")
    t3 = _new_task(archived_org, owner)
    stranger_project = _new_project(owner)
    await _add_all(db, evicted, t1, link, mem, joined, t2, link2, mem2, mine,
                   archived_org, t3, _attach(archived_org, org, owner), stranger_project)
    await _add_all(db, _new_annotation(t1, member), _new_annotation(t2, member),
                   _new_annotation(t3, member))
    await db.delete(mem)
    archived_org.is_archived = True
    await db.commit()

    with _as_user(member):
        r = await async_test_client.get("/api/projects/", params={"page_size": 100})
        assert r.status_code == 200, r.text
        rows = {p["id"]: p for p in r.json()["items"]}
        assert rows[evicted.id]["access_tier"] == "attempted"
        assert rows[evicted.id]["participant_via"] is None
        assert rows[evicted.id]["evaluation_config"] is None
        # participant beats attempted; full beats both.
        assert rows[joined.id]["access_tier"] == "participant"
        assert rows[mine.id]["access_tier"] == "full"
        assert stranger_project.id not in rows

        # Archived exam under the org context: the annotator archive filter
        # lets the own submission through, tagged attempted.
        r = await async_test_client.get(
            "/api/projects/",
            params={"page_size": 100, "is_archived": "true"},
        )
        assert r.status_code == 200, r.text
        rows = {p["id"]: p for p in r.json()["items"]}
        assert rows[archived_org.id]["access_tier"] == "attempted"

        # A stale org context still lists the attempted project (no 403).
        r = await async_test_client.get(
            "/api/projects/"
        )
        assert r.status_code == 200, r.text
        assert {p["id"] for p in r.json()["items"]} >= {evicted.id}


# -------------------------------------------------- sync endpoints ----
# annotation POST, draft PUT, checkpoint POST, my-tasks run on the sync lane.


def _sync_world(test_db):
    owner, member = _new_user(), _new_user()
    p = _new_project(owner)
    mine, not_mine = _new_task(p, owner, 0), _new_task(p, owner, 1)
    link, mem = _new_share(p, owner, member)
    for row in (owner, member, p, mine, not_mine, link, mem):
        test_db.add(row)
        test_db.flush()
    ann = _new_annotation(mine, member)
    test_db.add(ann)
    test_db.flush()
    test_db.delete(mem)  # evicted -> attempted
    test_db.commit()
    return owner, member, p, mine, not_mine, ann


@pytest.mark.integration
def test_sync_writes_refused_and_my_tasks_allowed(client, test_db):
    owner, member, p, mine, not_mine, ann = _sync_world(test_db)
    body = {"result": [{"v": "again"}], "was_cancelled": False}

    with _as_user(member):
        r = client.post(f"/api/projects/tasks/{mine.id}/annotations", json=body)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "attempted_read_only"
        r = client.post(f"/api/projects/tasks/{not_mine.id}/annotations", json=body)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "attempted_read_only"

        r = client.put(f"/api/projects/{p.id}/tasks/{mine.id}/draft", json={"result": [{"v": 1}]})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "attempted_read_only"
        r = client.post(f"/api/projects/{p.id}/tasks/{mine.id}/checkpoint", json={"result": [{"v": 1}]})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "attempted_read_only"
        # Own checkpoint history stays readable.
        r = client.get(f"/api/projects/{p.id}/tasks/{mine.id}/checkpoints")
        assert r.status_code == 200, r.text

        r = client.get(f"/api/projects/{p.id}/my-tasks")
        assert r.status_code == 200, r.text
        assert [t["id"] for t in r.json()["tasks"]] == [mine.id]

    test_db.refresh(ann)
    assert ann.result == [{"v": member.id}]
    assert test_db.query(Annotation).filter(Annotation.project_id == p.id).count() == 1
