"""Usage logging and rate-limit headers for ``/api/v1`` (pure ASGI).

For every HTTP request under ``/api/v1`` this middleware:

* makes sure the response carries ``X-Request-ID`` (the caller's, when it
  sent one, otherwise a fresh id);
* adds ``X-RateLimit-Limit/-Remaining/-Reset`` when the key rate limiter
  stored its numbers on ``request.state.rate_limit``;
* after the response, hands one usage event to
  ``services.api_usage_writer.enqueue`` when the request was made with an
  access key (``request.state.principal.kind == "api_key"``).

The event records the route template (``scope["route"].path``), never the
raw path, and no request or response body. The client IP is reduced per
``API_USAGE_IP_MODE``.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

V1_PREFIX = "/api/v1"


def _header(scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except Exception:  # pragma: no cover
                return None
    return None


def _client_ip(scope) -> Optional[str]:
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else None


def _int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class ApiUsageMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path") or ""
        root = scope.get("root_path") or ""
        if root and path.startswith(root):
            path = path[len(root):]
        if not (path == V1_PREFIX or path.startswith(V1_PREFIX + "/")):
            return await self.app(scope, receive, send)

        started = time.perf_counter()
        request_id = (_header(scope, b"x-request-id") or "")[:64] or uuid.uuid4().hex
        sent_request_id = _header(scope, b"x-request-id") is not None
        result: Dict[str, Any] = {"status": None, "bytes": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                result["status"] = message.get("status")
                headers = list(message.get("headers") or [])
                names = {k.lower() for k, _ in headers}
                if not sent_request_id and b"x-request-id" not in names:
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                rate = (scope.get("state") or {}).get("rate_limit")
                if isinstance(rate, dict) and b"x-ratelimit-limit" not in names:
                    for name, key in (
                        (b"x-ratelimit-limit", "limit"),
                        (b"x-ratelimit-remaining", "remaining"),
                        (b"x-ratelimit-reset", "reset"),
                    ):
                        if rate.get(key) is not None:
                            headers.append((name, str(rate[key]).encode("latin-1")))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                result["bytes"] += len(message.get("body") or b"")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                self._record(scope, request_id, result, started)
            except Exception:  # pragma: no cover - logging must not break requests
                pass

    def _record(self, scope, request_id, result, started) -> None:
        state = scope.get("state") or {}
        principal = state.get("principal")
        if principal is None or getattr(principal, "kind", None) != "api_key":
            return
        from services import api_usage_writer
        from services.api_key_service import mask_ip

        route = scope.get("route")
        template = getattr(route, "path", None)
        path_params = scope.get("path_params") or {}
        event = {
            "api_key_id": principal.api_key_id,
            "key_prefix": principal.key_prefix,
            "organization_id": principal.organization_id,
            "user_id": principal.user_id,
            "request_id": request_id,
            "method": scope.get("method"),
            "route": template or "(unmatched)",
            "project_id": path_params.get("project_id"),
            "status_code": result["status"] or 500,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "scope_used": state.get("scope_used"),
            "ip_address": mask_ip(_client_ip(scope)),
            "user_agent": _header(scope, b"user-agent"),
            "request_bytes": _int(_header(scope, b"content-length")),
            "response_bytes": result["bytes"],
            "created_at": datetime.now(timezone.utc),
        }
        api_usage_writer.enqueue(event)
