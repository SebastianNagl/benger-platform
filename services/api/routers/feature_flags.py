"""
Feature Flags API Router
Handles all feature flag management endpoints
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from auth_module.dependencies import require_superadmin, require_user
from database import get_db
from feature_flag_service import FeatureFlagService
from models import FeatureFlag as DBFeatureFlag
from models import User
from schemas.feature_flag_schemas import (
    FeatureFlagResponse,
    FeatureFlagStatusResponse,
    FeatureFlagUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])


@router.get("", response_model=List[FeatureFlagResponse])
async def list_feature_flags(
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """List all feature flags (Admin only)"""
    try:
        flags = db.query(DBFeatureFlag).all()
        return [FeatureFlagResponse.model_validate(flag) for flag in flags]
    except Exception as e:
        logger.error(f"Error listing feature flags: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list feature flags",
        )


@router.get("/all")
async def get_feature_flags(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    response: Response = None,
):
    """Get all feature flags (global, same for all users)"""
    try:
        # Set cache control headers to prevent browser caching
        if response:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        service = FeatureFlagService(db)
        return service.get_feature_flags()
    except Exception as e:
        logger.error(f"Error getting feature flags: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feature flags",
        )


@router.get("/{flag_id}", response_model=FeatureFlagResponse)
async def get_feature_flag(
    flag_id: str,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Get a specific feature flag (Admin only)"""
    try:
        flag = db.query(DBFeatureFlag).filter(DBFeatureFlag.id == flag_id).first()
        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature flag not found",
            )
        return FeatureFlagResponse.model_validate(flag)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feature flag: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feature flag",
        )


@router.put("/{flag_id}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    flag_id: str,
    flag_data: FeatureFlagUpdate,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Update a feature flag (Admin only)"""
    try:
        service = FeatureFlagService(db)
        updates = flag_data.model_dump(exclude_unset=True)

        # Update the feature flag
        updated_flag = service.update_flag(flag_id, updates)
        return FeatureFlagResponse.model_validate(updated_flag)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error updating feature flag: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feature flag",
        )


@router.delete("/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature_flag(
    flag_id: str,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Delete a feature flag (Admin only)"""
    try:
        service = FeatureFlagService(db)

        # Check if flag exists
        flag = db.query(DBFeatureFlag).filter(DBFeatureFlag.id == flag_id).first()
        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature flag not found",
            )

        # Delete the flag
        db.delete(flag)
        db.commit()

        # Invalidate cache
        service.invalidate_cache(flag.name)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting feature flag: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete feature flag",
        )


@router.get("/check/{flag_name}", response_model=FeatureFlagStatusResponse)
async def check_feature_flag(
    flag_name: str,
    organization_id: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Check if a feature flag is enabled for the current user"""
    try:
        # Load user with organization_memberships relationship for feature flag evaluation
        user = (
            db.query(User)
            .options(joinedload(User.organization_memberships))
            .filter(User.id == current_user.id)
            .first()
        )

        service = FeatureFlagService(db)
        is_enabled = service.is_enabled(flag_name, user, organization_id)

        return FeatureFlagStatusResponse(
            flag_name=flag_name,
            is_enabled=is_enabled,
        )
    except Exception as e:
        logger.error(f"Error checking feature flag: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check feature flag",
        )
