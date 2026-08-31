"""Organization group management (org → group → user layer).

Groups partition project visibility and provider API keys inside an org
(see ``services/shared/org_groups.py`` for the eligibility rule). This
module owns the generic CRUD + membership surface:

- Group CRUD is org-admin territory (``can_manage_organization``).
- Group MEMBER management extends to the group's own admins
  (``is_group_admin`` on the membership row) via ``can_manage_group``.
- Any active org member may list the org's groups (names are needed for
  pickers); per-group member lists stay behind ``can_manage_group``.

Handlers run on the async lane (new-code default) with inline async gates,
following the ``org_api_keys.py`` pattern; the sync ``can_manage_group``
helper lives beside ``can_manage_organization`` in ``_common`` for sync
callers. Schemas stay endpoint-local (``org_api_keys.py`` precedent).
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from models import (
    OrganizationApiKey,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
)
from project_models import ProjectOrganization

from ._common import router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GroupResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    member_count: Optional[int] = None
    is_member: bool = False
    is_group_admin: bool = False

    class Config:
        from_attributes = True


class GroupMemberUpsert(BaseModel):
    user_id: str
    is_group_admin: bool = False


class GroupMemberUpdate(BaseModel):
    is_group_admin: bool


class GroupMemberResponse(BaseModel):
    id: str
    group_id: str
    user_id: str
    is_group_admin: bool
    created_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    org_role: Optional[OrganizationRole] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Gates (async inline copies — org_api_keys.py pattern)
# ---------------------------------------------------------------------------


async def _get_membership(
    db: AsyncSession, user_id: str, org_id: str
) -> Optional[OrganizationMembership]:
    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _require_org_member(user: AuthUser, org_id: str, db: AsyncSession):
    if user.is_superadmin:
        return
    if await _get_membership(db, user.id, org_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


async def _require_org_admin(user: AuthUser, org_id: str, db: AsyncSession):
    if user.is_superadmin:
        return
    membership = await _get_membership(db, user.id, org_id)
    if membership is None or membership.role != OrganizationRole.ORG_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this organization",
        )


async def _load_group_or_404(
    db: AsyncSession, org_id: str, group_id: str
) -> OrganizationGroup:
    result = await db.execute(
        select(OrganizationGroup).where(
            OrganizationGroup.id == group_id,
            OrganizationGroup.organization_id == org_id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        )
    return group


async def _require_can_manage_group(
    user: AuthUser, org_id: str, group_id: str, db: AsyncSession
):
    """Superadmin ∨ org ORG_ADMIN ∨ that group's admin (async)."""
    if user.is_superadmin:
        return
    membership = await _get_membership(db, user.id, org_id)
    if membership is not None and membership.role == OrganizationRole.ORG_ADMIN:
        return
    result = await db.execute(
        select(OrganizationGroupMembership.id).where(
            OrganizationGroupMembership.group_id == group_id,
            OrganizationGroupMembership.user_id == user.id,
            OrganizationGroupMembership.is_group_admin == True,  # noqa: E712
        )
    )
    if result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this group",
        )


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/groups", response_model=List[GroupResponse])
async def list_organization_groups(
    organization_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List an org's groups. Any active member (names feed the pickers);
    member counts are included for CONTRIBUTOR+ callers only."""
    await _require_org_member(current_user, organization_id, db)
    membership = await _get_membership(db, current_user.id, organization_id)
    include_counts = current_user.is_superadmin or (
        membership is not None and membership.role != OrganizationRole.ANNOTATOR
    )

    groups = (
        (
            await db.execute(
                select(OrganizationGroup)
                .where(OrganizationGroup.organization_id == organization_id)
                .order_by(OrganizationGroup.created_at)
            )
        )
        .scalars()
        .all()
    )

    counts: dict = {}
    if include_counts and groups:
        count_rows = await db.execute(
            select(
                OrganizationGroupMembership.group_id,
                func.count(OrganizationGroupMembership.id),
            )
            .where(
                OrganizationGroupMembership.group_id.in_([g.id for g in groups])
            )
            .group_by(OrganizationGroupMembership.group_id)
        )
        counts = {gid: n for gid, n in count_rows.all()}

    own_rows = await db.execute(
        select(
            OrganizationGroupMembership.group_id,
            OrganizationGroupMembership.is_group_admin,
        ).where(
            OrganizationGroupMembership.user_id == current_user.id,
            OrganizationGroupMembership.group_id.in_([g.id for g in groups])
            if groups
            else False,
        )
    )
    own = {gid: bool(admin) for gid, admin in own_rows.all()}

    return [
        GroupResponse(
            id=g.id,
            organization_id=g.organization_id,
            name=g.name,
            description=g.description,
            is_active=g.is_active,
            created_at=g.created_at,
            updated_at=g.updated_at,
            member_count=counts.get(g.id, 0) if include_counts else None,
            is_member=g.id in own,
            is_group_admin=own.get(g.id, False),
        )
        for g in groups
    ]


@router.post(
    "/{organization_id}/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_group(
    organization_id: str,
    payload: GroupCreate,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a group (org admin / superadmin)."""
    await _require_org_admin(current_user, organization_id, db)

    duplicate = await db.execute(
        select(OrganizationGroup.id).where(
            OrganizationGroup.organization_id == organization_id,
            OrganizationGroup.name == payload.name,
        )
    )
    if duplicate.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A group with this name already exists in the organization",
        )

    group = OrganizationGroup(
        id=str(uuid4()),
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        is_active=True,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return GroupResponse(
        id=group.id,
        organization_id=group.organization_id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=0,
        is_member=False,
        is_group_admin=False,
    )


@router.patch("/{organization_id}/groups/{group_id}", response_model=GroupResponse)
async def update_organization_group(
    organization_id: str,
    group_id: str,
    payload: GroupUpdate,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Rename / describe / (de)activate a group (org admin / superadmin).

    Deactivation hides the group from pickers and blocks new attachments;
    it never changes visibility or key scope of existing rows.
    """
    await _require_org_admin(current_user, organization_id, db)
    group = await _load_group_or_404(db, organization_id, group_id)

    if payload.name is not None and payload.name != group.name:
        duplicate = await db.execute(
            select(OrganizationGroup.id).where(
                OrganizationGroup.organization_id == organization_id,
                OrganizationGroup.name == payload.name,
                OrganizationGroup.id != group_id,
            )
        )
        if duplicate.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A group with this name already exists in the organization",
            )
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.is_active is not None:
        group.is_active = payload.is_active

    await db.commit()
    await db.refresh(group)
    count = (
        await db.execute(
            select(func.count(OrganizationGroupMembership.id)).where(
                OrganizationGroupMembership.group_id == group_id
            )
        )
    ).scalar_one()
    return GroupResponse(
        id=group.id,
        organization_id=group.organization_id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=count,
    )


@router.delete("/{organization_id}/groups/{group_id}")
async def delete_organization_group(
    organization_id: str,
    group_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a group (org admin / superadmin).

    409 while project attachments, group API keys, or LTI (Moodle/ILIAS)
    registrations still reference it — detach/delete those first,
    explicitly. A delete never silently widens visibility (project
    attachments), promotes keys org-wide, or re-scopes an LMS integration;
    group memberships cascade away with the group.
    """
    await _require_org_admin(current_user, organization_id, db)
    group = await _load_group_or_404(db, organization_id, group_id)

    from models import LtiPlatformRegistration

    attachment_count = (
        await db.execute(
            select(func.count(ProjectOrganization.id)).where(
                ProjectOrganization.group_id == group_id
            )
        )
    ).scalar_one()
    key_count = (
        await db.execute(
            select(func.count(OrganizationApiKey.id)).where(
                OrganizationApiKey.group_id == group_id
            )
        )
    ).scalar_one()
    lti_count = (
        await db.execute(
            select(func.count(LtiPlatformRegistration.id)).where(
                LtiPlatformRegistration.group_id == group_id
            )
        )
    ).scalar_one()
    if attachment_count or key_count or lti_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Group still has {attachment_count} project attachment(s), "
                f"{key_count} API key(s), and {lti_count} LTI registration(s). "
                "Reassign the projects, remove the keys, and re-scope the LMS "
                "registrations first."
            ),
        )

    await db.delete(group)
    await db.commit()
    return {"message": "Group deleted"}


