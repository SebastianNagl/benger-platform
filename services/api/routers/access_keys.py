"""Management of access keys (``bgr_...``) for the public ``/api/v1``.

* Organization keys: ``/api/organizations/{org_id}/access-keys``. Org admins
  manage every key of the org; group admins manage the keys of the groups
  they administer (``auth_module.org_scope``). An org key acts as its own
  service-account user with role ANNOTATOR, CONTRIBUTOR or (org-wide keys
  of an org-wide admin, core 2.45) ORG_ADMIN.
* Personal keys: ``/api/users/me/access-keys``. They act as their owner.
* Superadmin: ``/api/admin/access-keys`` (list across orgs, revoke, CSV
  export of usage).
* ``/api/access-keys/scopes``: scope definitions and presets for the UI.

An access key may call these routes with the ``keys:manage`` scope
(personal keys only, ``app/core/key_routes.py``). It never grants more
than it holds, and a key limited to projects or a group cannot create
keys. The full key is returned once, in the create response; lists only
show ``key_prefix``.
"""

from __future__ import annotations

import base64
import csv
import io
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scopes import GrantContext, scope_catalog, validate_scopes_for_grant
from auth_module import User, require_superadmin, require_user
from auth_module.principal import get_principal
from auth_module.org_scope import require_scope_admin
from database import get_async_db
from models import ApiKey, ApiKeyUsageEvent
from project_models import Project, ProjectOrganization
from schemas.access_key_schemas import (
    AccessKeyCreate,
    AccessKeyCreated,
    AccessKeyOut,
    AccessKeyPage,
    AccessKeyRevoke,
    AccessKeyUpdate,
    OrgAccessKeyCreate,
    ScopeCatalog,
    UsageEventPage,
    UsageSummary,
)
from routers.public_api_gate import require_public_api
from services import api_key_service as svc

logger = logging.getLogger(__name__)

# Unreleased feature: every route answers 404 feature_disabled unless the
# public_api gate is open for the caller (routers/public_api_gate.py).
router = APIRouter(tags=["Access keys"], dependencies=[Depends(require_public_api)])

#: Active keys per owner (a user's personal keys, an org's keys).
MAX_ACTIVE_PERSONAL_KEYS = 25
MAX_ACTIVE_ORG_KEYS = 200

Granularity = Literal["day", "route"]


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _key_not_found() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "access_key_not_found", "Access key not found")


def _out(key: ApiKey) -> AccessKeyOut:
    return AccessKeyOut(**svc.public_key_dict(key))


def _created(key: ApiKey, plain: str) -> AccessKeyCreated:
    return AccessKeyCreated(key=_out(key), secret=plain)


# --------------------------------------------------------------------------- #
# Shared checks
# --------------------------------------------------------------------------- #


async def _count_active(db: AsyncSession, *conditions) -> int:
    return (
        await db.execute(
            select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None), *conditions)
        )
    ).scalar_one()


async def _check_org_projects(
    db: AsyncSession, org_id: str, group_id: Optional[str], project_ids: Optional[List[str]]
) -> None:
    """Every listed project must be visible to the org (or group): public, or
    attached to the org (to the group or org-wide for a group key)."""
    if not project_ids:
        return
    attached = select(ProjectOrganization.project_id).where(
        ProjectOrganization.organization_id == org_id
    )
    if group_id is not None:
        attached = attached.where(
            or_(ProjectOrganization.group_id == group_id, ProjectOrganization.group_id.is_(None))
        )
    rows = (
        await db.execute(
            select(Project.id).where(
                Project.id.in_(project_ids),
                Project.deleted_at.is_(None),
                or_(Project.is_public.is_(True), Project.id.in_(attached)),
            )
        )
    ).scalars().all()
    missing = sorted(set(project_ids) - set(rows))
    if missing:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_project",
            f"Not a project of this organization: {', '.join(missing)}",
        )


async def _check_personal_projects(
    db: AsyncSession, user: User, project_ids: Optional[List[str]]
) -> None:
    """Every listed project must be one the owner can see as a non-superadmin
    (keys never carry superadmin powers)."""
    if not project_ids:
        return
    from routers.projects.helpers import get_accessible_project_ids_async

    plain_user = user.model_copy(update={"is_superadmin": False})
    accessible = set(await get_accessible_project_ids_async(db, plain_user) or [])
    missing = sorted(set(project_ids) - accessible)
    if missing:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_project",
            f"Projects not accessible: {', '.join(missing)}",
        )


