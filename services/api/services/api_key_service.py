"""Access keys for the public ``/api/v1`` surface.

Key format: ``bgr_<live|test>_<kid>_<secret>``

* ``kid``: 8 base62 characters, the public key id.
* ``secret``: ``secrets.token_urlsafe(32)`` (43 characters).
* ``key_prefix`` = ``bgr_<env>_<kid>``: the lookup handle stored in clear
  and shown in lists. The full key is shown once, at creation.
* ``key_hash`` = sha256(API_KEY_PEPPER + key), hex. ``hash_version`` names
  the scheme so it can change later without invalidating old keys.

A deployment accepts only keys carrying its own tag (``live`` in
production, ``test`` elsewhere; ``API_KEY_ENVIRONMENT`` overrides), so a
staging key never works against production and vice versa.

Keys are deny-by-default: they authenticate only on ``/api/v1/...`` and the
health probes. Everything else (the browser API) answers 401
``api_key_not_allowed_here``.

Personal keys act as their owner. Organization keys act as their own
service-account user (``users.is_service_account``), created together with
the key and holding an ``OrganizationMembership`` with the key's
``org_role`` (plus a group membership for group keys). Revoking an org key
deactivates that user and its memberships.

Async functions serve the async lane; ``*_sync`` twins run the same
statements on a sync ``Session`` (the auth dependency and the user
deletion/anonymization paths are sync).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import (
    ApiKey,
    ApiKeyUsageEvent,
    Organization,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)

from auth_module.principal import Principal

logger = logging.getLogger(__name__)

KEY_PREFIX = "bgr"
KID_LENGTH = 8
SECRET_BYTES = 32
CURRENT_HASH_VERSION = 1
_BASE62 = string.digits + string.ascii_letters
_KEY_RE = re.compile(r"^bgr_(live|test)_([0-9A-Za-z]{8})_([A-Za-z0-9_-]{43})$")

#: Paths (besides ``/api/v1/...``) where a key may authenticate.
KEY_ALLOWED_EXACT_PATHS = frozenset({"/health", "/healthz"})
KEY_ALLOWED_PATH_PREFIX = "/api/v1/"

#: Roles an organization key may carry. ORG_ADMIN is never handed to a key.
ORG_KEY_ROLES = (OrganizationRole.ANNOTATOR, OrganizationRole.CONTRIBUTOR)

_ROLE_RANK = {
    OrganizationRole.ANNOTATOR.value: 1,
    OrganizationRole.CONTRIBUTOR.value: 2,
    OrganizationRole.ORG_ADMIN.value: 3,
}

#: last_used_at is written at most once per this many seconds per key.
LAST_USED_THROTTLE_SECONDS = 60

DEFAULT_SERVICE_EMAIL_HOST = "service-accounts.what-a-benger.net"
SERVICE_USERNAME_PREFIX = "svc-"


def _settings():
    from app.core.config import settings

    return settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _error(
    status_code: int,
    code: str,
    message: str,
    headers: Optional[Dict[str, str]] = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def _unauthorized(code: str, message: str) -> HTTPException:
    return _error(
        status.HTTP_401_UNAUTHORIZED,
        code,
        message,
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


# ---------------------------------------------------------------------------
# Format, hashing, parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedKey:
    environment: str
    kid: str
    secret: str

    @property
    def prefix(self) -> str:
        return f"{KEY_PREFIX}_{self.environment}_{self.kid}"


def current_env_tag() -> str:
    return _settings().api_key_env_tag


def parse_api_key(plain: Any) -> Optional[ParsedKey]:
    if not isinstance(plain, str):
        return None
    match = _KEY_RE.match(plain.strip())
    if not match:
        return None
    return ParsedKey(match.group(1), match.group(2), match.group(3))


def _new_kid() -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(KID_LENGTH))


def generate_api_key(environment: Optional[str] = None) -> Tuple[str, str]:
    """A fresh ``(plain_key, key_prefix)`` pair."""
    env = environment or current_env_tag()
    if env not in ("live", "test"):
        raise ValueError(f"Unknown key environment: {env!r}")
    kid = _new_kid()
    secret = secrets.token_urlsafe(SECRET_BYTES)
    prefix = f"{KEY_PREFIX}_{env}_{kid}"
    return f"{prefix}_{secret}", prefix


def hash_api_key(plain: str, version: int = CURRENT_HASH_VERSION) -> str:
    if version != 1:
        raise ValueError(f"Unknown key hash version: {version}")
    pepper = _settings().api_key_pepper or ""
    return hashlib.sha256((pepper + plain).encode("utf-8")).hexdigest()


def path_allows_api_key(path: Optional[str]) -> bool:
    """Deny by default: keys work only on /api/v1/... and the health probes."""
    if not isinstance(path, str):
        return False
    return path.startswith(KEY_ALLOWED_PATH_PREFIX) or path in KEY_ALLOWED_EXACT_PATHS


def mask_ip(ip: Optional[str], mode: Optional[str] = None) -> Optional[str]:
    """Apply ``API_USAGE_IP_MODE``: full, truncated (/24, /48) or none."""
    mode = mode or _settings().api_usage_ip_mode
    if not ip or mode == "none":
        return None
    if mode == "full":
        return ip[:64]
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if addr.version == 4 else 48
    network = ipaddress.ip_network(f"{addr}/{prefix}", strict=False)
    return str(network)


# ---------------------------------------------------------------------------
# Public shape
# ---------------------------------------------------------------------------


def key_status(key: ApiKey, now: Optional[datetime] = None) -> str:
    now = now or _now()
    if key.revoked_at is not None:
        return "revoked"
    expires = key.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            return "expired"
    return "active"


def public_key_dict(key: ApiKey) -> Dict[str, Any]:
    """Everything a list may show. Never the hash, never the secret."""
    role = key.org_role
    return {
        "id": key.id,
        "name": key.name,
        "key_prefix": key.key_prefix,
        "owner_type": key.owner_type,
        "user_id": key.user_id,
        "organization_id": key.organization_id,
        "group_id": key.group_id,
        "org_role": getattr(role, "value", role),
        "scopes": list(key.scopes or []),
        "project_ids": list(key.project_ids) if key.project_ids is not None else None,
        "environment": key.environment,
        "expires_at": key.expires_at,
        "revoked_at": key.revoked_at,
        "revoked_by": key.revoked_by,
        "revoke_reason": key.revoke_reason,
        "last_used_at": key.last_used_at,
        "last_used_ip": key.last_used_ip,
        "rate_limit_per_minute": key.rate_limit_per_minute,
        "rate_limit_per_day": key.rate_limit_per_day,
        "created_by": key.created_by,
        "created_at": key.created_at,
        "status": key_status(key),
    }


def principal_for_key(key: ApiKey) -> Principal:
    return Principal(
        kind="api_key",
        user_id=str(key.user_id),
        api_key_id=key.id,
        key_prefix=key.key_prefix,
        scopes=frozenset(key.scopes or ()),
        project_ids=(
            frozenset(str(p) for p in key.project_ids)
            if key.project_ids is not None
            else None
        ),
        organization_id=key.organization_id,
        group_id=key.group_id,
        rate_limit=(key.rate_limit_per_minute, key.rate_limit_per_day),
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@dataclass
class ApiKeyAuth:
    user: User
    key: ApiKey
    principal: Principal


def _build_select_key_by_prefix(prefix: str):
    return select(ApiKey).where(ApiKey.key_prefix == prefix)


def _precheck(plain: str, path: Optional[str]) -> ParsedKey:
    parsed = parse_api_key(plain)
    if parsed is None:
        raise _unauthorized("invalid_api_key", "Invalid API key")
    if parsed.environment != current_env_tag():
        raise _unauthorized(
            "invalid_api_key", "This API key belongs to a different environment"
        )
    if not path_allows_api_key(path):
        raise _unauthorized(
            "api_key_not_allowed_here",
            "API keys are only accepted on /api/v1 endpoints",
        )
    return parsed


def _check_key(key: Optional[ApiKey], plain: str) -> ApiKey:
    if key is None:
        # Spend the same hashing work as a real comparison.
        hmac.compare_digest(hash_api_key(plain), "0" * 64)
        raise _unauthorized("invalid_api_key", "Invalid API key")
    try:
        expected = hash_api_key(plain, key.hash_version or CURRENT_HASH_VERSION)
    except ValueError:
        raise _unauthorized("invalid_api_key", "Invalid API key")
    if not hmac.compare_digest(expected, key.key_hash or ""):
        raise _unauthorized("invalid_api_key", "Invalid API key")
    state = key_status(key)
    if state == "revoked":
        raise _unauthorized("api_key_revoked", "This API key has been revoked")
    if state == "expired":
        raise _unauthorized("api_key_expired", "This API key has expired")
    return key


def _check_org(org_row) -> None:
    if org_row is None or not org_row.is_active:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "organization_inactive",
            "The organization of this API key is not active",
        )


def _check_user(user: Optional[User]) -> User:
    if user is None or not user.is_active:
        raise _unauthorized("api_key_owner_inactive", "The account of this API key is inactive")
    return user


def authenticate_api_key_sync(db: Session, plain: str, *, path: Optional[str]) -> ApiKeyAuth:
    parsed = _precheck(plain, path)
    key = db.execute(_build_select_key_by_prefix(parsed.prefix)).scalar_one_or_none()
    key = _check_key(key, plain)
    if key.owner_type == "org":
        org = db.execute(
            select(Organization.id, Organization.is_active).where(
                Organization.id == key.organization_id
            )
        ).first()
        _check_org(org)
    user = _check_user(db.get(User, key.user_id))
    return ApiKeyAuth(user=user, key=key, principal=principal_for_key(key))


async def authenticate_api_key(
    db: AsyncSession, plain: str, *, path: Optional[str]
) -> ApiKeyAuth:
    parsed = _precheck(plain, path)
    key = (
        await db.execute(_build_select_key_by_prefix(parsed.prefix))
    ).scalar_one_or_none()
    key = _check_key(key, plain)
    if key.owner_type == "org":
        org = (
            await db.execute(
                select(Organization.id, Organization.is_active).where(
                    Organization.id == key.organization_id
                )
            )
        ).first()
        _check_org(org)
    user = _check_user(await db.get(User, key.user_id))
    return ApiKeyAuth(user=user, key=key, principal=principal_for_key(key))


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def _field(payload: Any, name: str, default=None):
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _role_enum(role: Any) -> OrganizationRole:
    try:
        return OrganizationRole(str(getattr(role, "value", role)).upper())
    except ValueError:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_org_role",
            "org_role must be ANNOTATOR or CONTRIBUTOR",
        )


def role_at_least(role: Any, minimum: Any) -> bool:
    value = str(getattr(role, "value", role) or "").upper()
    floor = str(getattr(minimum, "value", minimum) or "").upper()
    return _ROLE_RANK.get(value, 0) >= _ROLE_RANK.get(floor, 99)


def _validate_expiry(expires_at: Optional[datetime]) -> Optional[datetime]:
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_expiry",
            "expires_at must lie in the future",
        )
    return expires_at


def _normalize_project_ids(project_ids) -> Optional[List[str]]:
    if project_ids is None:
        return None
    return sorted({str(p) for p in project_ids})


def _key_row(
    *,
    name: str,
    prefix: str,
    plain: str,
    owner_type: str,
    user_id: str,
    created_by: str,
    scopes: Sequence[str],
    project_ids: Optional[List[str]],
    expires_at: Optional[datetime],
    rpm: Optional[int],
    rpd: Optional[int],
    organization_id: Optional[str] = None,
    group_id: Optional[str] = None,
    org_role: Optional[OrganizationRole] = None,
) -> ApiKey:
    return ApiKey(
        id=str(uuid.uuid4()),
        name=name,
        key_prefix=prefix,
        key_hash=hash_api_key(plain),
        hash_version=CURRENT_HASH_VERSION,
        owner_type=owner_type,
        user_id=user_id,
        organization_id=organization_id,
        group_id=group_id,
        org_role=org_role,
        scopes=list(scopes),
        project_ids=project_ids,
        environment=prefix.split("_")[1],
        expires_at=expires_at,
        rate_limit_per_minute=rpm,
        rate_limit_per_day=rpd,
        created_by=created_by,
    )


def service_account_for(kid: str, key_name: str) -> User:
    """The (unsaved) machine user behind an organization key."""
    host = _settings().service_account_email_host or DEFAULT_SERVICE_EMAIL_HOST
    return User(
        id=str(uuid.uuid4()),
        username=f"{SERVICE_USERNAME_PREFIX}{kid}",
        email=f"{SERVICE_USERNAME_PREFIX}{kid}@{host}",
        name=f"API-Zugang: {key_name}"[:255],
        email_verified=True,
        email_verification_method="system",
        hashed_password=None,
        password_set=False,
        profile_completed=True,
        mandatory_profile_completed=True,
        is_superadmin=False,
        is_active=True,
        is_service_account=True,
        use_pseudonym=False,
    )


def _personal_parts(owner_user_id: str, payload: Any, created_by: Optional[str]):
    plain, prefix = generate_api_key()
    row = _key_row(
        name=_field(payload, "name"),
        prefix=prefix,
        plain=plain,
        owner_type="user",
        user_id=str(owner_user_id),
        created_by=str(created_by or owner_user_id),
        scopes=_field(payload, "scopes") or [],
        project_ids=_normalize_project_ids(_field(payload, "project_ids")),
        expires_at=_validate_expiry(_field(payload, "expires_at")),
        rpm=_field(payload, "rate_limit_per_minute"),
        rpd=_field(payload, "rate_limit_per_day"),
    )
    return row, plain


def _org_parts(creator_id: str, org_id: str, payload: Any):
    role = _role_enum(_field(payload, "org_role") or OrganizationRole.ANNOTATOR)
    if role not in ORG_KEY_ROLES:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_org_role",
            "org_role must be ANNOTATOR or CONTRIBUTOR",
        )
    group_id = _field(payload, "group_id")
    name = _field(payload, "name")
    plain, prefix = generate_api_key()
    kid = prefix.rsplit("_", 1)[1]
    svc = service_account_for(kid, name)
    rows: List[Any] = [svc]
    rows.append(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=svc.id,
            organization_id=org_id,
            role=role,
            is_active=True,
        )
    )
    if group_id:
        rows.append(
            OrganizationGroupMembership(
                id=str(uuid.uuid4()), group_id=group_id, user_id=svc.id, role=role
            )
        )
    key = _key_row(
        name=name,
        prefix=prefix,
        plain=plain,
        owner_type="org",
        user_id=svc.id,
        created_by=str(creator_id),
        scopes=_field(payload, "scopes") or [],
        project_ids=_normalize_project_ids(_field(payload, "project_ids")),
        expires_at=_validate_expiry(_field(payload, "expires_at")),
        rpm=_field(payload, "rate_limit_per_minute"),
        rpd=_field(payload, "rate_limit_per_day"),
        organization_id=org_id,
        group_id=group_id,
        org_role=role,
    )
    return rows, key, plain


def create_personal_key_sync(
    db: Session, owner_user_id: str, payload: Any, *, created_by: Optional[str] = None
) -> Tuple[ApiKey, str]:
    """Create a personal key; returns ``(row, plain_key)``. Flushes, the
    caller commits. Scopes must be validated by the caller."""
    row, plain = _personal_parts(owner_user_id, payload, created_by)
    db.add(row)
    db.flush()
    return row, plain


async def create_personal_key(
    db: AsyncSession, owner_user_id: str, payload: Any, *, created_by: Optional[str] = None
) -> Tuple[ApiKey, str]:
    row, plain = _personal_parts(owner_user_id, payload, created_by)
    db.add(row)
    await db.flush()
    return row, plain


def create_org_key_sync(
    db: Session, creator_id: str, org_id: str, payload: Any
) -> Tuple[ApiKey, str]:
    """Create an organization key with its service-account user and
    memberships in the caller's transaction; returns ``(row, plain_key)``."""
    rows, key, plain = _org_parts(creator_id, org_id, payload)
    db.add(rows[0])
    db.flush()
    for row in rows[1:]:
        db.add(row)
    db.flush()
    db.add(key)
    db.flush()
    return key, plain


