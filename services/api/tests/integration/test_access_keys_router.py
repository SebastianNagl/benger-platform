"""Access-key management API: who may manage which keys, show-once
secrets, revocation, usage, superadmin views, and the service-account
login block."""

import csv
import io
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import ApiKey, ApiKeyUsageEvent, OrganizationMembership, User
from project_models import Project, ProjectOrganization
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world, seed_world_sync


@contextmanager
def _as(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _base(org_id):
    return f"/api/organizations/{org_id}/access-keys"


async def _create_org_key(client, world, **body):
    payload = {"name": "pipeline", "scopes": ["projects:read"], **body}
    return await client.post(_base(world["org"].id), json=payload)


@pytest.fixture
async def world(async_test_db):
    return await seed_world(async_test_db)


async def test_org_admin_creates_lists_and_secret_is_shown_once(async_test_client, world):
    with _as(world["admin"]):
        r = await _create_org_key(async_test_client, world, org_role="CONTRIBUTOR")
        assert r.status_code == 201, r.text
        body = r.json()
        secret = body["secret"]
        assert svc.parse_api_key(secret) is not None
        assert body["key"]["key_prefix"] == svc.parse_api_key(secret).prefix
        assert body["key"]["org_role"] == "CONTRIBUTOR"
        assert body["key"]["status"] == "active"

        r = await async_test_client.get(_base(world["org"].id))
        assert r.status_code == 200
        listed = r.json()
        assert len(listed) == 1
        text = r.text
        assert secret not in text and "key_hash" not in text
        assert listed[0]["key_prefix"] == body["key"]["key_prefix"]


async def test_member_and_outsider_cannot_manage(async_test_client, world):
    for who in ("member", "outsider"):
        with _as(world[who]):
            assert (await async_test_client.get(_base(world["org"].id))).status_code in (403, 404)
            assert (await _create_org_key(async_test_client, world)).status_code in (403, 404)


async def test_group_admin_scope(async_test_client, async_test_db, world):
    group_id = world["group"].id
    with _as(world["admin"]):
        org_wide = (await _create_org_key(async_test_client, world)).json()["key"]
    with _as(world["group_admin"]):
        # Org-wide keys need an org admin.
        r = await _create_org_key(async_test_client, world)
        assert r.status_code == 403
        r = await _create_org_key(async_test_client, world, group_id=group_id)
        assert r.status_code == 201, r.text
        own = r.json()["key"]
        assert own["group_id"] == group_id

        listed = (await async_test_client.get(_base(world["org"].id))).json()
        assert [k["id"] for k in listed] == [own["id"]]

        r = await async_test_client.post(f"{_base(world['org'].id)}/{org_wide['id']}/revoke")
        assert r.status_code == 404
        r = await async_test_client.patch(
            f"{_base(world['org'].id)}/{own['id']}", json={"name": "renamed"}
        )
        assert r.status_code == 200 and r.json()["name"] == "renamed"


async def test_org_role_admin_rejected_and_reference_scope_rules(async_test_client, world):
    with _as(world["admin"]):
        r = await _create_org_key(async_test_client, world, org_role="ORG_ADMIN")
        assert r.status_code == 422
        r = await _create_org_key(
            async_test_client, world, org_role="ANNOTATOR", scopes=["tasks:read_reference"]
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "scope_not_grantable"
        r = await _create_org_key(
            async_test_client, world, org_role="CONTRIBUTOR", scopes=["tasks:read_reference"]
        )
        assert r.status_code == 201
        r = await _create_org_key(async_test_client, world, scopes=["keys:manage"])
        assert r.status_code == 400
        r = await _create_org_key(async_test_client, world, scopes=["what:ever"])
        assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_scope"


async def test_project_ids_must_belong_to_org(async_test_client, async_test_db, world):
    db = async_test_db
    inside = Project(id=str(uuid.uuid4()), title="in", created_by=world["admin"].id, is_private=True)
    outside = Project(
        id=str(uuid.uuid4()), title="out", created_by=world["outsider"].id, is_private=True
    )
    db.add_all([inside, outside])
    await db.flush()
    db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()), project_id=inside.id, organization_id=world["org"].id,
            assigned_by=world["admin"].id,
        )
    )
    await db.flush()
    with _as(world["admin"]):
        r = await _create_org_key(async_test_client, world, project_ids=[inside.id])
        assert r.status_code == 201 and r.json()["key"]["project_ids"] == [inside.id]
        r = await _create_org_key(async_test_client, world, project_ids=[outside.id])
        assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_project"


