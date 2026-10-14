"""End-to-end flow of a benchmark consumer on /api/v1 with real access
keys: me, projects (allowlist and group filter), blinded tasks, reference
tasks for a CONTRIBUTOR key, exports, revocation."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from models import ExportJob, JobStatus
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import bearer, ids, make_project, make_tasks, v1_auth


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db)
    owner = w["admin"]
    w["p1"] = await make_project(db, owner.id, org_id=w["org"].id, title="P1")
    w["p2"] = await make_project(db, owner.id, org_id=w["org"].id, title="P2")
    w["p_group"] = await make_project(
        db, owner.id, org_id=w["org"].id, group_id=w["group"].id, title="Grouped"
    )
    w["tasks"] = await make_tasks(db, w["p1"], 3, owner.id)
    await make_tasks(db, w["p_group"], 1, owner.id)
    return w


async def _org_key(db, w, **payload):
    body = {"name": "bench", "org_role": "ANNOTATOR", **payload}
    key, plain = await svc.create_org_key(db, w["admin"].id, w["org"].id, body)
    return key, plain


async def test_me_describes_an_org_key(async_test_client, async_test_db, world):
    key, plain = await _org_key(
        async_test_db, world, scopes=["projects:read", "tasks:read"],
        project_ids=[world["p1"].id], rate_limit_per_minute=30,
    )
    with v1_auth(async_test_db):
        r = await async_test_client.get("/api/v1/me", headers=bearer(plain))
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["principal"]
    assert p["kind"] == "api_key"
    assert p["key_prefix"] == key.key_prefix
    assert p["scopes"] == ["projects:read", "tasks:read"]
    assert p["project_ids"] == [world["p1"].id]
    assert p["organization"]["id"] == world["org"].id
    assert p["organization"]["slug"] == world["org"].slug
    assert p["group"] is None
    assert p["rate_limit"]["per_minute"] == 30
    assert body["user"]["is_service_account"] is True
    assert r.headers["x-api-version"] == "1"
    assert r.headers["access-control-allow-origin"] == "*"


async def test_benchmark_flow(async_test_client, async_test_db, world):
    db = async_test_db
    w = world
    annot_key, annot = await _org_key(
        db, w, scopes=["projects:read", "tasks:read"], project_ids=[w["p1"].id, w["p_group"].id]
    )
    group_key, grouped = await _org_key(
        db, w, scopes=["projects:read", "tasks:read"], group_id=w["group"].id
    )
    _, contrib = await _org_key(
        db, w, org_role="CONTRIBUTOR",
        scopes=["projects:read", "tasks:read_reference", "exports:read"],
    )

    with v1_auth(db):
        c = async_test_client
        # Projects: the allowlist drops P2; the grouped project stays hidden
        # from a key outside the group although it is on the allowlist.
        r = await c.get("/api/v1/projects", headers=bearer(annot))
        assert r.status_code == 200, r.text
        assert ids(r.json()["items"]) == [w["p1"].id]
        r = await c.get("/api/v1/projects", headers=bearer(grouped))
        assert ids(r.json()["items"]) == [w["p_group"].id]
        r = await c.get(f"/api/v1/projects/{w['p2'].id}", headers=bearer(annot))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"

        r = await c.get(f"/api/v1/projects/{w['p1'].id}", headers=bearer(annot))
        project = r.json()
        assert project["task_count"] == 3
        assert project["bound_fields"] == ["sachverhalt"]
        assert [f["name"] for f in project["answer_fields"]] == ["antwort", "ergebnis"]
        assert project["answer_fields"][1]["options"] == ["ja", "nein"]
        assert project["access"] == {
            "tier": "full", "effective_role": "ANNOTATOR", "blinded": True,
        }

        # Blinded tasks for the annotator key.
        r = await c.get(f"/api/v1/projects/{w['p1'].id}/tasks", headers=bearer(annot))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert [t["inner_id"] for t in items] == [1, 2, 3]
        for t in items:
            assert set(t["data"]) == {"sachverhalt"}
            assert "audit_log" not in t["meta"]
            assert t["meta"]["benchmark"] == {"rechtsgebiet": "BGB AT"}
        assert "Lösung" not in r.text and "editor@example.com" not in r.text

        one = w["tasks"][0]
        r = await c.get(f"/api/v1/projects/{w['p1'].id}/tasks/{one.id}", headers=bearer(annot))
        assert r.status_code == 200 and set(r.json()["data"]) == {"sachverhalt"}

        # A missing scope answers 403 insufficient_scope.
        r = await c.post(f"/api/v1/projects/{w['p1'].id}/exports", headers=bearer(annot))
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "insufficient_scope"

        # The CONTRIBUTOR key with tasks:read_reference sees the reference.
        r = await c.get(f"/api/v1/projects/{w['p1'].id}/tasks", headers=bearer(contrib))
        assert r.status_code == 200
        first = r.json()["items"][0]
        assert first["data"]["Musterloesung"] == "Lösung 1"
        assert first["meta"]["audit_log"][0]["by"] == "editor@example.com"
        r = await c.get(f"/api/v1/projects/{w['p1'].id}", headers=bearer(contrib))
        assert r.json()["access"]["blinded"] is False

        # Exports: job created, polled, downloaded through a presigned 302.
        with patch(
            "routers.projects.import_export.send_task_safe",
            return_value=MagicMock(id="celery-1"),
        ) as send:
            r = await c.post(
                f"/api/v1/projects/{w['p1'].id}/exports",
                json={"format": "json"},
                headers=bearer(contrib),
            )
        assert r.status_code == 202, r.text
        job = r.json()
        assert job["status"] == "pending" and job["download_url"] is None
        assert r.headers["location"] == f"/api/v1/exports/{job['id']}"
        send.assert_called_once()

        r = await c.get(f"/api/v1/exports/{job['id']}/download", headers=bearer(contrib))
        assert r.status_code == 404 and r.json()["error"]["code"] == "export_not_ready"

        row = (
            await db.execute(select(ExportJob).where(ExportJob.id == job["id"]))
        ).scalar_one()
        row.status = JobStatus.COMPLETED.value
        row.object_key = "exports/x.json"
        await db.flush()

        r = await c.get(f"/api/v1/exports/{job['id']}", headers=bearer(contrib))
        assert r.json()["download_url"] == f"/api/v1/exports/{job['id']}/download"
        with patch(
            "routers.projects.import_export.object_storage.get_download_url",
            return_value="https://storage.example/presigned",
        ):
            r = await c.get(
                f"/api/v1/exports/{job['id']}/download",
                headers=bearer(contrib),
                follow_redirects=False,
            )
        assert r.status_code == 302
        assert r.headers["location"] == "https://storage.example/presigned"

        # The annotator key cannot read the job (no scope); revocation is 401.
        r = await c.get(f"/api/v1/exports/{job['id']}", headers=bearer(annot))
        assert r.status_code == 403
        await svc.revoke_key(db, annot_key, w["admin"].id, "test")
        await db.flush()
        r = await c.get("/api/v1/me", headers=bearer(annot))
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "api_key_revoked"
        assert r.json()["error"]["request_id"]


async def test_task_pagination_and_etag(async_test_client, async_test_db, world):
    _, plain = await _org_key(async_test_db, world, scopes=["tasks:read"])
    url = f"/api/v1/projects/{world['p1'].id}/tasks"
    with v1_auth(async_test_db):
        c = async_test_client
        r = await c.get(url, params={"limit": 2}, headers=bearer(plain))
        page1 = r.json()
        assert [t["inner_id"] for t in page1["items"]] == [1, 2]
        assert page1["next_cursor"]
        etag = r.headers["etag"]
        assert etag.startswith('W/"') and r.headers["last-modified"]

        r = await c.get(
            url, params={"limit": 2}, headers={**bearer(plain), "If-None-Match": etag}
        )
        assert r.status_code == 304 and r.content == b""
        assert r.headers["etag"] == etag

        r = await c.get(
            url, params={"limit": 2, "cursor": page1["next_cursor"]}, headers=bearer(plain)
        )
        page2 = r.json()
        assert [t["inner_id"] for t in page2["items"]] == [3]
        assert page2["next_cursor"] is None
        assert r.headers["etag"] != etag

        r = await c.get(url, params={"cursor": "garbage!"}, headers=bearer(plain))
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_cursor"


async def test_export_idempotency_replays_the_first_job(
    async_test_client, async_test_db, world
):
    _, contrib = await _org_key(
        async_test_db, world, org_role="CONTRIBUTOR",
        scopes=["tasks:read_reference", "exports:read"],
    )
    url = f"/api/v1/projects/{world['p1'].id}/exports"
    headers = {**bearer(contrib), "Idempotency-Key": "run-1"}
    with v1_auth(async_test_db), patch(
        "routers.projects.import_export.send_task_safe", return_value=MagicMock(id="c")
    ) as send:
        r1 = await async_test_client.post(url, json={"format": "json"}, headers=headers)
        r2 = await async_test_client.post(url, json={"format": "json"}, headers=headers)
        r3 = await async_test_client.post(url, json={"format": "csv"}, headers=headers)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in r1.headers
    assert send.call_count == 1
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "idempotency_key_reused"


async def test_usage_events_record_the_full_route_template(
    async_test_client, async_test_db, world
):
    from services import api_usage_writer as writer

    _, plain = await _org_key(async_test_db, world, scopes=["projects:read"])
    seen = []
    writer.set_sink(seen.append)
    try:
        with v1_auth(async_test_db):
            r = await async_test_client.get(
                f"/api/v1/projects/{world['p1'].id}", headers=bearer(plain)
            )
        assert r.status_code == 200
    finally:
        writer.set_sink(None)
    assert [e["route"] for e in seen] == ["/api/v1/projects/{project_id}"]
    assert seen[0]["project_id"] == world["p1"].id
    assert seen[0]["scope_used"] == "projects:read"