def _grant_context(request: Request, **kw) -> GrantContext:
    """Who grants: a browser session, or an access key (``keys:manage``),
    which never grants more than it holds and must not be project-bound."""
    principal = get_principal(request)
    if principal is None or not principal.is_api_key:
        return GrantContext(**kw)
    if principal.project_ids is not None or principal.group_id is not None:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "key_project_restricted",
            "A key limited to projects or a group cannot create keys",
        )
    return GrantContext(creator_scopes=principal.scopes, **kw)


def _parse_window(frm: Optional[datetime], to: Optional[datetime]):
    return svc.default_usage_window(frm, to)


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


@router.get("/api/access-keys/scopes", response_model=ScopeCatalog)
async def get_scope_catalog(current_user: User = Depends(require_user)):
    """Scope definitions (with German and English descriptions) and presets."""
    return scope_catalog()


# --------------------------------------------------------------------------- #
# Organization keys
# --------------------------------------------------------------------------- #

ORG_BASE = "/api/organizations/{org_id}/access-keys"


async def _load_org_key(db: AsyncSession, org_id: str, key_id: str) -> ApiKey:
    key = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.organization_id == org_id,
                ApiKey.owner_type == "org",
            )
        )
    ).scalar_one_or_none()
    if key is None:
        raise _key_not_found()
    return key


async def _gate_org_key(db: AsyncSession, user: User, org_id: str, key_id: str) -> ApiKey:
    """Load the key and require admin rights over its scope. A group admin
    asking for a key outside their groups gets 404, not 403."""
    scope = await require_scope_admin(db, user, org_id, any_group=True)
    key = await _load_org_key(db, org_id, key_id)
    if not scope.covers(key.group_id):
        raise _key_not_found()
    return key


def _usage_csv_rows(events: Iterable[ApiKeyUsageEvent]):
    for ev in events:
        yield [
            ev.created_at.isoformat() if ev.created_at else "",
            ev.key_prefix,
            ev.api_key_id or "",
            ev.organization_id or "",
            ev.user_id or "",
            ev.method or "",
            ev.route or "",
            ev.project_id or "",
            ev.status_code if ev.status_code is not None else "",
            ev.duration_ms if ev.duration_ms is not None else "",
            ev.scope_used or "",
            ev.ip_address or "",
            ev.request_id or "",
        ]


CSV_HEADER = [
    "created_at",
    "key_prefix",
    "api_key_id",
    "organization_id",
    "user_id",
    "method",
    "route",
    "project_id",
    "status_code",
    "duration_ms",
    "scope_used",
    "ip_address",
    "request_id",
]
CSV_BATCH = 1000


async def _stream_usage_csv(db: AsyncSession, conditions) -> AsyncIterator[str]:
    """CSV in keyset-paginated batches, so memory stays O(batch)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    yield buf.getvalue()
    last_id = None
    while True:
        stmt = select(ApiKeyUsageEvent).where(*conditions)
        if last_id is not None:
            stmt = stmt.where(ApiKeyUsageEvent.id > last_id)
        rows = (
            await db.execute(stmt.order_by(ApiKeyUsageEvent.id).limit(CSV_BATCH))
        ).scalars().all()
        if not rows:
            break
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerows(_usage_csv_rows(rows))
        yield buf.getvalue()
        last_id = rows[-1].id
        if len(rows) < CSV_BATCH:
            break


def _csv_response(gen, filename: str) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(ORG_BASE + "/usage/export.csv")
async def export_org_usage_csv(
    org_id: str,
    frm: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Usage events of the org's keys (group admins: their groups' keys)."""
    scope = await require_scope_admin(db, current_user, org_id, any_group=True)
    frm, to = _parse_window(frm, to)
    conditions = [
        ApiKeyUsageEvent.organization_id == org_id,
        ApiKeyUsageEvent.created_at >= frm,
        ApiKeyUsageEvent.created_at < to,
    ]
    if not scope.org_wide:
        group_keys = select(ApiKey.id).where(
            ApiKey.organization_id == org_id,
            ApiKey.group_id.in_(list(scope.admin_group_ids)),
        )
        conditions.append(ApiKeyUsageEvent.api_key_id.in_(group_keys))
    return _csv_response(_stream_usage_csv(db, conditions), f"access-key-usage-{org_id}.csv")