async def create_org_key(
    db: AsyncSession, creator_id: str, org_id: str, payload: Any
) -> Tuple[ApiKey, str]:
    rows, key, plain = _org_parts(creator_id, org_id, payload)
    db.add(rows[0])
    await db.flush()
    for row in rows[1:]:
        db.add(row)
    await db.flush()
    db.add(key)
    await db.flush()
    return key, plain


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


def _revoke_values(by: Optional[str], reason: Optional[str]) -> Dict[str, Any]:
    return {
        "revoked_at": func.now(),
        "revoked_by": by,
        "revoke_reason": reason,
        "updated_at": func.now(),
    }


def _build_select_active_keys(*conditions):
    return select(ApiKey.id, ApiKey.owner_type, ApiKey.user_id).where(
        ApiKey.revoked_at.is_(None), *conditions
    )


def _revocation_statements(rows, by: Optional[str], reason: Optional[str]) -> list:
    """Statements that revoke ``rows`` (id, owner_type, user_id) and retire
    the service accounts of organization keys among them."""
    ids = [r.id for r in rows]
    if not ids:
        return []
    statements = [
        update(ApiKey)
        .where(ApiKey.id.in_(ids), ApiKey.revoked_at.is_(None))
        .values(**_revoke_values(by, reason))
        .execution_options(synchronize_session=False)
    ]
    svc_ids = [r.user_id for r in rows if r.owner_type == "org"]
    if svc_ids:
        statements += [
            update(User)
            .where(User.id.in_(svc_ids), User.is_service_account.is_(True))
            .values(is_active=False)
            .execution_options(synchronize_session=False),
            update(OrganizationMembership)
            .where(OrganizationMembership.user_id.in_(svc_ids))
            .values(is_active=False)
            .execution_options(synchronize_session=False),
            delete(OrganizationGroupMembership)
            .where(OrganizationGroupMembership.user_id.in_(svc_ids))
            .execution_options(synchronize_session=False),
        ]
    return statements


