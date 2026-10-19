"""``/api/feature-flags`` and the legacy ``/api/ext/feature-flags`` (core
2.41): ``/me`` shapes (anonymous included), the admin list with
unregistered rows, ``DELETE /{name}`` and a registry sync that keeps rows
nobody registers."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from feature_flags import registry, service
from feature_flags.registry import FlagDefinition
from models import FeatureFlag, FeatureFlagTarget, User

PKG = "benger_fake_router"


@pytest.fixture(autouse=True)
def _flags():
    service.reset_registry_sync_state()
    registry.register_flags(
        PKG, [FlagDefinition("fake_feature", "A fake feature", "everyone")]
    )
    registry.register_master_flag(PKG, "fakerouter", "allowlist")
    yield
    registry.unregister_flags(PKG)
    service.reset_registry_sync_state()


def _auth_user(db_user):
    from auth_module.models import User as AuthUser

    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import optional_user, require_user
    from main import app

    auth_user = _auth_user(db_user) if db_user is not None else None
    app.dependency_overrides[optional_user] = lambda: auth_user
    if auth_user is not None:
        app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(optional_user, None)
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"ff-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Flag Tester",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_me_for_anonymous_callers(async_test_client, async_test_db):
    with _as_user(None):
        response = await async_test_client.get("/api/feature-flags/me")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    body = response.json()
    # The master is allowlist: anonymous callers get neither the master nor
    # the flag it owns (owner coupling), even though the flag is "everyone".
    assert body["extensions"] == {"fakerouter": False}
    assert body["flags"]["extension.fakerouter"] is False
    assert body["flags"]["fake_feature"] is False
    assert "public_api" in body["flags"]


@pytest.mark.asyncio
async def test_me_for_an_allowlisted_user_and_the_legacy_shape(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await service.sync_registry(async_test_db)
    master = (
        await async_test_db.execute(
            select(FeatureFlag).where(FeatureFlag.name == "extension.fakerouter")
        )
    ).scalar_one()
    async_test_db.add(
        FeatureFlagTarget(id=str(uuid.uuid4()), flag_id=master.id, user_id=user.id)
    )
    await async_test_db.commit()
    service.invalidate_cache()

    with _as_user(user):
        new = await async_test_client.get("/api/feature-flags/me")
        legacy = await async_test_client.get("/api/ext/feature-flags/me")
    assert new.status_code == 200
    assert new.json()["extensions"] == {"fakerouter": True}
    assert new.json()["flags"]["fake_feature"] is True
    assert legacy.status_code == 200
    flat = legacy.json()
    assert flat["fake_feature"] is True and flat["extension.fakerouter"] is True
    assert "flags" not in flat


@pytest.mark.asyncio
async def test_legacy_me_needs_a_login(async_test_client):
    response = await async_test_client.get("/api/ext/feature-flags/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_marks_unregistered_rows_and_delete(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, superadmin=True)
    async_test_db.add(
        FeatureFlag(id=str(uuid.uuid4()), name="retired_flag", description="old", state="everyone")
    )
    await async_test_db.commit()

    with _as_user(admin):
        listed = await async_test_client.get("/api/feature-flags")
        assert listed.status_code == 200
        by_name = {f["name"]: f for f in listed.json()}
        assert by_name["fake_feature"]["registered"] is True
        assert by_name["fake_feature"]["owner"] == PKG
        assert by_name["extension.fakerouter"]["is_master"] is True
        assert by_name["extension.fakerouter"]["default_state"] == "allowlist"
        assert by_name["public_api"]["owner"] == "platform"
        retired = by_name["retired_flag"]
        assert retired["registered"] is False
        assert retired["owner"] is None
        assert retired["state"] == "everyone"
        assert retired["description"] == "old"

        # The sync that ran for the list kept the unregistered row.
        assert (
            await async_test_db.execute(select(FeatureFlag).where(FeatureFlag.name == "retired_flag"))
        ).scalar_one_or_none() is not None

        refused = await async_test_client.delete("/api/feature-flags/fake_feature")
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "flag_registered"

        deleted = await async_test_client.delete("/api/feature-flags/retired_flag")
        assert deleted.status_code == 204
        missing = await async_test_client.delete("/api/feature-flags/retired_flag")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "unknown_flag"

        # The same routes answer on the legacy path.
        legacy = await async_test_client.get("/api/ext/feature-flags")
        assert legacy.status_code == 200


@pytest.mark.asyncio
async def test_state_and_targets(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, superadmin=True)
    user = await _make_user(async_test_db)
    with _as_user(admin):
        put = await async_test_client.put(
            "/api/feature-flags/extension.fakerouter", json={"state": "everyone"}
        )
        assert put.status_code == 200
        assert put.json()["state"] == "everyone"
        assert put.json()["is_master"] is True

        added = await async_test_client.post(
            "/api/feature-flags/fake_feature/targets", json={"user_id": user.id}
        )
        assert added.status_code == 201
        dup = await async_test_client.post(
            "/api/feature-flags/fake_feature/targets", json={"user_id": user.id}
        )
        assert dup.status_code == 409
        removed = await async_test_client.delete(
            f"/api/feature-flags/fake_feature/targets/{added.json()['id']}"
        )
        assert removed.status_code == 204

        unknown = await async_test_client.put("/api/feature-flags/nope", json={"state": "off"})
        assert unknown.status_code == 404
        assert unknown.json()["detail"] == {"code": "unknown_flag", "flag": "nope"}


@pytest.mark.asyncio
async def test_admin_routes_need_a_superadmin(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    with _as_user(user):
        assert (await async_test_client.get("/api/feature-flags")).status_code == 403
        assert (
            await async_test_client.delete("/api/feature-flags/retired_flag")
        ).status_code == 403
