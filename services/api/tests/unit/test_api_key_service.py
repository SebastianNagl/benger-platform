"""Access-key service: format, hashing, the deny-by-default path rule,
authentication failures and the service-account shape of org keys."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from models import (
    ApiKey,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world_sync


# --------------------------------------------------------------------------- #
# Format and hashing
# --------------------------------------------------------------------------- #


def test_generated_key_parses_and_carries_its_prefix():
    plain, prefix = svc.generate_api_key("test")
    parsed = svc.parse_api_key(plain)
    assert parsed is not None
    assert parsed.environment == "test"
    assert parsed.prefix == prefix
    assert prefix.startswith("bgr_test_") and len(parsed.kid) == 8
    assert len(parsed.secret) == 43
    assert plain == f"{prefix}_{parsed.secret}"


def test_generated_keys_are_unique():
    keys = {svc.generate_api_key("live")[0] for _ in range(50)}
    assert len(keys) == 50


@pytest.mark.parametrize(
    "value",
    [
        None,
        42,
        "",
        "bgr_prod_abcdefgh_" + "a" * 43,
        "bgr_test_abc_" + "a" * 43,
        "bgr_test_abcdefgh_" + "a" * 42,
        "xyz_test_abcdefgh_" + "a" * 43,
        "bgr_test_abcdefg!_" + "a" * 43,
    ],
)
def test_parse_rejects_malformed(value):
    assert svc.parse_api_key(value) is None


def test_generate_rejects_unknown_environment():
    with pytest.raises(ValueError):
        svc.generate_api_key("prod")


def test_hash_uses_pepper_and_version(monkeypatch):
    plain, _ = svc.generate_api_key("test")
    monkeypatch.setattr(settings, "api_key_pepper", "")
    unpeppered = svc.hash_api_key(plain)
    assert unpeppered == hashlib.sha256(plain.encode()).hexdigest()
    monkeypatch.setattr(settings, "api_key_pepper", "pepper!")
    peppered = svc.hash_api_key(plain)
    assert peppered == hashlib.sha256(("pepper!" + plain).encode()).hexdigest()
    assert peppered != unpeppered
    with pytest.raises(ValueError):
        svc.hash_api_key(plain, version=2)


def test_env_tag_follows_deployment(monkeypatch):
    monkeypatch.setattr(settings, "api_key_environment", None)
    monkeypatch.setattr(settings, "environment", "production")
    assert svc.current_env_tag() == "live"
    monkeypatch.setattr(settings, "environment", "development")
    assert svc.current_env_tag() == "test"
    monkeypatch.setattr(settings, "api_key_environment", "live")
    assert svc.current_env_tag() == "live"


@pytest.mark.parametrize(
    "path,ok",
    [
        ("/api/v1/me", True),
        ("/api/v1/projects/abc", True),
        ("/health", True),
        ("/healthz", True),
        ("/api/v1", False),
        ("/api/projects", False),
        ("/api/auth/me", False),
        ("/api/v10/x", False),
        ("/api/organizations/x/access-keys", False),
        (None, False),
    ],
)
def test_deny_by_default_path_rule(path, ok):
    assert svc.path_allows_api_key(path) is ok


@pytest.mark.parametrize(
    "ip,mode,expected",
    [
        ("203.0.113.77", "truncated", "203.0.113.0/24"),
        ("2001:db8:abcd:12::1", "truncated", "2001:db8:abcd::/48"),
        ("203.0.113.77", "full", "203.0.113.77"),
        ("203.0.113.77", "none", None),
        ("not-an-ip", "truncated", None),
        (None, "full", None),
    ],
)
def test_mask_ip(ip, mode, expected):
    assert svc.mask_ip(ip, mode) == expected


# --------------------------------------------------------------------------- #
# Creation, show-once, authentication
# --------------------------------------------------------------------------- #

V1 = "/api/v1/me"


def _personal(db, user, **extra):
    payload = {"name": "laptop", "scopes": ["projects:read"], **extra}
    return svc.create_personal_key_sync(db, user.id, payload)


def test_personal_key_round_trip_and_show_once(test_db):
    world = seed_world_sync(test_db)
    key, plain = _personal(test_db, world["member"])
    assert key.key_hash != plain and plain not in str(svc.public_key_dict(key))
    public = svc.public_key_dict(key)
    assert "key_hash" not in public and public["key_prefix"] == key.key_prefix
    assert public["status"] == "active"
    assert key.environment == "test"

    auth = svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert auth.user.id == world["member"].id
    assert auth.principal.kind == "api_key"
    assert auth.principal.scopes == frozenset({"projects:read"})
    assert auth.principal.project_ids is None
    assert auth.principal.key_prefix == key.key_prefix


def _code(exc):
    return exc.value.detail["code"]


def test_wrong_secret_is_rejected(test_db):
    world = seed_world_sync(test_db)
    key, plain = _personal(test_db, world["member"])
    tampered = plain[:-1] + ("A" if plain[-1] != "A" else "B")
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, tampered, path=V1)
    assert ei.value.status_code == 401 and _code(ei) == "invalid_api_key"


def test_unknown_prefix_and_garbage_rejected(test_db):
    plain, _ = svc.generate_api_key("test")
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert _code(ei) == "invalid_api_key"
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, "bgr_nonsense", path=V1)
    assert _code(ei) == "invalid_api_key"


def test_other_environment_rejected(test_db):
    plain, _ = svc.generate_api_key("live")
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert ei.value.status_code == 401 and _code(ei) == "invalid_api_key"


def test_key_outside_v1_is_not_allowed_here(test_db):
    world = seed_world_sync(test_db)
    _, plain = _personal(test_db, world["member"])
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path="/api/projects")
    assert ei.value.status_code == 401
    assert _code(ei) == "api_key_not_allowed_here"
    assert ei.value.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


def test_revoked_key_rejected(test_db):
    world = seed_world_sync(test_db)
    key, plain = _personal(test_db, world["member"])
    assert svc.revoke_key_sync(test_db, key, world["member"].id, "lost") is True
    assert svc.revoke_key_sync(test_db, key, world["member"].id, "again") is False
    test_db.refresh(key)
    assert key.revoked_at is not None and key.revoke_reason == "lost"
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert _code(ei) == "api_key_revoked"


def test_expired_key_rejected(test_db):
    world = seed_world_sync(test_db)
    key, plain = _personal(
        test_db, world["member"], expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    test_db.flush()
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert _code(ei) == "api_key_expired"


def test_past_expiry_refused_at_creation(test_db):
    world = seed_world_sync(test_db)
    with pytest.raises(HTTPException) as ei:
        _personal(
            test_db, world["member"], expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
    assert ei.value.status_code == 422


def test_inactive_owner_rejected(test_db):
    world = seed_world_sync(test_db)
    _, plain = _personal(test_db, world["member"])
    world["member"].is_active = False
    test_db.flush()
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert ei.value.status_code == 401 and _code(ei) == "api_key_owner_inactive"


def _org_key(db, world, **extra):
    payload = {
        "name": "CI pipeline",
        "scopes": ["projects:read"],
        "org_role": "ANNOTATOR",
        **extra,
    }
    return svc.create_org_key_sync(db, world["admin"].id, world["org"].id, payload)


def test_org_key_creates_service_account_and_memberships(test_db):
    world = seed_world_sync(test_db)
    key, plain = _org_key(test_db, world, group_id=world["group"].id)
    svc_user = test_db.get(User, key.user_id)
    assert svc_user.is_service_account is True
    assert svc_user.username == f"svc-{key.key_prefix.rsplit('_', 1)[1]}"
    assert svc_user.email.endswith("@service-accounts.what-a-benger.net")
    assert svc_user.name == "API-Zugang: CI pipeline"
    assert svc_user.hashed_password is None and svc_user.password_set is False
    assert svc_user.email_verified is True and svc_user.profile_completed is True
    assert svc_user.is_superadmin is False

    om = test_db.execute(
        select(OrganizationMembership).where(OrganizationMembership.user_id == svc_user.id)
    ).scalar_one()
    assert om.organization_id == world["org"].id
    assert om.role == OrganizationRole.ANNOTATOR and om.is_active
    gm = test_db.execute(
        select(OrganizationGroupMembership).where(
            OrganizationGroupMembership.user_id == svc_user.id
        )
    ).scalar_one()
    assert gm.group_id == world["group"].id and gm.role == OrganizationRole.ANNOTATOR

    assert key.owner_type == "org" and key.created_by == world["admin"].id
    auth = svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert auth.user.id == svc_user.id
    assert auth.principal.organization_id == world["org"].id
    assert auth.principal.group_id == world["group"].id


def test_org_key_roles(test_db):
    """ORG_ADMIN keys exist since core 2.45 (the router keeps them org-wide
    and admin-made); unknown roles stay invalid."""
    world = seed_world_sync(test_db)
    key, _ = _org_key(test_db, world, org_role="ORG_ADMIN")
    membership = (
        test_db.execute(
            select(OrganizationMembership).where(OrganizationMembership.user_id == key.user_id)
        )
    ).scalar_one()
    assert membership.role == OrganizationRole.ORG_ADMIN
    with pytest.raises(HTTPException) as ei:
        _org_key(test_db, world, org_role="KING")
    assert ei.value.status_code == 422 and _code(ei) == "invalid_org_role"


def test_service_account_email_host_setting(test_db, monkeypatch):
    monkeypatch.setattr(settings, "service_account_email_host", "svc.example.org")
    world = seed_world_sync(test_db)
    key, _ = _org_key(test_db, world)
    assert test_db.get(User, key.user_id).email.endswith("@svc.example.org")


def test_revoking_org_key_retires_service_account(test_db):
    world = seed_world_sync(test_db)
    key, plain = _org_key(test_db, world, group_id=world["group"].id)
    svc.revoke_key_sync(test_db, key, world["admin"].id, "rotated")
    test_db.expire_all()
    svc_user = test_db.get(User, key.user_id)
    assert svc_user.is_active is False
    om = test_db.execute(
        select(OrganizationMembership).where(OrganizationMembership.user_id == svc_user.id)
    ).scalar_one()
    assert om.is_active is False
    assert (
        test_db.execute(
            select(OrganizationGroupMembership).where(
                OrganizationGroupMembership.user_id == svc_user.id
            )
        ).first()
        is None
    )
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert _code(ei) == "api_key_revoked"


def test_inactive_org_rejects_org_key(test_db):
    world = seed_world_sync(test_db)
    _, plain = _org_key(test_db, world)
    world["org"].is_active = False
    test_db.flush()
    with pytest.raises(HTTPException) as ei:
        svc.authenticate_api_key_sync(test_db, plain, path=V1)
    assert ei.value.status_code == 403 and _code(ei) == "organization_inactive"


def test_bulk_revocation_helpers(test_db):
    world = seed_world_sync(test_db)
    p1, _ = _personal(test_db, world["member"])
    p2, _ = _personal(test_db, world["member"])
    o1, _ = _org_key(test_db, world)
    g1, _ = _org_key(test_db, world, group_id=world["group"].id)

    assert svc.revoke_all_for_user_sync(test_db, world["member"].id, None, "x") == 2
    assert svc.revoke_all_for_group_sync(test_db, world["group"].id, None, "g") == 1
    assert svc.revoke_all_for_org_sync(test_db, world["org"].id, None, "o") == 1
    test_db.expire_all()
    for k in (p1, p2, o1, g1):
        assert test_db.get(ApiKey, k.id).revoked_at is not None
    assert test_db.get(ApiKey, g1.id).revoke_reason == "g"
    assert test_db.get(ApiKey, o1.id).revoke_reason == "o"


def test_touch_last_used_is_throttled(test_db):
    world = seed_world_sync(test_db)
    key, _ = _personal(test_db, world["member"])
    now = datetime.now(timezone.utc)
    assert svc.touch_last_used_sync(test_db, key.id, "198.51.100.0/24", now) is True
    assert svc.touch_last_used_sync(test_db, key.id, "x", now + timedelta(seconds=30)) is False
    assert svc.touch_last_used_sync(test_db, key.id, "y", now + timedelta(seconds=61)) is True
    test_db.expire_all()
    assert test_db.get(ApiKey, key.id).last_used_ip == "y"


def test_role_at_least():
    assert svc.role_at_least("ORG_ADMIN", "CONTRIBUTOR")
    assert svc.role_at_least(OrganizationRole.CONTRIBUTOR, OrganizationRole.CONTRIBUTOR)
    assert not svc.role_at_least("ANNOTATOR", "CONTRIBUTOR")
    assert not svc.role_at_least(None, "ANNOTATOR")
