"""Isolation on /api/v1: organizations, Safe Exam Browser projects, access
windows and the role cap on tasks:read_reference."""

from datetime import datetime, timedelta, timezone

import pytest

from models import OrganizationRole
from services import api_key_service as svc
from tests.fixtures.access_keys import make_membership, seed_world
from tests.fixtures.v1 import bearer, ids, make_project, make_tasks, v1_auth

SCOPES = ["projects:read", "tasks:read"]


@pytest.fixture
async def two_orgs(async_test_db):
    db = async_test_db
    a = await seed_world(db, group=False)
    b = await seed_world(db, group=False)
    a["project"] = await make_project(db, a["admin"].id, org_id=a["org"].id, title="A")
    b["project"] = await make_project(db, b["admin"].id, org_id=b["org"].id, title="B")
    await make_tasks(db, a["project"], 1, a["admin"].id)
    await make_tasks(db, b["project"], 1, b["admin"].id)
    return a, b


async def _key(db, world, **payload):
    body = {"name": "k", "org_role": "ANNOTATOR", "scopes": SCOPES, **payload}
    return (await svc.create_org_key(db, world["admin"].id, world["org"].id, body))[1]


async def test_consumer_orgs_cannot_see_each_other(async_test_client, async_test_db, two_orgs):
    a, b = two_orgs
    key_a = await _key(async_test_db, a)
    key_b = await _key(async_test_db, b)
    with v1_auth(async_test_db):
        c = async_test_client
        assert ids((await c.get("/api/v1/projects", headers=bearer(key_a))).json()["items"]) == [
            a["project"].id
        ]
        assert ids((await c.get("/api/v1/projects", headers=bearer(key_b))).json()["items"]) == [
            b["project"].id
        ]
        for path in (
            f"/api/v1/projects/{b['project'].id}",
            f"/api/v1/projects/{b['project'].id}/tasks",
        ):
            r = await c.get(path, headers=bearer(key_a))
            assert r.status_code == 404, path
            assert r.json()["error"]["code"] == "not_found"


async def test_seb_project_is_hidden_from_keys(async_test_client, async_test_db, two_orgs):
    a, _ = two_orgs
    seb = await make_project(
        async_test_db, a["admin"].id, org_id=a["org"].id, title="SEB", seb_required=True
    )
    key = await _key(async_test_db, a)
    with v1_auth(async_test_db):
        r = await async_test_client.get("/api/v1/projects", headers=bearer(key))
        assert seb.id not in ids(r.json()["items"])
        r = await async_test_client.get(f"/api/v1/projects/{seb.id}/tasks", headers=bearer(key))
        assert r.status_code == 404


async def test_access_window_is_enforced(async_test_client, async_test_db, two_orgs):
    a, _ = two_orgs
    upcoming = await make_project(
        async_test_db,
        a["admin"].id,
        org_id=a["org"].id,
        title="Later",
        window_start_at=datetime.now(timezone.utc) + timedelta(days=2),
        window_end_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    tasks = await make_tasks(async_test_db, upcoming, 1, a["admin"].id)
    key = await _key(async_test_db, a)
    with v1_auth(async_test_db):
        c = async_test_client
        # The project is listed (metadata), its task data is not served yet.
        r = await c.get("/api/v1/projects", headers=bearer(key))
        assert upcoming.id in ids(r.json()["items"])
        for path in (
            f"/api/v1/projects/{upcoming.id}/tasks",
            f"/api/v1/projects/{upcoming.id}/tasks/{tasks[0].id}",
        ):
            r = await c.get(path, headers=bearer(key))
            assert r.status_code == 403, path
            error = r.json()["error"]
            assert error["code"] == "project_window_upcoming"
            assert error["details"]["window_start_at"]


async def test_personal_key_of_annotator_stays_blinded(
    async_test_client, async_test_db, two_orgs
):
    a, _ = two_orgs
    db = async_test_db
    annotator = a["group_admin"]  # an org ANNOTATOR in seed_world
    _, plain = await svc.create_personal_key(
        db, annotator.id, {"name": "mine", "scopes": ["projects:read", "tasks:read_reference"]}
    )
    contributor = a["member"]
    _, contrib_plain = await svc.create_personal_key(
        db, contributor.id, {"name": "mine", "scopes": ["tasks:read_reference"]}
    )
    url = f"/api/v1/projects/{a['project'].id}/tasks"
    with v1_auth(db):
        r = await async_test_client.get(url, headers=bearer(plain))
        assert r.status_code == 200, r.text
        assert set(r.json()["items"][0]["data"]) == {"sachverhalt"}
        assert "audit_log" not in r.json()["items"][0]["meta"]
        r = await async_test_client.get(
            f"/api/v1/projects/{a['project'].id}", headers=bearer(plain)
        )
        assert r.json()["access"]["blinded"] is True
        # A CONTRIBUTOR's personal key with the scope gets the reference.
        r = await async_test_client.get(url, headers=bearer(contrib_plain))
        assert "Musterloesung" in r.json()["items"][0]["data"]


async def test_session_on_v1_follows_the_browser_rules(
    async_test_client, async_test_db, two_orgs
):
    a, b = two_orgs
    db = async_test_db
    annotator = a["group_admin"]
    with v1_auth(db, session_user=annotator):
        r = await async_test_client.get("/api/v1/me")
        principal = r.json()["principal"]
        assert principal["kind"] == "session" and principal["scopes"] == ["*"]
        assert principal["organization"]["id"] == a["org"].id
        r = await async_test_client.get(f"/api/v1/projects/{a['project'].id}/tasks")
        assert set(r.json()["items"][0]["data"]) == {"sachverhalt"}
        # Sessions keep the browser API's 403 for a foreign project.
        r = await async_test_client.get(f"/api/v1/projects/{b['project'].id}")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"
    # A second membership does not change the primary organization.
    later = make_membership(annotator.id, b["org"].id, OrganizationRole.ANNOTATOR)
    later.joined_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.add(later)
    await db.flush()
    with v1_auth(db, session_user=annotator):
        r = await async_test_client.get("/api/v1/me")
        assert r.json()["principal"]["organization"]["id"] == a["org"].id
