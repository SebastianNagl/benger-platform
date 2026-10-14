"""GET /api/v1/me for sessions, organization keys and personal keys."""

from datetime import datetime, timezone

from fastapi import Request

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from auth_module.principal import Principal, session_principal
from main import app
from tests.fixtures.access_keys import seed_world


def _override(db_user, principal):
    au = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email, name=db_user.name,
        is_superadmin=False, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )

    def _with_principal(request: Request):
        request.state.principal = principal
        return au

    app.dependency_overrides[require_user] = _with_principal


async def test_session(async_test_client, async_test_db):
    world = await seed_world(async_test_db, group=False)
    member = world["member"]
    _override(member, session_principal(member.id))
    try:
        r = await async_test_client.get("/api/v1/me")
    finally:
        app.dependency_overrides.pop(require_user, None)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["principal"] == {
        "kind": "session",
        "key_prefix": None,
        "scopes": ["*"],
        "project_ids": None,
        "organization": {
            "id": world["org"].id,
            "name": world["org"].display_name,
            "slug": world["org"].slug,
        },
        "group": None,
        "expires_at": None,
        "rate_limit": {"per_minute": None, "per_day": None},
    }
    assert body["user"] == {
        "id": member.id,
        "username": member.username,
        "name": member.name,
        "is_service_account": False,
    }


async def test_session_without_org(async_test_client, async_test_db):
    world = await seed_world(async_test_db, group=False)
    outsider = world["outsider"]
    _override(outsider, session_principal(outsider.id))
    try:
        r = await async_test_client.get("/api/v1/me")
    finally:
        app.dependency_overrides.pop(require_user, None)
    assert r.json()["principal"]["organization"] is None


async def test_personal_key_scopes_are_expanded_and_defaults_apply(
    async_test_client, async_test_db
):
    from app.core.config import settings

    world = await seed_world(async_test_db)
    member = world["member"]
    principal = Principal(
        kind="api_key",
        user_id=member.id,
        api_key_id="not-a-stored-key",
        key_prefix="bgr_test_abcdefgh",
        scopes=frozenset({"tasks:read_reference", "submissions:write"}),
        project_ids=frozenset({"p2", "p1"}),
        group_id=world["group"].id,
    )
    _override(member, principal)
    try:
        r = await async_test_client.get("/api/v1/me")
    finally:
        app.dependency_overrides.pop(require_user, None)
    p = r.json()["principal"]
    assert p["kind"] == "api_key" and p["key_prefix"] == "bgr_test_abcdefgh"
    assert p["scopes"] == [
        "submissions:read", "submissions:write", "tasks:read", "tasks:read_reference",
    ]
    assert p["project_ids"] == ["p1", "p2"]
    assert p["organization"] is None
    assert p["group"] == {"id": world["group"].id, "name": world["group"].name}
    assert p["expires_at"] is None
    assert p["rate_limit"] == {
        "per_minute": settings.api_key_default_rpm,
        "per_day": settings.api_key_default_rpd,
    }
