"""Integration tests for running an LMS connection (/api/admin/lti).

Deleting a connection (two steps, account choice, clean-up of org
attachments and LMS entitlements), the activity and LMS user lists (real
names for everyone who may manage the connection, D8), unlinking, the change history, the grade
transfer list with context, and the retry that queues the push through the
``dispatch_lti_grade_sync`` hook.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import extensions
from models import (
    LtiAdminEvent,
    LtiDeployment,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiResourceLink,
    LtiResourceLinkUser,
    LtiUserLink,
    User,
)
from project_models import MarketplaceEntitlement, ProjectOrganization
from tests.fixtures.lti_admin_world import (
    LINEITEM_SCOPE,
    SCORE_SCOPE,
    FakeExtended,
    as_user,
    build_world,
    detail_code,
    make_grade_sync,
    make_invite,
    make_participation,
    make_project,
    make_registration,
    make_resource_link,
    make_user,
    make_user_link,
    set_tool_host_env,
)

BASE = "/api/admin/lti"


@pytest.fixture(autouse=True)
def _community_edition_with_two_hosts(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", None)
    set_tool_host_env(monkeypatch)


async def _rows(db, model, *conditions):
    stmt = select(model).where(*conditions).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().all()


async def _events(db, **filters):
    stmt = (
        select(LtiAdminEvent)
        .order_by(LtiAdminEvent.created_at)
        .execution_options(populate_existing=True)
    )
    for field, value in filters.items():
        stmt = stmt.where(getattr(LtiAdminEvent, field) == value)
    return (await db.execute(stmt)).scalars().all()


def _attach(db, project, org, *, via, by):
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=by.id,
            attached_via=via,
        )
    )


def _entitle(db, user, project, *, source="lti"):
    row = MarketplaceEntitlement(
        id=str(uuid.uuid4()), user_id=user.id, project_id=project.id, source=source
    )
    db.add(row)
    return row


# --------------------------------------------------------------------------- #
# Deleting a connection
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_requires_disabled_and_an_account_choice_then_cleans_up(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    owner = world.org_admin
    reg = await make_registration(db, world.org, name="Old Moodle")
    sibling = await make_registration(db, world.org, name="Second Moodle")
    foreign = await make_registration(db, world.other_org)

    only_here = await make_project(db, owner, title="only here")
    shared_in_org = await make_project(db, owner, title="also sibling")
    shared_abroad = await make_project(db, owner, title="also foreign org")
    manual = await make_project(db, owner, title="manually shared")
    _attach(db, only_here, world.org, via="lti", by=owner)
    _attach(db, shared_in_org, world.org, via="lti", by=owner)
    _attach(db, shared_abroad, world.org, via="lti", by=owner)
    _attach(db, shared_abroad, world.other_org, via="lti", by=owner)
    _attach(db, manual, world.org, via="manual", by=owner)

    link_only = await make_resource_link(db, reg, project=only_here)
    await make_resource_link(db, reg, project=shared_in_org)
    await make_resource_link(db, reg, project=shared_abroad)
    await make_resource_link(db, reg, project=manual)
    await make_resource_link(db, sibling, project=shared_in_org)
    await make_resource_link(db, foreign, project=shared_abroad)

    provisioned = await make_user(db)
    proven = await make_user(db)
    abroad = await make_user(db)
    await make_user_link(db, reg, provisioned)
    await make_user_link(db, reg, proven, link_method="login_proof")
    await make_user_link(db, foreign, abroad)
    await make_grade_sync(db, link_only, provisioned)
    await make_participation(db, link_only, provisioned)

    lost_only = _entitle(db, provisioned, only_here)
    lost_abroad = _entitle(db, provisioned, shared_abroad)
    kept_abroad = _entitle(db, abroad, shared_abroad)
    kept_in_org = _entitle(db, proven, shared_in_org)
    kept_purchase = _entitle(db, proven, only_here, source="purchase")
    invite = await make_invite(db, world.org)
    invite.resulting_registration_id = reg.id
    await db.commit()
    path = f"{BASE}/registrations/{reg.id}"
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.delete(path, params={"accounts": "keep"})
        assert r.status_code == 409
        assert detail_code(r) == "registration_active"

        r = await client.put(path, json={"status": "disabled"})
        assert r.status_code == 200
        r = await client.delete(path)
        assert r.status_code == 409
        assert detail_code(r) == "accounts_choice_required"
        assert r.json()["detail"]["provisioned_accounts"] == 1
        r = await client.delete(path, params={"accounts": "anonymize"})
        assert r.status_code == 422

        r = await client.delete(path, params={"accounts": "keep"})
        assert r.status_code == 204, r.text
        r = await client.get(path)
        assert r.status_code == 404

    # The connection and everything hanging off it are gone.
    assert (
        await _rows(db, LtiPlatformRegistration, LtiPlatformRegistration.id == reg.id)
        == []
    )
    assert await _rows(db, LtiDeployment, LtiDeployment.registration_id == reg.id) == []
    assert (
        await _rows(db, LtiResourceLink, LtiResourceLink.registration_id == reg.id)
        == []
    )
    assert await _rows(db, LtiUserLink, LtiUserLink.registration_id == reg.id) == []
    assert await _rows(db, LtiGradeSync, LtiGradeSync.user_id == provisioned.id) == []
    assert (
        await _rows(
            db, LtiResourceLinkUser, LtiResourceLinkUser.user_id == provisioned.id
        )
        == []
    )
    # Accounts stay.
    assert len(await _rows(db, User, User.id.in_([provisioned.id, proven.id]))) == 2
    # The foreign connection is untouched.
    assert (
        len(await _rows(db, LtiUserLink, LtiUserLink.registration_id == foreign.id))
        == 1
    )

    attachments = {
        (row.project_id, row.organization_id): row.attached_via
        for row in await _rows(
            db,
            ProjectOrganization,
            ProjectOrganization.project_id.in_(
                [only_here.id, shared_in_org.id, shared_abroad.id, manual.id]
            ),
        )
    }
    assert attachments == {
        (shared_in_org.id, world.org.id): "lti",
        (shared_abroad.id, world.other_org.id): "lti",
        (manual.id, world.org.id): "manual",
    }

    entitlements = {
        row.id: row.revoked_at
        for row in await _rows(
            db,
            MarketplaceEntitlement,
            MarketplaceEntitlement.id.in_(
                [
                    lost_only.id,
                    lost_abroad.id,
                    kept_abroad.id,
                    kept_in_org.id,
                    kept_purchase.id,
                ]
            ),
        )
    }
    assert entitlements[lost_only.id] is not None
    assert entitlements[lost_abroad.id] is not None
    assert entitlements[kept_abroad.id] is None
    assert entitlements[kept_in_org.id] is None
    assert entitlements[kept_purchase.id] is None

    await db.refresh(invite)
    assert invite.resulting_registration_id is None

    events = await _events(db, organization_id=world.org.id)
    assert [e.action for e in events] == [
        "registration_updated",
        "registration_deleted",
    ]
    deleted = events[-1]
    # Earlier events lose the registration id with the row; the delete event
    # carries it in its changes and keeps the name.
    assert all(e.registration_id is None for e in events)
    assert deleted.registration_name == "Old Moodle"
    assert deleted.actor_user_id == world.org_admin.id
    assert deleted.changes["registration_id"] == reg.id
    assert deleted.changes["accounts"] == "keep"
    assert deleted.changes["resource_links"] == 4
    assert deleted.changes["user_links"] == 2
    assert deleted.changes["provisioned_accounts"] == 1
    assert deleted.changes["unlinked_project_ids"] == sorted(
        [only_here.id, shared_abroad.id, manual.id]
    )
    # The manual share is not an LTI attachment and stays.
    assert deleted.changes["detached_project_ids"] == sorted(
        [only_here.id, shared_abroad.id]
    )
    assert deleted.changes["revoked_entitlements"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_deletes_a_disabled_group_connection(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    own = await make_registration(
        async_test_db, world.org, group=world.group_a, status="disabled"
    )
    org_wide = await make_registration(async_test_db, world.org, status="disabled")
    student = await make_user(async_test_db)
    # A linked account that the launch did not create needs no choice.
    await make_user_link(async_test_db, own, student, link_method="email_proof")
    await async_test_db.commit()

    with as_user(world.group_admin):
        r = await async_test_client.delete(f"{BASE}/registrations/{org_wide.id}")
        assert r.status_code == 403
        r = await async_test_client.delete(f"{BASE}/registrations/{own.id}")
        assert r.status_code == 204, r.text
    assert (
        await _rows(
            async_test_db, LtiPlatformRegistration, LtiPlatformRegistration.id == own.id
        )
        == []
    )


# --------------------------------------------------------------------------- #
# Activities
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_resource_links_list(async_test_client, async_test_db):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, group=world.group_a)
    exam = await make_project(
        db, world.contributor, tasks=2, title="Klausur Strafrecht"
    )
    gone = await make_project(db, world.contributor, title="Deleted exam")
    gone.deleted_at = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    graded = await make_resource_link(
        db,
        reg,
        project=exam,
        context_title="A-Kurs",
        resource_title="Klausur 1",
        lineitem_url="https://lms.example/lineitems/1/lineitem",
        ags_scopes=[LINEITEM_SCOPE, SCORE_SCOPE],
        linked_by=world.contributor.id,
        linked_at=now,
        ai_lineitem_status="unavailable",
        ai_lineitem_error="lineitem scope not granted",
    )
    await make_resource_link(
        db,
        reg,
        context_title="B-Kurs",
        resource_title="Offen",
        ags_scopes=[SCORE_SCOPE],
    )
    await make_resource_link(db, reg, project=gone, context_title="C-Kurs")
    learners = [await make_user(db), await make_user(db)]
    for learner in learners:
        await make_participation(db, graded, learner)
    teacher = await make_user(db)
    await make_participation(db, graded, teacher, instructor=True)
    await make_grade_sync(db, graded, learners[0], status="failed")
    await make_grade_sync(db, graded, learners[0], status="synced", kind="ai")
    await make_grade_sync(db, graded, learners[1], status="synced")
    await db.commit()
    path = f"{BASE}/registrations/{reg.id}/resource-links"

    with as_user(world.org_admin):
        r = await async_test_client.get(path)
        assert r.status_code == 200, r.text
        rows = r.json()
    assert [row["context_title"] for row in rows] == ["A-Kurs", "B-Kurs", "C-Kurs"]
    first, unbound, deleted = rows
    assert first["project"] == {
        "id": exam.id,
        "title": "Klausur Strafrecht",
        "task_count": 2,
        "deleted": False,
    }
    assert first["resource_title"] == "Klausur 1"
    assert first["grades_supported"] is True
    assert first["column_management"] is True
    assert first["granted_scopes"] == [LINEITEM_SCOPE, SCORE_SCOPE]
    assert first["ai_lineitem_status"] == "unavailable"
    assert first["ai_lineitem_error"] == "lineitem scope not granted"
    assert first["participant_count"] == 2
    assert first["instructor_count"] == 1
    assert first["last_launch_at"] is not None
    assert first["sync_counts"] == {"failed": 1, "synced": 2}
    assert first["linked_by_display"] == world.contributor.name
    assert first["sync_ai_grades"] is True

    assert unbound["project"] is None
    assert unbound["grades_supported"] is False
    assert unbound["column_management"] is False
    assert unbound["participant_count"] == 0
    assert unbound["sync_counts"] == {}
    assert unbound["linked_by_display"] is None
    assert deleted["project"]["deleted"] is True

    # A group admin of the connection's group sees the same list, with
    # real names (D8).
    with as_user(world.group_admin):
        r = await async_test_client.get(path)
        assert r.status_code == 200
        assert r.json()[0]["linked_by_display"] == world.contributor.name


# --------------------------------------------------------------------------- #
# LMS users
# --------------------------------------------------------------------------- #
async def _seed_user_links(db, world):
    reg = await make_registration(db, world.org, group=world.group_a)
    link = await make_resource_link(db, reg)
    now = datetime.now(timezone.utc)
    teacher = await make_user(db, name="Erika Lehrerin")
    learner = await make_user(db, name="Max Lerner")
    legacy = await make_user(db, name="Alte Verknuepfung")
    legacy.anonymized_at = now
    gone = await make_user(db, name="Geloeste Person")
    teacher_link = await make_user_link(db, reg, teacher, last_launch_at=now)
    teacher_link.claims = {"name": teacher.name, "role": "instructor", "roles": []}
    learner_link = await make_user_link(
        db,
        reg,
        learner,
        link_method="login_proof",
        last_launch_at=now - timedelta(hours=1),
        research_consent_at=now,
    )
    await make_participation(db, link, learner)
    legacy_link = await make_user_link(db, reg, legacy, link_method="legacy_email")
    gone_link = await make_user_link(db, reg, gone, unlinked_at=now)
    await db.commit()
    return reg, {
        "teacher": (teacher, teacher_link),
        "learner": (learner, learner_link),
        "legacy": (legacy, legacy_link),
        "gone": (gone, gone_link),
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_links_show_real_names_to_connection_admins(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    reg, people = await _seed_user_links(async_test_db, world)
    path = f"{BASE}/registrations/{reg.id}/user-links"

    with as_user(world.org_admin):
        r = await async_test_client.get(path)
        assert r.status_code == 200, r.text
        page = r.json()
    assert page["total"] == 4
    assert (page["limit"], page["offset"]) == (50, 0)
    items = page["items"]
    by_user = {item["user_id"]: item for item in items}
    # Most recent launch first; never-launched rows last.
    assert [item["user_id"] for item in items[:2]] == [
        people["teacher"][0].id,
        people["learner"][0].id,
    ]
    teacher, teacher_link = people["teacher"]
    row = by_user[teacher.id]
    assert row["id"] == teacher_link.id
    assert row["sub"] == teacher_link.sub
    assert row["name"] == "Erika Lehrerin"
    assert row["email"] == teacher.email
    assert row["pseudonym"] == teacher.pseudonym
    assert row["role"] == "instructor"
    assert row["link_method"] == "provisioned"
    assert row["provisioned_account"] is True
    assert row["consent_version"] == "lti-2"
    assert row["consent_at"] is not None
    assert "claims" not in row
    learner_row = by_user[people["learner"][0].id]
    assert learner_row["role"] == "learner"
    assert learner_row["provisioned_account"] is False
    assert learner_row["research_consent_at"] is not None
    legacy_row = by_user[people["legacy"][0].id]
    assert legacy_row["role"] is None
    assert legacy_row["anonymized"] is True
    gone_row = by_user[people["gone"][0].id]
    assert gone_row["unlinked_at"] is not None

    # D8: the admin of the connection's group sees the real names too.
    with as_user(world.group_admin):
        r = await async_test_client.get(path)
        assert r.status_code == 200
        items = r.json()["items"]
    assert len(items) == 4
    assert {item["user_id"]: item["name"] for item in items}[teacher.id] == (
        "Erika Lehrerin"
    )
    assert all(item["pseudonym"] for item in items)

    # Plain members and admins of other organizations see nothing at all.
    for outsider in (world.contributor, world.foreign_admin):
        with as_user(outsider):
            r = await async_test_client.get(path)
            assert r.status_code == 403, r.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_links_pagination_and_search(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    reg, people = await _seed_user_links(async_test_db, world)
    path = f"{BASE}/registrations/{reg.id}/user-links"
    client = async_test_client

    async def total(**params):
        r = await client.get(path, params=params)
        assert r.status_code == 200, r.text
        return r.json()["total"]

    with as_user(world.org_admin):
        r = await client.get(path, params={"limit": 2})
        assert len(r.json()["items"]) == 2
        assert r.json()["total"] == 4
        r = await client.get(path, params={"limit": 2, "offset": 2})
        assert len(r.json()["items"]) == 2
        r = await client.get(path, params={"offset": 10})
        assert r.json() == {"items": [], "total": 4, "limit": 50, "offset": 10}
        assert (await client.get(path, params={"limit": 201})).status_code == 422
        assert (await client.get(path, params={"limit": 0})).status_code == 422

        assert await total(q="lehrerin") == 1
        assert await total(q=people["teacher"][0].email) == 1
        assert await total(q=people["learner"][0].pseudonym.lower()) == 1
        assert await total(q=people["legacy"][1].sub) == 1
        # LIKE wildcards are matched literally.
        assert await total(q="%") == 0
        assert await total(q="_") == 0

    with as_user(world.group_admin):
        # The group's admin sees real names, so they can search them.
        assert await total(q="lehrerin") == 1
        assert await total(q=people["teacher"][0].email) == 1
        assert await total(q=people["learner"][0].pseudonym) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unlink_keeps_the_account_and_clears_this_connection(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    other = await make_registration(db, world.org)
    link = await make_resource_link(db, reg)
    other_link = await make_resource_link(db, other)
    provisioned = await make_user(db)
    proven = await make_user(db)
    prov_link = await make_user_link(db, reg, provisioned)
    proof_link = await make_user_link(db, reg, proven, link_method="login_proof")
    foreign_link = await make_user_link(db, other, provisioned)
    await make_grade_sync(db, link, provisioned)
    await make_grade_sync(db, link, provisioned, kind="ai", status="synced")
    kept_sync = await make_grade_sync(db, other_link, provisioned)
    await make_participation(db, link, provisioned)
    kept_participation = await make_participation(db, other_link, provisioned)
    proven_sync = await make_grade_sync(db, link, proven)
    await db.commit()
    base = f"{BASE}/registrations/{reg.id}"
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.delete(f"{base}/user-links/{foreign_link.id}")
        assert r.status_code == 404
        assert detail_code(r) == "user_link_not_found"

        r = await client.delete(f"{base}/user-links/{prov_link.id}")
        assert r.status_code == 204, r.text

        # Provisioned: kept as a tombstone without the claims snapshot and
        # without the consent, so a relaunch asks for it again.
        row = (
            await db.execute(
                select(LtiUserLink)
                .where(LtiUserLink.id == prov_link.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.unlinked_at is not None
        assert row.claims is None
        assert (row.consent_at, row.consent_version, row.research_consent_at) == (
            None,
            None,
            None,
        )
        assert row.user_id == provisioned.id
        remaining = await _rows(
            db, LtiGradeSync, LtiGradeSync.user_id == provisioned.id
        )
        assert [s.id for s in remaining] == [kept_sync.id]
        remaining = await _rows(
            db, LtiResourceLinkUser, LtiResourceLinkUser.user_id == provisioned.id
        )
        assert [p.id for p in remaining] == [kept_participation.id]
        assert await _rows(db, User, User.id == provisioned.id)

        r = await client.get(base)
        assert r.json()["user_link_count"] == 1

        # A second unlink is a no-op.
        r = await client.delete(f"{base}/user-links/{prov_link.id}")
        assert r.status_code == 204

        # A proof link is deleted outright.
        r = await client.delete(f"{base}/user-links/{proof_link.id}")
        assert r.status_code == 204
        assert await _rows(db, LtiUserLink, LtiUserLink.id == proof_link.id) == []
        assert await _rows(db, LtiGradeSync, LtiGradeSync.id == proven_sync.id) == []
        assert await _rows(db, User, User.id == proven.id)

    events = await _events(db, registration_id=reg.id)
    assert [e.action for e in events] == ["user_link_unlinked", "user_link_unlinked"]
    first, second = (e.changes for e in events)
    assert first == {
        "user_link_id": prov_link.id,
        "user_id": provisioned.id,
        "link_method": "provisioned",
        "tombstone": True,
        "grade_syncs_deleted": 2,
        "participations_deleted": 1,
    }
    assert second["tombstone"] is False
    assert second["grade_syncs_deleted"] == 1
    # No personal data in the history.
    assert provisioned.email not in str(first)
    assert provisioned.name not in str(first)


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_events_are_scoped_and_newest_first(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org, group=world.group_a)
    other = await make_registration(async_test_db, world.org)
    await async_test_db.commit()
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.put(f"{BASE}/registrations/{reg.id}", json={"name": "Neu"})
        assert r.status_code == 200
        r = await client.put(
            f"{BASE}/registrations/{reg.id}", json={"status": "disabled"}
        )
        assert r.status_code == 200
        r = await client.put(f"{BASE}/registrations/{other.id}", json={"name": "B"})
        assert r.status_code == 200

        r = await client.get(f"{BASE}/registrations/{reg.id}/events")
        assert r.status_code == 200
        events = r.json()
    assert [e["changes"] for e in events] == [
        {"status": {"old": "active", "new": "disabled"}},
        {"name": {"old": "Seeded Moodle", "new": "Neu"}},
    ]
    assert events[0]["action"] == "registration_updated"
    assert events[0]["actor_kind"] == "user"
    assert events[0]["registration_name"] == "Neu"
    assert events[0]["actor_display"] == world.org_admin.name

    with as_user(world.group_admin):
        r = await client.get(f"{BASE}/registrations/{reg.id}/events")
        assert r.status_code == 200
        assert r.json()[0]["actor_display"] == world.org_admin.name
        r = await client.get(f"{BASE}/registrations/{other.id}/events")
        assert r.status_code == 403

    # At most 100, the newest ones.
    start = datetime.now(timezone.utc)
    for index in range(105):
        async_test_db.add(
            LtiAdminEvent(
                id=str(uuid.uuid4()),
                organization_id=world.org.id,
                registration_id=reg.id,
                registration_name="Neu",
                actor_kind="dynamic_registration",
                action="dynamic_registration_completed",
                changes={"n": index},
                created_at=start + timedelta(minutes=index),
            )
        )
    await async_test_db.commit()
    with as_user(world.org_admin):
        r = await client.get(f"{BASE}/registrations/{reg.id}/events")
        events = r.json()
    assert len(events) == 100
    assert events[0]["changes"] == {"n": 104}
    assert events[0]["actor_display"] is None


# --------------------------------------------------------------------------- #
# Grade transfers
# --------------------------------------------------------------------------- #
async def _seed_transfers(db, world):
    org_wide = await make_registration(db, world.org, name="Org Moodle")
    chair = await make_registration(db, world.org, group=world.group_a, name="Chair")
    exam = await make_project(db, world.org_admin, title="Klausur A")
    chair_exam = await make_project(db, world.contributor, title="Klausur Chair")
    link = await make_resource_link(
        db,
        org_wide,
        project=exam,
        context_title="Kurs A",
        resource_title="Aktivitaet 1",
    )
    chair_link = await make_resource_link(
        db, chair, project=chair_exam, resource_title="Chair Aktivitaet"
    )
    student = await make_user(db, name="Studi Klarname")
    org_sync = await make_grade_sync(db, link, student)
    chair_sync = await make_grade_sync(db, chair_link, student, kind="ai")
    await db.commit()
    return {
        "student": student,
        "exam": exam,
        "org_sync": org_sync,
        "chair_sync": chair_sync,
        "org_wide": org_wide,
        "chair": chair,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_grade_sync_list_has_context_and_follows_the_scope(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    seed = await _seed_transfers(async_test_db, world)
    student = seed["student"]
    params = {"organization_id": world.org.id}
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.get(BASE + "/grade-syncs", params=params)
        assert r.status_code == 200, r.text
        rows = {row["id"]: row for row in r.json()}
    assert set(rows) == {seed["org_sync"].id, seed["chair_sync"].id}
    org_row = rows[seed["org_sync"].id]
    assert org_row["registration_id"] == seed["org_wide"].id
    assert org_row["registration_name"] == "Org Moodle"
    assert org_row["organization_id"] == world.org.id
    assert org_row["context_title"] == "Kurs A"
    assert org_row["resource_title"] == "Aktivitaet 1"
    assert org_row["project_id"] == seed["exam"].id
    assert org_row["project_title"] == "Klausur A"
    assert org_row["student_pseudonym"] == student.pseudonym
    assert org_row["student_name"] == "Studi Klarname"
    assert org_row["kind"] == "final"
    assert org_row["status"] == "failed"
    assert rows[seed["chair_sync"].id]["kind"] == "ai"

    with as_user(world.group_admin):
        r = await client.get(BASE + "/grade-syncs", params=params)
        assert r.status_code == 200
        rows = r.json()
        assert [row["id"] for row in rows] == [seed["chair_sync"].id]
        # D8: real names for the LMS users of the admin's group.
        assert rows[0]["student_name"] == "Studi Klarname"
        assert rows[0]["student_pseudonym"] == student.pseudonym
        r = await client.get(
            BASE + "/grade-syncs",
            params={**params, "project_id": seed["exam"].id},
        )
        assert r.json() == []

        r = await client.post(f"{BASE}/grade-syncs/{seed['org_sync'].id}/retry")
        assert r.status_code == 403
        r = await client.post(f"{BASE}/grade-syncs/{seed['chair_sync'].id}/retry")
        assert r.status_code == 200, r.text
        assert r.json()["student_name"] == "Studi Klarname"
        assert r.json()["status"] == "pending"

    with as_user(world.superadmin):
        r = await client.get(BASE + "/grade-syncs")
        rows = {row["id"]: row for row in r.json()}
        assert rows[seed["org_sync"].id]["student_name"] == "Studi Klarname"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_dispatches_through_the_hook(
    async_test_client, async_test_db, monkeypatch
):
    world = await build_world(async_test_db)
    seed = await _seed_transfers(async_test_db, world)
    sync = seed["org_sync"]
    dispatched = []

    def _dispatch(sync_id):
        dispatched.append(sync_id)
        return True

    monkeypatch.setattr(
        extensions,
        "_extended",
        FakeExtended({"dispatch_lti_grade_sync": _dispatch}),
    )
    path = f"{BASE}/grade-syncs/{sync.id}/retry"

    with as_user(world.org_admin):
        r = await async_test_client.post(path)
        assert r.status_code == 200, r.text
        body = r.json()
    assert dispatched == [sync.id]
    assert body["dispatched"] is True
    assert body["status"] == "pending"
    assert body["attempts"] == 0
    assert body["last_error"] is None
    assert body["student_name"] == "Studi Klarname"
    assert body["resource_title"] == "Aktivitaet 1"

    row = (
        await async_test_db.execute(
            select(LtiGradeSync)
            .where(LtiGradeSync.id == sync.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert (row.status, row.attempts, row.last_error) == ("pending", 0, None)

    events = await _events(async_test_db, registration_id=seed["org_wide"].id)
    assert [e.action for e in events] == ["grade_sync_retried"]
    assert events[0].registration_name == "Org Moodle"
    assert events[0].changes == {
        "grade_sync_id": sync.id,
        "kind": "final",
        "previous_status": "failed",
        "previous_attempts": 3,
    }

    # A failing dispatch still resets the row; the sweep sends it later.
    def _broken(sync_id):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        extensions, "_extended", FakeExtended({"dispatch_lti_grade_sync": _broken})
    )
    with as_user(world.org_admin):
        r = await async_test_client.post(path)
        assert r.status_code == 200
        assert r.json()["dispatched"] is False
        assert r.json()["status"] == "pending"
