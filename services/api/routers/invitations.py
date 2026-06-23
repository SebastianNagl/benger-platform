"""
Organization invitation system API endpoints
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4


from fastapi import APIRouter, Depends, HTTPException, status  # noqa: E402
from pydantic import BaseModel, EmailStr, TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from auth_module import require_user  # noqa: E402
from database import get_async_db, get_db  # noqa: E402
from models import Invitation, Organization, OrganizationMembership, OrganizationRole, User  # noqa: E402
from notification_service import (  # noqa: E402
    notify_organization_invitation_accepted,
    notify_organization_invitation_sent,
)

# Import organization management check from organizations router
from routers.organizations import can_manage_organization  # noqa: E402

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

# Celery app
from celery_client import get_celery_app  # noqa: E402


logger = logging.getLogger(__name__)
celery_app = get_celery_app()


# Pydantic models for API
class InvitationCreate(BaseModel):
    email: EmailStr
    role: OrganizationRole


class InvitationResponse(BaseModel):
    id: str
    organization_id: str
    email: str
    role: OrganizationRole
    token: str
    invited_by: str
    expires_at: datetime
    accepted_at: Optional[datetime]
    accepted: bool
    created_at: datetime
    organization_name: Optional[str] = None
    inviter_name: Optional[str] = None

    class Config:
        from_attributes = True


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


@router.post("/organizations/{organization_id}/invitations", response_model=InvitationResponse)
async def create_invitation(
    organization_id: str,
    invitation_data: InvitationCreate,
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

    # Check permissions
    if not can_manage_organization(current_user, organization_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can send invitations",
        )

    # Check if user is already a member
    existing_user = db.query(User).filter(User.email == invitation_data.email).first()
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
            Invitation.email == invitation_data.email,
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
        token=generate_invitation_token(),
        invited_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),  # 7 days to accept
        accepted=False,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # Queue invitation email via Celery
    frontend_url = get_settings().frontend_url
    invitation_url = f"{frontend_url}/accept-invitation/{invitation.token}"

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
            queue="emails",
            retry=True,
            retry_policy={
                'max_retries': 3,
                'interval_start': 0,
                'interval_step': 0.2,
                'interval_max': 0.2,
            },
        )
        logger.info(f"📮 Queued invitation email for {invitation.email}")
    except Exception as e:
        # Log error but don't fail the invitation creation
        logger.error(f"Failed to queue invitation email: {e}")

    # Notify organization admins about invitation sent
    try:
        notify_organization_invitation_sent(
            db=db,
            organization_id=organization_id,
            organization_name=organization.name,
            invitee_email=invitation_data.email,
            inviter_name=current_user.name,
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
        token=invitation.token,
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

    if not can_manage_organization(current_user, organization_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can send invitations",
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
        existing_user = db.query(User).filter(User.email == email).first()
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
                Invitation.email == email,
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

        frontend_url = get_settings().frontend_url
        payload = [
            {
                "invitation_id": inv.id,
                "to_email": inv.email,
                "inviter_name": current_user.name,
                "organization_name": organization.name,
                "invitation_url": f"{frontend_url}/accept-invitation/{inv.token}",
                "role": inv.role.value,
            }
            for inv in created
        ]
        try:
            celery_app.send_task(
                "emails.send_bulk_invitations",
                args=[payload],
                queue="emails",
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
        except Exception as e:
            logger.error(f"Failed to queue bulk invitation emails: {e}")

        # Notify org admins per queued invite (best-effort, mirrors single invite).
        for inv in created:
            try:
                notify_organization_invitation_sent(
                    db=db,
                    organization_id=organization_id,
                    organization_name=organization.name,
                    invitee_email=inv.email,
                    inviter_name=current_user.name,
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
    response_model=List[InvitationResponse],
)
async def list_organization_invitations(
    organization_id: str,
    include_expired: bool = False,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List organization invitations (org admin or superadmin only)"""

    # Check permissions
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

    if not include_expired:
        stmt = stmt.where(Invitation.expires_at > datetime.now(timezone.utc))

    invitations = (await db.execute(stmt)).all()

    result = []
    for invitation, organization, inviter in invitations:
        invitation_dict = invitation.__dict__.copy()
        invitation_dict["organization_name"] = organization.name
        invitation_dict["inviter_name"] = inviter.name
        result.append(InvitationResponse(**invitation_dict))

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


@router.get("/token/{token}", response_model=InvitationResponse)
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

    return InvitationResponse(**invitation_dict)


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

    # Check if user is already a member
    existing_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == invitation.organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )
    if existing_membership:
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

    # Create organization membership
    membership = OrganizationMembership(
        id=str(uuid4()),
        user_id=current_user.id,
        organization_id=invitation.organization_id,
        role=invitation.role,
        is_active=True,
    )

    # Mark invitation as accepted
    invitation.accepted = True
    invitation.accepted_at = datetime.now(timezone.utc)

    # Organization membership created - no default organization needed in new system

    db.add(membership)
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

    # Check permissions
    if not current_user.is_superadmin:
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
                detail="Only organization admins or the inviter can cancel invitations",
            )

    # Delete the invitation
    await db.delete(invitation)
    await db.commit()

    return {"message": "Invitation cancelled successfully"}
