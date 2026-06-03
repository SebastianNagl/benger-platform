"""
Organization management API endpoints
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from auth_module import get_current_user, require_user
from auth_module.user_service import delete_user as delete_user_service
from database import get_db
from models import Organization, OrganizationMembership, OrganizationRole, User

# Performance monitoring removed - cleanup

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def can_manage_organization(user: User, organization_id: str, db: Session) -> bool:
    """Check if user can manage the specified organization"""
    if not user:
        return False

    if user.is_superadmin:
        return True

    # Check if user is admin of the specific organization
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    return membership is not None


def can_create_organization(user: User, db: Session) -> bool:
    """Check if user can create organizations (superadmin or org admin of any organization)"""
    if not user:
        return False

    if user.is_superadmin:
        return True

    # Check if user is an admin of any organization
    admin_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    return admin_membership is not None


# Pydantic models for API
class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    settings: Optional[dict] = {}


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class OrganizationResponse(OrganizationBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    member_count: Optional[int] = None
    role: Optional[OrganizationRole] = None  # User's role in this organization

    class Config:
        from_attributes = True


class OrganizationMemberResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    role: OrganizationRole
    is_active: bool
    joined_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    email_verified: Optional[bool] = None
    email_verification_method: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateMemberRole(BaseModel):
    role: OrganizationRole


@router.get(
    "/",
    response_model=List[OrganizationResponse],
    summary="List Organizations",
    description="""
    Retrieve list of organizations accessible to the current user.

    **Access Control:**
    - **Superadmins**: Can see all active organizations
    - **Regular Users**: Can only see organizations they are members of

    **Response includes:**
    - Organization details (name, description, settings)
    - Member count for each organization
    - Organization status and metadata

    **Use Cases:**
    - Organization switcher in UI
    - Admin management interfaces
    - User dashboard organization listings
    """,
    responses={
        200: {
            "description": "List of accessible organizations",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "name": "Technical University of Munich",
                            "slug": "tum",
                            "description": "Main research organization",
                            "member_count": 25,
                            "is_active": True,
                            "created_at": "2024-01-15T10:00:00Z",
                        }
                    ]
                }
            },
        },
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions"},
    },
    operation_id="listOrganizations",
)
# @timing_decorator removed
async def list_organizations(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """List organizations accessible to the current user"""
    # Performance monitoring removed
    if current_user.is_superadmin:
        # OPTIMIZED: Get all organizations first
        organizations = db.query(Organization).filter(Organization.is_active == True).all()  # noqa: E712

        # Get member counts for all organizations
        member_counts_query = (
            db.query(
                OrganizationMembership.organization_id,
                func.count(OrganizationMembership.id).label("member_count"),
            )
            .filter(
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .group_by(OrganizationMembership.organization_id)
            .all()
        )

        # Create a lookup dict for member counts
        member_count_dict = {org_id: count for org_id, count in member_counts_query}

        # Get superadmin's actual roles in organizations (if any)
        superadmin_roles_query = (
            db.query(OrganizationMembership.organization_id, OrganizationMembership.role)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .all()
        )
        superadmin_roles_dict = {org_id: role for org_id, role in superadmin_roles_query}

        # Build response objects
        result = []
        for org in organizations:
            org_dict = org.__dict__.copy()
            org_dict["member_count"] = member_count_dict.get(org.id, 0)
            # Superadmins get their actual role if they have one, otherwise None (indicating superadmin access)
            org_dict["role"] = superadmin_roles_dict.get(org.id)
            result.append(OrganizationResponse(**org_dict))

        return result
    else:
        # OPTIMIZED: Get user's organizations with their roles
        # Join organizations with memberships to get role information
        user_orgs_with_roles = (
            db.query(Organization, OrganizationMembership.role)
            .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,  # noqa: E712
                Organization.is_active == True,  # noqa: E712
            )
            .all()
        )

        # OPTIMIZED: Single query to get all member counts at once
        if user_orgs_with_roles:
            org_ids = [org.id for org, role in user_orgs_with_roles]
            member_counts_query = (
                db.query(
                    OrganizationMembership.organization_id,
                    func.count(OrganizationMembership.id).label("member_count"),
                )
                .filter(
                    OrganizationMembership.organization_id.in_(org_ids),
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
                .group_by(OrganizationMembership.organization_id)
                .all()
            )

            # Create a lookup dict for member counts
            member_count_dict = {org_id: count for org_id, count in member_counts_query}
        else:
            member_count_dict = {}

        # Build response objects efficiently with role information
        result = []
        for org, role in user_orgs_with_roles:
            org_dict = org.__dict__.copy()
            org_dict["member_count"] = member_count_dict.get(org.id, 0)
            org_dict["role"] = role  # Include the user's role in this organization
            result.append(OrganizationResponse(**org_dict))

        return result


@router.post("/", response_model=OrganizationResponse)
async def create_organization(
    organization: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new organization (superadmin or org admin)"""
    # Check permissions
    if not can_create_organization(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins and organization admins can create organizations",
        )

    # Check if slug already exists
    existing = db.query(Organization).filter(Organization.slug == organization.slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization slug already exists",
        )

    # Create organization
    db_org = Organization(
        id=str(uuid4()),
        name=organization.name,
        display_name=organization.display_name,
        slug=organization.slug,
        description=organization.description,
        settings=organization.settings or {},
        is_active=True,
    )

    db.add(db_org)
    db.commit()
    db.refresh(db_org)

    return OrganizationResponse(**db_org.__dict__, member_count=0)


