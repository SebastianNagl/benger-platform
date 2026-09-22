from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from services.member_privacy import (
    name_admin_org_ids,
    org_name_mask,
    reveal_group_accounts,
)


def _require_login(current_user) -> None:
    """``get_current_user`` is optional auth and answers None for anonymous
    and deactivated (e.g. anonymized) accounts: refuse with 401, never 500."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


class OrganizationMemberListItem(OrganizationMemberResponse):
    """A member row of the org member list.

    ``is_lms_account``: the account came from, or is linked to, an LMS
    connection. ``is_pseudonymized``: the viewer may not see the real name
    (owner decision D8), so ``user_name`` is the pseudonym and
    ``user_email`` is None.
    """

    is_lms_account: bool = False
    is_pseudonymized: bool = False


class AddUserToOrganization(BaseModel):
    user_id: str
    role: OrganizationRole = OrganizationRole.ANNOTATOR



class VerifyEmailRequest(BaseModel):
    """Request model for verifying user email"""

    reason: Optional[str] = Field(None, description="Optional reason for verification")


class BulkVerifyEmailRequest(BaseModel):
    """Request model for bulk email verification"""

    user_ids: List[str] = Field(..., description="List of user IDs to verify")
    reason: Optional[str] = Field(None, description="Optional reason for verification")



async def _administers_a_group(db: AsyncSession, user_id: str, organization_id: str) -> bool:
    """Whether the user is group admin of a group of the org."""
    from models import OrganizationGroup, OrganizationGroupMembership

    row = (
        await db.execute(
            select(OrganizationGroupMembership.id)
            .join(
                OrganizationGroup,
                OrganizationGroup.id == OrganizationGroupMembership.group_id,
            )
            .where(
                OrganizationGroupMembership.user_id == user_id,
                OrganizationGroupMembership.is_group_admin == True,  # noqa: E712
                OrganizationGroup.organization_id == organization_id,
            )
            .limit(1)
        )
    ).first()
    return row is not None


@router.get("/{organization_id}/members", response_model=List[OrganizationMemberListItem])
async def list_organization_members(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List organization members.

    LMS accounts are listed by pseudonym, without email, unless the viewer
    is a superadmin, the account itself, or an org admin here and the
    account belongs to one of this org's own LMS connections (D8). In an org
    whose LMS connections only superadmins run, its contributors see those
    names too (the platform operator appoints them). A group admin sees the
    names of the accounts of this org's connections scoped to the groups
    they administer (the same names their group roster shows); group
    membership alone reveals nothing.
    """
    _require_login(current_user)
    name_admin_ids: list = []
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
        # ANNOTATOR members (incl. every LTI-provisioned student) must not
        # enumerate the org roster — names and emails of the whole cohort and
        # staff. Member visibility is a CONTRIBUTOR+ concern — or a GROUP
        # admin's: the org role is the capability axis and is_group_admin is
        # orthogonal, so an org-ANNOTATOR may legitimately administer a
        # group (group-scoped invitation, admin toggle) and needs the roster
        # to pick members for it.
        if membership.role == OrganizationRole.ANNOTATOR:
            if not await _administers_a_group(db, current_user.id, organization_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Member list requires a contributor or admin role",
                )
        name_admin_ids = await name_admin_org_ids(
            db, [(organization_id, membership.role)]
        )

    # Get members with user details
    members = (
        await db.execute(
            select(OrganizationMembership, User)
            .join(User, OrganizationMembership.user_id == User.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).all()

    # Group chips: one joined query over this org's groups.
    from models import OrganizationGroup, OrganizationGroupMembership

    group_rows = (
        await db.execute(
            select(
                OrganizationGroupMembership.user_id,
                OrganizationGroup.id,
                OrganizationGroup.name,
                OrganizationGroupMembership.is_group_admin,
            )
            .join(
                OrganizationGroup,
                OrganizationGroup.id == OrganizationGroupMembership.group_id,
            )
            .where(OrganizationGroup.organization_id == organization_id)
        )
    ).all()
    groups_by_user: dict = {}
    for user_id, gid, gname, is_admin in group_rows:
        groups_by_user.setdefault(user_id, []).append(
            MemberGroupInfo(id=gid, name=gname, is_group_admin=bool(is_admin))
        )

    mask = await org_name_mask(
        db,
        [user for _, user in members],
        viewer=current_user,
        admin_org_ids=name_admin_ids,
    )
    if mask.masked_ids and not name_admin_ids:
        viewer_id = str(current_user.id)
        admin_group_ids = {
            gid
            for uid, gid, _name, is_admin in group_rows
            if str(uid) == viewer_id and is_admin
        }
        if admin_group_ids:
            # The LMS users of the connections scoped to those groups, on
            # every row: who is in a group is up to the group admin, so it
            # decides nothing.
            mask = await reveal_group_accounts(
                db, mask, organization_id, admin_group_ids, mask.masked_ids
            )

    result = []
    for membership, user in members:
        member_dict = membership.__dict__.copy()
        member_dict["user_name"] = mask.label(user)
        member_dict["user_email"] = mask.email(user)
        member_dict["email_verified"] = user.email_verified
        member_dict["email_verification_method"] = user.email_verification_method
        member_dict["groups"] = groups_by_user.get(membership.user_id, [])
        member_dict["is_lms_account"] = mask.is_lms(user.id)
        member_dict["is_pseudonymized"] = mask.is_masked(user.id)
        result.append(OrganizationMemberListItem(**member_dict))

    return result

@router.put("/{organization_id}/members/{user_id}/role")
async def update_member_role(
    organization_id: str,
    user_id: str,
    role_update: UpdateMemberRole,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update member role in organization (org admin or superadmin only)"""
    _require_login(current_user)
    # Check permissions
    # can_manage_organization (org admin of this org OR superadmin) is the sync
    # helper in _common.py; bridge it via db.run_sync onto this async session's
    # connection (same transaction) — the single authz source instead of an
    # inlined ORG_ADMIN query per endpoint.
    if not await db.run_sync(
        lambda sync_db: can_manage_organization(
            current_user, organization_id, sync_db
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can update member roles",
        )

    # Find the membership to update
    target_membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

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

    await db.commit()

    return {"message": "Member role updated successfully"}

@router.delete("/{organization_id}/members/{user_id}")
async def remove_member(
    organization_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove member from organization (org admin or superadmin only)"""
    _require_login(current_user)
    # Check permissions
    if not await db.run_sync(
        lambda sync_db: can_manage_organization(
            current_user, organization_id, sync_db
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can remove members",
        )

    # Find the membership to remove
    target_membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

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

    await db.commit()

    return {"message": "Member removed from organization successfully"}

@router.post("/{organization_id}/members")
async def add_user_to_organization(
    organization_id: str,
    add_user: AddUserToOrganization,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Add user to organization (superadmin or org admin)"""
    _require_login(current_user)
    # Check permissions
    if not await db.run_sync(
        lambda sync_db: can_manage_organization(
            current_user, organization_id, sync_db
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can add members",
        )

    # Check if organization exists
    organization = (
        await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Check if user exists
    user = (
        await db.execute(select(User).where(User.id == add_user.user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if user is already a member (including inactive/removed memberships)
    existing_membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == add_user.user_id,
                OrganizationMembership.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()

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

    await db.commit()

    return {"message": "User added to organization successfully"}

@router.post("/{organization_id}/members/{user_id}/verify-email")
async def verify_member_email(
    organization_id: str,
    user_id: str,
    request: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Verify email address for an organization member (org admin or superadmin only)

    This endpoint allows organization administrators to manually verify the email
    address of members in their organization.
    """
    _require_login(current_user)
    from datetime import datetime, timezone

    # Check permissions
    if not await db.run_sync(
        lambda sync_db: can_manage_organization(
            current_user, organization_id, sync_db
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can verify member emails",
        )

    # Check if the user to be verified is a member of this organization
    # Skip this check for superadmins as they can verify any user
    if not current_user.is_superadmin:
        membership = (
            await db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a member of this organization",
            )

    # Get the user to verify
    user_to_verify = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user_to_verify:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    # The address stays hidden for LMS accounts of other orgs' connections
    # (D8); the caller is an admin of this org or a superadmin.
    email_mask = await org_name_mask(
        db, [user_to_verify], viewer=current_user, admin_org_ids=[organization_id]
    )
    shown_email = email_mask.email(user_to_verify)

    # Check if already verified
    if user_to_verify.email_verified:
        return {
            "message": "Email already verified",
            "email": shown_email,
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

    await db.commit()

    # Log the action (could be extended to a proper audit log)
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Email verified by admin: user={user_to_verify.id}, "
        f"verified_by={current_user.id}, organization={organization_id}, "
        f"reason={request.reason}"
    )

    return {
        "message": "Email verified successfully",
        "email": shown_email,
        "verified_by": current_user.email,
        "verification_method": "admin",
    }

@router.post("/{organization_id}/members/verify-emails")
async def bulk_verify_member_emails(
    organization_id: str,
    request: BulkVerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Bulk verify email addresses for organization members (org admin or superadmin only)

    This endpoint allows organization administrators to verify multiple member
    email addresses at once.
    """
    _require_login(current_user)
    from datetime import datetime, timezone

    # Check permissions
    if not await db.run_sync(
        lambda sync_db: can_manage_organization(
            current_user, organization_id, sync_db
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins or superadmins can verify member emails",
        )

    results = []
    success_count = 0
    skip_count = 0
    error_count = 0

    # One lookup for every requested user, and one mask over them (the
    # address stays hidden for LMS accounts of other orgs' connections, D8).
    requested_ids = sorted({str(uid) for uid in request.user_ids})
    users_by_id = {}
    for start in range(0, len(requested_ids), 5000):
        chunk = requested_ids[start : start + 5000]
        rows = await db.execute(select(User).where(User.id.in_(chunk)))
        users_by_id.update({str(u.id): u for u in rows.scalars().all()})
    email_mask = await org_name_mask(
        db,
        list(users_by_id.values()),
        viewer=current_user,
        admin_org_ids=[organization_id],
    )

    for user_id in request.user_ids:
        # Check if user is a member of this organization
        # Skip this check for superadmins as they can verify any user
        if not current_user.is_superadmin:
            membership = (
                await db.execute(
                    select(OrganizationMembership).where(
                        OrganizationMembership.user_id == user_id,
                        OrganizationMembership.organization_id == organization_id,
                        OrganizationMembership.is_active == True,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()

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
        user_to_verify = users_by_id.get(str(user_id))
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
        shown_email = email_mask.email(user_to_verify)

        # Check if already verified
        if user_to_verify.email_verified:
            results.append(
                {
                    "user_id": user_id,
                    "email": shown_email,
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
                "email": shown_email,
                "status": "success",
                "message": "Email verified successfully",
            }
        )
        success_count += 1

    # Commit all changes at once for better performance
    await db.commit()

    # Log the bulk action
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Bulk email verification by admin: verified_by={current_user.id}, "
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