@router.get(ORG_BASE, response_model=List[AccessKeyOut])
async def list_org_keys(
    org_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    scope = await require_scope_admin(db, current_user, org_id, any_group=True)
    group_ids = None if scope.org_wide else scope.admin_group_ids
    return [_out(k) for k in await svc.list_keys_for_org(db, org_id, group_ids)]


@router.post(ORG_BASE, response_model=AccessKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_org_key(
    org_id: str,
    payload: OrgAccessKeyCreate,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create an org key. Org-wide keys need an org admin; group keys a
    group admin of that group (or an org admin)."""
    scope = await require_scope_admin(db, current_user, org_id, payload.group_id)
    # The creator must hold at least the key's role in that scope. Admins
    # (the only ones past the gate) always do; kept explicit for future
    # non-admin creators.
    creator_role = "ORG_ADMIN" if scope.covers(payload.group_id) else None
    if not svc.role_at_least(creator_role, payload.org_role):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "role_exceeds_creator",
            "You cannot create a key with a higher role than your own",
        )
    if payload.org_role == "ORG_ADMIN" and (payload.group_id or not scope.org_wide):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "role_exceeds_creator",
            "Only an organization admin can create an org-wide ORG_ADMIN key",
        )
    scopes = validate_scopes_for_grant(
        _grant_context(request, is_superadmin=scope.is_superadmin, is_org_admin=scope.org_wide),
        "org",
        payload.org_role,
        payload.scopes,
    )
    await _check_org_projects(db, org_id, payload.group_id, payload.project_ids)
    if await _count_active(db, ApiKey.organization_id == org_id) >= MAX_ACTIVE_ORG_KEYS:
        raise _error(
            status.HTTP_409_CONFLICT,
            "too_many_keys",
            f"An organization can hold at most {MAX_ACTIVE_ORG_KEYS} active keys",
        )
    data = payload.model_dump()
    data["scopes"] = scopes
    key, plain = await svc.create_org_key(db, current_user.id, org_id, data)
    await db.commit()
    logger.info(
        "Access key %s created for org %s by user %s", key.key_prefix, org_id, current_user.id
    )
    return _created(key, plain)


@router.patch(ORG_BASE + "/{key_id}", response_model=AccessKeyOut)
async def update_org_key(
    org_id: str,
    key_id: str,
    payload: AccessKeyUpdate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _gate_org_key(db, current_user, org_id, key_id)
    if "project_ids" in payload.model_fields_set:
        await _check_org_projects(db, org_id, key.group_id, payload.project_ids)
    _apply_update(key, payload)
    await db.commit()
    await db.refresh(key)
    return _out(key)


@router.post(ORG_BASE + "/{key_id}/revoke", response_model=AccessKeyOut)
async def revoke_org_key(
    org_id: str,
    key_id: str,
    body: Optional[AccessKeyRevoke] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _gate_org_key(db, current_user, org_id, key_id)
    await svc.revoke_key(db, key, current_user.id, body.reason if body else None)
    await db.commit()
    await db.refresh(key)
    logger.info("Access key %s revoked by user %s", key.key_prefix, current_user.id)
    return _out(key)


@router.get(ORG_BASE + "/{key_id}/usage", response_model=UsageSummary)
async def org_key_usage(
    org_id: str,
    key_id: str,
    frm: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    granularity: Granularity = Query("day"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _gate_org_key(db, current_user, org_id, key_id)
    return await svc.usage_summary(db, key.id, frm, to, granularity)


@router.get(ORG_BASE + "/{key_id}/usage/events", response_model=UsageEventPage)
async def org_key_usage_events(
    org_id: str,
    key_id: str,
    cursor: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _gate_org_key(db, current_user, org_id, key_id)
    return await svc.usage_events(db, key.id, cursor, limit)


def _apply_update(key: ApiKey, payload: AccessKeyUpdate) -> None:
    if key.revoked_at is not None:
        raise _error(
            status.HTTP_409_CONFLICT, "access_key_revoked", "A revoked key cannot be changed"
        )
    fields = payload.model_fields_set
    if "name" in fields:
        if not payload.name or not payload.name.strip():
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_name", "name is required")
        key.name = payload.name.strip()
    if "project_ids" in fields:
        key.project_ids = svc._normalize_project_ids(payload.project_ids)
    if "expires_at" in fields:
        key.expires_at = svc._validate_expiry(payload.expires_at)
    if "rate_limit_per_minute" in fields:
        key.rate_limit_per_minute = payload.rate_limit_per_minute
    if "rate_limit_per_day" in fields:
        key.rate_limit_per_day = payload.rate_limit_per_day
    key.updated_at = datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Personal keys
# --------------------------------------------------------------------------- #

ME_BASE = "/api/users/me/access-keys"


async def _load_own_key(db: AsyncSession, user: User, key_id: str) -> ApiKey:
    key = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id, ApiKey.owner_type == "user", ApiKey.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if key is None:
        raise _key_not_found()
    return key


@router.get(ME_BASE, response_model=List[AccessKeyOut])
async def list_my_keys(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    return [_out(k) for k in await svc.list_keys_for_user(db, current_user.id)]


@router.post(ME_BASE, response_model=AccessKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_my_key(
    payload: AccessKeyCreate,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    scopes = validate_scopes_for_grant(
        _grant_context(request, is_superadmin=bool(current_user.is_superadmin)),
        "user",
        None,
        payload.scopes,
    )
    await _check_personal_projects(db, current_user, payload.project_ids)
    active = await _count_active(
        db, ApiKey.owner_type == "user", ApiKey.user_id == current_user.id
    )
    if active >= MAX_ACTIVE_PERSONAL_KEYS:
        raise _error(
            status.HTTP_409_CONFLICT,
            "too_many_keys",
            f"You can hold at most {MAX_ACTIVE_PERSONAL_KEYS} active keys",
        )
    data = payload.model_dump()
    data["scopes"] = scopes
    key, plain = await svc.create_personal_key(db, current_user.id, data)
    await db.commit()
    logger.info("Personal access key %s created by user %s", key.key_prefix, current_user.id)
    return _created(key, plain)


@router.post(ME_BASE + "/{key_id}/revoke", response_model=AccessKeyOut)
async def revoke_my_key(
    key_id: str,
    body: Optional[AccessKeyRevoke] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _load_own_key(db, current_user, key_id)
    await svc.revoke_key(db, key, current_user.id, body.reason if body else None)
    await db.commit()
    await db.refresh(key)
    return _out(key)


@router.get(ME_BASE + "/{key_id}/usage", response_model=UsageSummary)
async def my_key_usage(
    key_id: str,
    frm: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    granularity: Granularity = Query("day"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    key = await _load_own_key(db, current_user, key_id)
    return await svc.usage_summary(db, key.id, frm, to, granularity)


# --------------------------------------------------------------------------- #
# Superadmin
# --------------------------------------------------------------------------- #

ADMIN_BASE = "/api/admin/access-keys"


def _encode_cursor(key: ApiKey) -> str:
    raw = f"{key.created_at.isoformat()}|{key.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, key_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), key_id
    except (ValueError, UnicodeDecodeError):
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_cursor", "Invalid cursor")


@router.get(ADMIN_BASE + "/usage/export.csv")
async def export_all_usage_csv(
    frm: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    frm, to = _parse_window(frm, to)
    conditions = [ApiKeyUsageEvent.created_at >= frm, ApiKeyUsageEvent.created_at < to]
    if organization_id:
        conditions.append(ApiKeyUsageEvent.organization_id == organization_id)
    return _csv_response(_stream_usage_csv(db, conditions), "access-key-usage.csv")


@router.get(ADMIN_BASE, response_model=AccessKeyPage)
async def admin_list_keys(
    organization_id: Optional[str] = Query(None),
    owner_type: Optional[Literal["user", "org"]] = Query(None),
    key_status: Optional[Literal["active", "revoked", "expired"]] = Query(None, alias="status"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ApiKey)
    if organization_id:
        stmt = stmt.where(ApiKey.organization_id == organization_id)
    if owner_type:
        stmt = stmt.where(ApiKey.owner_type == owner_type)
    now = datetime.now(timezone.utc)
    if key_status == "revoked":
        stmt = stmt.where(ApiKey.revoked_at.is_not(None))
    elif key_status == "expired":
        stmt = stmt.where(ApiKey.revoked_at.is_(None), ApiKey.expires_at <= now)
    elif key_status == "active":
        stmt = stmt.where(
            ApiKey.revoked_at.is_(None),
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
        )
    if cursor:
        ts, key_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(ApiKey.created_at < ts, (ApiKey.created_at == ts) & (ApiKey.id < key_id))
        )
    rows = (
        await db.execute(
            stmt.order_by(ApiKey.created_at.desc(), ApiKey.id.desc()).limit(limit + 1)
        )
    ).scalars().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return AccessKeyPage(
        items=[_out(k) for k in rows],
        next_cursor=_encode_cursor(rows[-1]) if more and rows else None,
    )


@router.post(ADMIN_BASE + "/{key_id}/revoke", response_model=AccessKeyOut)
async def admin_revoke_key(
    key_id: str,
    body: Optional[AccessKeyRevoke] = None,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if key is None:
        raise _key_not_found()
    await svc.revoke_key(db, key, current_user.id, body.reason if body else None)
    await db.commit()
    await db.refresh(key)
    logger.info("Access key %s revoked by superadmin %s", key.key_prefix, current_user.id)
    return _out(key)
