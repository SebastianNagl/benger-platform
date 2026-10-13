"""``Idempotency-Key`` support for the public API's POST routes.

Usage in a handler::

    @router.post("/things")
    async def create(..., idem: IdempotencyContext = Depends(idempotent())):
        body = {...}
        await idem.save(201, body)
        return JSONResponse(status_code=201, content=body)

With the header present, the first request reserves the key (Redis
``SET NX``, keyed ``idem:{api_key_id or user_id}:{METHOD route}:{key}``):

* a duplicate arriving while the first one runs gets 409
  ``idempotency_in_progress``;
* once the handler called :meth:`IdempotencyContext.save`, the stored
  ``{status, body, fingerprint}`` is kept for 24 hours and a retry with the
  same request answers the stored response with ``Idempotent-Replayed: true``;
* a retry with the same key but a different request (method, path, query or
  body) gets 422 ``idempotency_key_reused``;
* when the handler fails, the reservation is dropped so the client may retry.

Without the header the route behaves as usual. When Redis is unavailable (or
in tests) an in-process store is used; it only protects one API process.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, Header, Request

from auth_module import require_user
from auth_module.principal import get_principal
from routers.v1._errors import IdempotentReplay, V1Error

IDEMPOTENCY_TTL_SECONDS = 24 * 3600
IN_PROGRESS_TTL_SECONDS = 120
MAX_KEY_LENGTH = 255


class MemoryStore:
    def __init__(self):
        self._data: Dict[str, Tuple[float, str]] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._data.items() if exp <= now]:
            self._data.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        self._prune()
        entry = self._data.get(key)
        return entry[1] if entry else None

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        self._prune()
        if key in self._data:
            return False
        self._data[key] = (time.monotonic() + ttl, value)
        return True

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._data[key] = (time.monotonic() + ttl, value)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


class RedisStore:
    def __init__(self, client):
        self.client = client

    async def get(self, key: str) -> Optional[str]:
        return await asyncio.to_thread(self.client.get, key)

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        return bool(await asyncio.to_thread(self.client.set, key, value, nx=True, ex=ttl))

    async def set(self, key: str, value: str, ttl: int) -> None:
        await asyncio.to_thread(self.client.set, key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete, key)


memory_store = MemoryStore()


def get_store():
    """Redis when the shared client is up (outside tests), else memory."""
    if os.environ.get("TESTING") == "true":
        return memory_store
    try:
        from services.rate_limiter import rate_limiter

        client = getattr(rate_limiter, "redis_client", None)
    except Exception:  # pragma: no cover - import problems fall back
        client = None
    return RedisStore(client) if client is not None else memory_store


class IdempotencyContext:
    def __init__(self, store=None, storage_key: Optional[str] = None, fingerprint: str = ""):
        self.store = store
        self.storage_key = storage_key
        self.fingerprint = fingerprint
        self.completed = False

    @property
    def active(self) -> bool:
        return self.storage_key is not None

    async def save(self, status_code: int, body: Any) -> None:
        """Store the response for replays (no-op without the header)."""
        if not self.active:
            return
        record = {
            "state": "done",
            "status": int(status_code),
            "body": body,
            "fingerprint": self.fingerprint,
        }
        await self.store.set(
            self.storage_key, json.dumps(record, default=str), IDEMPOTENCY_TTL_SECONDS
        )
        self.completed = True


def _fingerprint(request: Request, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update((request.method or "").encode())
    digest.update(b"\0")
    digest.update(request.url.path.encode())
    digest.update(b"\0")
    digest.update(str(request.url.query or "").encode())
    digest.update(b"\0")
    digest.update(body or b"")
    return digest.hexdigest()


def _check_record(raw: str, fingerprint: str) -> None:
    try:
        record = json.loads(raw)
    except Exception:
        record = {"state": "pending"}
    if record.get("state") != "done":
        raise V1Error(
            409,
            "idempotency_in_progress",
            "A request with this Idempotency-Key is still being processed",
        )
    if record.get("fingerprint") != fingerprint:
        raise V1Error(
            422,
            "idempotency_key_reused",
            "This Idempotency-Key was used for a different request",
        )
    raise IdempotentReplay(record.get("status") or 200, record.get("body"))


def idempotent():
    """Dependency factory; declare it after the route's scope dependency."""

    async def _idempotent(
        request: Request,
        user=Depends(require_user),
        idempotency_key: Optional[str] = Header(
            None,
            alias="Idempotency-Key",
            description=(
                "Optional client-chosen key (1 to 255 characters). Retries with "
                "the same key and request replay the first response for 24 hours."
            ),
        ),
    ):
        if idempotency_key is None:
            yield IdempotencyContext()
            return
        key = idempotency_key.strip()
        if not key or len(key) > MAX_KEY_LENGTH:
            raise V1Error(
                400,
                "invalid_idempotency_key",
                f"Idempotency-Key must be 1 to {MAX_KEY_LENGTH} characters",
            )
        principal = get_principal(request)
        owner = (principal.api_key_id if principal and principal.api_key_id else None) or str(
            user.id
        )
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        storage_key = f"idem:{owner}:{request.method} {route_path}:{key}"
        fingerprint = _fingerprint(request, await request.body())
        store = get_store()

        raw = await store.get(storage_key)
        if raw is not None:
            _check_record(raw, fingerprint)
        pending = json.dumps({"state": "pending", "fingerprint": fingerprint})
        if not await store.set_nx(storage_key, pending, IN_PROGRESS_TTL_SECONDS):
            raw = await store.get(storage_key)
            _check_record(raw or "{}", fingerprint)

        ctx = IdempotencyContext(store, storage_key, fingerprint)
        try:
            yield ctx
        finally:
            if not ctx.completed:
                try:
                    await store.delete(storage_key)
                except Exception:  # pragma: no cover - best effort
                    pass

    return _idempotent