@router.get("/by-slug/{slug}", response_model=OrganizationResponse)
async def get_organization_by_slug(
    slug: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get organization by slug (used for subdomain routing)."""
    import re

    if not re.match(r'^[a-z0-9-]+$', slug):
        raise HTTPException(status_code=400, detail="Invalid slug format")

    organization = (
        db.query(Organization)
        .filter(Organization.slug == slug, Organization.is_active == True)  # noqa: E712
        .first()
    )
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check access
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this organization")

    # Get member count
    member_count = (
        db.query(func.count(OrganizationMembership.id))
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .scalar()
    )

    # Get user's role in this org
    user_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count
    org_dict["role"] = user_membership.role if user_membership else None

    return OrganizationResponse(**org_dict)


@router.get("/{organization_id}", response_model=OrganizationResponse)
# @timing_decorator removed
async def get_organization(
    organization_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get organization details"""
    # Performance monitoring removed
    # Get organization
    organization = db.query(Organization).filter(Organization.id == organization_id).first()

    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check access permissions
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this organization",
            )

    # OPTIMIZED: Get member count efficiently
    member_count = (
        db.query(func.count(OrganizationMembership.id))
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .scalar()
    )

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count or 0
    return OrganizationResponse(**org_dict)


@router.put("/{organization_id}", response_model=OrganizationResponse)
# @timing_decorator removed
async def update_organization(
    organization_id: str,
    update_data: OrganizationUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update organization (org admin or superadmin only)"""
    # Performance monitoring removed
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check permissions
    if not can_manage_organization(current_user, organization_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can update organization settings",
        )

    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(organization, field, value)

    organization.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(organization)

    # Invalidate slug cache (slug may have changed)
    from redis_cache import OrgSlugCache

    OrgSlugCache.invalidate_all()

    # OPTIMIZED: Get member count efficiently
    member_count = (
        db.query(func.count(OrganizationMembership.id))
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .scalar()
    )

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count or 0
    return OrganizationResponse(**org_dict)


@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete organization (superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can delete organizations",
        )
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Soft delete - just deactivate
    organization.is_active = False
    organization.updated_at = datetime.utcnow()

    # Also deactivate all memberships
    db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization_id
    ).update({"is_active": False, "updated_at": datetime.utcnow()})

    db.commit()

    # Invalidate slug cache for deleted org
    from redis_cache import OrgSlugCache

    OrgSlugCache.invalidate_slug(organization.slug)

    return {"message": "Organization deleted successfully"}


@router.get("/{organization_id}/members", response_model=List[OrganizationMemberResponse])
async def list_organization_members(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List organization members"""
    # Check access permissions
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this organization",
            )

    # Get members with user details
    members = (
        db.query(OrganizationMembership, User)
        .join(User, OrganizationMembership.user_id == User.id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .all()
    )

    result = []
    for membership, user in members:
        member_dict = membership.__dict__.copy()
        member_dict["user_name"] = user.name
        member_dict["user_email"] = user.email
        member_dict["email_verified"] = user.email_verified
        member_dict["email_verification_method"] = user.email_verification_method
        result.append(OrganizationMemberResponse(**member_dict))

    return result


@router.put("/{organization_id}/members/{user_id}/role")
async def update_member_role(
    organization_id: str,
    user_id: str,
    role_update: UpdateMemberRole,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update member role in organization (org admin or superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        # Check if user is org admin of this organization
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or superadmins can update member roles",
            )

    # Find the membership to update
    target_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization",
        )

    # Prevent users from modifying their own role (unless superadmin)
    if current_user.id == user_id and not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own role",
        )

    # Update role
    target_membership.role = role_update.role
    target_membership.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Member role updated successfully"}


@router.delete("/{organization_id}/members/{user_id}")
async def remove_member(
    organization_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove member from organization (org admin or superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        # Check if user is org admin of this organization
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or superadmins can remove members",
            )

    # Find the membership to remove
    target_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization",
        )

    # Prevent users from removing themselves (unless superadmin)
    if current_user.id == user_id and not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself from organization",
        )

    # Soft delete - deactivate membership
    target_membership.is_active = False
    target_membership.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Member removed from organization successfully"}


