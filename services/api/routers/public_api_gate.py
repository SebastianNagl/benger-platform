"""Availability gate of the access-key feature (core 2.38).

Key management (``routers/access_keys.py``) and the public ``/api/v1``
surface are unreleased: they answer 404 ``feature_disabled`` unless
``extensions.public_api_enabled`` says the feature is on for the caller
(the extended edition evaluates its ``public_api`` feature flag; without an
extension the ``PUBLIC_API_ENABLED`` setting decides, default off).
``GET /api/access-keys/availability`` tells the frontend whether to show the
feature's entry points at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

import extensions
from auth_module import User, require_user
from auth_module.dependencies import optional_user
from auth_module.principal import get_principal
from database import get_async_db

FEATURE_DISABLED = "feature_disabled"


async def public_api_available(
    request: Request, user: User | None, db: AsyncSession
) -> bool:
    """The hook's answer for this request's caller. An organization key is
    judged by its organization as well as by its service account."""
    principal = get_principal(request)
    organization_id = (
        principal.organization_id if principal and principal.is_api_key else None
    )
    return await extensions.public_api_enabled(
        db, user, organization_id=organization_id
    )


async def require_public_api(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Router dependency: 404 ``feature_disabled`` while the feature is off,
    so the routes look like they do not exist to signed-in callers.

    Depends on ``require_user`` (every gated route needs a caller anyway) so
    FastAPI resolves the caller once per request: a second resolution would
    check an access key twice and count it twice against its rate limits.
    Anonymous requests therefore get the usual 401 first."""
    if not await public_api_available(request, user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": FEATURE_DISABLED, "message": "Not found"},
        )


async def require_public_api_public(
    request: Request,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """The gate for the public v1 docs (OpenAPI spec, Swagger UI), which
    need no login: anonymous callers pass only when the feature is open to
    everyone. Those routes authenticate nothing else, so resolving the
    caller here is the only resolution."""
    if not await public_api_available(request, user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": FEATURE_DISABLED, "message": "Not found"},
        )


availability_router = APIRouter(tags=["Access keys"])


@availability_router.get("/api/access-keys/availability")
async def access_keys_availability(
    request: Request,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """``{"enabled": bool}``: whether the caller may see the feature."""
    return {"enabled": await public_api_available(request, user, db)}
