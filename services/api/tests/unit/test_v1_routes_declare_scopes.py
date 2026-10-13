"""Deny by default for /api/v1: every route declares its scopes, and the
scope / project dependencies answer as documented."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from auth_module import require_user
from auth_module.models import User as AuthUser
from auth_module.principal import Principal, session_principal
from database import get_async_db
from main import app as main_app
from project_models import Project, ProjectOrganization
from routers.v1._deps import (
    SCOPES_ATTR,
    assert_v1_routes_scoped,
    require_scope,
    unscoped_v1_routes,
    v1_project_access,
)
from tests.fixtures.access_keys import seed_world


def test_main_app_has_no_unscoped_v1_routes():
    assert unscoped_v1_routes(main_app) == []
    assert_v1_routes_scoped(main_app)


def test_unscoped_route_is_reported():
    app = FastAPI()

    @app.get("/api/v1/scoped", dependencies=[Depends(require_scope("projects:read"))])
    def scoped():
        return {}

    @app.get("/api/v1/me")
    def me(principal=Depends(require_scope())):
        return {}

    @app.get("/api/v1/leaky")
    def leaky(user=Depends(require_user)):
        return {}

    @app.get("/api/projects")
    def browser(user=Depends(require_user)):
        return {}

    assert unscoped_v1_routes(app) == ["GET /api/v1/leaky"]
    with pytest.raises(RuntimeError, match="/api/v1/leaky"):
        assert_v1_routes_scoped(app)


def test_nested_scope_marker_counts():
    app = FastAPI()
    inner = require_scope("tasks:read")

    def outer(p=Depends(inner)):
        return p

    @app.get("/api/v1/nested")
    def nested(x=Depends(outer)):
        return {}

    assert unscoped_v1_routes(app) == []


def test_markers_carry_the_scopes():
    assert getattr(require_scope("a:b", "c:d"), SCOPES_ATTR) == frozenset({"a:b", "c:d"})
    assert getattr(require_scope(), SCOPES_ATTR) == frozenset()
    assert getattr(v1_project_access("tasks:read"), SCOPES_ATTR) == frozenset({"tasks:read"})


# --------------------------------------------------------------------------- #
# Behaviour of the dependencies (require_user replaced by a principal double)
# --------------------------------------------------------------------------- #


def _auth_user(user_id: str) -> AuthUser:
    return AuthUser(
        id=user_id, username=f"u-{user_id[:6]}", email=f"{user_id[:6]}@x.org",
        name="U", created_at=datetime.now(timezone.utc),
    )


def _test_app(async_test_db, principal_holder):
    app = FastAPI()

    @app.get("/api/v1/scoped")
    async def scoped(p=Depends(require_scope("submissions:read"))):
        return {"kind": p.kind}

    @app.get("/api/v1/projects/{project_id}")
    async def project(access=Depends(v1_project_access("projects:read"))):
        return {"id": access.project.id, "tier": access.tier}

    def fake_require_user(request):
        principal = principal_holder["p"]
        request.state.principal = principal
        return _auth_user(principal.user_id)

    from fastapi import Request

    def _dep(request: Request):
        return fake_require_user(request)

    async def _db():
        yield async_test_db

    app.dependency_overrides[require_user] = _dep
    app.dependency_overrides[get_async_db] = _db
    return app


def _key(user_id, **kw):
    return Principal(kind="api_key", user_id=user_id, api_key_id=str(uuid.uuid4()),
                     key_prefix="bgr_test_abcdefgh", **kw)


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_insufficient_scope_403_with_header(async_test_db):
    holder = {"p": _key("u1", scopes=frozenset({"projects:read"}))}
    async with await _client(_test_app(async_test_db, holder)) as c:
        r = await c.get("/api/v1/scoped")
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "insufficient_scope"
        assert r.headers["www-authenticate"] == (
            'Bearer error="insufficient_scope", scope="submissions:read"'
        )
        holder["p"] = _key("u1", scopes=frozenset({"submissions:write"}))
        r = await c.get("/api/v1/scoped")
        assert r.status_code == 200 and r.json() == {"kind": "api_key"}
        holder["p"] = session_principal("u1")
        r = await c.get("/api/v1/scoped")
        assert r.status_code == 200 and r.json() == {"kind": "session"}


async def _project(db, owner_id, **kw):
    p = Project(id=str(uuid.uuid4()), title="v1 deps", created_by=owner_id, **kw)
    db.add(p)
    await db.flush()
    return p


async def test_project_allowlist_seb_and_group_restriction(async_test_db):
    db = async_test_db
    world = await seed_world(db)
    owner = world["member"]
    allowed = await _project(db, owner.id)
    other = await _project(db, owner.id)
    seb = await _project(db, owner.id, seb_required=True)
    grouped = await _project(db, owner.id)
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()), project_id=grouped.id, organization_id=world["org"].id,
            group_id=world["group"].id, assigned_by=owner.id,
        )
    )
    await db.flush()
    read = frozenset({"projects:read"})
    holder = {"p": _key(owner.id, scopes=read, project_ids=frozenset({allowed.id, seb.id}))}
    async with await _client(_test_app(db, holder)) as c:
        assert (await c.get(f"/api/v1/projects/{allowed.id}")).status_code == 200
        r = await c.get(f"/api/v1/projects/{other.id}")
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
        assert (await c.get(f"/api/v1/projects/{seb.id}")).status_code == 404
        assert (await c.get("/api/v1/projects/does-not-exist")).status_code == 404

        holder["p"] = _key(owner.id, scopes=read, organization_id=world["org"].id,
                           group_id=world["group"].id)
        assert (await c.get(f"/api/v1/projects/{grouped.id}")).status_code == 200
        assert (await c.get(f"/api/v1/projects/{allowed.id}")).status_code == 404

        holder["p"] = session_principal(owner.id)
        assert (await c.get(f"/api/v1/projects/{seb.id}")).status_code == 200
        assert (await c.get(f"/api/v1/projects/{other.id}")).status_code == 200


async def test_project_without_access_is_404_for_keys_403_for_sessions(async_test_db):
    db = async_test_db
    world = await seed_world(db, group=False)
    private = await _project(db, world["admin"].id, is_private=True)
    holder = {"p": _key(world["outsider"].id, scopes=frozenset({"projects:read"}))}
    async with await _client(_test_app(db, holder)) as c:
        assert (await c.get(f"/api/v1/projects/{private.id}")).status_code == 404
        holder["p"] = session_principal(world["outsider"].id)
        assert (await c.get(f"/api/v1/projects/{private.id}")).status_code == 403
