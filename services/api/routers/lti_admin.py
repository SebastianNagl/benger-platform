"""Superadmin CRUD for LTI 1.3 (Moodle) platform registrations.

Split-rule note: this router is the generic persistence surface over the
platform-owned ``lti_*`` tables — registration/deployment CRUD, the
tool-config echo, and grade-sync outbox reads + retry. It contains NO LTI
protocol logic: the OIDC login/launch/deep-linking endpoints and the AGS
grade-passback client live in ``benger_extended`` (which is why the
tool-config URLs point at ``/api/lti/*`` routes that only exist in the
extended edition). The community edition ships this admin surface over an
otherwise-dormant schema.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_module.dependencies import require_superadmin
from database import get_async_db
from models import (
    LtiDeployment,
    LtiGradeSync,
    LtiPlatformRegistration,
    LtiRegistrationInvite,
    LtiResourceLink,
    Organization,
)
from schemas.lti_schemas import (
    LtiDeploymentCreate,
    LtiDeploymentRead,
    LtiGradeSyncRead,
    LtiRegistrationCreate,
    LtiRegistrationInviteCreate,
    LtiRegistrationInviteCreated,
    LtiRegistrationInviteRead,
    LtiRegistrationRead,
    LtiRegistrationUpdate,
    LtiToolConfigRead,
    _require_http_url,
)

router = APIRouter(prefix="/api/admin/lti", tags=["admin", "lti"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _registration_read(
    reg: LtiPlatformRegistration, *, resource_link_count: Optional[int] = None
) -> LtiRegistrationRead:
    """Build the read shape from an eagerly-loaded registration row."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    deployments = sorted(
        reg.deployments, key=lambda d: (d.created_at or epoch, d.deployment_id)
    )
    return LtiRegistrationRead(
        id=reg.id,
        organization_id=reg.organization_id,
        name=reg.name,
        issuer=reg.issuer,
        client_id=reg.client_id,
        auth_login_url=reg.auth_login_url,
        auth_token_url=reg.auth_token_url,
        jwks_uri=reg.jwks_uri,
        link_existing_users_by_email=reg.link_existing_users_by_email,
        instructor_org_role=reg.instructor_org_role,
        status=reg.status,
        created_at=reg.created_at,
        updated_at=reg.updated_at,
        deployments=[LtiDeploymentRead.model_validate(d) for d in deployments],
        deployment_count=len(deployments),
        resource_link_count=resource_link_count,
    )


async def _load_registration(
    db: AsyncSession, registration_id: str
) -> LtiPlatformRegistration:
    """Fetch a registration with deployments eagerly loaded, or 404."""
    reg = (
        await db.execute(
            select(LtiPlatformRegistration)
            .options(selectinload(LtiPlatformRegistration.deployments))
            .where(LtiPlatformRegistration.id == registration_id)
        )
    ).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    return reg