def _revoke_sync(db: Session, conditions, by, reason) -> int:
    rows = db.execute(_build_select_active_keys(*conditions)).all()
    for stmt in _revocation_statements(rows, by, reason):
        db.execute(stmt)
    return len(rows)


async def _revoke(db: AsyncSession, conditions, by, reason) -> int:
    rows = (await db.execute(_build_select_active_keys(*conditions))).all()
    for stmt in _revocation_statements(rows, by, reason):
        await db.execute(stmt)
    return len(rows)


def revoke_key_sync(db: Session, key: ApiKey, by: Optional[str], reason: Optional[str]) -> bool:
    """Revoke one key (no-op when already revoked). The caller commits."""
    done = _revoke_sync(db, [ApiKey.id == key.id], by, reason) > 0
    db.expire(key)
    return done


async def revoke_key(
    db: AsyncSession, key: ApiKey, by: Optional[str], reason: Optional[str]
) -> bool:
    done = await _revoke(db, [ApiKey.id == key.id], by, reason) > 0
    db.expire(key)
    return done


def _personal_conditions(user_id: str):
    return [ApiKey.owner_type == "user", ApiKey.user_id == user_id]


def revoke_all_for_user_sync(db: Session, user_id: str, by=None, reason=None) -> int:
    """Revoke the user's personal keys."""
    return _revoke_sync(db, _personal_conditions(user_id), by, reason)


