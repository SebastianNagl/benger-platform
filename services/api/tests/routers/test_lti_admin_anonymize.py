"""LMS admins anonymize the accounts their connections created (D16).

``GET|POST /api/admin/lti/registrations/{rid}/user-links/{lid}/anonymization``
and ``.../anonymize``, the connection-wide preview
``GET /registrations/{rid}/anonymization`` and
``DELETE /registrations/{rid}?accounts=anonymize``: who may act (org admins,
group admins for their group's connections, superadmins; everyone else is
refused), every blocker and warning, the stale-link guard, the audit row
without personal data and the bulk delete with its report. The scrub itself
is covered in ``tests/integration/test_user_anonymization.py``.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import extensions
from models import (
    LtiAdminEvent,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiResourceLinkUser,
    LtiUserLink,
    MarketplaceOrder,
    OrganizationRole,
    StudentSubscription,
    User,
)
from services.user_anonymization import ANONYMIZED_NAME
from tests.fixtures.lti_admin_world import (
    FakeExtended,
    add_group_member,
    add_member,
    as_user,
    build_world,
    detail_code,
    make_grade_sync,
    make_org,
    make_participation,
    make_project,
    make_registration,
    make_resource_link,
    make_user,
    make_user_link,
)

BASE = "/api/admin/lti"


@pytest.fixture(autouse=True)
def _community_edition(monkeypatch):
    monkeypatch.setattr(extensions, "_extended", None)


@pytest.fixture
def revoked(monkeypatch):
    """Records the post-commit Redis token cleanup calls."""
    calls = []
    monkeypatch.setattr(
        "routers.lti_admin.revoke_lms_link_tokens", lambda ids: calls.append(list(ids))
    )
    return calls


def _use_hook(monkeypatch, policy):
    monkeypatch.setattr(
        extensions,
        "_extended",
        FakeExtended({"lti_anonymization_policy": policy}),
    )


async def _fresh(db, model, *conditions):
    stmt = select(model).where(*conditions).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().all()


async def _user(db, user_id) -> User:
    return (await _fresh(db, User, User.id == user_id))[0]


async def _student(db, reg, *, org=None, link_method="provisioned", name=None):
    """An LMS account of ``reg`` with the memberships a launch grants."""
    student = await make_user(db, name=name)
    if org is not None:
        await add_member(db, student, org, OrganizationRole.ANNOTATOR)
    link = await make_user_link(db, reg, student, link_method=link_method)
    await db.commit()
    return student, link


def _paths(reg_id, link_id):
    base = f"{BASE}/registrations/{reg_id}/user-links/{link_id}"
    return f"{base}/anonymization", f"{base}/anonymize"


async def _anonymize(client, reg_id, link_id, user_id):
    _preview, action = _paths(reg_id, link_id)
    return await client.post(action, json={"expected_user_id": user_id})


def _blockers(response):
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "anonymization_blocked"
    return detail["blockers"]


# --------------------------------------------------------------------------- #
# Who may act
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_previews_and_anonymizes(
    async_test_client, async_test_db, revoked
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    project = await make_project(db, world.org_admin)
    activity = await make_resource_link(db, reg, project=project)
    student, link = await _student(db, reg, org=world.org, name="Erika Muster")
    await make_grade_sync(db, activity, student)
    await make_participation(db, activity, student)
    await db.commit()
    old_email = student.email
    old_pseudonym = student.pseudonym
    preview_path, _action = _paths(reg.id, link.id)

    with as_user(world.org_admin):
        preview = await async_test_client.get(preview_path)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["user_link_id"] == link.id
        assert body["registration_id"] == reg.id
        assert body["eligible"] is True
        assert body["blockers"] == [] and body["warnings"] == []
        assert body["user"] == {
            "id": student.id,
            "display": "Erika Muster",
            "pseudonym": old_pseudonym,
            "name": "Erika Muster",
            "email": old_email,
        }
        assert body["keeps"] == {
            "annotations": 0,
            "task_evaluations": 0,
            "projects_created": 0,
        }
        assert body["removes"] == {
            "lti_user_links": 1,
            "lti_grade_syncs": 1,
            "sessions": 0,
            "memberships": 1,
        }

        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user_id"] == student.id
    assert data["anonymized"] is True
    assert data["pseudonym"].startswith("Anonym-")
    assert data["pseudonym"] != old_pseudonym
    assert data["removed"]["lti_user_links"] == 1
    assert data["removed"]["lti_grade_syncs"] == 1
    assert revoked == [[student.id]]

    user = await _user(db, student.id)
    assert user.name == ANONYMIZED_NAME and user.is_active is False
    assert user.pseudonym == data["pseudonym"]
    assert await _fresh(db, LtiUserLink, LtiUserLink.user_id == student.id) == []
    assert await _fresh(db, LtiGradeSync, LtiGradeSync.user_id == student.id) == []
    # The activity still counts the participant.
    assert len(
        await _fresh(db, LtiResourceLinkUser, LtiResourceLinkUser.user_id == student.id)
    ) == 1

    events = await _fresh(db, LtiAdminEvent, LtiAdminEvent.registration_id == reg.id)
    assert [e.action for e in events] == ["user_anonymized"]
    event = events[0]
    assert event.actor_user_id == world.org_admin.id
    assert event.organization_id == world.org.id
    assert event.changes["user_id"] == student.id
    assert event.changes["user_link_id"] == link.id
    assert event.changes["reason"] == "lti_admin"
    dumped = repr(event.changes)
    assert old_email not in dumped and "Erika" not in dumped
    assert link.sub not in dumped

    # The account is gone from the connection's account list; a second
    # attempt finds no link any more.
    with as_user(world.org_admin):
        listing = await async_test_client.get(
            f"{BASE}/registrations/{reg.id}/user-links"
        )
        assert listing.json()["total"] == 0
        again = await _anonymize(async_test_client, reg.id, link.id, student.id)
        assert again.status_code == 404
        assert detail_code(again) == "user_link_not_found"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "who", ["foreign_admin", "contributor", "member", "stranger", "group_admin"]
)
async def test_others_are_refused(async_test_client, async_test_db, revoked, who):
    db = async_test_db
    world = await build_world(db)
    # An org-wide connection: group admins do not manage it.
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    preview_path, _action = _paths(reg.id, link.id)

    with as_user(getattr(world, who)):
        preview = await async_test_client.get(preview_path)
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert preview.status_code == 403
    assert response.status_code == 403
    assert detail_code(response) == "scope_admin_required"
    assert (await _user(db, student.id)).anonymized_at is None
    assert revoked == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_anonymizes_on_their_group_connection(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, group=world.group_a)
    student, link = await _student(db, reg, org=world.org)
    await add_group_member(db, student, world.group_a, admin=False)
    other_reg = await make_registration(db, world.org, group=world.group_b)
    other, other_link = await _student(db, other_reg, org=world.org)
    await db.commit()

    with as_user(world.group_admin):
        preview = await async_test_client.get(_paths(reg.id, link.id)[0])
        assert preview.json()["user"]["name"] == student.name
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)
        assert response.status_code == 200, response.text
        # Group B is outside their scope.
        refused = await _anonymize(
            async_test_client, other_reg.id, other_link.id, other.id
        )
        assert refused.status_code == 403

    assert (await _user(db, student.id)).anonymized_at is not None
    assert (await _user(db, other.id)).anonymized_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_superadmin_anonymizes_on_any_connection(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.other_org)
    student, link = await _student(db, reg, org=world.other_org)

    with as_user(world.superadmin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert response.status_code == 200, response.text
    assert (await _user(db, student.id)).anonymized_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_protected_org_connections_stay_superadmin_only(
    async_test_client, async_test_db, monkeypatch
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    monkeypatch.setattr(
        extensions,
        "_extended",
        FakeExtended({"lti_protected_org_ids": lambda _db: {world.org.id}}),
    )

    with as_user(world.org_admin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert response.status_code == 403
    assert detail_code(response) == "connection_protected"


# --------------------------------------------------------------------------- #
# Blockers and warnings
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_self_and_superadmin_targets_are_blocked(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    own_link = await make_user_link(db, reg, world.org_admin)
    admin_target = await make_user(db, superadmin=True)
    admin_link = await make_user_link(db, reg, admin_target)
    await db.commit()

    with as_user(world.org_admin):
        own = await _anonymize(
            async_test_client, reg.id, own_link.id, world.org_admin.id
        )
        assert _blockers(own) == ["self"]
        preview = await async_test_client.get(_paths(reg.id, admin_link.id)[0])
        assert preview.json()["eligible"] is False
        assert preview.json()["blockers"] == ["superadmin"]
        target = await _anonymize(
            async_test_client, reg.id, admin_link.id, admin_target.id
        )
        assert _blockers(target) == ["superadmin"]

    assert (await _user(db, world.org_admin.id)).anonymized_at is None
    assert (await _user(db, admin_target.id)).is_active is True
    assert await _fresh(db, LtiAdminEvent, LtiAdminEvent.registration_id == reg.id) == []


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["login_proof", "email_proof", "legacy_email", None])
async def test_accounts_linked_by_proof_are_only_unlinked(
    async_test_client, async_test_db, method
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org, link_method=method)

    with as_user(world.org_admin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert _blockers(response) == ["not_provisioned"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tombstone_of_an_unlinked_provisioned_account_can_be_anonymized(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)

    with as_user(world.org_admin):
        unlinked = await async_test_client.delete(
            f"{BASE}/registrations/{reg.id}/user-links/{link.id}"
        )
        assert unlinked.status_code == 204
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert response.status_code == 200, response.text
    assert await _fresh(db, LtiUserLink, LtiUserLink.id == link.id) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_is_a_warning_not_a_blocker(async_test_client, async_test_db):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    student.hashed_password = "bcrypt-hash"
    student.password_set = True
    await db.commit()

    with as_user(world.org_admin):
        preview = await async_test_client.get(_paths(reg.id, link.id)[0])
        assert preview.json()["eligible"] is True
        assert preview.json()["warnings"] == ["has_password"]
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == ["has_password"]
    user = await _user(db, student.id)
    assert user.hashed_password is None and user.password_set is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_link_on_another_orgs_connection_blocks(
    async_test_client, async_test_db
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    foreign_reg = await make_registration(db, world.other_org)
    student, link = await _student(db, reg, org=world.org)
    # An unlinked (tombstoned) identity elsewhere counts as well.
    await make_user_link(
        db,
        foreign_reg,
        student,
        link_method="login_proof",
        unlinked_at=datetime.now(timezone.utc),
    )
    await db.commit()

    with as_user(world.org_admin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)
    assert _blockers(response) == ["linked_elsewhere"]

    # The superadmin acting through this org's panel keeps the same scope.
    with as_user(world.superadmin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)
    assert _blockers(response) == ["linked_elsewhere"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_scope_blockers(async_test_client, async_test_db):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, group=world.group_a)
    org_wide = await make_registration(db, world.org)

    # Linked on an org-wide connection of the same org as well.
    wide, wide_link = await _student(db, reg, org=world.org)
    await make_user_link(db, org_wide, wide)
    # Member of a group the group admin does not administer.
    other_group, other_group_link = await _student(db, reg, org=world.org)
    await add_group_member(db, other_group, world.group_b, admin=False)
    # An org admin who launched through the chair's connection.
    admin, admin_link = await _student(db, reg)
    await add_member(db, admin, world.org, OrganizationRole.ORG_ADMIN)
    await db.commit()

    with as_user(world.group_admin):
        assert _blockers(
            await _anonymize(async_test_client, reg.id, wide_link.id, wide.id)
        ) == ["linked_elsewhere"]
        assert _blockers(
            await _anonymize(
                async_test_client, reg.id, other_group_link.id, other_group.id
            )
        ) == ["member_elsewhere"]
        assert _blockers(
            await _anonymize(async_test_client, reg.id, admin_link.id, admin.id)
        ) == ["target_is_org_admin"]

    # The org admin covers all of it.
    with as_user(world.org_admin):
        for user, link in (
            (wide, wide_link),
            (other_group, other_group_link),
            (admin, admin_link),
        ):
            response = await _anonymize(async_test_client, reg.id, link.id, user.id)
            assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memberships_elsewhere(
    async_test_client, async_test_db, monkeypatch, revoked
):
    db = async_test_db
    world = await build_world(db)
    implicit_org = await make_org(db)
    reg = await make_registration(db, world.org)

    staff, staff_link = await _student(db, reg, org=world.org)
    await add_member(db, staff, world.other_org, OrganizationRole.CONTRIBUTOR)
    annotator, annotator_link = await _student(db, reg, org=world.org)
    await add_member(db, annotator, world.other_org, OrganizationRole.ANNOTATOR)
    implicit, implicit_link = await _student(db, reg, org=world.org)
    await add_member(db, implicit, implicit_org, OrganizationRole.ANNOTATOR)
    implicit_staff, implicit_staff_link = await _student(db, reg, org=world.org)
    await add_member(db, implicit_staff, implicit_org, OrganizationRole.CONTRIBUTOR)
    removed, removed_link = await _student(db, reg, org=world.org)
    await add_member(
        db, removed, world.other_org, OrganizationRole.CONTRIBUTOR, active=False
    )
    await db.commit()
    seen = []

    def policy(_db, user_id):
        seen.append(user_id)
        return {"implicit_org_ids": {implicit_org.id}, "blockers": []}

    _use_hook(monkeypatch, policy)

    with as_user(world.org_admin):
        for user, link in (
            (staff, staff_link),
            (annotator, annotator_link),
            (implicit_staff, implicit_staff_link),
        ):
            response = await _anonymize(async_test_client, reg.id, link.id, user.id)
            assert _blockers(response) == ["member_elsewhere"], user.id
        for user, link in ((implicit, implicit_link), (removed, removed_link)):
            response = await _anonymize(async_test_client, reg.id, link.id, user.id)
            assert response.status_code == 200, response.text

    assert implicit.id in seen
    assert (await _user(db, staff.id)).anonymized_at is None
    assert (await _user(db, implicit.id)).anonymized_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("record", ["subscription", "order"])
async def test_payment_records_block(async_test_client, async_test_db, record):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    if record == "subscription":
        db.add(
            StudentSubscription(
                id=str(uuid.uuid4()),
                user_id=student.id,
                provider_customer_id="cus_1",
                status="canceled",
            )
        )
    else:
        db.add(
            MarketplaceOrder(
                id=str(uuid.uuid4()),
                buyer_user_id=student.id,
                amount_cents=900,
                status="paid",
            )
        )
    await db.commit()

    with as_user(world.org_admin):
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)

    assert _blockers(response) == ["has_payment_records"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extended_policy_blockers(async_test_client, async_test_db, monkeypatch):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    _use_hook(
        monkeypatch,
        lambda _db, _uid: {"implicit_org_ids": set(), "blockers": ["active_subscription"]},
    )

    with as_user(world.org_admin):
        preview = await async_test_client.get(_paths(reg.id, link.id)[0])
        assert preview.json()["blockers"] == ["active_subscription"]
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)
        assert _blockers(response) == ["active_subscription"]

        def broken(_db, _uid):
            raise RuntimeError("billing down")

        _use_hook(monkeypatch, broken)
        response = await _anonymize(async_test_client, reg.id, link.id, student.id)
        assert _blockers(response) == ["policy_unavailable"]

    assert (await _user(db, student.id)).anonymized_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stale_or_foreign_link_is_refused(async_test_client, async_test_db):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org)
    sibling = await make_registration(db, world.org)
    student, link = await _student(db, reg, org=world.org)
    other, other_link = await _student(db, sibling, org=world.org)

    with as_user(world.org_admin):
        changed = await _anonymize(async_test_client, reg.id, link.id, other.id)
        assert changed.status_code == 409
        assert detail_code(changed) == "link_changed"

        # A link of another connection is not found through this one.
        wrong = await _anonymize(async_test_client, reg.id, other_link.id, other.id)
        assert wrong.status_code == 404
        assert detail_code(wrong) == "user_link_not_found"
        missing = await async_test_client.get(_paths(reg.id, "nope")[0])
        assert missing.status_code == 404

        invalid = await async_test_client.post(_paths(reg.id, link.id)[1], json={})
        assert invalid.status_code == 422

    assert (await _user(db, student.id)).anonymized_at is None
    assert (await _user(db, other.id)).anonymized_at is None


# --------------------------------------------------------------------------- #
# Deleting a connection with accounts=anonymize
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_with_anonymize_reports_skipped_accounts(
    async_test_client, async_test_db, revoked
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, name="Old Moodle")
    foreign = await make_registration(db, world.other_org)
    project = await make_project(db, world.org_admin)
    activity = await make_resource_link(db, reg, project=project)

    plain, _plain_link = await _student(db, reg, org=world.org, name="Anna Plain")
    await make_participation(db, activity, plain)
    with_password, _pw_link = await _student(db, reg, org=world.org)
    with_password.hashed_password = "bcrypt-hash"
    unlinked, unlinked_link = await _student(db, reg, org=world.org)
    elsewhere, elsewhere_link = await _student(db, reg, org=world.org, name="Ben Else")
    await make_user_link(db, foreign, elsewhere)
    proven, _proven_link = await _student(
        db, reg, org=world.org, link_method="login_proof"
    )
    own_link = await make_user_link(db, reg, world.org_admin)
    await db.commit()
    path = f"{BASE}/registrations/{reg.id}"
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.delete(f"{path}/user-links/{unlinked_link.id}")
        assert r.status_code == 204
        r = await client.put(path, json={"status": "disabled"})
        assert r.status_code == 200

        preview = await client.get(f"{path}/anonymization")
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["registration_id"] == reg.id
        assert body["provisioned_accounts"] == 5
        assert body["eligible_accounts"] == 3
        assert body["warnings"] == {"has_password": 1}
        skipped = {item["user_id"]: item for item in body["skipped"]}
        assert skipped[elsewhere.id]["blockers"] == ["linked_elsewhere"]
        assert skipped[elsewhere.id]["display"] == "Ben Else"
        assert skipped[elsewhere.id]["user_link_id"] == elsewhere_link.id
        assert skipped[world.org_admin.id]["blockers"] == ["self"]
        assert skipped[world.org_admin.id]["user_link_id"] == own_link.id
        assert set(skipped) == {elsewhere.id, world.org_admin.id}
        # Previewing writes nothing.
        assert (await _user(db, plain.id)).anonymized_at is None

        r = await client.delete(path, params={"accounts": "anonymize"})
        assert r.status_code == 200, r.text
        report = r.json()
        r = await client.get(path)
        assert r.status_code == 404

    assert report["registration_id"] == reg.id
    assert report["deleted"] is True
    assert report["anonymized_accounts"] == 3
    assert set(report["anonymized_user_ids"]) == {
        plain.id,
        with_password.id,
        unlinked.id,
    }
    assert {item["user_id"] for item in report["skipped"]} == {
        elsewhere.id,
        world.org_admin.id,
    }
    assert revoked == [report["anonymized_user_ids"]]

    for user_id in report["anonymized_user_ids"]:
        user = await _user(db, user_id)
        assert user.anonymized_at is not None and user.name == ANONYMIZED_NAME
    # Skipped and proof-linked accounts stay as they were.
    for user_id in (elsewhere.id, proven.id, world.org_admin.id):
        user = await _user(db, user_id)
        assert user.anonymized_at is None and user.is_active is True
    # The skipped account keeps its link on the other org's connection.
    assert len(await _fresh(db, LtiUserLink, LtiUserLink.user_id == elsewhere.id)) == 1
    assert (
        await _fresh(
            db, LtiPlatformRegistration, LtiPlatformRegistration.id == reg.id
        )
        == []
    )

    events = await _fresh(
        db, LtiAdminEvent, LtiAdminEvent.organization_id == world.org.id
    )
    by_action = {}
    for event in events:
        by_action.setdefault(event.action, []).append(event)
    anonymized_events = by_action["user_anonymized"]
    assert {e.changes["user_id"] for e in anonymized_events} == set(
        report["anonymized_user_ids"]
    )
    for event in anonymized_events:
        assert event.registration_name == "Old Moodle"
        assert event.changes["registration_id"] == reg.id
        assert event.changes["reason"] == "registration_deleted"
    deleted = by_action["registration_deleted"][0]
    assert deleted.changes["accounts"] == "anonymize"
    assert deleted.changes["anonymized_accounts"] == 3
    assert sorted(
        (item["user_id"], item["blockers"])
        for item in deleted.changes["skipped_accounts"]
    ) == sorted(
        [(elsewhere.id, ["linked_elsewhere"]), (world.org_admin.id, ["self"])]
    )
    assert "Anna" not in repr(deleted.changes) and "Ben" not in repr(deleted.changes)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_delete_with_anonymize_uses_their_scope(
    async_test_client, async_test_db, revoked
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, group=world.group_a, status="disabled")
    inside, _link = await _student(db, reg, org=world.org)
    outside, _outside_link = await _student(db, reg, org=world.org)
    await add_group_member(db, outside, world.group_b, admin=False)
    await db.commit()
    path = f"{BASE}/registrations/{reg.id}"

    with as_user(world.group_admin):
        preview = await async_test_client.get(f"{path}/anonymization")
        assert preview.json()["eligible_accounts"] == 1
        r = await async_test_client.delete(path, params={"accounts": "anonymize"})

    assert r.status_code == 200, r.text
    assert r.json()["anonymized_user_ids"] == [inside.id]
    assert [item["blockers"] for item in r.json()["skipped"]] == [["member_elsewhere"]]
    assert (await _user(db, outside.id)).anonymized_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_keep_still_answers_204_and_scope_applies_to_the_preview(
    async_test_client, async_test_db, revoked
):
    db = async_test_db
    world = await build_world(db)
    reg = await make_registration(db, world.org, status="disabled")
    student, _link = await _student(db, reg, org=world.org)
    path = f"{BASE}/registrations/{reg.id}"

    with as_user(world.foreign_admin):
        assert (await async_test_client.get(f"{path}/anonymization")).status_code == 403
        r = await async_test_client.delete(path, params={"accounts": "anonymize"})
        assert r.status_code == 403

    with as_user(world.org_admin):
        r = await async_test_client.delete(path, params={"accounts": "keep"})
    assert r.status_code == 204
    assert r.content == b""
    assert revoked == []
    user = await _user(db, student.id)
    assert user.anonymized_at is None and user.is_active is True
