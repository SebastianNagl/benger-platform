"""Idempotency-Key handling of v1 POST routes."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from auth_module import require_user
from auth_module.models import User as AuthUser
from auth_module.principal import Principal
from routers.v1 import _idempotency as idem_mod
from routers.v1._errors import install_v1_exception_handlers
from routers.v1._idempotency import IdempotencyContext, idempotent


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    idem_mod.memory_store.clear()
    yield
    idem_mod.memory_store.clear()


def _app(calls, key_id="key-1"):
    app = FastAPI()
    install_v1_exception_handlers(app)

    def _user(request: Request):
        request.state.principal = Principal(
            kind="api_key", user_id="u1", api_key_id=key_id, key_prefix="bgr_test_x"
        )
        return AuthUser(
            id="u1", username="u1", email="u1@x.org", name="U",
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[require_user] = _user

    @app.post("/api/v1/things")
    async def create(
        payload: dict = Body(...),
        idem: IdempotencyContext = Depends(idempotent()),
    ):
        calls.append(payload)
        if payload.get("fail"):
            raise HTTPException(status_code=500, detail="boom")
        body = {"id": str(uuid.uuid4()), "n": len(calls)}
        await idem.save(201, body)
        return JSONResponse(status_code=201, content=body)

    return app


async def _post(app, payload, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/api/v1/things", json=payload, headers=headers)


async def test_replay_returns_the_stored_response():
    calls = []
    app = _app(calls)
    r1 = await _post(app, {"a": 1}, "k1")
    r2 = await _post(app, {"a": 1}, "k1")
    assert r1.status_code == r2.status_code == 201
    assert r2.json() == r1.json()
    assert r2.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in r1.headers
    assert len(calls) == 1


async def test_without_header_every_request_runs():
    calls = []
    app = _app(calls)
    await _post(app, {"a": 1})
    await _post(app, {"a": 1})
    assert len(calls) == 2


async def test_same_key_different_body_is_422():
    calls = []
    app = _app(calls)
    await _post(app, {"a": 1}, "k1")
    r = await _post(app, {"a": 2}, "k1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "idempotency_key_reused"
    assert len(calls) == 1


async def test_in_progress_duplicate_is_409():
    calls = []
    app = _app(calls)
    storage_key = "idem:key-1:POST /api/v1/things:k1"
    await idem_mod.memory_store.set(
        storage_key, json.dumps({"state": "pending", "fingerprint": "x"}), 60
    )
    r = await _post(app, {"a": 1}, "k1")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "idempotency_in_progress"
    assert calls == []


async def test_keys_are_scoped_per_credential():
    calls = []
    await _post(_app(calls, key_id="key-1"), {"a": 1}, "shared")
    r = await _post(_app(calls, key_id="key-2"), {"a": 1}, "shared")
    assert "idempotent-replayed" not in r.headers
    assert len(calls) == 2


async def test_failed_request_releases_the_key():
    calls = []
    app = _app(calls)
    r = await _post(app, {"fail": True}, "k1")
    assert r.status_code == 500
    assert await idem_mod.memory_store.get("idem:key-1:POST /api/v1/things:k1") is None


async def test_invalid_key_is_400():
    calls = []
    r = await _post(_app(calls), {"a": 1}, "x" * 300)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_idempotency_key"


async def test_redis_store_is_used_outside_tests(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.data = {}

        def get(self, k):
            return self.data.get(k)

        def set(self, k, v, nx=False, ex=None):
            if nx and k in self.data:
                return None
            self.data[k] = v
            return True

        def delete(self, k):
            self.data.pop(k, None)

    from services import rate_limiter as rl

    fake = FakeRedis()
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setattr(rl.rate_limiter, "redis_client", fake)
    store = idem_mod.get_store()
    assert isinstance(store, idem_mod.RedisStore)
    assert await store.set_nx("a", "1", 10) is True
    assert await store.set_nx("a", "2", 10) is False
    assert await store.get("a") == "1"
    await store.delete("a")
    assert await store.get("a") is None
    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
    assert idem_mod.get_store() is idem_mod.memory_store