# Global user management endpoints


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    email_verified: bool = False
    email_verification_method: Optional[str] = None
    name: str
    is_superadmin: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserSuperadminUpdate(BaseModel):
    is_superadmin: bool


class AddUserToOrganization(BaseModel):
    user_id: str
    role: OrganizationRole = OrganizationRole.ANNOTATOR


@router.get("/manage/users", response_model=List[UserResponse])
async def list_all_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None,
        description=(
            "Optional ILIKE filter against username / email / name. Pushed "
            "to SQL so the admin tab doesn't have to load every user just "
            "to filter in JS."
        ),
    ),
    limit: int = Query(
        500, ge=1, le=5_000, description="Safety cap on the response size."
    ),
):
    """List users visible to the current user.

    Superadmins see all users. Non-superadmins see only users from
    their own organizations.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    from sqlalchemy import or_ as sa_or

    query = db.query(User).filter(User.is_active == True)  # noqa: E712

    if not current_user.is_superadmin:
        # Get user's organization IDs from the Pydantic User model
        user_org_ids = [org['id'] for org in (current_user.organizations or [])]

        if not user_org_ids:
            return []

        # Get users who are members of the same organizations
        member_user_ids = (
            db.query(OrganizationMembership.user_id)
            .filter(
                OrganizationMembership.organization_id.in_(user_org_ids),
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .distinct()
            .subquery()
        )
        query = query.filter(User.id.in_(member_user_ids))

    # `search` defaults to FastAPI's Query(None) sentinel — truthy when this
    # handler is called directly from tests (FastAPI resolves it to None in
    # the request path). isinstance keeps the function safe in both paths.
    if isinstance(search, str) and search:
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        like = f"%{escaped}%"
        query = query.filter(
            sa_or(
                User.username.ilike(like),
                User.email.ilike(like),
                User.name.ilike(like),
            )
        )

    users = query.order_by(User.created_at.desc()).limit(limit).all()
    return [UserResponse(**user.__dict__) for user in users]


@router.put("/manage/users/{user_id}/superadmin")
async def update_user_superadmin_status(
    user_id: str,
    superadmin_update: UserSuperadminUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user's superadmin status (superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can promote other users to superadmin",
        )

    # Find user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update superadmin status
    user.is_superadmin = superadmin_update.is_superadmin
    user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    # Return the updated user with all fields
    return UserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        email=user.email,
        email_verified=user.email_verified,
        email_verification_method=user.email_verification_method,
        is_active=user.is_active,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.delete("/manage/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a user (superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can delete users",
        )

    try:
        # Use raw SQL for all operations to avoid SQLAlchemy lazy loading issues
        # First check if user exists
        result = db.execute(
            text("SELECT id, email, is_superadmin FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).first()

        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        is_superadmin = result.is_superadmin

        # Don't allow deleting yourself
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )

        # Don't allow deleting last superadmin
        if is_superadmin:
            superadmin_count = db.execute(
                text("SELECT COUNT(*) FROM users WHERE is_superadmin = true")
            ).scalar()
            if superadmin_count == 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete last superadmin",
                )

        # Delegate to the canonical cleanup in auth_module.user_service. It is the
        # single source of truth for user deletion: it reassigns authored content
        # (projects, korrektur comments, templates, …) to a fallback superadmin
        # and clears/cascades the per-user rows, covering every users.id FK. The
        # hand-rolled raw-SQL block that used to live here had drifted out of sync
        # — it omitted korrektur_comments (the FK that 500'd), destroyed content
        # instead of reassigning it, and interpolated user_id into SQL strings.
        if not delete_user_service(db, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        import logging

        logging.info(f"Successfully deleted user {user_id}")
        return {"message": "User deleted successfully"}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        # Log the error for debugging
        import logging

        logging.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}",
        )


@router.post("/{organization_id}/members")
async def add_user_to_organization(
    organization_id: str,
    add_user: AddUserToOrganization,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add user to organization (superadmin or org admin)"""
    # Check permissions
    if not current_user.is_superadmin:
        # Check if user is org admin of this organization
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or superadmins can add members",
            )

    # Check if organization exists
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check if user exists
    user = db.query(User).filter(User.id == add_user.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if user is already a member (including inactive/removed memberships)
    existing_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == add_user.user_id,
            OrganizationMembership.organization_id == organization_id,
        )
        .first()
    )

    if existing_membership and existing_membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization",
        )

    if existing_membership:
        # Reactivate previously removed membership
        existing_membership.is_active = True
        existing_membership.role = add_user.role
        existing_membership.updated_at = datetime.utcnow()
    else:
        # Create new membership
        membership = OrganizationMembership(
            id=str(uuid4()),
            user_id=add_user.user_id,
            organization_id=organization_id,
            role=add_user.role,
            is_active=True,
        )
        db.add(membership)

    db.commit()

    return {"message": "User added to organization successfully"}


