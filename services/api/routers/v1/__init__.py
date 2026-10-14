"""The public, versioned API (``/api/v1``).

Every route here is reachable with an access key (``Authorization: Bearer
bgr_...``) as well as with a browser session, and must declare the scopes
it needs through ``routers.v1._deps.require_scope`` (or
``v1_project_access``). ``assert_v1_routes_scoped`` enforces that at
startup.

:func:`install_v1` wires the package into the app: the platform routes, the
overlay routes from ``extensions.get_v1_routers_all()`` (mounted under
``/api/v1`` followed by the overlay router's own prefix; a path that
collides with an existing v1 route fails startup), the error-envelope
handlers and the CORS/version middleware. The v1 surface is part of the main
app on purpose (no mounted sub-application), so dependency overrides and
the usage middleware apply to it like to every other route.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Set, Tuple

from fastapi import APIRouter, Depends, FastAPI

V1_PREFIX = "/api/v1"


def build_v1_router() -> APIRouter:
    from routers.v1 import docs, exports, me, projects, tasks

    from routers.public_api_gate import require_public_api, require_public_api_public

    # Unreleased: the whole surface answers 404 feature_disabled unless the
    # public_api gate is open for the caller. The docs need no login, so they
    # get the anonymous-capable variant.
    router = APIRouter(prefix=V1_PREFIX)
    router.include_router(me.router, dependencies=[Depends(require_public_api)])
    router.include_router(projects.router, dependencies=[Depends(require_public_api)])
    router.include_router(tasks.router, dependencies=[Depends(require_public_api)])
    router.include_router(exports.router, dependencies=[Depends(require_public_api)])
    router.include_router(docs.router, dependencies=[Depends(require_public_api_public)])
    return router


def _route_keys(routes: Iterable) -> Set[Tuple[str, str]]:
    """``{(METHOD, path)}`` of ``routes`` with included routers flattened."""
    try:
        from fastapi.routing import iter_route_contexts

        contexts = list(iter_route_contexts(list(routes)))
    except ImportError:  # pragma: no cover - older FastAPI flattens itself
        contexts = list(routes)
    keys: Set[Tuple[str, str]] = set()
    for route in contexts:
        path = getattr(route, "path", None)
        if not path:
            continue
        methods = getattr(route, "methods", None) or {"*"}
        for method in methods:
            keys.add((method.upper(), path))
    return keys


def _v1_keys(app: FastAPI) -> Set[Tuple[str, str]]:
    return {
        key
        for key in _route_keys(app.routes)
        if key[1] == V1_PREFIX or key[1].startswith(V1_PREFIX + "/")
    }


def include_overlay_v1_routers(
    app: FastAPI, overlay_routers: Optional[Sequence[Tuple[APIRouter, dict]]] = None
) -> None:
    """Mount overlay routers under ``/api/v1``.

    ``overlay_routers`` defaults to ``extensions.get_v1_routers_all()``. A
    router's own ``prefix`` kwarg is appended after ``/api/v1``. Raises
    ``RuntimeError`` when an overlay path collides with an existing v1 route.
    """
    if overlay_routers is None:
        from extensions import get_v1_routers_all

        overlay_routers = get_v1_routers_all()
    for router, kwargs in overlay_routers or ():
        kwargs = dict(kwargs or {})
        own = (kwargs.pop("prefix", "") or "").rstrip("/")
        if own and not own.startswith("/"):
            own = "/" + own
        prefix = V1_PREFIX + own
        existing = _v1_keys(app)
        incoming = {
            (method, prefix + path)
            for method, path in _route_keys(router.routes)
        }
        clash = sorted(existing & incoming)
        if clash:
            raise RuntimeError(
                "Overlay /api/v1 routes collide with existing ones: "
                + "; ".join(f"{m} {p}" for m, p in clash)
            )
        from routers.public_api_gate import require_public_api

        # Overlay routes share the platform's availability gate.
        kwargs["dependencies"] = [
            Depends(require_public_api),
            *(kwargs.get("dependencies") or ()),
        ]
        app.include_router(router, prefix=prefix, **kwargs)


def install_v1(app: FastAPI, overlay_routers=None) -> None:
    """Platform v1 routes, overlay v1 routes and the v1 exception handlers.
    The CORS/version middleware is added separately (``V1HeadersMiddleware``)
    because middleware order matters."""
    from routers.v1._errors import install_v1_exception_handlers

    app.include_router(build_v1_router())
    include_overlay_v1_routers(app, overlay_routers)
    install_v1_exception_handlers(app)
