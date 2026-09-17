"""Integration tests for the LMS connection admin API (/api/admin/lti).

Drives the platform-owned persistence CRUD through the real async HTTP stack:
who may manage which connection (superadmin, org admin, group admin, other
roles, protected orgs), the registration round-trip incl. deployments,
(issuer, client_id) uniqueness without leaking the owner, tool host
validation and the URLs built from it, invites, and the grade-sync outbox
filters. Deletion, activities, LMS users, history and retry dispatch live in
``test_lti_admin_operations.py``. The LTI protocol itself
(login/launch/AGS) lives in ``benger_extended`` and is out of scope here.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import extensions
from models import (
    LtiAdminEvent,
    LtiDeployment,
    LtiPlatformRegistration,
    LtiRegistrationInvite,
)
from tests.fixtures.lti_admin_world import (
    MAIN_URL,
    STUDENT_URL,
    FakeExtended,
    as_user,
    build_world,
    detail_code,
    make_grade_sync,
    make_group,
    make_invite,
    make_org,
    make_project,
    make_registration,
    make_resource_link,
    make_user,
    make_user_link,
    registration_payload,
    set_tool_host_env,
)

BASE = "/api/admin/lti"


@pytest.fixture(autouse=True)
def _community_edition_with_two_hosts(monkeypatch):
    # Hooks are switched on per test; by default none are loaded.
    monkeypatch.setattr(extensions, "_extended", None)
    set_tool_host_env(monkeypatch)


async def _events(db, **filters):
    stmt = (
        select(LtiAdminEvent)
        .order_by(LtiAdminEvent.created_at)
        .execution_options(populate_existing=True)
    )
    for field, value in filters.items():
        stmt = stmt.where(getattr(LtiAdminEvent, field) == value)
    return (await db.execute(stmt)).scalars().all()


# --------------------------------------------------------------------------- #
# Who may manage what
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["stranger", "member", "contributor"])
async def test_non_admins_forbidden_everywhere(async_test_client, async_test_db, who):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org, group=world.group_a)
    await async_test_db.commit()
    client = async_test_client
    org_id = world.org.id

    with as_user(getattr(world, who)):
        # Lists need an organization for non-superadmins.
        for path in ("/registrations", "/registrations/invites", "/grade-syncs"):
            r = await client.get(BASE + path)
            assert r.status_code == 422, (path, r.text)
            assert detail_code(r) == "organization_id_required"
            r = await client.get(BASE + path, params={"organization_id": org_id})
            assert r.status_code == 403, (path, r.text)
            assert detail_code(r) == "scope_admin_required"

        r = await client.post(
            BASE + "/registrations", json=registration_payload(org_id)
        )
        assert r.status_code == 403
        r = await client.post(
            BASE + "/registrations",
            json=registration_payload(org_id, group_id=world.group_a.id),
        )
        assert r.status_code == 403
        r = await client.post(
            BASE + "/registrations/invites", json={"organization_id": org_id}
        )
        assert r.status_code == 403
        r = await client.get(f"{BASE}/registrations/{reg.id}")
        assert r.status_code == 403
        r = await client.put(f"{BASE}/registrations/{reg.id}", json={"name": "x"})
        assert r.status_code == 403

    # Signed-in users may read the public tool host list.
    with as_user(getattr(world, who)):
        r = await client.get(BASE + "/tool-hosts")
        assert r.status_code == 200


async def _seed_connection(db, world, *, group=None):
    """A connection with one of everything an object endpoint touches."""
    reg = await make_registration(db, world.org, group=group)
    project = await make_project(db, world.org_admin)
    link = await make_resource_link(db, reg, project=project)
    student = await make_user(db)
    user_link = await make_user_link(db, reg, student)
    sync = await make_grade_sync(db, link, student)
    invite = await make_invite(db, world.org, group=group)
    await db.commit()
    return {
        "reg": reg.id,
        "user_link": user_link.id,
        "sync": sync.id,
        "invite": invite.id,
    }


def _object_requests(ids):
    reg = ids["reg"]
    dep = ids["deployment"]
    return [
        ("GET", f"/registrations/{reg}", None),
        ("PUT", f"/registrations/{reg}", {"name": "Hijacked"}),
        ("DELETE", f"/registrations/{reg}?accounts=keep", None),
        ("POST", f"/registrations/{reg}/deployments", {"deployment_id": "x"}),
        ("PATCH", f"/registrations/{reg}/deployments/{dep}", {"status": "disabled"}),
        ("DELETE", f"/registrations/{reg}/deployments/{dep}", None),
        ("GET", f"/registrations/{reg}/tool-config", None),
        ("GET", f"/registrations/{reg}/resource-links", None),
        ("GET", f"/registrations/{reg}/user-links", None),
        ("DELETE", f"/registrations/{reg}/user-links/{ids['user_link']}", None),
        ("GET", f"/registrations/{reg}/events", None),
        ("POST", f"/grade-syncs/{ids['sync']}/retry", None),
        ("DELETE", f"/registrations/invites/{ids['invite']}", None),
    ]


async def _send(client, method, path, body):
    return await client.request(method, BASE + path, json=body)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_foreign_org_admin_403_on_every_object_endpoint(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    ids = await _seed_connection(async_test_db, world)
    ids["deployment"] = (
        await async_test_db.execute(
            select(LtiDeployment.id).where(LtiDeployment.registration_id == ids["reg"])
        )
    ).scalar_one()

    with as_user(world.foreign_admin):
        for method, path, body in _object_requests(ids):
            r = await _send(async_test_client, method, path, body)
            assert r.status_code == 403, (method, path, r.status_code, r.text)
            assert detail_code(r) == "scope_admin_required", (method, path)
        r = await async_test_client.get(
            BASE + "/registrations", params={"organization_id": world.org.id}
        )
        assert r.status_code == 403
        r = await async_test_client.post(
            BASE + "/registrations", json=registration_payload(world.org.id)
        )
        assert r.status_code == 403

    # Nothing changed.
    reg = await async_test_db.get(LtiPlatformRegistration, ids["reg"])
    assert reg is not None and reg.name == "Seeded Moodle"
    assert await _events(async_test_db, organization_id=world.org.id) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_manages_only_their_groups(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    org_wide = await make_registration(async_test_db, world.org, name="Org-wide")
    other_group = await make_registration(
        async_test_db, world.org, group=world.group_b, name="Chair B"
    )
    await make_invite(async_test_db, world.org)
    await async_test_db.commit()
    client = async_test_client
    org_id = world.org.id

    with as_user(world.group_admin):
        # Creating needs one of their groups.
        r = await client.post(
            BASE + "/registrations", json=registration_payload(org_id)
        )
        assert r.status_code == 403
        r = await client.post(
            BASE + "/registrations",
            json=registration_payload(org_id, group_id=world.group_b.id),
        )
        assert r.status_code == 403
        r = await client.post(
            BASE + "/registrations",
            json=registration_payload(org_id, group_id=world.group_a.id),
        )
        assert r.status_code == 201, r.text
        own = r.json()
        assert own["group_id"] == world.group_a.id
        assert own["status"] == "active"

        # The list shows only their groups' connections.
        r = await client.get(
            BASE + "/registrations", params={"organization_id": org_id}
        )
        assert r.status_code == 200
        assert [reg["id"] for reg in r.json()] == [own["id"]]

        # Other connections of the org stay closed.
        for reg in (org_wide, other_group):
            r = await client.get(f"{BASE}/registrations/{reg.id}")
            assert r.status_code == 403

        # Own connection: read, edit, but no widening to the whole org or to
        # a group they do not administer.
        r = await client.get(f"{BASE}/registrations/{own['id']}")
        assert r.status_code == 200
        r = await client.put(
            f"{BASE}/registrations/{own['id']}", json={"name": "Chair A Moodle"}
        )
        assert r.status_code == 200, r.text
        r = await client.put(
            f"{BASE}/registrations/{own['id']}", json={"group_id": None}
        )
        assert r.status_code == 403
        r = await client.put(
            f"{BASE}/registrations/{own['id']}", json={"group_id": world.group_b.id}
        )
        assert r.status_code == 403

        # Invites follow the same rule; the list hides the org-wide invite.
        r = await client.post(
            BASE + "/registrations/invites", json={"organization_id": org_id}
        )
        assert r.status_code == 403
        r = await client.post(
            BASE + "/registrations/invites",
            json={"organization_id": org_id, "group_id": world.group_a.id},
        )
        assert r.status_code == 201, r.text
        invite_id = r.json()["id"]
        r = await client.get(
            BASE + "/registrations/invites", params={"organization_id": org_id}
        )
        assert [row["id"] for row in r.json()] == [invite_id]

        # Another org is out of reach entirely.
        r = await client.get(
            BASE + "/registrations", params={"organization_id": world.other_org.id}
        )
        assert r.status_code == 403

    # The org admin sees all of it.
    with as_user(world.org_admin):
        r = await client.get(
            BASE + "/registrations", params={"organization_id": org_id}
        )
        assert {reg["id"] for reg in r.json()} == {
            own["id"],
            org_wide.id,
            other_group.id,
        }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_admin_on_inactive_group_is_refused(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    world.group_a.is_active = False
    await async_test_db.commit()

    with as_user(world.group_admin):
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, group_id=world.group_a.id),
        )
        assert r.status_code == 403
    with as_user(world.org_admin):
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, group_id=world.group_a.id),
        )
        assert r.status_code == 400
        assert detail_code(r) == "group_inactive"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_instructor_role_cap_for_group_admins(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    client = async_test_client
    group_payload = lambda **kw: registration_payload(  # noqa: E731
        world.org.id, group_id=world.group_a.id, **kw
    )

    # A contributor group admin: contributor and none, never org_admin.
    with as_user(world.group_admin):
        r = await client.post(
            BASE + "/registrations", json=group_payload(instructor_org_role="org_admin")
        )
        assert r.status_code == 403
        assert detail_code(r) == "instructor_role_cap"
        assert r.json()["detail"]["max_role"] == "contributor"
        r = await client.post(BASE + "/registrations", json=group_payload())
        assert r.status_code == 201
        assert r.json()["instructor_org_role"] == "contributor"
        reg_id = r.json()["id"]
        r = await client.put(
            f"{BASE}/registrations/{reg_id}", json={"instructor_org_role": "org_admin"}
        )
        assert r.status_code == 403
        r = await client.put(
            f"{BASE}/registrations/{reg_id}", json={"instructor_org_role": "none"}
        )
        assert r.status_code == 200
        assert r.json()["instructor_org_role"] == "none"

    # An annotator group admin: only none. The default is capped instead of
    # refused; an explicit contributor is refused.
    with as_user(world.annotator_group_admin):
        r = await client.post(
            BASE + "/registrations",
            json=group_payload(instructor_org_role="contributor"),
        )
        assert r.status_code == 403
        assert r.json()["detail"]["max_role"] == "none"
        r = await client.post(BASE + "/registrations", json=group_payload())
        assert r.status_code == 201, r.text
        assert r.json()["instructor_org_role"] == "none"
        capped_id = r.json()["id"]
        r = await client.put(
            f"{BASE}/registrations/{capped_id}",
            json={"instructor_org_role": "contributor"},
        )
        assert r.status_code == 403

    # An org admin set contributor on a chair connection; the annotator
    # group admin can still edit other fields and resend the same role.
    with as_user(world.org_admin):
        r = await client.put(
            f"{BASE}/registrations/{capped_id}",
            json={"instructor_org_role": "org_admin"},
        )
        assert r.status_code == 200
    with as_user(world.annotator_group_admin):
        r = await client.put(
            f"{BASE}/registrations/{capped_id}",
            json={"name": "Renamed", "instructor_org_role": "org_admin"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_protected_org_connections_are_superadmin_only(
    async_test_client, async_test_db, monkeypatch
):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org)
    await async_test_db.commit()
    monkeypatch.setattr(
        extensions,
        "_extended",
        FakeExtended({"lti_protected_org_ids": lambda db: {world.org.id}}),
    )
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.get(
            BASE + "/registrations", params={"organization_id": world.org.id}
        )
        assert r.status_code == 403
        assert detail_code(r) == "connection_protected"
        r = await client.post(
            BASE + "/registrations", json=registration_payload(world.org.id)
        )
        assert r.status_code == 403
        r = await client.get(f"{BASE}/registrations/{reg.id}")
        assert r.status_code == 403
        assert detail_code(r) == "connection_protected"
    with as_user(world.group_admin):
        r = await client.post(
            BASE + "/registrations/invites",
            json={"organization_id": world.org.id, "group_id": world.group_a.id},
        )
        assert r.status_code == 403
    with as_user(world.superadmin):
        r = await client.get(f"{BASE}/registrations/{reg.id}")
        assert r.status_code == 200

    # A failing hook keeps the connections closed.
    def _broken(db):
        raise RuntimeError("hook exploded")

    monkeypatch.setattr(
        extensions, "_extended", FakeExtended({"lti_protected_org_ids": _broken})
    )
    with as_user(world.org_admin):
        r = await client.get(f"{BASE}/registrations/{reg.id}")
        assert r.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_move_is_superadmin_only(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org)
    await async_test_db.commit()
    path = f"{BASE}/registrations/{reg.id}"

    with as_user(world.org_admin):
        r = await async_test_client.put(
            path, json={"organization_id": world.other_org.id}
        )
        assert r.status_code == 403
        assert detail_code(r) == "org_move_forbidden"
        # Sending the current org is not a move.
        r = await async_test_client.put(
            path, json={"organization_id": world.org.id, "name": "Same org"}
        )
        assert r.status_code == 200, r.text

    with as_user(world.superadmin):
        r = await async_test_client.put(
            path, json={"organization_id": str(uuid.uuid4())}
        )
        assert r.status_code == 404
        r = await async_test_client.put(
            path, json={"organization_id": world.other_org.id}
        )
        assert r.status_code == 200, r.text
        assert r.json()["organization_id"] == world.other_org.id

    # The old org admin lost access, the new org's admin gained it.
    with as_user(world.org_admin):
        assert (await async_test_client.get(path)).status_code == 403
    with as_user(world.foreign_admin):
        assert (await async_test_client.get(path)).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_issuer_conflict_does_not_reveal_the_owner(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    foreign = await make_registration(
        async_test_db, world.other_org, name="Secret Foreign Moodle"
    )
    await async_test_db.commit()
    payload = registration_payload(
        world.org.id, issuer=foreign.issuer, client_id=foreign.client_id
    )

    with as_user(world.org_admin):
        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "issuer_client_taken"
        assert set(detail) == {"code", "message"}
        assert world.other_org.id not in r.text
        assert foreign.id not in r.text
        assert "Secret Foreign" not in r.text

        # The same leak guard applies on update.
        own = await make_registration(async_test_db, world.org)
        await async_test_db.commit()
        r = await async_test_client.put(
            f"{BASE}/registrations/{own.id}", json={"client_id": foreign.client_id}
        )
        # Different issuer: no conflict.
        assert r.status_code == 200
        r = await async_test_client.put(
            f"{BASE}/registrations/{own.id}",
            json={"issuer": foreign.issuer, "client_id": foreign.client_id},
        )
        assert r.status_code == 409
        assert set(r.json()["detail"]) == {"code", "message"}

    with as_user(world.superadmin):
        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 409
        assert r.json()["detail"]["registration_id"] == foreign.id


# --------------------------------------------------------------------------- #
# Registration round-trip
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_org_admin_round_trip(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    client = async_test_client

    with as_user(world.org_admin):
        r = await client.post(
            BASE + "/registrations",
            json=registration_payload(
                world.org.id, deployment_ids=["dep-1", "dep-2", "dep-1"]
            ),
        )
        assert r.status_code == 201, r.text
        created = r.json()
        reg_id = created["id"]
        assert created["status"] == "active"
        assert created["tool_host"] == "student_locked"
        assert created["tool_base_url"] == STUDENT_URL
        assert created["instructor_org_role"] == "contributor"
        assert created["deployment_count"] == 2

        r = await client.get(
            BASE + "/registrations", params={"organization_id": world.org.id}
        )
        assert [reg["id"] for reg in r.json()] == [reg_id]

        r = await client.get(f"{BASE}/registrations/{reg_id}")
        detail = r.json()
        assert detail["resource_link_count"] == 0
        assert detail["user_link_count"] == 0

        r = await client.put(
            f"{BASE}/registrations/{reg_id}",
            json={
                "instructor_org_role": "org_admin",
                "status": "disabled",
                "tool_host": "main",
                "lms_family": "moodle",
                # Explicit nulls on required fields are ignored.
                "name": None,
            },
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["instructor_org_role"] == "org_admin"
        assert updated["status"] == "disabled"
        assert updated["tool_host"] == "main"
        assert updated["tool_base_url"] == MAIN_URL
        assert updated["name"] == "Uni Passau Moodle"

        r = await client.get(f"{BASE}/registrations/{reg_id}/tool-config")
        assert r.json() == {
            "login_url": f"{MAIN_URL}/api/lti/login",
            "launch_url": f"{MAIN_URL}/api/lti/launch",
            "jwks_url": f"{MAIN_URL}/api/lti/jwks",
            "tool_host": "main",
            "base_url": MAIN_URL,
        }

        r = await client.post(
            f"{BASE}/registrations/{reg_id}/deployments",
            json={"deployment_id": "dep-3"},
        )
        assert r.status_code == 201
        dep_pk = r.json()["id"]
        r = await client.patch(
            f"{BASE}/registrations/{reg_id}/deployments/{dep_pk}",
            json={"status": "disabled"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"
        r = await client.delete(f"{BASE}/registrations/{reg_id}/deployments/{dep_pk}")
        assert r.status_code == 204

    events = await _events(async_test_db, registration_id=reg_id)
    assert [e.action for e in events] == [
        "registration_created",
        "registration_updated",
        "deployment_added",
        "deployment_status_changed",
        "deployment_removed",
    ]
    assert all(e.actor_user_id == world.org_admin.id for e in events)
    assert events[0].changes["deployment_ids"] == ["dep-1", "dep-2"]
    assert events[1].changes == {
        "instructor_org_role": {"old": "contributor", "new": "org_admin"},
        "status": {"old": "active", "new": "disabled"},
        "tool_host": {"old": "student_locked", "new": "main"},
        "lms_family": {"old": None, "new": "moodle"},
    }
    assert events[3].changes["status"] == {"old": "active", "new": "disabled"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_registration_crud_round_trip(async_test_client, async_test_db):
    org = await make_org(async_test_db)
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        # Create — duplicate deployment ids collapse, order preserved.
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(
                org.id, deployment_ids=["dep-1", "dep-2", "dep-1"]
            ),
        )
        assert r.status_code == 201, r.text
        created = r.json()
        reg_id = created["id"]
        assert created["organization_id"] == org.id
        assert created["status"] == "active"
        assert created["lms_family"] is None  # optional, defaults to generic
        assert created["link_existing_users_by_email"] is True
        assert created["instructor_org_role"] == "contributor"
        assert created["student_org_role"] == "annotator"
        assert created["deployment_count"] == 2
        assert sorted(d["deployment_id"] for d in created["deployments"]) == [
            "dep-1",
            "dep-2",
        ]

        # The unfiltered list (superadmins only) includes it.
        r = await async_test_client.get(BASE + "/registrations")
        assert r.status_code == 200
        listed = [reg for reg in r.json() if reg["id"] == reg_id]
        assert len(listed) == 1
        assert listed[0]["deployment_count"] == 2

        r = await async_test_client.get(f"{BASE}/registrations/{reg_id}")
        assert r.status_code == 200
        assert r.json()["resource_link_count"] == 0
        assert len(r.json()["deployments"]) == 2

        r = await async_test_client.put(
            f"{BASE}/registrations/{reg_id}",
            json={
                "name": "Uni Passau Moodle (renamed)",
                "jwks_uri": "https://moodle.uni-passau.de/mod/lti/certs2.php",
                "instructor_org_role": "org_admin",
                "student_org_role": "none",
                "status": "disabled",
                "lms_family": "ilias",
            },
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["name"] == "Uni Passau Moodle (renamed)"
        assert updated["jwks_uri"].endswith("certs2.php")
        assert updated["instructor_org_role"] == "org_admin"
        assert updated["student_org_role"] == "none"
        assert updated["status"] == "disabled"
        assert updated["lms_family"] == "ilias"
        assert updated["issuer"] == "https://moodle.uni-passau.de"
        assert updated["deployment_count"] == 2

        # Vendor tag accepts only known families.
        r = await async_test_client.put(
            f"{BASE}/registrations/{reg_id}", json={"lms_family": "blackboard"}
        )
        assert r.status_code == 422
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(org.id, lms_family="canvas"),
        )
        assert r.status_code == 422
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(
                org.id, issuer="https://ilias.uni-passau.de", lms_family="ilias"
            ),
        )
        assert r.status_code == 201, r.text
        assert r.json()["lms_family"] == "ilias"

        # Deployments: adding twice conflicts, removing twice 404s.
        r = await async_test_client.post(
            f"{BASE}/registrations/{reg_id}/deployments",
            json={"deployment_id": "dep-3"},
        )
        assert r.status_code == 201, r.text
        dep_pk = r.json()["id"]
        r = await async_test_client.post(
            f"{BASE}/registrations/{reg_id}/deployments",
            json={"deployment_id": "dep-3"},
        )
        assert r.status_code == 409
        assert detail_code(r) == "deployment_exists"
        r = await async_test_client.delete(
            f"{BASE}/registrations/{reg_id}/deployments/{dep_pk}"
        )
        assert r.status_code == 204
        r = await async_test_client.delete(
            f"{BASE}/registrations/{reg_id}/deployments/{dep_pk}"
        )
        assert r.status_code == 404
        assert detail_code(r) == "deployment_not_found"
        r = await async_test_client.get(f"{BASE}/registrations/{reg_id}")
        assert r.json()["deployment_count"] == 2

        r = await async_test_client.get(f"{BASE}/registrations/nope")
        assert r.status_code == 404
        assert detail_code(r) == "registration_not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deployment_status_patch(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org, deployment_ids=("a",))
    other = await make_registration(async_test_db, world.org, deployment_ids=("b",))
    await async_test_db.commit()
    dep = (
        await async_test_db.execute(
            select(LtiDeployment).where(LtiDeployment.registration_id == reg.id)
        )
    ).scalar_one()
    other_dep = (
        await async_test_db.execute(
            select(LtiDeployment).where(LtiDeployment.registration_id == other.id)
        )
    ).scalar_one()
    path = f"{BASE}/registrations/{reg.id}/deployments"

    with as_user(world.org_admin):
        r = await async_test_client.patch(f"{path}/{dep.id}", json={"status": "gone"})
        assert r.status_code == 422
        # A deployment of another connection is not found under this one.
        r = await async_test_client.patch(
            f"{path}/{other_dep.id}", json={"status": "disabled"}
        )
        assert r.status_code == 404
        r = await async_test_client.patch(
            f"{path}/{dep.id}", json={"status": "disabled"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"
        # Sending the current status again changes nothing and logs nothing.
        r = await async_test_client.patch(
            f"{path}/{dep.id}", json={"status": "disabled"}
        )
        assert r.status_code == 200
        r = await async_test_client.patch(f"{path}/{dep.id}", json={"status": "active"})
        assert r.json()["status"] == "active"

    actions = [e.action for e in await _events(async_test_db, registration_id=reg.id)]
    assert actions == ["deployment_status_changed", "deployment_status_changed"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_issuer_client_conflict(async_test_client, async_test_db):
    org = await make_org(async_test_db)
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        payload = registration_payload(org.id, client_id="client-dup")
        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 201, r.text

        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 409
        assert detail_code(r) == "issuer_client_taken"

        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(org.id, client_id="client-other"),
        )
        assert r.status_code == 201, r.text
        other_id = r.json()["id"]

        r = await async_test_client.put(
            f"{BASE}/registrations/{other_id}", json={"client_id": "client-dup"}
        )
        assert r.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_student_org_role_validation_and_explicit_none(
    async_test_client, async_test_db
):
    org = await make_org(async_test_db)
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        payload = registration_payload(org.id)
        payload["student_org_role"] = "contributor"  # not a legal student role
        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 422

        payload["student_org_role"] = "none"
        r = await async_test_client.post(BASE + "/registrations", json=payload)
        assert r.status_code == 201, r.text
        assert r.json()["student_org_role"] == "none"

        reg_id = r.json()["id"]
        r = await async_test_client.put(
            f"{BASE}/registrations/{reg_id}", json={"student_org_role": "annotator"}
        )
        assert r.status_code == 200
        assert r.json()["student_org_role"] == "annotator"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_org_group_and_bad_urls(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)

    with as_user(world.superadmin):
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(str(uuid.uuid4())),
        )
        assert r.status_code == 404
        assert detail_code(r) == "organization_not_found"
        # A group of another org is not found in this one.
        foreign_group = await make_group(async_test_db, world.other_org)
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, group_id=foreign_group.id),
        )
        assert r.status_code == 404
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(
                world.org.id, jwks_uri="ftp://moodle.example.com/certs"
            ),
        )
        assert r.status_code == 422
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, issuer="not-a-url"),
        )
        assert r.status_code == 422

    # An inactive org is invisible to its own admins.
    world.org.is_active = False
    await async_test_db.commit()
    with as_user(world.org_admin):
        r = await async_test_client.post(
            BASE + "/registrations", json=registration_payload(world.org.id)
        )
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Tool hosts
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_hosts_list_configured_hosts(
    async_test_client, async_test_db, monkeypatch
):
    user = await make_user(async_test_db)

    with as_user(user):
        r = await async_test_client.get(BASE + "/tool-hosts")
        assert r.status_code == 200
        assert r.json() == [
            {
                "key": "student_locked",
                "label": "student.example.test",
                "host": "student.example.test",
                "base_url": STUDENT_URL,
                "is_default": True,
            },
            {
                "key": "main",
                "label": "main.example.test",
                "host": "main.example.test",
                "base_url": MAIN_URL,
                "is_default": False,
            },
        ]

        set_tool_host_env(monkeypatch, student=False)
        r = await async_test_client.get(BASE + "/tool-hosts")
        assert [(h["key"], h["is_default"]) for h in r.json()] == [("main", True)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_host_is_validated(async_test_client, async_test_db, monkeypatch):
    world = await build_world(async_test_db)

    with as_user(world.org_admin):
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, tool_host="elsewhere"),
        )
        assert r.status_code == 422
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, tool_host="main"),
        )
        assert r.status_code == 201
        assert r.json()["tool_host"] == "main"
        reg_id = r.json()["id"]

        # Without the student host, it can be neither chosen nor used.
        set_tool_host_env(monkeypatch, student=False)
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(world.org.id, tool_host="student_locked"),
        )
        assert r.status_code == 400
        assert detail_code(r) == "tool_host_unavailable"
        r = await async_test_client.put(
            f"{BASE}/registrations/{reg_id}", json={"tool_host": "student_locked"}
        )
        assert r.status_code == 400
        r = await async_test_client.post(
            BASE + "/registrations/invites",
            json={"organization_id": world.org.id, "tool_host": "student_locked"},
        )
        assert r.status_code == 400
        # Omitted means the deployment default, which is now the main host.
        r = await async_test_client.post(
            BASE + "/registrations", json=registration_payload(world.org.id)
        )
        assert r.status_code == 201
        assert r.json()["tool_host"] == "main"

    # A stored student host that is no longer configured has no tool sheet.
    stale = await make_registration(
        async_test_db, world.org, tool_host="student_locked"
    )
    await async_test_db.commit()
    with as_user(world.org_admin):
        r = await async_test_client.get(f"{BASE}/registrations/{stale.id}")
        assert r.json()["tool_base_url"] is None
        r = await async_test_client.get(f"{BASE}/registrations/{stale.id}/tool-config")
        assert r.status_code == 400
        assert detail_code(r) == "tool_host_unavailable"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_config_uses_the_connection_host(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org)
    await async_test_db.commit()

    with as_user(world.org_admin):
        # A base_url from an older client is ignored.
        r = await async_test_client.get(
            f"{BASE}/registrations/{reg.id}/tool-config",
            params={"base_url": "https://attacker.example.com"},
        )
        assert r.status_code == 200, r.text
        # No deep_linking_url: the tool rejects LtiDeepLinkingRequest, so the
        # config sheet must not advertise a nonexistent route.
        assert r.json() == {
            "login_url": f"{STUDENT_URL}/api/lti/login",
            "launch_url": f"{STUDENT_URL}/api/lti/launch",
            "jwks_url": f"{STUDENT_URL}/api/lti/jwks",
            "tool_host": "student_locked",
            "base_url": STUDENT_URL,
        }
        r = await async_test_client.get(f"{BASE}/registrations/nope/tool-config")
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Dynamic Registration invites
# --------------------------------------------------------------------------- #
async def _create_invite(client, org_id: str, **body) -> dict:
    r = await client.post(
        BASE + "/registrations/invites", json={"organization_id": org_id, **body}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _get_invite_row(db, invite_id: str) -> LtiRegistrationInvite:
    return (
        await db.execute(
            select(LtiRegistrationInvite).where(LtiRegistrationInvite.id == invite_id)
        )
    ).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invite_url_comes_from_the_tool_host(async_test_client, async_test_db):
    world = await build_world(async_test_db)

    with as_user(world.org_admin):
        created = await _create_invite(async_test_client, world.org.id)
        token = created["token"]
        assert len(token) >= 32
        assert created["tool_host"] == "student_locked"
        assert created["register_url"] == (
            f"{STUDENT_URL}/api/lti/register/init?token={token}"
        )

        # The chosen host wins; a base_url query from older clients is ignored.
        r = await async_test_client.post(
            BASE + "/registrations/invites",
            json={"organization_id": world.org.id, "tool_host": "main"},
            params={"base_url": "https://attacker.example.com"},
        )
        assert r.status_code == 201, r.text
        main_invite = r.json()
        assert main_invite["register_url"].startswith(
            f"{MAIN_URL}/api/lti/register/init?token="
        )
        assert main_invite["token"] != token

        r = await async_test_client.post(
            BASE + "/registrations/invites",
            json={"organization_id": world.org.id, "tool_host": "moon"},
        )
        assert r.status_code == 422

        # Default expiry is ~14 days out; 1..90 is enforced.
        expires_at = datetime.fromisoformat(
            created["expires_at"].replace("Z", "+00:00")
        )
        delta = expires_at - datetime.now(timezone.utc)
        assert timedelta(days=13) < delta <= timedelta(days=14)
        for days in (0, 91):
            r = await async_test_client.post(
                BASE + "/registrations/invites",
                json={"organization_id": world.org.id, "expires_in_days": days},
            )
            assert r.status_code == 422

    # Only the hash is stored; the creator is the calling org admin.
    row = await _get_invite_row(async_test_db, created["id"])
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (row.token_hash, row.id)
    assert row.created_by == world.org_admin.id
    assert row.tool_host == "student_locked"
    assert row.used_at is None
    assert row.resulting_registration_id is None
    main_row = await _get_invite_row(async_test_db, main_invite["id"])
    assert main_row.tool_host == "main"

    events = await _events(async_test_db, organization_id=world.org.id)
    assert [e.action for e in events] == ["invite_created", "invite_created"]
    assert events[1].changes["tool_host"] == "main"
    assert token not in str(events[0].changes)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_invite_rejects_unknown_org(async_test_client, async_test_db):
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        r = await async_test_client.post(
            BASE + "/registrations/invites",
            json={"organization_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_invites_computes_status_and_hides_secrets(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)

    with as_user(world.org_admin):
        pending = await _create_invite(async_test_client, world.org.id)
        expired = await _create_invite(async_test_client, world.org.id)
        used = await _create_invite(async_test_client, world.org.id, tool_host="main")

        expired_row = await _get_invite_row(async_test_db, expired["id"])
        expired_row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        used_row = await _get_invite_row(async_test_db, used["id"])
        used_row.used_at = datetime.now(timezone.utc)
        await async_test_db.commit()

        r = await async_test_client.get(
            BASE + "/registrations/invites",
            params={"organization_id": world.org.id},
        )
        assert r.status_code == 200, r.text
        by_id = {row["id"]: row for row in r.json()}
        assert by_id[pending["id"]]["status"] == "pending"
        assert by_id[expired["id"]]["status"] == "expired"
        assert by_id[used["id"]]["status"] == "used"
        assert by_id[used["id"]]["used_at"] is not None
        assert by_id[used["id"]]["tool_host"] == "main"
        assert by_id[pending["id"]]["used_at"] is None

        for row in r.json():
            assert "token" not in row
            assert "token_hash" not in row
            assert "register_url" not in row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_invites_organization_filter(async_test_client, async_test_db):
    org_a = await make_org(async_test_db)
    org_b = await make_org(async_test_db)
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        invite_a = await _create_invite(async_test_client, org_a.id)
        invite_b = await _create_invite(async_test_client, org_b.id)

        r = await async_test_client.get(
            BASE + "/registrations/invites", params={"organization_id": org_a.id}
        )
        assert r.status_code == 200
        assert [row["id"] for row in r.json()] == [invite_a["id"]]

        # For superadmins an unknown org id is a filter miss, not a 404.
        r = await async_test_client.get(
            BASE + "/registrations/invites",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        assert r.json() == []

        r = await async_test_client.get(BASE + "/registrations/invites")
        ids = {row["id"] for row in r.json()}
        assert {invite_a["id"], invite_b["id"]} <= ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_invite_deletes_pending_but_keeps_used(
    async_test_client, async_test_db
):
    world = await build_world(async_test_db)
    org_id = world.org.id

    with as_user(world.org_admin):
        pending = await _create_invite(async_test_client, org_id)
        used = await _create_invite(async_test_client, org_id)
        used_row = await _get_invite_row(async_test_db, used["id"])
        used_row.used_at = datetime.now(timezone.utc)
        await async_test_db.commit()

        r = await async_test_client.delete(
            f"{BASE}/registrations/invites/{pending['id']}"
        )
        assert r.status_code == 204
        r = await async_test_client.get(
            BASE + "/registrations/invites", params={"organization_id": org_id}
        )
        assert pending["id"] not in {row["id"] for row in r.json()}

        r = await async_test_client.delete(f"{BASE}/registrations/invites/{used['id']}")
        assert r.status_code == 409
        assert detail_code(r) == "invite_used"
        r = await async_test_client.get(
            BASE + "/registrations/invites", params={"organization_id": org_id}
        )
        assert used["id"] in {row["id"] for row in r.json()}

        r = await async_test_client.delete(
            f"{BASE}/registrations/invites/{uuid.uuid4()}"
        )
        assert r.status_code == 404

    actions = [e.action for e in await _events(async_test_db, organization_id=org_id)]
    assert actions == ["invite_created", "invite_created", "invite_revoked"]


# --------------------------------------------------------------------------- #
# Lists (superadmin filters and counts)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.asyncio
async def test_registrations_organization_filter(async_test_client, async_test_db):
    org_a = await make_org(async_test_db)
    org_b = await make_org(async_test_db)
    admin = await make_user(async_test_db, superadmin=True)

    with as_user(admin):
        r = await async_test_client.post(
            BASE + "/registrations", json=registration_payload(org_a.id)
        )
        assert r.status_code == 201, r.text
        reg_a = r.json()["id"]
        r = await async_test_client.post(
            BASE + "/registrations",
            json=registration_payload(
                org_b.id, issuer="https://moodle.uni-b.example.com"
            ),
        )
        assert r.status_code == 201, r.text
        reg_b = r.json()["id"]

        r = await async_test_client.get(
            BASE + "/registrations", params={"organization_id": org_a.id}
        )
        assert r.status_code == 200
        assert [reg["id"] for reg in r.json()] == [reg_a]

        r = await async_test_client.get(
            BASE + "/registrations", params={"organization_id": str(uuid.uuid4())}
        )
        assert r.status_code == 200
        assert r.json() == []

        r = await async_test_client.get(BASE + "/registrations")
        assert r.status_code == 200
        ids = [reg["id"] for reg in r.json()]
        assert reg_a in ids and reg_b in ids
        assert {"id", "organization_id", "deployments", "deployment_count"} <= set(
            r.json()[0].keys()
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_grade_sync_filters_and_retry_reset(async_test_client, async_test_db):
    world = await build_world(async_test_db)
    org_b = world.other_org
    reg_a = await make_registration(async_test_db, world.org)
    reg_b = await make_registration(async_test_db, org_b)
    project_a = await make_project(async_test_db, world.org_admin)
    project_b = await make_project(async_test_db, world.foreign_admin)
    link_a = await make_resource_link(async_test_db, reg_a, project=project_a)
    link_b = await make_resource_link(async_test_db, reg_b, project=project_b)
    student = await make_user(async_test_db)
    sync_a = await make_grade_sync(async_test_db, link_a, student)
    sync_b = await make_grade_sync(async_test_db, link_b, student)
    await async_test_db.commit()
    client = async_test_client

    async def ids(**params):
        r = await client.get(BASE + "/grade-syncs", params=params)
        assert r.status_code == 200, r.text
        return [row["id"] for row in r.json()]

    with as_user(world.superadmin):
        assert {sync_a.id, sync_b.id} <= set(await ids())
        assert set(await ids(status="failed")) >= {sync_a.id, sync_b.id}
        assert await ids(project_id=project_a.id) == [sync_a.id]
        assert await ids(project_id=str(uuid.uuid4())) == []
        assert await ids(organization_id=world.org.id) == [sync_a.id]
        assert await ids(organization_id=str(uuid.uuid4())) == []
        assert await ids(organization_id=world.org.id, status="pending") == []
        assert await ids(organization_id=world.org.id, project_id=project_b.id) == []
        assert await ids(
            organization_id=org_b.id, project_id=project_b.id, status="failed"
        ) == [sync_b.id]
        assert await ids(registration_id=reg_b.id) == [sync_b.id]
        assert len(await ids(organization_id=world.org.id, limit=1)) == 1
        assert await ids(organization_id=world.org.id, offset=1) == []

        r = await client.post(f"{BASE}/grade-syncs/{sync_a.id}/retry")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["attempts"] == 0
        assert body["last_error"] is None
        assert body["next_retry_at"] is not None
        # Community edition: nothing to dispatch to, the sweep sends it.
        assert body["dispatched"] is False
        assert await ids(organization_id=world.org.id, status="pending") == [sync_a.id]

        r = await client.post(f"{BASE}/grade-syncs/{uuid.uuid4()}/retry")
        assert r.status_code == 404
        assert detail_code(r) == "grade_sync_not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_ags_count_on_list_and_detail(async_test_client, async_test_db):
    """Bound links without an AGS lineitem are counted; unbound and graded
    links are not — the org panel warns before the first grade push fails."""
    world = await build_world(async_test_db)
    reg = await make_registration(async_test_db, world.org)
    project = await make_project(async_test_db, world.org_admin)
    await make_resource_link(async_test_db, reg, project=project)
    await make_resource_link(
        async_test_db,
        reg,
        project=project,
        lineitem_url="https://lms.example/services/1/lineitems/9/lineitem",
    )
    await make_resource_link(async_test_db, reg)
    await async_test_db.commit()

    with as_user(world.org_admin):
        listed = await async_test_client.get(
            BASE + "/registrations", params={"organization_id": world.org.id}
        )
        assert listed.status_code == 200
        row = next(r for r in listed.json() if r["id"] == reg.id)
        assert row["resource_links_missing_ags"] == 1

        detail = await async_test_client.get(f"{BASE}/registrations/{reg.id}")
        assert detail.status_code == 200
        assert detail.json()["resource_links_missing_ags"] == 1
        assert detail.json()["resource_link_count"] == 3
