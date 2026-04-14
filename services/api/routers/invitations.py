"""
Organization invitation system API endpoints
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth_module import require_user
from database import get_db
from models import Invitation, Organization, OrganizationMembership, OrganizationRole, User
from notification_service import (
    notify_organization_invitation_accepted,
    notify_organization_invitation_sent,
)

# Import organization management check from organizations router
from routers.organizations import can_manage_organization

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

# Celery app
from celery_client import get_celery_app

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
    """Create and send an organization invitation (org admin or superadmin only)"""

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
                OrganizationMembership.is_active == True,
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
            Invitation.accepted == False,
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
    import os

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
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


@router.get(
    "/organizations/{organization_id}/invitations",
    response_model=List[InvitationResponse],
)
async def list_organization_invitations(
    organization_id: str,
    include_expired: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List organization invitations (org admin or superadmin only)"""

    # Check permissions
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins can view invitations",
            )

    # Build query
    query = (
        db.query(Invitation, Organization, User)
        .join(Organization, Invitation.organization_id == Organization.id)
        .join(User, Invitation.invited_by == User.id)
        .filter(Invitation.organization_id == organization_id)
        .filter(Invitation.accepted == False)  # Only show pending invitations
    )

    if not include_expired:
        query = query.filter(Invitation.expires_at > datetime.now(timezone.utc))

    invitations = query.all()

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
async def validate_invitation_token(token: str, db: Session = Depends(get_db)):
    """Validate invitation token for registration flow (public endpoint)"""

    invitation = (
        db.query(Invitation, Organization, User)
        .join(Organization, Invitation.organization_id == Organization.id)
        .join(User, Invitation.invited_by == User.id)
        .filter(Invitation.token == token)
        .first()
    )

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
async def get_invitation_by_token(token: str, db: Session = Depends(get_db)):
    """Get invitation details by token (public endpoint for invitation acceptance)"""

    invitation = (
        db.query(Invitation, Organization, User)
        .join(Organization, Invitation.organization_id == Organization.id)
        .join(User, Invitation.invited_by == User.id)
        .filter(Invitation.token == token)
        .first()
    )

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
            OrganizationMembership.is_active == True,
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
    db: Session = Depends(get_db),
):
    """Cancel an invitation (org admin or superadmin only)"""

    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    # Check permissions
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == invitation.organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,
            )
            .first()
        )
        if not membership and invitation.invited_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or the inviter can cancel invitations",
            )

    # Delete the invitation
    db.delete(invitation)
    db.commit()

    return {"message": "Invitation cancelled successfully"}
