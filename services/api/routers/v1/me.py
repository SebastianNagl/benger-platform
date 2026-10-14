"""``GET /api/v1/me``: who is calling and what the credential may do."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scopes import expand
from auth_module import require_user
from auth_module.principal import Principal
from database import get_async_db
from models import ApiKey, Organization, OrganizationGroup, OrganizationMembership
from routers.v1._deps import require_scope
from routers.v1._schemas import ERROR_RESPONSES, MeResponse

router = APIRouter(tags=["me"])


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _org_dict(org) -> Optional[dict]:
    if org is None:
        return None
    return {"id": str(org.id), "name": org.display_name or org.name, "slug": org.slug}


def _build_select_primary_org(user_id: str):
    """The user's oldest active membership whose organization is active."""
    return (
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.user_id == str(user_id),
            OrganizationMembership.is_active == True,  # noqa: E712
            Organization.is_active == True,  # noqa: E712
        )
        .order_by(OrganizationMembership.joined_at.asc(), Organization.id.asc())
        .limit(1)
    )


async def principal_summary(db: AsyncSession, principal: Principal) -> dict:
    """The ``principal`` object of ``/api/v1/me``."""
    if not principal.is_api_key:
        org = (
            await db.execute(_build_select_primary_org(principal.user_id))
        ).scalar_one_or_none()
        return {
            "kind": "session",
            "key_prefix": None,
            "scopes": ["*"],
            "project_ids": None,
            "organization": _org_dict(org),
            "group": None,
            "expires_at": None,
            "rate_limit": {"per_minute": None, "per_day": None},
        }

    from services.rate_limiter import api_key_limits

    key = await db.get(ApiKey, principal.api_key_id) if principal.api_key_id else None
    org = (
        await db.get(Organization, principal.organization_id)
        if principal.organization_id
        else None
    )
    group = (
        await db.get(OrganizationGroup, principal.group_id) if principal.group_id else None
    )
    limits = api_key_limits(principal)
    return {
        "kind": "api_key",
        "key_prefix": principal.key_prefix,
        "scopes": sorted(expand(principal.scopes)),
        "project_ids": sorted(principal.project_ids) if principal.project_ids is not None else None,
        "organization": _org_dict(org),
        "group": {"id": str(group.id), "name": group.name} if group is not None else None,
        "expires_at": _iso(key.expires_at) if key is not None else None,
        "rate_limit": {"per_minute": limits["minute"][0], "per_day": limits["day"][0]},
    }


@router.get(
    "/me",
    response_model=MeResponse,
    responses={401: ERROR_RESPONSES[401], 429: ERROR_RESPONSES[429]},
    summary="The calling key or session",
)
async def get_me(
    principal: Principal = Depends(require_scope()),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Describe the credential: its kind, expanded scopes, project allowlist,
    organization and group, expiry and rate limit, plus the user it acts as
    (the service account for an organization key). Needs no scope."""
    return {
        "principal": await principal_summary(db, principal),
        "user": {
            "id": str(user.id),
            "username": user.username,
            "name": user.name,
            "is_service_account": bool(getattr(user, "is_service_account", False)),
        },
    }
