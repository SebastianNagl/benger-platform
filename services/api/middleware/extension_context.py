"""Per-request extension activation context (pure ASGI, core 2.41).

Sets ``extension_activation``'s :class:`ExtContext` for every HTTP and
WebSocket request: the user id comes from the session JWT (the
``access_token`` cookie, else ``Authorization: Bearer``), verified with the
platform's token check and **without any database access**. Access keys
(``Bearer bgr_...``) and invalid or missing tokens give an anonymous
context; the ``/api/v1`` gate adds the key's organization later
(``feature_flags.deps.require_extension_active``).

Deactivated accounts keep their user id here: the context only decides
which extension packages run, the auth dependencies still refuse them.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Optional

import extension_activation as activation


def _header(scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except Exception:  # pragma: no cover
                return None
    return None


def _token(scope) -> Optional[str]:
    raw_cookie = _header(scope, b"cookie")
    if raw_cookie:
        try:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get("access_token")
            if morsel is not None and morsel.value:
                return morsel.value
        except Exception:
            pass
    auth = _header(scope, b"authorization")
    if auth and auth.startswith("Bearer ") and not auth.startswith("Bearer bgr_"):
        return auth.split(" ", 1)[1].strip() or None
    return None


def user_id_from_scope(scope) -> Optional[str]:
    """The ``user_id`` claim of a valid session access token, else None."""
    token = _token(scope)
    if not token:
        return None
    try:
        from auth_module.service import verify_token

        payload = verify_token(token)
    except Exception:
        return None
    user_id = payload.get("user_id") if isinstance(payload, dict) else None
    return str(user_id) if user_id else None


class ExtensionContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        ctx = activation.new_context(
            user_id=user_id_from_scope(scope), kind=activation.KIND_REQUEST
        )
        token = activation.set_context(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            activation.reset_context(token)
