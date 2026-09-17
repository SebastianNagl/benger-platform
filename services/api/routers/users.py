"""
User management endpoints.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth_module import (
    User,
    require_superadmin,
)
# Re-exported for tests that patch routers.users.get_all_users.
from auth_module import get_all_users  # noqa: F401
# Async twins for the user-status updaters (migrated handlers below). The
# legacy sync ``update_user_status`` / ``update_user_superadmin_status`` are no
# longer called here — the handlers were moved to the async DB lane.
from auth_module.user_service import (
    update_user_status_async,
    update_user_superadmin_status_async,
)
from auth_module.email_verification import email_verification_service
from database import get_async_db, get_db
from models import LtiAdminEvent, LtiPlatformRegistration, LtiUserLink
from models import User as DBUser
from schemas.user_anonymization_schemas import (
    AnonymizeResult,
    UserAnonymizationPreviewRead,
)
from services.user_anonymization import (
    AnonymizationRefused,
    AnonymizationUserNotFound,
    anonymization_check,
    anonymization_footprint,
    anonymize_user,
    revoke_lms_link_tokens,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[User])
async def get_all_users_endpoint(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
    search: Optional[str] = Query(
        None,
        description=(
            "Optional ILIKE filter against username / email / name. "
            "When set, the admin UI's user table avoids the full-table "
            "load just to filter in JS."
        ),
    ),
    limit: int = Query(
        500, ge=1, le=5_000, description="Safety cap on the response size."
    ),
):
    """Get all users (admin only).

    Optional `search` narrows the result on the server side; without it the
    handler preserves its historical "return everything" behaviour (bounded
    by `limit` to keep a stray superadmin click from streaming an unbounded
    table). The admin tab debounces the search input so per-keystroke
    typing doesn't fan out queries.
    """
    if not search:
        result = await db.execute(
            select(DBUser).order_by(DBUser.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    escaped = search.replace("%", r"\%").replace("_", r"\_")
    like = f"%{escaped}%"
    result = await db.execute(
        select(DBUser)
        .where(
            or_(
                DBUser.username.ilike(like),
                DBUser.email.ilike(like),
                DBUser.name.ilike(like),
            )
        )
        .order_by(DBUser.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.patch("/{user_id}/role", response_model=User)
async def update_user_role_endpoint(
    user_id: str,
    role_data: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Update user role (admin only)"""
    # Get superadmin status from request
    is_superadmin = role_data.get("is_superadmin", False)
    if not isinstance(is_superadmin, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="is_superadmin must be boolean",
        )

    # Update role
    updated_user = await update_user_superadmin_status_async(db, user_id, is_superadmin)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return updated_user


@router.patch("/{user_id}/status", response_model=User)
async def update_user_status_endpoint(
    user_id: str,
    status_data: dict,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Update user active status (admin only).

    An anonymized account cannot be switched back on (400
    ``account_anonymized``): it has no name, email or password any more.
    """
    if status_data.get("is_active"):
        anonymized_at = (
            await db.execute(select(DBUser.anonymized_at).where(DBUser.id == user_id))
        ).scalar()
        if anonymized_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="account_anonymized",
            )
    # Update status
    updated_user = await update_user_status_async(db, user_id, status_data.get("is_active"))
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return updated_user


@router.get("/{user_id}/anonymization", response_model=UserAnonymizationPreviewRead)
async def preview_user_anonymization_endpoint(
    user_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Whether an account may be anonymized, with what stays and goes
    (superadmin only). Blocker and warning codes as in
    ``services/user_anonymization.py``; no organization scope applies."""
    target = (
        await db.execute(select(DBUser).where(DBUser.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    check = await anonymization_check(db, target, actor_id=current_user.id)
    footprint = await anonymization_footprint(db, target.id)
    return UserAnonymizationPreviewRead(
        user_id=target.id,
        eligible=check.eligible,
        blockers=check.blockers,
        warnings=check.warnings,
        keeps=footprint["keeps"],
        removes=footprint["removes"],
    )


@router.post("/{user_id}/anonymize", response_model=AnonymizeResult)
async def anonymize_user_endpoint(
    user_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Anonymize an account (superadmin only).

    The support path for accounts an organization cannot anonymize itself
    (for example after its LMS connection was deleted). Same scrub as the LMS
    admin action, without organization scope rules; superadmins, the caller
    and accounts with payment records are refused (409
    ``anonymization_blocked`` with ``blockers``). Answers and grades stay;
    nothing is reassigned. Every organization whose LMS connection linked the
    account gets an audit entry (ids only).
    """
    linked = (
        await db.execute(
            select(
                LtiPlatformRegistration.id,
                LtiPlatformRegistration.name,
                LtiPlatformRegistration.organization_id,
                LtiPlatformRegistration.group_id,
            )
            .join(LtiUserLink, LtiUserLink.registration_id == LtiPlatformRegistration.id)
            .where(LtiUserLink.user_id == user_id)
            .distinct()
        )
    ).all()
    try:
        result = await anonymize_user(
            db, user_id, actor_id=current_user.id, reason="superadmin"
        )
    except AnonymizationUserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from None
    except AnonymizationRefused as refused:
        # Nothing was written; closing the session releases the row lock.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "anonymization_blocked",
                "message": "This account cannot be anonymized.",
                "blockers": refused.blockers,
            },
        ) from None

    now = datetime.now(timezone.utc)
    for registration_id, registration_name, organization_id, group_id in linked:
        db.add(
            LtiAdminEvent(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                registration_id=registration_id,
                registration_name=registration_name,
                group_id=group_id,
                actor_user_id=current_user.id,
                actor_kind="user",
                action="user_anonymized",
                changes={
                    "user_id": result.user_id,
                    "reason": "superadmin",
                    "warnings": list(result.warnings),
                    "removed": dict(result.removed),
                },
                created_at=now,
            )
        )
    await db.commit()
    await run_in_threadpool(revoke_lms_link_tokens, [result.user_id])
    logger.info("Superadmin %s anonymized user %s", current_user.id, result.user_id)
    return AnonymizeResult(
        user_id=result.user_id,
        anonymized_at=result.anonymized_at,
        pseudonym=result.pseudonym,
        warnings=result.warnings,
        removed=result.removed,
        kept=result.kept,
    )


@router.patch("/{user_id}/verify-email", response_model=User)
async def verify_user_email_endpoint(
    user_id: str,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Mark user's email as verified by admin (admin only)"""
    # Check if user exists
    target_user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Mark email as verified by admin
    success = email_verification_service.mark_email_verified(
        db=db, user_id=user_id, verified_by_id=current_user.id, method="admin"
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email",
        )

    # Return updated user
    updated_user = db.query(DBUser).filter(DBUser.id == user_id).first()
    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: str,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Delete a user (admin only)"""
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    # Check if user exists and delete
    from auth_module.user_service import delete_user

    try:
        if not delete_user(db, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except HTTPException:
        # Re-raise HTTPException as is
        raise
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete user: {e}"
        )

    return
