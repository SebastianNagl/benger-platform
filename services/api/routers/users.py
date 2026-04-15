"""
User management endpoints.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_module import (
    User,
    get_all_users,
    require_superadmin,
    update_user_status,
    update_user_superadmin_status,
)
from auth_module.email_verification import email_verification_service
from database import get_db
from models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[User])
async def get_all_users_endpoint(
    current_user: User = Depends(require_superadmin), db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    return get_all_users(db)


@router.patch("/{user_id}/role", response_model=User)
async def update_user_role_endpoint(
    user_id: str,
    role_data: dict,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
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
    updated_user = update_user_superadmin_status(db, user_id, is_superadmin)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return updated_user


@router.patch("/{user_id}/status", response_model=User)
async def update_user_status_endpoint(
    user_id: str,
    status_data: dict,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Update user active status (admin only)"""
    # Update status
    updated_user = update_user_status(db, user_id, status_data.get("is_active"))
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return updated_user


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
    from user_service import delete_user

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
