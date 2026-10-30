"""Access keys on the full API (pure ASGI, core 2.45).

For every HTTP request that carries ``Authorization: Bearer bgr_...`` and
is not under ``/api/v1`` (v1 routes check keys themselves) this middleware:

1. matches the route the router will pick and looks up its rule
   (``app/core/key_routes.py``); a route closed to keys answers 401
   ``api_key_not_allowed_here``;
2. authenticates the key (401 ``invalid_api_key`` / ``api_key_revoked`` /
   ``api_key_expired`` ...);
3. checks the ``public_api`` gate for the key's user and organization (404
   ``feature_disabled`` while the feature is off for them);
4. checks the rule's scopes (403 ``insufficient_scope``);
5. checks the projects the request names (path parameters, plus the rule's
   query/body bindings): a key never reaches a project outside its project
   list or group, nor a Safe Exam Browser project (404 ``not_found``). A
   project-restricted key may call a route that names no project only when
   the rule is ``neutral`` (403 ``key_project_restricted``);
6. counts the request against the key's rate limits (429 ``rate_limited``).

On success the key's principal and user go to ``request.state``
(``principal``, ``key_gate_user``) where the auth dependencies
(``auth_module.dependencies``) pick them up without a second lookup, and
the extension activation context gets the key's user and organization.

Errors use the browser API's shape ``{"detail": {"code", "message"}}``.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

V1_PREFIX = "/api/v1"
#: Probes accept keys without checking them (no auth dependency there).
PASS_THROUGH_PATHS = frozenset({"/health", "/healthz"})
#: Largest JSON body read for a body binding (restricted keys only).
MAX_BOUND_BODY = 1024 * 1024
INDEX_ATTR = "_benger_key_route_index"


def _header(scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except Exception:  # pragma: no cover
                return None
    return None


def _key_from_scope(scope) -> Optional[str]:
    value = _header(scope, b"authorization")
    if not value or not value.startswith("Bearer bgr_"):
        return None
    return value[len("Bearer "):].strip() or None


def _path(scope) -> str:
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def _error(status_code: int, code: str, message: str, headers=None, **extra) -> JSONResponse:
    detail = {"code": code, "message": message, **extra}
    return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)


def _from_http_exception(exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"code": "error", "message": str(detail)}
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


def get_index(app) -> list:
    """The route index of ``app`` (built once, cached on the app)."""
    index = getattr(app, INDEX_ATTR, None)
    if index is None:
        from app.core.key_routes import build_index

        index = build_index(app)
        try:
            setattr(app, INDEX_ATTR, index)
        except Exception:  # pragma: no cover
            pass
    return index


def reset_index(app) -> None:
    """Forget the cached index (tests that mount routes later)."""
    if hasattr(app, INDEX_ATTR):
        delattr(app, INDEX_ATTR)


@asynccontextmanager
async def _async_db(app):
    """An AsyncSession from ``get_async_db``, honouring dependency
    overrides (the test suite runs on a SAVEPOINT session)."""
    from database import get_async_db

    provider = getattr(app, "dependency_overrides", {}).get(get_async_db, get_async_db)
    result = provider()
    if hasattr(result, "__anext__"):
        db = await result.__anext__()
        try:
            yield db
        finally:
            try:
                await result.aclose()
            except Exception:  # pragma: no cover
                pass
        return
    if hasattr(result, "__await__"):
        result = await result
    yield result


# --------------------------------------------------------------------------- #
# Project bindings
# --------------------------------------------------------------------------- #


def _resolver_statement(kind: str, value: str):
    """``SELECT project_id`` for one bound id, or None for ``project``."""
    from sqlalchemy import select

    if kind == "project":
        return None
    if kind == "task":
        from project_models import Task

        return select(Task.project_id).where(Task.id == value)
    if kind == "annotation":
        from project_models import Annotation

        return select(Annotation.project_id).where(Annotation.id == value)
    if kind == "evaluation_run":
        from models import EvaluationRun

        return select(EvaluationRun.project_id).where(EvaluationRun.id == value)
    if kind == "response_generation":
        from models import ResponseGeneration

        return select(ResponseGeneration.project_id).where(ResponseGeneration.id == value)
    if kind == "report":
        from report_models import ProjectReport

        return select(ProjectReport.project_id).where(ProjectReport.id == value)
    return _overlay_resolvers[kind](value)


#: Overlay resolvers: kind -> callable(value) returning a ``SELECT project_id``.
_overlay_resolvers: Dict[str, Any] = {}


def register_project_resolver(kind: str, statement_for) -> None:
    """Add a resolver kind (``statement_for(value)`` returns a SELECT of one
    project id) for :func:`app.core.key_routes.register_project_param`."""
    _overlay_resolvers[kind] = statement_for


def _as_ids(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None and str(v)]
    return [str(value)] if str(value) else []


def _binding_values(rule, scope, body: Optional[bytes]) -> Dict[str, List[str]]:
    """``{param: [ids]}`` from the rule's query/body bindings."""
    from urllib.parse import parse_qs

    found: Dict[str, List[str]] = {}
    query = None
    payload = None
    for spec in rule.bind:
        source, _, name = spec.partition(":")
        if source == "query":
            if query is None:
                raw = scope.get("query_string") or b""
                query = parse_qs(raw.decode("latin-1"))
            values = query.get(name) or []
        elif source == "body":
            if payload is None:
                try:
                    payload = json.loads(body) if body else {}
                except ValueError:
                    payload = {}
            values = _as_ids(payload.get(name)) if isinstance(payload, dict) else []
        else:  # pragma: no cover - rejected by the rule tests
            continue
        if values:
            # project_ids / task_id ... map onto the path-parameter names.
            key = name[:-1] if name.endswith("_ids") else name
            found.setdefault(key, []).extend(values)
    return found