# ---------------------------------------------------------------------------
# Group members
# ---------------------------------------------------------------------------


@router.get(
    "/{organization_id}/groups/{group_id}/members",
    response_model=List[GroupMemberResponse],
)
async def list_group_members(
    organization_id: str,
    group_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List a group's members (org admin / group admin / superadmin)."""
    await _load_group_or_404(db, organization_id, group_id)
    await _require_can_manage_group(current_user, organization_id, group_id, db)

    rows = (
        (
            await db.execute(
                select(OrganizationGroupMembership)
                .options(joinedload(OrganizationGroupMembership.user))
                .where(OrganizationGroupMembership.group_id == group_id)
                .order_by(OrganizationGroupMembership.created_at)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    org_roles = {
        uid: role
        for uid, role in (
            await db.execute(
                select(
                    OrganizationMembership.user_id, OrganizationMembership.role
                ).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id.in_([m.user_id for m in rows])
                    if rows
                    else False,
                )
            )
        ).all()
    }
    return [
        GroupMemberResponse(
            id=m.id,
            group_id=m.group_id,
            user_id=m.user_id,
            is_group_admin=m.is_group_admin,
            created_at=m.created_at,
            user_name=m.user.name if m.user else None,
            user_email=m.user.email if m.user else None,
            org_role=org_roles.get(m.user_id),
        )
        for m in rows
    ]


@router.post(
    "/{organization_id}/groups/{group_id}/members",
    response_model=GroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_member(
    organization_id: str,
    group_id: str,
    payload: GroupMemberUpsert,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Add an existing org member to the group (org admin / group admin)."""
    group = await _load_group_or_404(db, organization_id, group_id)
    await _require_can_manage_group(current_user, organization_id, group_id, db)
    if not group.is_active:
        raise HTTPException(status_code=400, detail="Group is not active")

    target_membership = await _get_membership(db, payload.user_id, organization_id)
    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be an active member of the organization first",
        )

    existing = (
        await db.execute(
            select(OrganizationGroupMembership).where(
                OrganizationGroupMembership.group_id == group_id,
                OrganizationGroupMembership.user_id == payload.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_group_admin = payload.is_group_admin
        await db.commit()
        await db.refresh(existing)
        member = existing
    else:
        member = OrganizationGroupMembership(
            id=str(uuid4()),
            group_id=group_id,
            user_id=payload.user_id,
            is_group_admin=payload.is_group_admin,
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)

    return GroupMemberResponse(
        id=member.id,
        group_id=member.group_id,
        user_id=member.user_id,
        is_group_admin=member.is_group_admin,
        created_at=member.created_at,
        org_role=target_membership.role,
    )


@router.patch(
    "/{organization_id}/groups/{group_id}/members/{user_id}",
    response_model=GroupMemberResponse,
)
async def update_group_member(
    organization_id: str,
    group_id: str,
    user_id: str,
    payload: GroupMemberUpdate,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Toggle a member's group-admin flag (org admin / group admin)."""
    await _load_group_or_404(db, organization_id, group_id)
    await _require_can_manage_group(current_user, organization_id, group_id, db)

    member = (
        await db.execute(
            select(OrganizationGroupMembership).where(
                OrganizationGroupMembership.group_id == group_id,
                OrganizationGroupMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found"
        )
    member.is_group_admin = payload.is_group_admin
    await db.commit()
    await db.refresh(member)
    return GroupMemberResponse(
        id=member.id,
        group_id=member.group_id,
        user_id=member.user_id,
        is_group_admin=member.is_group_admin,
        created_at=member.created_at,
    )


@router.delete("/{organization_id}/groups/{group_id}/members/{user_id}")
async def remove_group_member(
    organization_id: str,
    group_id: str,
    user_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove a member from the group (org admin / group admin)."""
    await _load_group_or_404(db, organization_id, group_id)
    await _require_can_manage_group(current_user, organization_id, group_id, db)

    member = (
        await db.execute(
            select(OrganizationGroupMembership).where(
                OrganizationGroupMembership.group_id == group_id,
                OrganizationGroupMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found"
        )
    await db.delete(member)
    await db.commit()
    return {"message": "Group member removed"}
