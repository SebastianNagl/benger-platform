"""
Organization invitation system API endpoints
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4


from fastapi import APIRouter, Depends, HTTPException, Request, status  # noqa: E402
from pydantic import BaseModel, EmailStr, TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from auth_module import require_user  # noqa: E402
from database import get_async_db, get_db  # noqa: E402
from models import (  # noqa: E402
    Invitation,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from notification_service import (  # noqa: E402
    notify_organization_invitation_accepted,
    notify_organization_invitation_sent,
)

# Import organization management checks from organizations router
from routers.organizations import can_manage_group, can_manage_organization  # noqa: E402

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

# Celery app
from celery_client import get_celery_app  # noqa: E402
from mailer.branding import resolve_email_brand  # noqa: E402


logger = logging.getLogger(__name__)
celery_app = get_celery_app()


# Pydantic models for API
class InvitationCreate(BaseModel):
    email: EmailStr
    role: OrganizationRole
    # Optional group scope: accepting also joins this group. Group admins may
    # invite ONLY into their own group (role capped below ORG_ADMIN).
    group_id: Optional[str] = None
    invited_as_group_admin: bool = False


class InvitationResponse(BaseModel):
    """Invitation shape for authenticated callers (create).

    Deliberately carries no ``token``: the token is the whole credential for
    accepting the invitation, and the invite link reaches the invitee by mail,
    rendered server-side. Only the by-token lookup echoes it, to a caller who
    already holds it (see ``InvitationByTokenResponse``).
    """

    id: str
    organization_id: str
    email: str
    role: OrganizationRole
    group_id: Optional[str] = None
    invited_as_group_admin: bool = False
    invited_by: str
    expires_at: datetime
    accepted_at: Optional[datetime]
    accepted: bool
    created_at: datetime
    organization_name: Optional[str] = None
    inviter_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvitationByTokenResponse(InvitationResponse):
    """Public by-token lookup. The caller already holds the token."""

    token: str


class InvitationAdminResponse(InvitationResponse):
    """Admin list shape: the invitation plus its mail-delivery state.

    Kept separate from ``InvitationByTokenResponse`` so the public by-token
    endpoint cannot leak a provider error message to whoever holds a link.
    Inherits no ``token``: an admin listing pending invitations must not be
    able to accept one on the invitee's behalf.
    """

    # sent | failed | queued | unknown, see invitation_email_status.
    email_status: str
    email_sent_at: Optional[datetime] = None
    email_last_attempt_at: Optional[datetime] = None
    email_attempts: int = 0
    email_last_error: Optional[str] = None


class InvitationResendResponse(BaseModel):
    """Result of a resend. Deliberately carries no token."""

    message: str
    invitation_id: str
    email: str
    email_status: str
    email_attempts: int
    email_last_attempt_at: Optional[datetime] = None


def invitation_email_status(invitation: Invitation) -> str:
    """Derive the delivery state an admin should see.

    ``unknown`` and ``failed`` are deliberately distinct: rows created before
    the bookkeeping columns existed (migration 107) carry no timestamps at
    all, and calling those failures would cry wolf on every historical invite.

    - ``sent``: SendGrid accepted the message.
    - ``failed``: a send was attempted or queued and the last outcome was an
      error. Retries that later succeed clear it.
    - ``queued``: attempted or queued, no confirmation and no error yet.
    - ``unknown``: nothing recorded.
    """
    if invitation.email_sent_at is not None:
        return "sent"
    if invitation.email_last_error:
        return "failed"
    if invitation.email_last_attempt_at is not None:
        return "queued"
    return "unknown"


# A resend is a human action on a single row, so the guard only has to stop an
# admin leaning on the button. The verification resend uses 5 minutes; an
# invitation resend is rarer and more often a genuine repair, so a minute is
# enough. Measured against email_last_attempt_at, which the API stamps at
# queue time, so a dead worker cannot turn the guard off.
RESEND_MIN_INTERVAL_SECONDS = 60

# Keeps a pathological provider message out of the row and off the screen.
INVITATION_ERROR_MAX_CHARS = 500


def _stamp_queued(invitation: Invitation, error: Optional[str] = None) -> None:
    """Record that an invitation mail was handed to (or refused by) Celery.

    Without this the row stays ``unknown`` between the enqueue and the
    worker's first attempt, and a broker outage would leave no trace at all.
    The worker stamps ``email_last_attempt_at`` again per attempt.

    A successful enqueue clears a stale error, so a resend after a failure
    reads as ``queued`` rather than keeping the old failure on screen. The
    worker writes a fresh error if this send fails too.
    """
    invitation.email_last_attempt_at = datetime.now(timezone.utc)
    invitation.email_last_error = (
        None if error is None else error[:INVITATION_ERROR_MAX_CHARS]
    )


class InvitationAccept(BaseModel):
    token: str
    user_info: Optional[dict] = None  # For new user registration during acceptance


# Bulk invite caps a single request so a pasted blob can't fan out unbounded.
MAX_BULK_INVITES = 100


class BulkInvitationCreate(BaseModel):
    # List[str] (not List[EmailStr]) on purpose: we validate each address inside
    # the handler so one malformed entry yields a per-email "invalid" result
    # instead of 422-ing the whole batch.
    emails: List[str]
    role: OrganizationRole
    group_id: Optional[str] = None
    invited_as_group_admin: bool = False


class BulkInvitationResultItem(BaseModel):
    email: str
    # queued | invalid | already_member | pending | duplicate
    status: str
    detail: Optional[str] = None


class BulkInvitationResponse(BaseModel):
    queued: int
    skipped: int
    total: int
    results: List[BulkInvitationResultItem]


# Reuses the exact validator behind InvitationCreate.email so single and bulk
# invites accept the same set of addresses.
_email_adapter = TypeAdapter(EmailStr)


def generate_invitation_token() -> str:
    """Generate a secure invitation token"""
    return secrets.token_urlsafe(32)


def _authorize_invitation(
    db: Session,
    current_user: User,
    organization_id: str,
    role: OrganizationRole,
    group_id: Optional[str],
) -> None:
    """Gate + group validation for invitation creation (single AND bulk).

    Org admins / superadmins invite freely (with or without a group scope).
    A GROUP admin may additionally invite — but only INTO their own group,
    and never as ORG_ADMIN (group admins must not mint org-wide admins).
    A group scope must reference an ACTIVE group of this org.
    """
    if can_manage_organization(current_user, organization_id, db):
        pass
    elif group_id and can_manage_group(current_user, organization_id, group_id, db):
        if role == OrganizationRole.ORG_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group admins cannot invite users as ORG_ADMIN",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only organization admins, superadmins, or the group's admins "
                "can send invitations"
            ),
        )

    if group_id:
        group = (
            db.query(OrganizationGroup)
            .filter(
                OrganizationGroup.id == group_id,
                OrganizationGroup.organization_id == organization_id,
            )
            .first()
        )
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
            )
        if not group.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Group is not active"
            )


@router.post("/organizations/{organization_id}/invitations", response_model=InvitationResponse)
async def create_invitation(
    organization_id: str,
    invitation_data: InvitationCreate,
    request: Request = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create and send an organization invitation (org admin or superadmin only).

    Stays on the SYNC DB lane: this handler calls
    ``can_manage_organization`` (sync, organizations domain) and
    ``notify_organization_invitation_sent`` (sync, ``shared/mailer`` — an
    excluded module that takes a sync ``Session`` and writes notification
    rows). Neither can accept an ``AsyncSession``, so converting this handler
    would require touching out-of-scope code. See the AUTH-domain migration
    notes — the read-only/notification-free invitation endpoints (list,
    validate, get-by-token, cancel) are on the async lane.
    """

    # Check if organization exists
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check permissions (org admin / superadmin, or the group's admin for
    # group-scoped invitations) + validate the group scope.
    _authorize_invitation(
        db,
        current_user,
        organization_id,
        invitation_data.role,
        invitation_data.group_id,
    )

    # Check if user is already a member
    existing_user = (
        db.query(User)
        .filter(func.lower(User.email) == invitation_data.email.strip().lower())
        .first()
    )
    if existing_user:
        existing_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == existing_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this organization",
            )

    # Check if there's already a pending invitation
    existing_invitation = (
        db.query(Invitation)
        .filter(
            Invitation.organization_id == organization_id,
            func.lower(Invitation.email) == invitation_data.email.strip().lower(),
            Invitation.accepted == False,  # noqa: E712
            Invitation.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active invitation already exists for this email",
        )

    # Create invitation
    invitation = Invitation(
        id=str(uuid4()),
        organization_id=organization_id,
        email=invitation_data.email,
        role=invitation_data.role,
        group_id=invitation_data.group_id,
        invited_as_group_admin=invitation_data.invited_as_group_admin,
        token=generate_invitation_token(),
        invited_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),  # 7 days to accept
        accepted=False,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # Queue invitation email via Celery. Brand it from the request host so a
    # vertretbar.net invite links to vertretbar + sends from the Vertretbar
    # sender (resolve_email_brand); benger hosts are unchanged.
    invite_host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host"))
        if request
        else None
    )
    brand = resolve_email_brand(invite_host)
    invitation_url = f"{brand.frontend_url}/accept-invitation/{invitation.token}"

    try:
        celery_app.send_task(
            "emails.send_invitation",
            args=[
                invitation.id,
                invitation.email,
                current_user.name,
                organization.name,
                invitation_url,
                invitation.role.value,
            ],
            kwargs={"host": invite_host},
            retry=True,
            retry_policy={
                'max_retries': 3,
                'interval_start': 0,
                'interval_step': 0.2,
                'interval_max': 0.2,
            },
        )
        logger.info(f"📮 Queued invitation email for invitation {invitation.id}")
        _stamp_queued(invitation)
    except Exception as e:
        # Log error but don't fail the invitation creation. The row records the
        # queue failure so the admin list shows "failed" instead of claiming
        # the invite went out.
        logger.error(f"Failed to queue invitation email: {e}")
        _stamp_queued(invitation, error=f"Failed to queue mail: {e}")
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record invitation mail queue state: {e}")
        db.rollback()

    # Notify organization admins about invitation sent
    try:
        notify_organization_invitation_sent(
            db=db,
            organization_id=organization_id,
            organization_name=organization.name,
            invitee_email=invitation_data.email,
            inviter_name=current_user.name,
            inviter_user_id=current_user.id,
        )
    except Exception as e:
        # Don't fail the invitation creation if notification fails
        print(f"Failed to send invitation notification: {e}")

    # Prepare response with additional info
    return InvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        role=invitation.role,
        group_id=invitation.group_id,
        invited_as_group_admin=invitation.invited_as_group_admin,
        invited_by=invitation.invited_by,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        accepted=invitation.accepted,
        created_at=invitation.created_at,
        organization_name=organization.name,
        inviter_name=current_user.name,
    )