async def revoke_all_for_user(db: AsyncSession, user_id: str, by=None, reason=None) -> int:
    return await _revoke(db, _personal_conditions(user_id), by, reason)


def revoke_all_for_org_sync(db: Session, org_id: str, by=None, reason=None) -> int:
    return _revoke_sync(db, [ApiKey.organization_id == org_id], by, reason)


async def revoke_all_for_org(db: AsyncSession, org_id: str, by=None, reason=None) -> int:
    return await _revoke(db, [ApiKey.organization_id == org_id], by, reason)


def revoke_all_for_group_sync(db: Session, group_id: str, by=None, reason=None) -> int:
    return _revoke_sync(db, [ApiKey.group_id == group_id], by, reason)


async def revoke_all_for_group(db: AsyncSession, group_id: str, by=None, reason=None) -> int:
    return await _revoke(db, [ApiKey.group_id == group_id], by, reason)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def build_select_keys_for_org(org_id: str, group_ids: Optional[Iterable[str]] = None):
    """Keys of an org; ``group_ids`` (not None) narrows to those groups'
    keys (what a group admin sees)."""
    stmt = select(ApiKey).where(
        ApiKey.owner_type == "org", ApiKey.organization_id == org_id
    )
    if group_ids is not None:
        stmt = stmt.where(ApiKey.group_id.in_(list(group_ids)))
    return stmt.order_by(ApiKey.created_at.desc(), ApiKey.id)


