"""``GET /api/v1/openapi.json`` and ``GET /api/v1/docs``.

The public spec covers the ``/api/v1`` routes only (the internal API's
``/openapi.json`` stays a development aid, see ``INTERNAL_DOCS_ENABLED``).
Each operation lists the scopes it needs under ``x-benger-scopes``, read
from the ``require_scope`` markers of its dependencies. Both endpoints are
public: the spec describes the contract, not data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute

from routers.v1._deps import SCOPES_ATTR, V1_PREFIX, _effective_routes

router = APIRouter(tags=["docs"])

TITLE = "BenGER Public API"
VERSION = "1.0.0"
#: Server announced by the committed snapshot (docs/api-docs/openapi-v1.json).
CANONICAL_SERVER_URL = "https://api.what-a-benger.net"

DESCRIPTION = """\
Versioned, key-authenticated access to BenGER projects and tasks.

Authenticate with an access key: `Authorization: Bearer bgr_<env>_<id>_<secret>`.
Every operation lists the scopes it needs under `x-benger-scopes`. Errors use
the envelope `{"error": {"code", "message", "request_id", "details"}}`.
Lists are cursor-paginated (`limit`, `cursor`, `next_cursor`). See
docs/public-api.md in the platform repository for the full guide.
"""


def _public_docs_route() -> None:
    """Marks the two documentation routes as intentionally unauthenticated
    for ``assert_v1_routes_scoped`` (an empty scope set, no auth)."""
    return None


setattr(_public_docs_route, SCOPES_ATTR, frozenset())


def operation_scopes(route) -> List[str]:
    """Union of every scope marker in the route's dependency tree."""
    found: set = set()
    stack = [route.dependant]
    while stack:
        node = stack.pop()
        marker = getattr(getattr(node, "call", None), SCOPES_ATTR, None)
        if marker:
            found |= set(marker)
        stack.extend(getattr(node, "dependencies", []) or [])
    return sorted(found)


def _is_v1(path: Optional[str]) -> bool:
    return bool(path) and (path == V1_PREFIX or path.startswith(V1_PREFIX + "/"))


def v1_routes(app: FastAPI, *, platform_only: bool = False) -> list:
    """The effective v1 API routes of ``app`` (included routers flattened,
    see ``routers.v1._deps._effective_routes``)."""
    routes = []
    for original, route in _effective_routes(app):
        if not isinstance(original, APIRoute) or not _is_v1(getattr(route, "path", None)):
            continue
        if not route.include_in_schema:
            continue
        module = getattr(original.endpoint, "__module__", "") or ""
        if platform_only and not module.startswith("routers.v1"):
            continue
        routes.append(route)
    return routes


def build_v1_openapi(
    app: FastAPI, server_url: Optional[str] = None, *, platform_only: bool = False
) -> Dict[str, Any]:
    """The OpenAPI document of the public API (``platform_only`` drops
    overlay routes; the committed snapshot is built that way)."""
    routes = v1_routes(app, platform_only=platform_only)
    schema = get_openapi(
        title=TITLE,
        version=VERSION,
        openapi_version="3.1.0",
        description=DESCRIPTION,
        routes=routes,
        servers=[{"url": server_url}] if server_url else None,
        tags=[
            {"name": "me", "description": "The calling credential"},
            {"name": "projects", "description": "Projects the credential may read"},
            {"name": "tasks", "description": "Blinded task reads"},
            {"name": "exports", "description": "Full project exports"},
        ],
    )
    components = schema.setdefault("components", {})
    components["securitySchemes"] = {
        "accessKey": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "bgr_<env>_<id>_<secret>",
            "description": (
                "An access key created in BenGER (organization settings or profile). "
                "Sent as `Authorization: Bearer bgr_live_...`."
            ),
        }
    }
    schema["security"] = [{"accessKey": []}]
    for route in routes:
        item = schema.get("paths", {}).get(route.path_format, {})
        for method in route.methods or ():
            op = item.get(method.lower())
            if op is not None:
                op["x-benger-scopes"] = operation_scopes(route)
    return schema


_cache: Dict[Tuple[int, Optional[str]], Dict[str, Any]] = {}


def cached_v1_openapi(app: FastAPI, server_url: Optional[str]) -> Dict[str, Any]:
    key = (id(app), server_url)
    if key not in _cache:
        _cache[key] = build_v1_openapi(app, server_url)
    return _cache[key]


def reset_cache() -> None:
    _cache.clear()


def server_url_for(request: Request) -> str:
    from app.core.config import get_settings

    configured = get_settings().public_api_base_url
    if configured:
        return configured
    base = str(request.base_url).rstrip("/")
    root = request.scope.get("root_path") or ""
    if root and base.endswith(root):
        base = base[: -len(root)]
    return base


@router.get(
    "/openapi.json",
    include_in_schema=False,
    dependencies=[Depends(_public_docs_route)],
)
async def v1_openapi(request: Request):
    return JSONResponse(cached_v1_openapi(request.app, server_url_for(request)))


@router.get(
    "/docs",
    include_in_schema=False,
    response_class=HTMLResponse,
    dependencies=[Depends(_public_docs_route)],
)
async def v1_swagger_ui(request: Request):
    root = request.scope.get("root_path") or ""
    return get_swagger_ui_html(
        openapi_url=f"{root}{V1_PREFIX}/openapi.json",
        title=f"{TITLE} - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": False, "tryItOutEnabled": False},
    )


def snapshot_spec(app: FastAPI) -> Dict[str, Any]:
    """The spec committed as docs/api-docs/openapi-v1.json: platform routes
    only, announced under :data:`CANONICAL_SERVER_URL`."""
    return build_v1_openapi(app, CANONICAL_SERVER_URL, platform_only=True)


def scopes_markdown() -> str:
    """docs/public-api-scopes.md: the built-in scopes and presets (overlay
    scopes are documented by their overlay)."""
    from app.core.scopes import SCOPE_PRESETS, all_scopes

    lines = [
        "# Public API scopes",
        "",
        "Generated by `make generate-public-api-docs` from `services/api/app/core/scopes.py`.",
        "Do not edit by hand. See [public-api.md](public-api.md) for how scopes are used.",
        "",
        "| Scope | Description | Implies | Who may grant it |",
        "|---|---|---|---|",
    ]
    for scope in all_scopes():
        if scope.source != "platform":
            continue
        implies = ", ".join(f"`{s}`" for s in scope.implies) or "-"
        lines.append(
            f"| `{scope.name}` | {scope.description_en} ({scope.description_de}) "
            f"| {implies} | `{scope.grantable}` |"
        )
    lines += [
        "",
        "`grantable`: `any` (every key), `full_data_role` (personal keys and organization",
        "keys with role CONTRIBUTOR), `org_admin` (organization keys created by an",
        "organization admin), `personal_only` (personal keys only).",
        "",
        "## Presets",
        "",
        "| Preset | Scopes |",
        "|---|---|",
    ]
    for name, scopes in SCOPE_PRESETS.items():
        lines.append(f"| `{name}` | {', '.join(f'`{s}`' for s in scopes)} |")
    return "\n".join(lines) + "\n"
