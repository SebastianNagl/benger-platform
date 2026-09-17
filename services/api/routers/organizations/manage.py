from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db, get_db
from lms_name_masking import lms_link_exists
from services.member_privacy import (
    lms_account_ids,
    masked_name,
    masked_org_member_ids,
    protected_org_ids,
)


def _require_login(current_user) -> None:
    """``get_current_user`` answers None for anonymous and deactivated
    accounts: refuse with 401, never 500."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )


class UserResponse(BaseModel):
    id: str
    username: str
    # None for an LMS account whose real identity the viewer may not see.
    email: Optional[str] = None
    email_verified: bool = False
    email_verification_method: Optional[str] = None
    name: str
    is_superadmin: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    # The account came from, or is linked to, an LMS connection.
    is_lms_account: bool = False
    # The viewer sees the pseudonym instead of the real name (owner decision
    # D8): ``name`` and ``username`` carry the pseudonym, ``email`` is None.
    is_pseudonymized: bool = False

    class Config:
        from_attributes = True


class UserSuperadminUpdate(BaseModel):
    is_superadmin: bool



@router.get("/manage/users", response_model=List[UserResponse])
async def list_all_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
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
    organizations where they hold a CONTRIBUTOR or ORG_ADMIN role —
    ANNOTATOR memberships (every LTI student) grant no user enumeration. On
    an org whose LMS connections stay superadmin-run, only ORG_ADMIN counts.

    LMS accounts appear by pseudonym, without email, unless the viewer is a
    superadmin, the account itself, or an org admin of an org whose own LMS
    connection the account belongs to (D8). The search matches such
    accounts by pseudonym only, so it cannot tie a real name to one.
    """
    _require_login(current_user)

    from sqlalchemy import String, any_, bindparam
    from sqlalchemy import and_ as sa_and
    from sqlalchemy import not_ as sa_not
    from sqlalchemy import or_ as sa_or
    from sqlalchemy.dialects.postgresql import ARRAY

    stmt = select(User).where(User.is_active == True)  # noqa: E712
    masked_ids: set = set()

    if not current_user.is_superadmin:
        # Resolve from the membership table, not the auth-model org dicts:
        # role must gate this, and the dict shape is not guaranteed to carry it.
        org_roles = (
            await db.execute(
                select(
                    OrganizationMembership.organization_id,
                    OrganizationMembership.role,
                ).where(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,  # noqa: E712
                    OrganizationMembership.role.in_(
                        (OrganizationRole.ORG_ADMIN, OrganizationRole.CONTRIBUTOR)
                    ),
                )
            )
        ).all()
        # The members of an org whose LMS connections stay superadmin-run
        # (every LMS user and pilot teacher joins it) are listed to its org
        # admins only.
        protected = await protected_org_ids(
            db,
            [org_id for org_id, role in org_roles if role != OrganizationRole.ORG_ADMIN],
        )
        org_roles = [
            (org_id, role)
            for org_id, role in org_roles
            if role == OrganizationRole.ORG_ADMIN or str(org_id) not in protected
        ]
        user_org_ids = [org_id for org_id, _ in org_roles]
        admin_org_ids = [
            org_id for org_id, role in org_roles if role == OrganizationRole.ORG_ADMIN
        ]

        if not user_org_ids:
            return []

        # Get users who are members of the same organizations
        member_user_ids = (
            select(OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id.in_(user_org_ids),
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .distinct()
            .subquery()
        )
        stmt = stmt.where(User.id.in_(select(member_user_ids)))

        # Masked before the search and the limit: LMS accounts with the
        # pseudonym on (the link table narrows the candidates, the hook
        # decides), minus those this viewer may see.
        candidate_ids = (
            (
                await db.execute(
                    select(User.id).where(
                        User.is_active == True,  # noqa: E712
                        User.id.in_(select(member_user_ids)),
                        User.id != str(current_user.id),
                        sa_or(User.use_pseudonym.is_(None), User.use_pseudonym == True),  # noqa: E712
                        lms_link_exists(User.id),
                    )
                )
            )
            .scalars()
            .all()
        )
        if candidate_ids:
            lms_candidates = await lms_account_ids(db, candidate_ids)
            masked_ids = await masked_org_member_ids(
                db, lms_candidates, viewer=current_user, admin_org_ids=admin_org_ids
            )

    # `search` defaults to FastAPI's Query(None) sentinel — truthy when this
    # handler is called directly from tests (FastAPI resolves it to None in
    # the request path). isinstance keeps the function safe in both paths.
    if isinstance(search, str) and search:
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        like = f"%{escaped}%"
        text_match = sa_or(
            User.username.ilike(like),
            User.email.ilike(like),
            User.name.ilike(like),
        )
        if masked_ids:
            # One array parameter, whatever the number of masked accounts
            # (``IN (...)`` binds one parameter per id, and the driver
            # refuses more than 32767).
            is_masked = User.id == any_(
                bindparam("masked_ids", sorted(masked_ids), type_=ARRAY(String))
            )
            text_match = sa_or(
                sa_and(sa_not(is_masked), text_match),
                sa_and(is_masked, User.pseudonym.ilike(like)),
            )
        stmt = stmt.where(text_match)

    stmt = stmt.order_by(User.created_at.desc()).limit(limit)
    users = (await db.execute(stmt)).scalars().all()
    lms_ids = await lms_account_ids(db, [user.id for user in users])

    result = []
    for user in users:
        row = dict(user.__dict__)
        row["is_lms_account"] = str(user.id) in lms_ids
        if str(user.id) in masked_ids:
            label = masked_name(user)
            row.update(
                name=label,
                username=label,
                email=None,
                is_pseudonymized=True,
            )
        result.append(UserResponse(**row))
    return result


@router.put("/manage/users/{user_id}/superadmin")
async def update_user_superadmin_status(
    user_id: str,
    superadmin_update: UserSuperadminUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update user's superadmin status (superadmin only)"""
    _require_login(current_user)
    # Check permissions
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can promote other users to superadmin",
        )

    # Find user
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update superadmin status
    user.is_superadmin = superadmin_update.is_superadmin
    user.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

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
    """Delete a user (superadmin only).

    NOTE: kept fully SYNC on purpose. User deletion is dominated by the
    sync-only ``auth_module.user_service.delete_user`` orchestration, which is
    the single source of truth for reassigning authored content (projects,
    korrektur comments, templates, …) across every ``users.id`` FK. That helper
    runs raw multi-table SQL, ``inspect(db.get_bind())`` schema reflection,
    ``db.flush()``/``db.delete()`` and — critically — owns its OWN transaction
    lifecycle (it calls ``db.commit()`` on success and ``db.rollback()`` on
    failure). There is no clean DB split here, and bridging a self-committing
    sync service through ``db.run_sync`` would have it commit the shared async
    transaction out from under the handler. The handler also performs its own
    ``db.rollback()`` on error. Migrating this handler buys nothing and risks
    the most destructive endpoint in the router, so it stays on ``get_db``.
    """
    _require_login(current_user)
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
