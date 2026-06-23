from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db

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
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List organizations accessible to the current user"""
    # Performance monitoring removed
    if current_user.is_superadmin:
        # OPTIMIZED: Get all organizations first
        organizations = (
            await db.execute(
                select(Organization).where(Organization.is_active == True)  # noqa: E712
            )
        ).scalars().all()

        # Get member counts for all organizations
        member_counts_query = (
            await db.execute(
                select(
                    OrganizationMembership.organization_id,
                    func.count(OrganizationMembership.id).label("member_count"),
                )
                .where(
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
                .group_by(OrganizationMembership.organization_id)
            )
        ).all()

        # Create a lookup dict for member counts
        member_count_dict = {org_id: count for org_id, count in member_counts_query}

        # Get superadmin's actual roles in organizations (if any)
        superadmin_roles_query = (
            await db.execute(
                select(
                    OrganizationMembership.organization_id, OrganizationMembership.role
                )
                .where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).all()
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
            await db.execute(
                select(Organization, OrganizationMembership.role)
                .join(
                    OrganizationMembership,
                    Organization.id == OrganizationMembership.organization_id,
                )
                .where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                    Organization.is_active == True,  # noqa: E712
                )
            )
        ).all()

        # OPTIMIZED: Single query to get all member counts at once
        if user_orgs_with_roles:
            org_ids = [org.id for org, role in user_orgs_with_roles]
            member_counts_query = (
                await db.execute(
                    select(
                        OrganizationMembership.organization_id,
                        func.count(OrganizationMembership.id).label("member_count"),
                    )
                    .where(
                        OrganizationMembership.organization_id.in_(org_ids),
                        OrganizationMembership.is_active == True,  # noqa: E712
                    )
                    .group_by(OrganizationMembership.organization_id)
                )
            ).all()

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
    db: AsyncSession = Depends(get_async_db),
):
    """Create a new organization (superadmin or org admin)"""
    # Check permissions. ``can_create_organization`` is a sync-only helper
    # (sync ``db.query`` in ``_common``); bridge it onto a sync Session bound to
    # THIS async session's connection via ``db.run_sync`` so it runs inside the
    # same transaction without opening a second connection.
    can_create = await db.run_sync(
        lambda sync_db: can_create_organization(current_user, sync_db)
    )
    if not can_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins and organization admins can create organizations",
        )

    # Check if slug already exists
    existing = (
        await db.execute(
            select(Organization).where(Organization.slug == organization.slug)
        )
    ).scalar_one_or_none()
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
    await db.commit()
    await db.refresh(db_org)

    return OrganizationResponse(**db_org.__dict__, member_count=0)

@router.get("/by-slug/{slug}", response_model=OrganizationResponse)
async def get_organization_by_slug(
    slug: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get organization by slug (used for subdomain routing)."""
    import re

    if not re.match(r'^[a-z0-9-]+$', slug):
        raise HTTPException(status_code=400, detail="Invalid slug format")

    organization = (
        await db.execute(
            select(Organization).where(
                Organization.slug == slug,
                Organization.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check access
    if not current_user.is_superadmin:
        membership = (
            await db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.organization_id == organization.id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this organization")

    # Get member count
    member_count = (
        await db.execute(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar()

    # Get user's role in this org
    user_membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count
    org_dict["role"] = user_membership.role if user_membership else None

    return OrganizationResponse(**org_dict)

@router.get("/{organization_id}", response_model=OrganizationResponse)
# @timing_decorator removed
async def get_organization(
    organization_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get organization details"""
    # Performance monitoring removed
    # Get organization
    organization = (
        await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()

    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check access permissions
    if not current_user.is_superadmin:
        membership = (
            await db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this organization",
            )

    # OPTIMIZED: Get member count efficiently
    member_count = (
        await db.execute(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar()

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count or 0
    return OrganizationResponse(**org_dict)

@router.put("/{organization_id}", response_model=OrganizationResponse)
# @timing_decorator removed
async def update_organization(
    organization_id: str,
    update_data: OrganizationUpdate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update organization (org admin or superadmin only)"""
    # Performance monitoring removed
    organization = (
        await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check permissions. ``can_manage_organization`` is a sync-only helper;
    # bridge it via ``db.run_sync`` so it runs on a sync Session bound to this
    # async session's connection (same transaction).
    can_manage = await db.run_sync(
        lambda sync_db: can_manage_organization(current_user, organization_id, sync_db)
    )
    if not can_manage:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can update organization settings",
        )

    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(organization, field, value)

    organization.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(organization)

    # Invalidate slug cache (slug may have changed)
    from redis_cache import OrgSlugCache

    OrgSlugCache.invalidate_all()

    # OPTIMIZED: Get member count efficiently
    member_count = (
        await db.execute(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar()

    org_dict = organization.__dict__.copy()
    org_dict["member_count"] = member_count or 0
    return OrganizationResponse(**org_dict)

@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete organization (superadmin only)"""
    # Check permissions
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can delete organizations",
        )
    organization = (
        await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Soft delete - just deactivate
    organization.is_active = False
    organization.updated_at = datetime.utcnow()

    # Also deactivate all memberships
    await db.execute(
        update(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization_id)
        .values(is_active=False, updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )

    await db.commit()

    # Invalidate slug cache for deleted org
    from redis_cache import OrgSlugCache

    OrgSlugCache.invalidate_slug(organization.slug)

    return {"message": "Organization deleted successfully"}
