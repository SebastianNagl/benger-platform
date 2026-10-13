"""Overlay routers from get_v1_routers() mount under /api/v1."""

from datetime import datetime, timezone

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.routing import iter_route_contexts
from httpx import ASGITransport, AsyncClient

from auth_module import require_user
from auth_module.models import User as AuthUser
from auth_module.principal import Principal
from routers.v1 import include_overlay_v1_routers, install_v1
from routers.v1._deps import require_scope, unscoped_v1_routes
from routers.v1.docs import build_v1_openapi


def _fake_overlay_router() -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status(principal: Principal = Depends(require_scope("compliance:read"))):
        return {"kind": principal.kind}

    return router


def _app(overlays) -> FastAPI:
    app = FastAPI()
    install_v1(app, overlay_routers=overlays)
    return app


def test_overlay_router_is_mounted_under_the_prefix():
    app = _app([(_fake_overlay_router(), {"prefix": "/compliance", "tags": ["compliance"]})])
    spec = build_v1_openapi(app)
    assert spec["paths"]["/api/v1/compliance/status"]["get"]["x-benger-scopes"] == [
        "compliance:read"
    ]
    assert "/api/v1/compliance/status" not in build_v1_openapi(app, platform_only=True)["paths"]
    assert unscoped_v1_routes(app) == []


async def test_overlay_route_answers_with_scopes_and_envelope():
    app = _app([(_fake_overlay_router(), {"prefix": "compliance"})])
    holder = {}

    def _user(request: Request):
        request.state.principal = holder["p"]
        return AuthUser(
            id="u1", username="u1", email="u1@x.org", name="U",
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[require_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        holder["p"] = Principal(kind="api_key", user_id="u1", api_key_id="k", scopes=frozenset())
        r = await c.get("/api/v1/compliance/status")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "insufficient_scope"
        holder["p"] = Principal(
            kind="api_key", user_id="u1", api_key_id="k", scopes=frozenset({"compliance:read"})
        )
        r = await c.get("/api/v1/compliance/status")
        assert r.status_code == 200 and r.json() == {"kind": "api_key"}


def test_collision_with_a_platform_route_fails():
    router = APIRouter()

    @router.get("/me")
    async def me(principal=Depends(require_scope())):
        return {}

    with pytest.raises(RuntimeError, match="GET /api/v1/me"):
        _app([(router, {})])


def test_collision_between_overlays_fails():
    with pytest.raises(RuntimeError, match="/api/v1/x/status"):
        _app(
            [
                (_fake_overlay_router(), {"prefix": "/x"}),
                (_fake_overlay_router(), {"prefix": "/x"}),
            ]
        )


def test_unscoped_overlay_route_is_reported():
    router = APIRouter()

    @router.get("/leak")
    async def leak(user=Depends(require_user)):
        return {}

    app = _app([(router, {"prefix": "/bad"})])
    assert unscoped_v1_routes(app) == ["GET /api/v1/bad/leak"]


def test_overlays_default_to_the_extension_registry(monkeypatch):
    import extensions

    monkeypatch.setattr(
        extensions,
        "get_v1_routers_all",
        lambda: [(_fake_overlay_router(), {"prefix": "/fake"})],
    )
    app = FastAPI()
    include_overlay_v1_routers(app)
    assert any(
        getattr(r, "path", None) == "/api/v1/fake/status" for r in iter_route_contexts(app.routes)
    )


def test_main_app_mounts_the_platform_routes():
    from main import app

    paths = set(build_v1_openapi(app)["paths"])
    assert {
        "/api/v1/me",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/tasks",
        "/api/v1/projects/{project_id}/tasks/{task_id}",
        "/api/v1/projects/{project_id}/exports",
        "/api/v1/exports/{job_id}",
        "/api/v1/exports/{job_id}/download",
    } <= paths
