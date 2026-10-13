"""Usage writer (batching, never raises), usage middleware and the
last_used throttle of record_usage."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from auth_module.principal import Principal
from middleware.api_usage import ApiUsageMiddleware
from models import ApiKey, ApiKeyUsageEvent
from services import api_key_service as svc
from services import api_usage_writer as writer
from tests.fixtures.access_keys import seed_world


@pytest.fixture(autouse=True)
def _reset_writer():
    writer.set_sink(None)
    yield
    writer.set_sink(None)


def test_enqueue_never_raises():
    assert writer.enqueue({"key_prefix": "x"}) is False  # no queue running

    def boom(_event):
        raise RuntimeError("sink down")

    writer.set_sink(boom)
    assert writer.enqueue({"key_prefix": "x"}) is False


async def test_full_queue_drops_without_raising(monkeypatch):
    queue = asyncio.Queue(maxsize=1)
    monkeypatch.setattr(writer, "_queue", queue)
    assert writer.enqueue({"n": 1}) is True
    assert writer.enqueue({"n": 2}) is False
    assert queue.qsize() == 1


async def test_consumer_batches_by_size_and_time(monkeypatch):
    batches = []

    async def fake_write(events):
        batches.append(len(events))
        return len(events)

    monkeypatch.setattr(writer, "write_batch", fake_write)
    monkeypatch.setattr(writer, "FLUSH_INTERVAL", 0.05)
    await writer.start()
    try:
        for i in range(250):
            assert writer.enqueue({"n": i})
        for _ in range(100):
            if sum(batches) >= 250:
                break
            await asyncio.sleep(0.02)
    finally:
        await writer.stop()
    assert sum(batches) == 250
    assert max(batches) <= writer.BATCH_SIZE
    assert batches[0] == writer.BATCH_SIZE


async def test_stop_flushes_pending(monkeypatch):
    written = []

    async def fake_write(events):
        written.extend(events)
        return len(events)

    monkeypatch.setattr(writer, "write_batch", fake_write)
    queue = asyncio.Queue()
    for i in range(3):
        queue.put_nowait({"n": i})
    monkeypatch.setattr(writer, "_queue", queue)
    monkeypatch.setattr(writer, "_task", None)
    await writer.stop()
    assert [e["n"] for e in written] == [0, 1, 2]


async def test_write_batch_swallows_errors(monkeypatch):
    async def broken(_db, _events):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "record_usage", broken)
    assert await writer.write_batch([{"key_prefix": "x"}]) == 0
    assert await writer.write_batch([]) == 0


async def test_record_usage_inserts_and_throttles_last_used(async_test_db):
    db = async_test_db
    world = await seed_world(db, group=False)
    key, _ = await svc.create_personal_key(db, world["member"].id, {"name": "k", "scopes": []})
    now = datetime.now(timezone.utc)

    def ev(ip, when):
        return {
            "api_key_id": key.id, "key_prefix": key.key_prefix, "user_id": world["member"].id,
            "method": "GET", "route": "/api/v1/me", "status_code": 200, "duration_ms": 3,
            "ip_address": ip, "user_agent": "x" * 400, "created_at": when,
        }

    assert await svc.record_usage(db, [ev("198.51.100.0/24", now)]) == 1
    assert await svc.record_usage(db, [ev("203.0.113.0/24", now + timedelta(seconds=20))]) == 1
    await db.flush()
    row = (await db.execute(select(ApiKey).where(ApiKey.id == key.id))).scalar_one()
    await db.refresh(row)
    assert row.last_used_ip == "198.51.100.0/24"
    events = (
        await db.execute(select(ApiKeyUsageEvent).where(ApiKeyUsageEvent.api_key_id == key.id))
    ).scalars().all()
    assert len(events) == 2 and all(len(e.user_agent) == 256 for e in events)

    assert await svc.record_usage(db, [ev("192.0.2.0/24", now + timedelta(seconds=90))]) == 1
    await db.refresh(row)
    assert row.last_used_ip == "192.0.2.0/24"

    summary = await svc.usage_summary(db, key.id, now - timedelta(days=1), now + timedelta(days=1))
    assert summary["total_requests"] == 3
    by_route = await svc.usage_summary(
        db, key.id, now - timedelta(days=1), now + timedelta(days=1), "route"
    )
    assert by_route["items"][0]["route"] == "/api/v1/me"
    page = await svc.usage_events(db, key.id, limit=2)
    assert len(page["items"]) == 2 and page["next_cursor"] is not None
    rest = await svc.usage_events(db, key.id, cursor=page["next_cursor"], limit=2)
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


def _app(principal=None, rate=None):
    app = FastAPI()

    def dep(request: Request):
        if principal is not None:
            request.state.principal = principal
            request.state.scope_used = "projects:read"
        if rate is not None:
            request.state.rate_limit = rate

    @app.get("/api/v1/projects/{project_id}", dependencies=[Depends(dep)])
    def v1(project_id: str):
        return {"ok": project_id}

    @app.get("/api/other", dependencies=[Depends(dep)])
    def other():
        return {"ok": True}

    app.add_middleware(ApiUsageMiddleware)
    return app


async def test_middleware_records_key_requests_with_route_template():
    seen = []
    writer.set_sink(seen.append)
    principal = Principal(
        kind="api_key", user_id="u1", api_key_id="key-1", key_prefix="bgr_test_abcdefgh",
        organization_id="org-1",
    )
    rate = {"limit": 120, "remaining": 119, "reset": 1700000040}
    app = _app(principal, rate)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/projects/p-42", headers={"X-Forwarded-For": "203.0.113.9"})
        assert r.status_code == 200
        assert r.headers["x-ratelimit-limit"] == "120"
        assert r.headers["x-ratelimit-remaining"] == "119"
        assert r.headers["x-ratelimit-reset"] == "1700000040"
        assert len(r.headers["x-request-id"]) == 32
        r = await c.get("/api/v1/projects/p-43", headers={"X-Request-ID": "abc"})
        # The caller's own id is kept, not replaced.
        assert r.headers.get("x-request-id") in (None, "abc")
        await c.get("/api/other")
    assert len(seen) == 2
    ev = seen[0]
    assert ev["route"] == "/api/v1/projects/{project_id}"
    assert ev["project_id"] == "p-42"
    assert ev["status_code"] == 200 and ev["method"] == "GET"
    assert ev["ip_address"] == "203.0.113.0/24"
    assert ev["api_key_id"] == "key-1" and ev["organization_id"] == "org-1"
    assert ev["scope_used"] == "projects:read"
    assert ev["response_bytes"] > 0
    assert seen[1]["request_id"] == "abc"


async def test_middleware_ignores_sessions():
    seen = []
    writer.set_sink(seen.append)
    app = _app(Principal(kind="session", user_id="u"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/projects/p")
        assert r.status_code == 200 and "x-ratelimit-limit" not in r.headers
    assert seen == []