@router.post(
    "/organizations/{organization_id}/invitations/bulk",
    response_model=BulkInvitationResponse,
)
async def create_bulk_invitations(
    organization_id: str,
    bulk_data: BulkInvitationCreate,
    request: Request = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create and send multiple organization invitations in one request.

    Mirrors create_invitation's permission + duplicate guards, but applies them
    per email so a single bad or duplicate address doesn't reject the whole
    batch. Each address comes back with an individual status; valid new ones are
    queued together via the emails.send_bulk_invitations Celery task.
    """
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    _authorize_invitation(
        db, current_user, organization_id, bulk_data.role, bulk_data.group_id
    )

    if len(bulk_data.emails) > MAX_BULK_INVITES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many invitations in one request (max {MAX_BULK_INVITES})",
        )

    results: List[BulkInvitationResultItem] = []
    created: List[Invitation] = []
    seen: set[str] = set()

    for raw_email in bulk_data.emails:
        email = raw_email.strip()
        if not email:
            continue

        # Validate with the same rules as the single-invite EmailStr field.
        try:
            email = _email_adapter.validate_python(email)
        except ValidationError:
            results.append(BulkInvitationResultItem(email=raw_email.strip(), status="invalid"))
            continue

        # Collapse duplicates within this request (case-insensitive).
        key = email.lower()
        if key in seen:
            results.append(BulkInvitationResultItem(email=email, status="duplicate"))
            continue
        seen.add(key)

        # Already an active member of this organization?
        existing_user = db.query(User).filter(func.lower(User.email) == key).first()
        if existing_user:
            existing_membership = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == existing_user.id,
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
                .first()
            )
            if existing_membership:
                results.append(BulkInvitationResultItem(email=email, status="already_member"))
                continue

        # Pending (unaccepted, unexpired) invitation already out?
        existing_invitation = (
            db.query(Invitation)
            .filter(
                Invitation.organization_id == organization_id,
                func.lower(Invitation.email) == key,
                Invitation.accepted == False,  # noqa: E712
                Invitation.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if existing_invitation:
            results.append(BulkInvitationResultItem(email=email, status="pending"))
            continue

        invitation = Invitation(
            id=str(uuid4()),
            organization_id=organization_id,
            email=email,
            role=bulk_data.role,
            group_id=bulk_data.group_id,
            invited_as_group_admin=bulk_data.invited_as_group_admin,
            token=generate_invitation_token(),
            invited_by=current_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        db.add(invitation)
        created.append(invitation)
        results.append(BulkInvitationResultItem(email=email, status="queued"))

    if created:
        db.commit()
        for invitation in created:
            db.refresh(invitation)

        invite_host = (
            (request.headers.get("x-forwarded-host") or request.headers.get("host"))
            if request
            else None
        )
        brand = resolve_email_brand(invite_host)
        payload = [
            {
                "invitation_id": inv.id,
                "to_email": inv.email,
                "inviter_name": current_user.name,
                "organization_name": organization.name,
                "invitation_url": f"{brand.frontend_url}/accept-invitation/{inv.token}",
                "role": inv.role.value,
                "host": invite_host,
            }
            for inv in created
        ]
        try:
            celery_app.send_task(
                "emails.send_bulk_invitations",
                args=[payload],
                retry=True,
                retry_policy={
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.2,
                    'interval_max': 0.2,
                },
            )
            logger.info(
                f"📮 Queued {len(payload)} bulk invitations for organization {organization_id}"
            )
            for inv in created:
                _stamp_queued(inv)
        except Exception as e:
            logger.error(f"Failed to queue bulk invitation emails: {e}")
            for inv in created:
                _stamp_queued(inv, error=f"Failed to queue mail: {e}")
        try:
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record bulk invitation mail queue state: {e}")
            db.rollback()

        # Notify org admins per queued invite (best-effort, mirrors single invite).
        for inv in created:
            try:
                notify_organization_invitation_sent(
                    db=db,
                    organization_id=organization_id,
                    organization_name=organization.name,
                    invitee_email=inv.email,
                    inviter_name=current_user.name,
                    inviter_user_id=current_user.id,
                )
            except Exception as e:
                logger.error(f"Failed to send bulk invitation notification: {e}")

    queued = sum(1 for item in results if item.status == "queued")
    return BulkInvitationResponse(
        queued=queued,
        skipped=len(results) - queued,
        total=len(results),
        results=results,
    )


@router.get(
    "/organizations/{organization_id}/invitations",
    response_model=List[InvitationAdminResponse],
)
async def list_organization_invitations(
    organization_id: str,
    include_expired: bool = False,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List organization invitations, with the mail-delivery state per row.

    Superadmins and the org's ORG_ADMINs see all pending invitations; a
    GROUP admin sees only the invitations scoped to their own groups (so
    the admin UI's pending list works for chair staff too).

    Read-only. ``email_status`` is derived per row (see
    ``invitation_email_status``) so the UI does not re-implement the rule.
    """

    # Check permissions
    admin_group_ids: Optional[List[str]] = None  # None = unrestricted
    if not current_user.is_superadmin:
        membership = (
            await db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if not membership:
            group_rows = await db.execute(
                select(OrganizationGroupMembership.group_id)
                .join(
                    OrganizationGroup,
                    OrganizationGroup.id == OrganizationGroupMembership.group_id,
                )
                .where(
                    OrganizationGroupMembership.user_id == current_user.id,
                    OrganizationGroupMembership.is_group_admin == True,  # noqa: E712
                    OrganizationGroup.organization_id == organization_id,
                )
            )
            admin_group_ids = [r[0] for r in group_rows.all()]
            if not admin_group_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only organization admins can view invitations",
                )

    # Build query
    stmt = (
        select(Invitation, Organization, User)
        .join(Organization, Invitation.organization_id == Organization.id)
        .join(User, Invitation.invited_by == User.id)
        .where(Invitation.organization_id == organization_id)
        .where(Invitation.accepted == False)  # Only show pending invitations  # noqa: E712
    )
    if admin_group_ids is not None:
        stmt = stmt.where(Invitation.group_id.in_(admin_group_ids))

    if not include_expired:
        stmt = stmt.where(Invitation.expires_at > datetime.now(timezone.utc))

    invitations = (await db.execute(stmt)).all()

    result = []
    for invitation, organization, inviter in invitations:
        invitation_dict = invitation.__dict__.copy()
        invitation_dict["organization_name"] = organization.name
        invitation_dict["inviter_name"] = inviter.name
        invitation_dict["email_status"] = invitation_email_status(invitation)
        result.append(InvitationAdminResponse(**invitation_dict))

    return result


class InvitationValidationResponse(BaseModel):
    """Response for invitation validation (registration use case)"""

    valid: bool
    email: str
    organization_name: str
    organization_id: str
    role: OrganizationRole
    inviter_name: str
    expires_at: datetime
    message: Optional[str] = None


@router.get("/validate/{token}", response_model=InvitationValidationResponse)
async def validate_invitation_token(token: str, db: AsyncSession = Depends(get_async_db)):
    """Validate invitation token for registration flow (public endpoint)"""

    invitation = (
        await db.execute(
            select(Invitation, Organization, User)
            .join(Organization, Invitation.organization_id == Organization.id)
            .join(User, Invitation.invited_by == User.id)
            .where(Invitation.token == token)
        )
    ).first()

    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation_obj, organization, inviter = invitation

    # Check if invitation is expired
    if invitation_obj.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired"
        )

    # Check if already accepted
    if invitation_obj.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted",
        )

    return InvitationValidationResponse(
        valid=True,
        email=invitation_obj.email,
        organization_name=organization.name,
        organization_id=organization.id,
        role=invitation_obj.role,
        inviter_name=inviter.name,
        expires_at=invitation_obj.expires_at,
        message=f"Valid invitation to join {organization.name} as {invitation_obj.role.value}",
    )