async def test_revoke_deactivates_service_user(async_test_client, async_test_db, world):
    with _as(world["admin"]):
        created = (await _create_org_key(async_test_client, world)).json()["key"]
        r = await async_test_client.post(
            f"{_base(world['org'].id)}/{created['id']}/revoke", json={"reason": "rotated"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "revoked" and r.json()["revoke_reason"] == "rotated"
        assert r.json()["revoked_by"] == world["admin"].id
        r = await async_test_client.patch(
            f"{_base(world['org'].id)}/{created['id']}", json={"name": "x"}
        )
        assert r.status_code == 409
    svc_user = (
        await async_test_db.execute(select(User).where(User.id == created["user_id"]))
    ).scalar_one()
    await async_test_db.refresh(svc_user)
    assert svc_user.is_service_account is True and svc_user.is_active is False
    om = (
        await async_test_db.execute(
            select(OrganizationMembership).where(OrganizationMembership.user_id == svc_user.id)
        )
    ).scalar_one()
    await async_test_db.refresh(om)
    assert om.is_active is False


async def test_patch_updates_and_clears_fields(async_test_client, world):
    with _as(world["admin"]):
        created = (
            await _create_org_key(async_test_client, world, rate_limit_per_minute=10)
        ).json()["key"]
        url = f"{_base(world['org'].id)}/{created['id']}"
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        r = await async_test_client.patch(url, json={"expires_at": future, "rate_limit_per_day": 5})
        assert r.status_code == 200
        assert r.json()["rate_limit_per_minute"] == 10 and r.json()["rate_limit_per_day"] == 5
        assert r.json()["expires_at"] is not None
        r = await async_test_client.patch(url, json={"rate_limit_per_minute": None, "expires_at": None})
        assert r.json()["rate_limit_per_minute"] is None and r.json()["expires_at"] is None
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert (await async_test_client.patch(url, json={"expires_at": past})).status_code == 422


async def _usage(db, key_id, prefix, org_id, n=3):
    now = datetime.now(timezone.utc)
    await svc.record_usage(
        db,
        [
            {
                "api_key_id": key_id, "key_prefix": prefix, "organization_id": org_id,
                "method": "GET", "route": "/api/v1/projects/{project_id}",
                "status_code": 200 if i else 404, "duration_ms": 5 + i,
                "ip_address": "203.0.113.0/24", "created_at": now - timedelta(minutes=i),
            }
            for i in range(n)
        ],
    )
    await db.flush()


async def test_usage_endpoints_and_org_csv(async_test_client, async_test_db, world):
    db = async_test_db
    with _as(world["admin"]):
        org_key = (await _create_org_key(async_test_client, world)).json()["key"]
        grp_key = (
            await _create_org_key(async_test_client, world, group_id=world["group"].id)
        ).json()["key"]
    await _usage(db, org_key["id"], org_key["key_prefix"], world["org"].id, 3)
    await _usage(db, grp_key["id"], grp_key["key_prefix"], world["org"].id, 2)
    base = _base(world["org"].id)
    with _as(world["admin"]):
        r = await async_test_client.get(f"{base}/{org_key['id']}/usage")
        assert r.status_code == 200
        assert r.json()["total_requests"] == 3 and r.json()["total_errors"] == 1
        r = await async_test_client.get(f"{base}/{org_key['id']}/usage?granularity=route")
        assert r.json()["items"][0]["route"] == "/api/v1/projects/{project_id}"
        r = await async_test_client.get(f"{base}/{org_key['id']}/usage/events?limit=2")
        page = r.json()
        assert len(page["items"]) == 2 and page["next_cursor"] is not None
        r = await async_test_client.get(f"{base}/usage/export.csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0][0] == "created_at" and len(rows) == 1 + 5
    with _as(world["group_admin"]):
        r = await async_test_client.get(f"{base}/usage/export.csv")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) == 1 + 2
        assert {row[2] for row in rows[1:]} == {grp_key["id"]}
        assert (await async_test_client.get(f"{base}/{org_key['id']}/usage")).status_code == 404
    with _as(world["member"]):
        assert (await async_test_client.get(f"{base}/usage/export.csv")).status_code == 403


async def test_personal_keys(async_test_client, async_test_db, world):
    with _as(world["member"]):
        r = await async_test_client.post(
            "/api/users/me/access-keys",
            json={"name": "laptop", "scopes": ["projects:read", "keys:manage"]},
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["key"]["owner_type"] == "user"
        assert created["key"]["user_id"] == world["member"].id
        r = await async_test_client.get("/api/users/me/access-keys")
        assert [k["id"] for k in r.json()] == [created["key"]["id"]]
        assert created["secret"] not in r.text
        r = await async_test_client.get(f"/api/users/me/access-keys/{created['key']['id']}/usage")
        assert r.status_code == 200 and r.json()["total_requests"] == 0
        r = await async_test_client.post(
            "/api/users/me/access-keys", json={"name": "x", "project_ids": ["nope"]}
        )
        assert r.status_code == 422
    with _as(world["admin"]):
        r = await async_test_client.post(
            f"/api/users/me/access-keys/{created['key']['id']}/revoke"
        )
        assert r.status_code == 404
        assert (await async_test_client.get("/api/users/me/access-keys")).json() == []
    with _as(world["member"]):
        r = await async_test_client.post(
            f"/api/users/me/access-keys/{created['key']['id']}/revoke", json={"reason": "lost"}
        )
        assert r.status_code == 200 and r.json()["status"] == "revoked"


async def test_superadmin_list_revoke_export(async_test_client, async_test_db, world):
    with _as(world["admin"]):
        org_key = (await _create_org_key(async_test_client, world)).json()["key"]
    with _as(world["member"]):
        await async_test_client.post("/api/users/me/access-keys", json={"name": "p"})
        assert (await async_test_client.get("/api/admin/access-keys")).status_code == 403
    await _usage(async_test_db, org_key["id"], org_key["key_prefix"], world["org"].id, 2)
    with _as(world["superadmin"]):
        r = await async_test_client.get(
            f"/api/admin/access-keys?organization_id={world['org'].id}"
        )
        assert r.status_code == 200 and [k["id"] for k in r.json()["items"]] == [org_key["id"]]
        r = await async_test_client.get("/api/admin/access-keys?owner_type=user&limit=1")
        assert r.status_code == 200 and len(r.json()["items"]) == 1
        r = await async_test_client.post(
            f"/api/admin/access-keys/{org_key['id']}/revoke", json={"reason": "abuse"}
        )
        assert r.status_code == 200 and r.json()["status"] == "revoked"
        r = await async_test_client.get(
            f"/api/admin/access-keys?organization_id={world['org'].id}&status=revoked"
        )
        assert len(r.json()["items"]) == 1
        r = await async_test_client.get(
            f"/api/admin/access-keys/usage/export.csv?organization_id={world['org'].id}"
        )
        assert r.status_code == 200
        assert len(list(csv.reader(io.StringIO(r.text)))) == 3


async def test_admin_list_cursor_paginates(async_test_client, async_test_db, world):
    with _as(world["admin"]):
        for i in range(3):
            await _create_org_key(async_test_client, world, name=f"k{i}")
    with _as(world["superadmin"]):
        seen = []
        cursor = None
        for _ in range(5):
            url = f"/api/admin/access-keys?organization_id={world['org'].id}&limit=2"
            if cursor:
                url += f"&cursor={cursor}"
            page = (await async_test_client.get(url)).json()
            seen += [k["id"] for k in page["items"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert len(seen) == 3 and len(set(seen)) == 3


async def test_scope_catalog(async_test_client, world):
    with _as(world["member"]):
        r = await async_test_client.get("/api/access-keys/scopes")
        assert r.status_code == 200
        assert "benchmark_read" in r.json()["presets"]
        assert any(s["name"] == "tasks:read_reference" for s in r.json()["scopes"])


def test_service_account_login_is_forbidden(client, test_db):
    world = seed_world_sync(test_db)
    key, _ = svc.create_org_key_sync(
        test_db, world["admin"].id, world["org"].id, {"name": "svc", "scopes": []}
    )
    test_db.commit()
    svc_user = test_db.get(User, key.user_id)
    r = client.post("/api/auth/login", json={"username": svc_user.username, "password": "x"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "service_account"
    r = client.post("/api/auth/request-password-reset", json={"email": svc_user.email})
    assert r.status_code == 403
