"""Response headers and CORS of the public API (pure ASGI, ``/api/v1`` only).

* **CORS.** The public API is called from any origin with a bearer key, never
  with cookies, so it answers ``Access-Control-Allow-Origin: *`` without
  ``Access-Control-Allow-Credentials``. Preflights (``OPTIONS`` with
  ``Access-Control-Request-Method``) are answered here, before the app-wide
  ``CORSMiddleware`` (which only knows the BenGER frontends and allows
  credentials) can see them; on ordinary responses this middleware replaces
  whatever ``Access-Control-*`` headers the inner middleware set. Every
  other path keeps the app-wide CORS policy untouched.
* **Versioning.** Every response carries ``X-API-Version: 1``; operations
  listed in :data:`_SUNSETS` also carry
  ``X-API-Deprecated: true; sunset=<date>``.

``X-Request-ID`` and ``X-RateLimit-*`` come from
``middleware.api_usage.ApiUsageMiddleware``, which runs inside this one.
"""

from __future__ import annotations

from typing import Dict, Optional

from routers.v1._errors import is_v1_path

API_VERSION = "1"

ALLOW_METHODS = "GET, POST, PATCH, DELETE, OPTIONS"
ALLOW_HEADERS = "Authorization, Content-Type, Idempotency-Key, If-None-Match, X-Request-ID"
EXPOSE_HEADERS = (
    "ETag, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, "
    "X-API-Version, X-Request-ID, Retry-After, Idempotent-Replayed, Last-Modified"
)
PREFLIGHT_MAX_AGE = "600"

#: Deprecated operations: ``"METHOD /api/v1/route/{template}"`` -> sunset
#: date (ISO, at least six months after the deprecation is announced, see
#: docs/public-api.md). Empty while nothing is deprecated.
_SUNSETS: Dict[str, str] = {}


def sunset_for(method: Optional[str], route_path: Optional[str]) -> Optional[str]:
    if not method or not route_path:
        return None
    return _SUNSETS.get(f"{method.upper()} {route_path}")


def _header(scope, name: bytes) -> Optional[bytes]:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            return value
    return None


def _cors_headers() -> list:
    return [
        (b"access-control-allow-origin", b"*"),
        (b"access-control-expose-headers", EXPOSE_HEADERS.encode("latin-1")),
    ]


class V1HeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not is_v1_path(
            scope.get("path"), scope.get("root_path") or ""
        ):
            return await self.app(scope, receive, send)

        if scope.get("method") == "OPTIONS" and _header(
            scope, b"access-control-request-method"
        ):
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [
                        (b"access-control-allow-origin", b"*"),
                        (b"access-control-allow-methods", ALLOW_METHODS.encode("latin-1")),
                        (b"access-control-allow-headers", ALLOW_HEADERS.encode("latin-1")),
                        (b"access-control-max-age", PREFLIGHT_MAX_AGE.encode("latin-1")),
                        (b"x-api-version", API_VERSION.encode("latin-1")),
                        (b"content-length", b"0"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in (message.get("headers") or [])
                    if not k.lower().startswith(b"access-control-")
                ]
                headers.extend(_cors_headers())
                headers.append((b"x-api-version", API_VERSION.encode("latin-1")))
                route = scope.get("route")
                sunset = sunset_for(scope.get("method"), getattr(route, "path", None))
                if sunset:
                    headers.append(
                        (b"x-api-deprecated", f"true; sunset={sunset}".encode("latin-1"))
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
