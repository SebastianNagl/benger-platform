"""``GET /api/v1/reference/openapi.json`` and ``GET /api/v1/reference``.

The reference of the full API (core 2.45): every route outside ``/api/v1``
an access key may call, with the scopes from ``app/core/key_routes.py``
under ``x-benger-scopes``. Unlike the v1 spec these routes are the ones the
browser uses and are not versioned; the spec says so in its description
and marks each operation ``x-benger-stability: unversioned``.

Both endpoints share the v1 docs gate (public while the feature is open to
everyone).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute

from routers.v1._deps import V1_PREFIX, _effective_routes
from routers.v1.docs import CANONICAL_SERVER_URL, _public_docs_route, server_url_for

router = APIRouter(tags=["docs"])

TITLE = "BenGER Full API"
VERSION = "unversioned"

DESCRIPTION = """\
Every endpoint of the BenGER app that an access key may call: the same
routes the browser uses, for scripts and pipelines that need more than the
versioned `/api/v1`.

Authenticate with an access key: `Authorization: Bearer bgr_<env>_<id>_<secret>`.
Each operation lists the scopes it needs under `x-benger-scopes`; the
handler's own checks (project roles, organization admin) still apply to the
key's user.

These routes are **not versioned**: they may change with any release. Use
`/api/v1` where it covers your need. Errors use FastAPI's shape
`{"detail": ...}`, usually `{"detail": {"code", "message"}}`. See
docs/full-api.md in the platform repository for the guide.
"""


def reference_routes(app: FastAPI, *, platform_only: bool = False) -> List[Tuple[Any, Any]]:
    """``(effective_route, IndexedRoute-per-method)`` of every key-capable
    route outside ``/api/v1``."""
    from middleware.key_gate import get_index

    allowed = {
        (e.method, e.template): e
        for e in get_index(app)
        if e.rule is not None and e.rule.allowed
        and (not platform_only or e.owner == "platform")
    }
    out = []
    for original, route in _effective_routes(app):
        if not isinstance(original, APIRoute) or not route.include_in_schema:
            continue
        path = getattr(route, "path", "") or ""
        if path == V1_PREFIX or path.startswith(V1_PREFIX + "/"):
            continue
        entries = {
            m: allowed[(m, path)] for m in (route.methods or ()) if (m, path) in allowed
        }
        if entries:
            out.append((route, entries))
    return out


def build_reference_openapi(
    app: FastAPI, server_url: Optional[str] = None, *, platform_only: bool = False
) -> Dict[str, Any]:
    pairs = reference_routes(app, platform_only=platform_only)
    schema = get_openapi(
        title=TITLE,
        version=VERSION,
        openapi_version="3.1.0",
        description=DESCRIPTION,
        routes=[route for route, _ in pairs],
        servers=[{"url": server_url}] if server_url else None,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "accessKey": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "bgr_<env>_<id>_<secret>",
        }
    }
    schema["security"] = [{"accessKey": []}]
    # Several route objects can share a path (one per method): collect the
    # key-capable methods per path first, then annotate and prune.
    by_path: Dict[str, Dict[str, Any]] = {}
    for route, entries in pairs:
        by_path.setdefault(route.path_format, {}).update(entries)
    paths = schema.get("paths", {})
    for path, item in list(paths.items()):
        entries = by_path.get(path, {})
        for method in list(item):
            entry = entries.get(method.upper())
            if entry is None:
                # A method of this path that keys may not call.
                item.pop(method)
                continue
            op = item[method]
            op["x-benger-scopes"] = list(entry.rule.scopes)
            op["x-benger-stability"] = "unversioned"
            if not entry.rule.neutral:
                op["x-benger-project-bound"] = True
        if not item:
            paths.pop(path)
    return schema


_cache: Dict[Tuple[int, Optional[str]], Dict[str, Any]] = {}


def reset_cache() -> None:
    _cache.clear()


@router.get(
    "/reference/openapi.json",
    include_in_schema=False,
    dependencies=[Depends(_public_docs_route)],
)
async def reference_openapi(request: Request):
    key = (id(request.app), server_url_for(request))
    if key not in _cache:
        _cache[key] = build_reference_openapi(request.app, key[1])
    return JSONResponse(_cache[key])


@router.get(
    "/reference",
    include_in_schema=False,
    response_class=HTMLResponse,
    dependencies=[Depends(_public_docs_route)],
)
async def reference_swagger_ui(request: Request):
    root = request.scope.get("root_path") or ""
    return get_swagger_ui_html(
        openapi_url=f"{root}{V1_PREFIX}/reference/openapi.json",
        title=f"{TITLE} - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": False, "tryItOutEnabled": False},
    )


def routes_markdown(app: FastAPI) -> str:
    """docs/full-api-routes.md: the access-key rule of every platform route
    (overlay routes are documented by their overlay)."""
    from app.core.key_routes import route_table

    lines = [
        "# Full API: routes and scopes",
        "",
        "Generated by `make generate-public-api-docs` from",
        "`services/api/app/core/key_routes.py`. Do not edit by hand. See",
        "[full-api.md](full-api.md) for how keys use these routes.",
        "",
        "`Scopes` lists what an access key needs (all of them); `-` means any",
        "valid key. `never` routes do not accept keys. `Project` says whether a",
        "key limited to projects or a group may call the route without naming a",
        "project (`any`) or only for its own projects (`bound`).",
        "",
        "| Method | Path | Scopes | Project |",
        "|---|---|---|---|",
    ]
    rows = sorted(route_table(app), key=lambda r: (r["path"], r["method"]))
    for row in rows:
        if not row["keys"]:
            scopes, bound = "never", ""
        else:
            scopes = ", ".join(f"`{s}`" for s in row["scopes"]) or "-"
            bound = "any" if row["neutral"] else "bound"
        lines.append(f"| {row['method']} | `{row['path']}` | {scopes} | {bound} |")
    return "\n".join(lines) + "\n"


def snapshot_reference(app: FastAPI) -> Dict[str, Any]:
    return build_reference_openapi(app, CANONICAL_SERVER_URL, platform_only=True)