def build_select_keys_for_user(user_id: str):
    return (
        select(ApiKey)
        .where(ApiKey.owner_type == "user", ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc(), ApiKey.id)
    )


async def list_keys_for_org(
    db: AsyncSession, org_id: str, group_ids: Optional[Iterable[str]] = None
) -> List[ApiKey]:
    return list((await db.execute(build_select_keys_for_org(org_id, group_ids))).scalars())


async def list_keys_for_user(db: AsyncSession, user_id: str) -> List[ApiKey]:
    return list((await db.execute(build_select_keys_for_user(user_id))).scalars())


def list_keys_for_user_sync(db: Session, user_id: str) -> List[ApiKey]:
    return list(db.execute(build_select_keys_for_user(user_id)).scalars())


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


def build_usage_summary(
    key_ids: Sequence[str], frm: datetime, to: datetime, granularity: str
):
    errors = func.count().filter(ApiKeyUsageEvent.status_code >= 400)
    avg_ms = func.avg(ApiKeyUsageEvent.duration_ms)
    window = and_(
        ApiKeyUsageEvent.api_key_id.in_(list(key_ids)),
        ApiKeyUsageEvent.created_at >= frm,
        ApiKeyUsageEvent.created_at < to,
    )
    if granularity == "route":
        return (
            select(
                ApiKeyUsageEvent.method,
                ApiKeyUsageEvent.route,
                func.count().label("requests"),
                errors.label("errors"),
                avg_ms.label("avg_duration_ms"),
            )
            .where(window)
            .group_by(ApiKeyUsageEvent.method, ApiKeyUsageEvent.route)
            .order_by(func.count().desc())
        )
    day = func.date_trunc("day", ApiKeyUsageEvent.created_at)
    return (
        select(
            day.label("day"),
            func.count().label("requests"),
            errors.label("errors"),
            avg_ms.label("avg_duration_ms"),
        )
        .where(window)
        .group_by(day)
        .order_by(day)
    )