@router.get("/token/{token}", response_model=InvitationByTokenResponse)
async def get_invitation_by_token(token: str, db: AsyncSession = Depends(get_async_db)):
    """Get invitation details by token (public endpoint for invitation acceptance)"""

    invitation = (
        await db.execute(
            select(Invitation, Organization, User)
            .join(Organization, Invitation.organization_id == Organization.id)
            .join(User, Invitation.invited_by == User.id)
            .where(Invitation.token == token)
        )
    ).first()

    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation_obj, organization, inviter = invitation

    # Check if invitation is expired
    if invitation_obj.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired"
        )

    # Check if already accepted
    if invitation_obj.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted",
        )

    invitation_dict = invitation_obj.__dict__.copy()
    invitation_dict["organization_name"] = organization.name
    invitation_dict["inviter_name"] = inviter.name

    return InvitationByTokenResponse(**invitation_dict)


@router.post("/accept/{token}")
async def accept_invitation(
    token: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Accept an organization invitation"""
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    # Check if invitation is expired
    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired"
        )

    # Check if already accepted
    if invitation.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted",
        )

    # Check if the current user's email matches the invitation
    if current_user.email != invitation.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is not for your email address",
        )

    # Check if user is already a member. Removed (inactive) rows count too:
    # (user, org) is unique, so a removed member comes back by reactivating
    # that row (as POST /organizations/{id}/members does), never by a second
    # insert, which failed with a 500.
    existing_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == invitation.organization_id,
        )
        .first()
    )
    if existing_membership is not None and existing_membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this organization",
        )

    # Check if profile completion is required (for invited users without password)
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == current_user.id).first()
    if db_user and db_user.created_via_invitation and not db_user.profile_completed:
        return {
            "message": "Please complete your profile setup first",
            "profile_completed": False,
            "redirect_url": "/complete-profile",
        }

    if existing_membership is not None:
        # Restore the removed membership with the invited role.
        existing_membership.is_active = True
        existing_membership.role = invitation.role
        existing_membership.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            OrganizationMembership(
                id=str(uuid4()),
                user_id=current_user.id,
                organization_id=invitation.organization_id,
                role=invitation.role,
                is_active=True,
            )
        )

    # Mark invitation as accepted
    invitation.accepted = True
    invitation.accepted_at = datetime.now(timezone.utc)

    # Group-scoped invitation: also join the group (shared with the
    # register-with-token path in auth/session.py — silent degrade when the
    # group is gone/inactive, idempotent for existing memberships).
    from org_groups import ensure_invitation_group_membership

    ensure_invitation_group_membership(db, invitation, current_user.id)

    db.commit()

    # Get organization name for notification
    organization = (
        db.query(Organization).filter(Organization.id == invitation.organization_id).first()
    )

    # Notify organization admins about invitation acceptance
    try:
        notify_organization_invitation_accepted(
            db=db,
            organization_id=invitation.organization_id,
            organization_name=(organization.name if organization else "Unknown Organization"),
            new_member_name=current_user.name,
            new_member_email=current_user.email,
            new_member_user_id=current_user.id,
        )
    except Exception as e:
        # Don't fail the invitation acceptance if notification fails
        print(f"Failed to send invitation acceptance notification: {e}")

    return {
        "message": "Invitation accepted successfully",
        "organization_id": invitation.organization_id,
        "role": invitation.role,
        "profile_completed": True,
    }


async def _authorize_existing_invitation(
    db: AsyncSession,
    current_user: User,
    invitation: Invitation,
    action: str,
) -> None:
    """Gate an admin action on an EXISTING invitation row (async lane).

    Superadmins pass; otherwise the actor must hold an active ORG_ADMIN
    membership in the invitation's organization, or be the inviter. Cancel and
    resend share this so a resend can never reach further than a cancel.
    """
    if current_user.is_superadmin:
        return

    membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == invitation.organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if not membership and invitation.invited_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only organization admins or the inviter can {action} invitations",
        )


@router.delete("/{invitation_id}")
async def cancel_invitation(
    invitation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Cancel an invitation (org admin or superadmin only)"""

    invitation = (
        await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    ).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    await _authorize_existing_invitation(db, current_user, invitation, "cancel")

    # Delete the invitation
    await db.delete(invitation)
    await db.commit()

    return {"message": "Invitation cancelled successfully"}


@router.post("/{invitation_id}/resend", response_model=InvitationResendResponse)
async def resend_invitation(
    invitation_id: str,
    request: Request = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Re-queue the invitation mail for a pending invitation.

    Before this the only repair for a lost invitation mail (a dead mail
    worker, a transient provider failure, a mail the recipient deleted) was to
    cancel the invitation and create it again, which mints a new token and
    breaks any link already in flight. This reuses the same token, so a link
    sent earlier keeps working.

    Authorization is the same gate as cancel. Rejects an accepted or expired
    invitation, and refuses a second resend within
    ``RESEND_MIN_INTERVAL_SECONDS`` of the last attempt. The response
    deliberately omits the token: an admin never needs it, and the mail is the
    only place it belongs.
    """
    row = (
        await db.execute(
            select(Invitation, Organization)
            .join(Organization, Invitation.organization_id == Organization.id)
            .where(Invitation.id == invitation_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation, organization = row

    await _authorize_existing_invitation(db, current_user, invitation, "resend")

    if invitation.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted",
        )
    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    # Hammering guard. email_last_attempt_at is stamped at queue time, so this
    # holds even when the worker never picks the task up.
    if invitation.email_last_attempt_at is not None:
        elapsed = (
            datetime.now(timezone.utc) - invitation.email_last_attempt_at
        ).total_seconds()
        if elapsed < RESEND_MIN_INTERVAL_SECONDS:
            wait = int(RESEND_MIN_INTERVAL_SECONDS - elapsed) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait} seconds before resending this invitation",
            )

    # The inviter's name is what the recipient already saw, so keep it rather
    # than substituting whoever pressed resend.
    inviter_name = (
        await db.execute(select(User.name).where(User.id == invitation.invited_by))
    ).scalar_one_or_none() or current_user.name

    invite_host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host"))
        if request
        else None
    )
    brand = resolve_email_brand(invite_host)
    invitation_url = f"{brand.frontend_url}/accept-invitation/{invitation.token}"

    queue_error: Optional[str] = None
    try:
        celery_app.send_task(
            "emails.send_invitation",
            args=[
                invitation.id,
                invitation.email,
                inviter_name,
                organization.name,
                invitation_url,
                invitation.role.value,
            ],
            kwargs={"host": invite_host},
            retry=True,
            retry_policy={
                'max_retries': 3,
                'interval_start': 0,
                'interval_step': 0.2,
                'interval_max': 0.2,
            },
        )
        logger.info(f"📮 Re-queued invitation email for invitation {invitation.id}")
    except Exception as e:
        # Mirrors create_invitation: the queue failure is recorded, not raised,
        # so the admin sees "failed" rather than a 500 with no trace.
        logger.error(f"Failed to re-queue invitation email: {e}")
        queue_error = f"Failed to queue mail: {e}"

    _stamp_queued(invitation, error=queue_error)
    await db.commit()
    await db.refresh(invitation)

    return InvitationResendResponse(
        message=(
            "Invitation email re-queued"
            if queue_error is None
            else "Invitation email could not be queued"
        ),
        invitation_id=invitation.id,
        email=invitation.email,
        email_status=invitation_email_status(invitation),
        email_attempts=invitation.email_attempts or 0,
        email_last_attempt_at=invitation.email_last_attempt_at,
    )
