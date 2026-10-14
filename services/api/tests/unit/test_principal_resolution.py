"""How require_user / get_current_user / optional_user resolve the caller:
access key first (v1 only), then the session JWT (header first on v1,
cookie first elsewhere), with request.state.principal set either way."""

from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from auth_module import create_access_token
from auth_module.dependencies import (
    get_current_user,
    optional_user,
    require_superadmin,
    require_user,
)
from auth_module.principal import Principal, extract_api_key, get_principal
from auth_module.service import WebSocketAuthError, verify_token_for_websocket
from database import get_db
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world_sync


def _app(test_db) -> FastAPI:
    app = FastAPI()

    def _describe(request: Request, user):
        p = get_principal(request)
        return {
            "user_id": user.id if user else None,
            "kind": p.kind if p else None,
            "is_superadmin": user.is_superadmin if user else None,
        }

    @app.get("/api/v1/me")
    def v1_me(request: Request, user=Depends(require_user)):
        return _describe(request, user)

    @app.get("/api/v1/optional")
    def v1_optional(request: Request, user=Depends(optional_user)):
        return _describe(request, user)

    @app.get("/api/projects")
    def projects(request: Request, user=Depends(require_user)):
        return _describe(request, user)

    @app.get("/api/whoami")
    def whoami(request: Request, user=Depends(get_current_user)):
        return _describe(request, user)

    @app.get("/api/v1/admin-only")
    def admin_only(request: Request, user=Depends(require_superadmin)):
        return _describe(request, user)

    app.dependency_overrides[get_db] = lambda: test_db
    return app


@pytest.fixture
def world(test_db):
    return seed_world_sync(test_db)


@pytest.fixture
def client(test_db):
    return TestClient(_app(test_db))


def _personal_key(test_db, user):
    key, plain = svc.create_personal_key_sync(
        test_db, user.id, {"name": "k", "scopes": ["projects:read"]}
    )
    return key, plain


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_key_on_browser_route_is_not_allowed_here(client, test_db, world):
    _, plain = _personal_key(test_db, world["member"])
    r = client.get("/api/projects", headers=_bearer(plain))
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "api_key_not_allowed_here"
    assert r.headers["www-authenticate"] == 'Bearer error="invalid_token"'


def test_key_on_optional_auth_browser_route_still_401(client, test_db, world):
    _, plain = _personal_key(test_db, world["member"])
    r = client.get("/api/whoami", headers=_bearer(plain))
    assert r.status_code == 401


def test_key_on_v1_route_resolves_user_and_principal(client, test_db, world):
    _, plain = _personal_key(test_db, world["member"])
    r = client.get("/api/v1/me", headers=_bearer(plain))
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": world["member"].id, "kind": "api_key", "is_superadmin": False}


def test_invalid_key_on_optional_route_is_401_not_anonymous(client):
    plain, _ = svc.generate_api_key("test")
    r = client.get("/api/v1/optional", headers=_bearer(plain))
    assert r.status_code == 401
    r = client.get("/api/v1/optional")
    assert r.status_code == 200 and r.json()["user_id"] is None


def test_session_principal_for_jwt(client, world):
    token = create_access_token({"user_id": world["member"].id})
    r = client.get("/api/projects", headers=_bearer(token))
    assert r.json()["kind"] == "session"


def test_header_first_on_v1_cookie_first_elsewhere(test_db, world):
    client = TestClient(_app(test_db))
    cookie_token = create_access_token({"user_id": world["member"].id})
    header_token = create_access_token({"user_id": world["admin"].id})
    client.cookies.set("access_token", cookie_token)
    r = client.get("/api/v1/me", headers=_bearer(header_token))
    assert r.json()["user_id"] == world["admin"].id
    r = client.get("/api/projects", headers=_bearer(header_token))
    assert r.json()["user_id"] == world["member"].id


def test_key_wins_over_cookie_on_v1(test_db, world):
    client = TestClient(_app(test_db))
    client.cookies.set("access_token", create_access_token({"user_id": world["admin"].id}))
    _, plain = _personal_key(test_db, world["member"])
    r = client.get("/api/v1/me", headers=_bearer(plain))
    assert r.json() == {"user_id": world["member"].id, "kind": "api_key", "is_superadmin": False}


def test_superadmin_key_never_carries_superadmin(client, test_db, world):
    _, plain = _personal_key(test_db, world["superadmin"])
    r = client.get("/api/v1/me", headers=_bearer(plain))
    assert r.json()["is_superadmin"] is False
    r = client.get("/api/v1/admin-only", headers=_bearer(plain))
    assert r.status_code == 403
    token = create_access_token({"user_id": world["superadmin"].id})
    r = client.get("/api/v1/admin-only", headers=_bearer(token))
    assert r.status_code == 200 and r.json()["kind"] == "session"


def test_require_superadmin_rejects_key_principal_directly():
    from auth_module.models import User
    from datetime import datetime, timezone

    user = User(
        id="u", username="u", email="u@x", name="U", is_superadmin=True,
        created_at=datetime.now(timezone.utc),
    )
    request = Mock()
    request.state.principal = Principal(kind="api_key", user_id="u")
    with pytest.raises(Exception) as ei:
        require_superadmin(user, request)
    assert ei.value.status_code == 403
    request.state.principal = Principal(kind="session", user_id="u")
    assert require_superadmin(user, request) is user


def test_service_account_jwt_is_refused(client, test_db, world):
    key, _ = svc.create_org_key_sync(
        test_db, world["admin"].id, world["org"].id,
        {"name": "svc", "scopes": [], "org_role": "ANNOTATOR"},
    )
    token = create_access_token({"user_id": key.user_id})
    assert client.get("/api/projects", headers=_bearer(token)).status_code == 401
    assert client.get("/api/whoami", headers=_bearer(token)).json()["user_id"] is None


def test_extract_api_key_is_defensive():
    assert extract_api_key(Mock()) is None
    req = Mock()
    req.headers = {"Authorization": "Bearer eyJhbGciOi"}
    assert extract_api_key(req) is None
    req.headers = {"Authorization": "Bearer bgr_test_x"}
    assert extract_api_key(req) == "bgr_test_x"
    req.headers = {"Authorization": "Basic bgr_test_x"}
    assert extract_api_key(req) is None


def test_websocket_rejects_keys():
    ws = Mock()
    ws.cookies = {}
    ws.headers = {"Authorization": "Bearer bgr_test_abcdefgh_" + "a" * 43}
    with pytest.raises(WebSocketAuthError):
        verify_token_for_websocket(ws)