def _summary_rows(rows, granularity: str) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        item = {
            "requests": int(r.requests or 0),
            "errors": int(r.errors or 0),
            "avg_duration_ms": (
                round(float(r.avg_duration_ms), 1) if r.avg_duration_ms is not None else None
            ),
        }
        if granularity == "route":
            item.update(method=r.method, route=r.route)
        else:
            item["day"] = r.day.date().isoformat() if r.day is not None else None
        out.append(item)
    return out


def default_usage_window(
    frm: Optional[datetime], to: Optional[datetime]
) -> Tuple[datetime, datetime]:
    to = to or _now()
    frm = frm or (to - timedelta(days=30))
    if frm.tzinfo is None:
        frm = frm.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)
    if frm >= to:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_window", "from must lie before to"
        )
    return frm, to


async def usage_summary(
    db: AsyncSession,
    key_id: str,
    frm: Optional[datetime] = None,
    to: Optional[datetime] = None,
    granularity: str = "day",
) -> Dict[str, Any]:
    frm, to = default_usage_window(frm, to)
    rows = (await db.execute(build_usage_summary([key_id], frm, to, granularity))).all()
    items = _summary_rows(rows, granularity)
    return {
        "key_id": key_id,
        "from": frm,
        "to": to,
        "granularity": granularity,
        "total_requests": sum(i["requests"] for i in items),
        "total_errors": sum(i["errors"] for i in items),
        "items": items,
    }