async def _bound_project_ids(
    db, bindings: Dict[str, Iterable[str]], owner: str
) -> Optional[Set[str]]:
    """Project ids the request names; None when one bound id is unknown
    (the handler answers 404 for it)."""
    from app.core.key_routes import project_params_for

    params = project_params_for(owner)
    projects: Set[str] = set()
    for param, values in bindings.items():
        kind = params.get(param)
        if kind is None:
            continue
        for value in values:
            stmt = _resolver_statement(kind, str(value))
            if stmt is None:
                projects.add(str(value))
                continue
            project_id = (await db.execute(stmt)).scalar_one_or_none()
            if project_id is None:
                return None
            projects.add(str(project_id))
    return projects


async def _check_projects(db, principal, project_ids: Set[str]) -> bool:
    from sqlalchemy import select

    from project_models import Project
    from routers.v1._deps import key_may_see_project

    for project_id in sorted(project_ids):
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if project is None:
            continue  # the handler answers 404
        if not await key_may_see_project(db, principal, project):
            return False
    return True


def _restricted(principal) -> bool:
    return principal.project_ids is not None or principal.group_id is not None


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class KeyGateMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        plain = _key_from_scope(scope)
        if plain is None:
            return await self.app(scope, receive, send)
        path = _path(scope)
        if path == V1_PREFIX or path.startswith(V1_PREFIX + "/") or path in PASS_THROUGH_PATHS:
            return await self.app(scope, receive, send)

        fastapi_app = scope.get("app")
        from app.core.key_routes import match

        entry, params = match(get_index(fastapi_app), scope.get("method", "GET"), path)
        if entry is None:
            # No such route: the router answers 404/405 and nothing
            # authenticates the key.
            return await self.app(scope, receive, send)
        rule = entry.rule
        if rule is None or not rule.allowed:
            response = _error(
                401,
                "api_key_not_allowed_here",
                "Access keys cannot be used on this endpoint",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
            return await response(scope, receive, send)

        body: Optional[bytes] = None
        receive_next = receive
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            # The usage log names the route even when the gate answers.
            state["key_gate_route"] = entry.template
            state["key_gate_project"] = (params or {}).get("project_id")
        try:
            response, body = await self._check(fastapi_app, scope, receive, plain, entry, params)
        except HTTPException as exc:
            response = _from_http_exception(exc)
        if response is not None:
            return await response(scope, receive, send)
        if body is not None:
            receive_next = _replay(body, receive)
        await self.app(scope, receive_next, send)

    async def _check(self, app, scope, receive, plain, entry, params):
        from app.core.scopes import scopes_satisfied
        from auth_module.service import db_user_to_user
        from routers.v1._deps import _insufficient_scope
        from services.api_key_service import authenticate_api_key
        from services.rate_limiter import enforce_key_rate_limit

        rule = entry.rule
        body: Optional[bytes] = None
        async with _async_db(app) as db:
            auth = await authenticate_api_key(db, plain, path=None, check_path=False)
            principal = auth.principal
            # Authenticated from here on: denials below are key usage too.
            _remember_principal(scope, principal, rule)
            if not await _public_api_enabled(db, auth.user, principal):
                return (
                    _error(404, "feature_disabled", "Not found", flag="public_api"),
                    None,
                )
            if not scopes_satisfied(principal.scopes, rule.scopes):
                raise _insufficient_scope(rule.scopes)

            bindings: Dict[str, List[str]] = {
                k: [str(v)] for k, v in (params or {}).items()
            }
            if rule.bind:
                if any(s.startswith("body:") for s in rule.bind) and _restricted(principal):
                    body = await _read_body(receive)
                    if body is None:
                        return (
                            _error(
                                413,
                                "request_too_large",
                                "Request body too large for a project-restricted key",
                            ),
                            None,
                        )
                for key, values in _binding_values(rule, scope, body).items():
                    bindings.setdefault(key, []).extend(values)
            projects = await _bound_project_ids(db, bindings, entry.owner)
            if projects is None:
                # An id that leads nowhere: the handler answers 404, but a
                # restricted key learns nothing either way.
                if _restricted(principal):
                    return _error(404, "not_found", "Not found"), body
                projects = set()
            elif projects and not await _check_projects(db, principal, projects):
                return _error(404, "not_found", "Not found"), body
            if _restricted(principal) and not projects and not rule.neutral:
                return (
                    _error(
                        403,
                        "key_project_restricted",
                        "This access key is limited to some projects; this endpoint "
                        "names no project",
                    ),
                    body,
                )
            user = await db.run_sync(lambda _s: db_user_to_user(auth.user))

        request = Request(scope)
        request.state.principal = principal
        await enforce_key_rate_limit(request, principal)
        request.state.key_gate_user = user
        _set_activation_context(principal, user)
        return None, body


def _remember_principal(scope, principal, rule) -> None:
    state = scope.setdefault("state", {})
    if isinstance(state, dict):
        state["principal"] = principal
        state["scope_used"] = " ".join(sorted(rule.scopes))[:64] or None


async def _public_api_enabled(db, user, principal) -> bool:
    from extensions import public_api_enabled

    return await public_api_enabled(
        db,
        user,
        organization_id=principal.organization_id if principal.is_api_key else None,
    )


def _set_activation_context(principal, user) -> None:
    try:
        import extension_activation as activation

        ctx = activation.current_context()
        ctx.user_id = str(user.id)
        if principal.organization_id:
            ctx.org_ids = frozenset({str(principal.organization_id)})
        ctx.memo.clear()
    except Exception:  # pragma: no cover - context is best effort
        logger.debug("could not set the activation context for a key", exc_info=True)


async def _read_body(receive) -> Optional[bytes]:
    chunks = []
    size = 0
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break
        chunk = message.get("body", b"") or b""
        size += len(chunk)
        if size > MAX_BOUND_BODY:
            return None
        chunks.append(chunk)
        if not message.get("more_body"):
            break
    return b"".join(chunks)


def _replay(body: bytes, receive):
    sent = False

    async def _receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return _receive
