from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db, get_db

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
    their own organizations.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    from sqlalchemy import or_ as sa_or

    stmt = select(User).where(User.is_active == True)  # noqa: E712

    if not current_user.is_superadmin:
        # Get user's organization IDs from the Pydantic User model
        user_org_ids = [org['id'] for org in (current_user.organizations or [])]

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

    # `search` defaults to FastAPI's Query(None) sentinel — truthy when this
    # handler is called directly from tests (FastAPI resolves it to None in
    # the request path). isinstance keeps the function safe in both paths.
    if isinstance(search, str) and search:
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        like = f"%{escaped}%"
        stmt = stmt.where(
            sa_or(
                User.username.ilike(like),
                User.email.ilike(like),
                User.name.ilike(like),
            )
        )

    stmt = stmt.order_by(User.created_at.desc()).limit(limit)
    users = (await db.execute(stmt)).scalars().all()
    return [UserResponse(**user.__dict__) for user in users]


@router.put("/manage/users/{user_id}/superadmin")
async def update_user_superadmin_status(
    user_id: str,
    superadmin_update: UserSuperadminUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update user's superadmin status (superadmin only)"""
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