def usage_event_dict(ev: ApiKeyUsageEvent) -> Dict[str, Any]:
    return {
        "id": ev.id,
        "api_key_id": ev.api_key_id,
        "key_prefix": ev.key_prefix,
        "organization_id": ev.organization_id,
        "user_id": ev.user_id,
        "request_id": ev.request_id,
        "method": ev.method,
        "route": ev.route,
        "project_id": ev.project_id,
        "status_code": ev.status_code,
        "duration_ms": ev.duration_ms,
        "scope_used": ev.scope_used,
        "ip_address": ev.ip_address,
        "user_agent": ev.user_agent,
        "request_bytes": ev.request_bytes,
        "response_bytes": ev.response_bytes,
        "created_at": ev.created_at,
    }


async def usage_events(
    db: AsyncSession, key_id: str, cursor: Optional[int] = None, limit: int = 50
) -> Dict[str, Any]:
    """Newest first, keyset-paginated on the identity id."""
    limit = max(1, min(int(limit or 50), 500))
    stmt = select(ApiKeyUsageEvent).where(ApiKeyUsageEvent.api_key_id == key_id)
    if cursor is not None:
        stmt = stmt.where(ApiKeyUsageEvent.id < cursor)
    stmt = stmt.order_by(ApiKeyUsageEvent.id.desc()).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [usage_event_dict(r) for r in rows],
        "next_cursor": rows[-1].id if more and rows else None,
    }


_USAGE_COLUMNS = (
    "api_key_id",
    "key_prefix",
    "organization_id",
    "user_id",
    "request_id",
    "method",
    "route",
    "project_id",
    "status_code",
    "duration_ms",
    "scope_used",
    "ip_address",
    "user_agent",
    "request_bytes",
    "response_bytes",
    "created_at",
)


def usage_row(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise an event dict to insertable column values (truncated)."""
    row = {c: event.get(c) for c in _USAGE_COLUMNS}
    for col, size in (
        ("key_prefix", 32),
        ("request_id", 64),
        ("method", 8),
        ("route", 200),
        ("scope_used", 64),
        ("ip_address", 64),
        ("user_agent", 256),
    ):
        if isinstance(row[col], str):
            row[col] = row[col][:size]
    if row["created_at"] is None:
        row["created_at"] = _now()
    return row


def _build_touch_last_used(key_id: str, ip: Optional[str], when: datetime):
    """DB-side throttle: write only when last_used_at is NULL or older than
    LAST_USED_THROTTLE_SECONDS."""
    threshold = when - timedelta(seconds=LAST_USED_THROTTLE_SECONDS)
    return (
        update(ApiKey)
        .where(
            ApiKey.id == key_id,
            or_(ApiKey.last_used_at.is_(None), ApiKey.last_used_at < threshold),
        )
        .values(last_used_at=when, last_used_ip=ip)
        .execution_options(synchronize_session=False)
    )


async def touch_last_used(
    db: AsyncSession, key_id: str, ip: Optional[str] = None, when: Optional[datetime] = None
) -> bool:
    result = await db.execute(_build_touch_last_used(key_id, ip, when or _now()))
    return (result.rowcount or 0) > 0


def touch_last_used_sync(
    db: Session, key_id: str, ip: Optional[str] = None, when: Optional[datetime] = None
) -> bool:
    result = db.execute(_build_touch_last_used(key_id, ip, when or _now()))
    return (result.rowcount or 0) > 0


async def record_usage(db: AsyncSession, events: Sequence[Dict[str, Any]]) -> int:
    """Insert usage rows and refresh last_used per key. The caller commits."""
    rows = [usage_row(e) for e in events if e.get("key_prefix")]
    if not rows:
        return 0
    from sqlalchemy import insert

    await db.execute(insert(ApiKeyUsageEvent), rows)
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row["api_key_id"]:
            latest[row["api_key_id"]] = row
    for key_id, row in latest.items():
        await db.execute(_build_touch_last_used(key_id, row["ip_address"], row["created_at"]))
    return len(rows)


def build_delete_usage_older_than(cutoff: datetime):
    return delete(ApiKeyUsageEvent).where(ApiKeyUsageEvent.created_at < cutoff)