async def _require_organization(db: AsyncSession, organization_id: str) -> None:
    org = (
        await db.execute(
            select(Organization.id).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")


async def _reject_issuer_client_conflict(
    db: AsyncSession, issuer: str, client_id: str, *, exclude_id: Optional[str] = None
) -> None:
    stmt = select(LtiPlatformRegistration.id).where(
        LtiPlatformRegistration.issuer == issuer,
        LtiPlatformRegistration.client_id == client_id,
    )
    if exclude_id:
        stmt = stmt.where(LtiPlatformRegistration.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A registration for this issuer and client_id already exists",
        )


# --------------------------------------------------------------------------- #
# Registrations
# --------------------------------------------------------------------------- #
@router.post("/registrations", status_code=201, response_model=LtiRegistrationRead)
async def create_registration(
    body: LtiRegistrationCreate,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Register an LTI platform (Moodle site) for an organization.

    ``deployment_ids`` become child ``LtiDeployment`` rows (deduplicated,
    order preserved). The (issuer, client_id) pair is globally unique.
    """
    await _require_organization(db, body.organization_id)
    await _reject_issuer_client_conflict(db, body.issuer, body.client_id)

    reg = LtiPlatformRegistration(
        id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        name=body.name,
        issuer=body.issuer,
        client_id=body.client_id,
        auth_login_url=body.auth_login_url,
        auth_token_url=body.auth_token_url,
        jwks_uri=body.jwks_uri,
        link_existing_users_by_email=body.link_existing_users_by_email,
        instructor_org_role=body.instructor_org_role,
    )
    db.add(reg)
    for deployment_id in dict.fromkeys(body.deployment_ids):
        db.add(
            LtiDeployment(
                id=str(uuid.uuid4()),
                registration_id=reg.id,
                deployment_id=deployment_id,
            )
        )
    await db.commit()

    return _registration_read(await _load_registration(db, reg.id))


@router.get("/registrations", response_model=List[LtiRegistrationRead])
async def list_registrations(
    organization_id: Optional[str] = Query(None),
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """All platform registrations (incl. their deployments + counts).

    Optionally filtered to one organization. An unknown organization id
    yields an empty list – it's a list filter, not a lookup.
    """
    stmt = (
        select(LtiPlatformRegistration)
        .options(selectinload(LtiPlatformRegistration.deployments))
        .order_by(LtiPlatformRegistration.created_at.desc())
    )
    if organization_id:
        stmt = stmt.where(
            LtiPlatformRegistration.organization_id == organization_id
        )
    regs = (await db.execute(stmt)).scalars().all()
    return [_registration_read(reg) for reg in regs]


# --------------------------------------------------------------------------- #
# Dynamic Registration invites
#
# Routes with the fixed "/registrations/invites" path segment MUST stay
# registered before "/registrations/{registration_id}" below — Starlette
# matches in registration order, so the parametrized route would otherwise
# swallow them with registration_id="invites".
# --------------------------------------------------------------------------- #
def _invite_status(invite: LtiRegistrationInvite, now: datetime) -> str:
    if invite.used_at is not None:
        return "used"
    if invite.expires_at < now:
        return "expired"
    return "pending"


def _invite_read(invite: LtiRegistrationInvite, now: datetime) -> LtiRegistrationInviteRead:
    return LtiRegistrationInviteRead(
        id=invite.id,
        organization_id=invite.organization_id,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        resulting_registration_id=invite.resulting_registration_id,
        status=_invite_status(invite, now),
    )


@router.post(
    "/registrations/invites",
    status_code=201,
    response_model=LtiRegistrationInviteCreated,
)
async def create_registration_invite(
    body: LtiRegistrationInviteCreate,
    request: Request,
    base_url: Optional[str] = Query(
        None,
        description=(
            "Public base URL of this deployment, e.g. https://what-a-benger.net. "
            "Defaults to the request's base URL."
        ),
    ),
    superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Mint a one-time LTI Dynamic Registration invite for an organization.

    The raw token (and the ``register_url`` embedding it) appears ONLY in
    this response — like an API key, only its sha256 is stored. The
    ``/api/lti/register/init`` endpoint that consumes the URL is served by
    the extended edition.
    """
    await _require_organization(db, body.organization_id)

    if base_url is None:
        base_url = str(request.base_url)
    try:
        _require_http_url(base_url)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="base_url must be an absolute http(s) URL"
        )

    token = secrets.token_urlsafe(32)
    invite = LtiRegistrationInvite(
        id=str(uuid.uuid4()),
        organization_id=body.organization_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        created_by=superadmin.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    base = base_url.rstrip("/")
    return LtiRegistrationInviteCreated(
        id=invite.id,
        organization_id=invite.organization_id,
        token=token,
        register_url=f"{base}/api/lti/register/init?token={token}",
        expires_at=invite.expires_at,
    )


@router.get(
    "/registrations/invites", response_model=List[LtiRegistrationInviteRead]
)
async def list_registration_invites(
    organization_id: Optional[str] = Query(None),
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """All Dynamic Registration invites, newest first, with computed status.

    Optionally filtered to one organization (an unknown id is a filter miss,
    not a 404). Never returns the raw token or its hash.
    """
    stmt = select(LtiRegistrationInvite).order_by(
        LtiRegistrationInvite.created_at.desc()
    )
    if organization_id:
        stmt = stmt.where(LtiRegistrationInvite.organization_id == organization_id)
    invites = (await db.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return [_invite_read(invite, now) for invite in invites]


@router.delete("/registrations/invites/{invite_id}", status_code=204)
async def revoke_registration_invite(
    invite_id: str,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke an unused invite (hard delete).

    A used invite is an audit record tied to the registration it created —
    it cannot be revoked (409).
    """
    invite = (
        await db.execute(
            select(LtiRegistrationInvite).where(LtiRegistrationInvite.id == invite_id)
        )
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.used_at is not None:
        raise HTTPException(
            status_code=409, detail="Invite already used; it is kept as an audit record"
        )
    await db.delete(invite)
    await db.commit()


@router.get("/registrations/{registration_id}", response_model=LtiRegistrationRead)
async def get_registration(
    registration_id: str,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """One registration with deployments and its resource-link count."""
    reg = await _load_registration(db, registration_id)
    resource_link_count = (
        await db.execute(
            select(func.count())
            .select_from(LtiResourceLink)
            .where(LtiResourceLink.registration_id == registration_id)
        )
    ).scalar() or 0
    return _registration_read(reg, resource_link_count=resource_link_count)


@router.put("/registrations/{registration_id}", response_model=LtiRegistrationRead)
async def update_registration(
    registration_id: str,
    body: LtiRegistrationUpdate,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Update registration fields and/or status (partial: only sent fields)."""
    reg = await _load_registration(db, registration_id)
    data = body.model_dump(exclude_unset=True)

    if "organization_id" in data:
        await _require_organization(db, data["organization_id"])

    new_issuer = data.get("issuer", reg.issuer)
    new_client_id = data.get("client_id", reg.client_id)
    if (new_issuer, new_client_id) != (reg.issuer, reg.client_id):
        await _reject_issuer_client_conflict(
            db, new_issuer, new_client_id, exclude_id=registration_id
        )

    for field_name, value in data.items():
        setattr(reg, field_name, value)
    await db.commit()

    return _registration_read(await _load_registration(db, registration_id))


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
@router.post(
    "/registrations/{registration_id}/deployments",
    status_code=201,
    response_model=LtiDeploymentRead,
)
async def add_deployment(
    registration_id: str,
    body: LtiDeploymentCreate,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Add a deployment id to a registration (unique per registration)."""
    await _load_registration(db, registration_id)
    existing = (
        await db.execute(
            select(LtiDeployment.id).where(
                LtiDeployment.registration_id == registration_id,
                LtiDeployment.deployment_id == body.deployment_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409, detail="Deployment id already registered"
        )

    deployment = LtiDeployment(
        id=str(uuid.uuid4()),
        registration_id=registration_id,
        deployment_id=body.deployment_id,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)
    return LtiDeploymentRead.model_validate(deployment)


@router.delete(
    "/registrations/{registration_id}/deployments/{deployment_pk}", status_code=204
)
async def remove_deployment(
    registration_id: str,
    deployment_pk: str,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove a deployment row (by its primary key) from a registration."""
    deployment = (
        await db.execute(
            select(LtiDeployment).where(
                LtiDeployment.id == deployment_pk,
                LtiDeployment.registration_id == registration_id,
            )
        )
    ).scalar_one_or_none()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    await db.delete(deployment)
    await db.commit()


# --------------------------------------------------------------------------- #
# Tool config
# --------------------------------------------------------------------------- #
@router.get(
    "/registrations/{registration_id}/tool-config",
    response_model=LtiToolConfigRead,
)
async def get_tool_config(
    registration_id: str,
    base_url: str = Query(
        ..., description="Public base URL of this deployment, e.g. https://what-a-benger.net"
    ),
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """The tool-side URLs to paste into Moodle's external-tool form.

    The ``/api/lti/*`` routes themselves are served by the extended edition;
    this endpoint only derives the canonical URLs from ``base_url``.
    """
    await _load_registration(db, registration_id)
    try:
        _require_http_url(base_url)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="base_url must be an absolute http(s) URL"
        )
    base = base_url.rstrip("/")
    return LtiToolConfigRead(
        login_url=f"{base}/api/lti/login",
        launch_url=f"{base}/api/lti/launch",
        jwks_url=f"{base}/api/lti/jwks",
        deep_linking_url=f"{base}/api/lti/deep-linking",
    )


# --------------------------------------------------------------------------- #
# Grade-sync outbox
# --------------------------------------------------------------------------- #
@router.get("/grade-syncs", response_model=List[LtiGradeSyncRead])
async def list_grade_syncs(
    project_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Grade-passback outbox rows, filterable by project, organization, status."""
    stmt = select(LtiGradeSync)
    if project_id or organization_id:
        # Join the resource link exactly once, even when both filters are set.
        stmt = stmt.join(
            LtiResourceLink, LtiResourceLink.id == LtiGradeSync.resource_link_id
        )
    if project_id:
        stmt = stmt.where(LtiResourceLink.project_id == project_id)
    if organization_id:
        stmt = stmt.join(
            LtiPlatformRegistration,
            LtiPlatformRegistration.id == LtiResourceLink.registration_id,
        ).where(LtiPlatformRegistration.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(LtiGradeSync.status == status_filter)
    stmt = stmt.order_by(LtiGradeSync.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [LtiGradeSyncRead.model_validate(row) for row in rows]


@router.post("/grade-syncs/{grade_sync_id}/retry", response_model=LtiGradeSyncRead)
async def retry_grade_sync(
    grade_sync_id: str,
    _superadmin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Reset a (typically failed) outbox row so the sync worker retries it now."""
    row = (
        await db.execute(select(LtiGradeSync).where(LtiGradeSync.id == grade_sync_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Grade sync not found")

    row.status = "pending"
    row.attempts = 0
    row.next_retry_at = datetime.now(timezone.utc)
    row.last_error = None
    await db.commit()
    await db.refresh(row)
    return LtiGradeSyncRead.model_validate(row)