# Email Verification Management Endpoints


class VerifyEmailRequest(BaseModel):
    """Request model for verifying user email"""

    reason: Optional[str] = Field(None, description="Optional reason for verification")


class BulkVerifyEmailRequest(BaseModel):
    """Request model for bulk email verification"""

    user_ids: List[str] = Field(..., description="List of user IDs to verify")
    reason: Optional[str] = Field(None, description="Optional reason for verification")


@router.post("/{organization_id}/members/{user_id}/verify-email")
async def verify_member_email(
    organization_id: str,
    user_id: str,
    request: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify email address for an organization member (org admin or superadmin only)

    This endpoint allows organization administrators to manually verify the email
    address of members in their organization.
    """
    from datetime import datetime, timezone

    # Check permissions
    if not current_user.is_superadmin:
        # Check if user is org admin of this organization
        admin_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )

        if not admin_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or superadmins can verify member emails",
            )

    # Check if the user to be verified is a member of this organization
    # Skip this check for superadmins as they can verify any user
    if not current_user.is_superadmin:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a member of this organization",
            )

    # Get the user to verify
    user_to_verify = db.query(User).filter(User.id == user_id).first()
    if not user_to_verify:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already verified
    if user_to_verify.email_verified:
        return {
            "message": "Email already verified",
            "email": user_to_verify.email,
            "verified_by": user_to_verify.email_verified_by_id,
            "verification_method": user_to_verify.email_verification_method,
        }

    # Verify the email
    user_to_verify.email_verified = True
    user_to_verify.email_verified_by_id = current_user.id
    user_to_verify.email_verified_at = datetime.now(timezone.utc)
    user_to_verify.email_verification_method = "admin"

    # Clear verification token if present
    user_to_verify.email_verification_token = None
    user_to_verify.email_verification_sent_at = None

    db.commit()

    # Log the action (could be extended to a proper audit log)
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Email verified by admin: user={user_to_verify.email}, "
        f"verified_by={current_user.email}, organization={organization_id}, "
        f"reason={request.reason}"
    )

    return {
        "message": "Email verified successfully",
        "email": user_to_verify.email,
        "verified_by": current_user.email,
        "verification_method": "admin",
    }


@router.post("/{organization_id}/members/verify-emails")
async def bulk_verify_member_emails(
    organization_id: str,
    request: BulkVerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bulk verify email addresses for organization members (org admin or superadmin only)

    This endpoint allows organization administrators to verify multiple member
    email addresses at once.
    """
    from datetime import datetime, timezone

    # Check permissions
    if not current_user.is_superadmin:
        # Check if user is org admin of this organization
        admin_membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )

        if not admin_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins or superadmins can verify member emails",
            )

    results = []
    success_count = 0
    skip_count = 0
    error_count = 0

    for user_id in request.user_ids:
        # Check if user is a member of this organization
        # Skip this check for superadmins as they can verify any user
        if not current_user.is_superadmin:
            membership = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
                .first()
            )

            if not membership:
                results.append(
                    {
                        "user_id": user_id,
                        "status": "error",
                        "message": "User is not a member of this organization",
                    }
                )
                error_count += 1
                continue

        # Get the user to verify
        user_to_verify = db.query(User).filter(User.id == user_id).first()
        if not user_to_verify:
            results.append(
                {
                    "user_id": user_id,
                    "status": "error",
                    "message": "User not found",
                }
            )
            error_count += 1
            continue

        # Check if already verified
        if user_to_verify.email_verified:
            results.append(
                {
                    "user_id": user_id,
                    "email": user_to_verify.email,
                    "status": "skipped",
                    "message": "Email already verified",
                }
            )
            skip_count += 1
            continue

        # Verify the email
        user_to_verify.email_verified = True
        user_to_verify.email_verified_by_id = current_user.id
        user_to_verify.email_verified_at = datetime.now(timezone.utc)
        user_to_verify.email_verification_method = "admin"

        # Clear verification token if present
        user_to_verify.email_verification_token = None
        user_to_verify.email_verification_sent_at = None

        results.append(
            {
                "user_id": user_id,
                "email": user_to_verify.email,
                "status": "success",
                "message": "Email verified successfully",
            }
        )
        success_count += 1

    # Commit all changes at once for better performance
    db.commit()

    # Log the bulk action
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Bulk email verification by admin: verified_by={current_user.email}, "
        f"organization={organization_id}, total={len(request.user_ids)}, "
        f"success={success_count}, skipped={skip_count}, errors={error_count}, "
        f"reason={request.reason}"
    )

    return {
        "summary": {
            "total": len(request.user_ids),
            "success": success_count,
            "skipped": skip_count,
            "errors": error_count,
        },
        "results": results,
    }
