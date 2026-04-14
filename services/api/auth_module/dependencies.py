"""
FastAPI dependencies for authentication

This module contains FastAPI dependency functions for authentication and authorization
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from .user_service import get_user_by_id

from .models import User
from .service import db_user_to_user, verify_token_cookie_or_header


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Get current user from token (either cookie or header)
    Returns None if no valid token is provided (for optional auth)
    """
    try:
        payload = verify_token_cookie_or_header(request)
        user_id: str = payload.get("user_id")
        if user_id is None:
            return None

        db_user = get_user_by_id(db, user_id)
        if db_user is None:
            return None

        return db_user_to_user(db_user)
    except HTTPException:
        # Return None for optional auth instead of raising exception
        return None


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Require authenticated user (raises 401 if not authenticated)
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        payload = verify_token_cookie_or_header(request)
        user_id: str = payload.get("user_id")
        if user_id is None:
            logger.warning("Token validation failed: no user_id in payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db_user = get_user_by_id(db, user_id)
        if db_user is None:
            logger.warning(f"User not found in database: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not db_user.is_active:
            logger.warning(f"Inactive user attempted access: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return db_user_to_user(db_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error - Exception type: {type(e)}, Message: {str(e)}")
        import traceback

        logger.error(f"Authentication error traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_superadmin(current_user: User = Depends(require_user)) -> User:
    """
    Require superadmin user (raises 403 if not superadmin)
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required"
        )
    return current_user


def optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None
    This is an alias for get_current_user for clarity
    """
    return get_current_user(request, db)


def require_org_admin(organization_id: Optional[str] = None):
    """
    Factory function to create organization admin dependency

    Args:
        organization_id: If provided, check against specific organization.
                        If None, will try to get from X-Organization-Context header
    """

    def _check_org_admin(
        request: Request,
        current_user: User = Depends(require_user),
        db: Session = Depends(get_db),
    ) -> User:
        from models import Organization, OrganizationMembership, OrganizationRole

        # Superadmin always has access
        if current_user.is_superadmin:
            return current_user

        # Determine which organization to check
        check_org_id = organization_id
        if not check_org_id:
            # Try to get from request state (set by middleware)
            check_org_id = getattr(request.state, "organization_context", None)
        if not check_org_id:
            # Fallback to header (for direct header access)
            check_org_id = request.headers.get("X-Organization-Context")

        if not check_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization context required",
            )

        # Check if user is admin of the organization
        membership = (
            db.query(OrganizationMembership)
            .join(Organization)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == check_org_id,
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,
                Organization.is_active == True,
            )
            .first()
        )

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization admin access required",
            )

        return current_user

    return _check_org_admin


def require_org_contributor(organization_id: Optional[str] = None):
    """
    Factory function to create organization contributor dependency

    Args:
        organization_id: If provided, check against specific organization.
                        If None, will try to get from X-Organization-Context header
    """

    def _check_org_contributor(
        request: Request,
        current_user: User = Depends(require_user),
        db: Session = Depends(get_db),
    ) -> User:
        from models import Organization, OrganizationMembership, OrganizationRole

        # Superadmin always has access
        if current_user.is_superadmin:
            return current_user

        # Determine which organization to check
        check_org_id = organization_id
        if not check_org_id:
            # Try to get from request state (set by middleware)
            check_org_id = getattr(request.state, "organization_context", None)
        if not check_org_id:
            # Fallback to header (for direct header access)
            check_org_id = request.headers.get("X-Organization-Context")

        if not check_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization context required",
            )

        # Check if user has contributor or admin role in the organization
        membership = (
            db.query(OrganizationMembership)
            .join(Organization)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == check_org_id,
                OrganizationMembership.role.in_(
                    [OrganizationRole.CONTRIBUTOR, OrganizationRole.ORG_ADMIN]
                ),
                OrganizationMembership.is_active == True,
                Organization.is_active == True,
            )
            .first()
        )

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization contributor access required",
            )

        return current_user

    return _check_org_contributor
