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
from .principal import extract_api_key, get_principal, session_principal
from .service import db_user_to_user, is_service_account, verify_token_cookie_or_header

#: Paths under this prefix form the public, key-capable API.
V1_PATH_PREFIX = "/api/v1/"


def _request_path(request) -> Optional[str]:
    """The request path without the app's root_path, or None (Mock requests)."""
    url = getattr(request, "url", None)
    path = getattr(url, "path", None)
    if not isinstance(path, str):
        return None
    scope = getattr(request, "scope", None)
    root = scope.get("root_path") if isinstance(scope, dict) else None
    if isinstance(root, str) and root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def _is_v1_path(path: Optional[str]) -> bool:
    return isinstance(path, str) and (path.startswith(V1_PATH_PREFIX) or path == "/api/v1")


def _set_principal(request, principal) -> None:
    try:
        request.state.principal = principal
    except Exception:  # pragma: no cover - requests without state
        pass


def _authenticate_api_key(request, db: Session, plain: str) -> User:
    """Resolve an access key to its user. Keys never carry superadmin
    powers, whatever the owner's flag says."""
    from services.api_key_service import authenticate_api_key_sync

    auth = authenticate_api_key_sync(db, plain, path=_request_path(request))
    _set_principal(request, auth.principal)
    user = db_user_to_user(auth.user)
    if user.is_superadmin:
        user = user.model_copy(update={"is_superadmin": False})
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Get current user from token (either cookie or header)
    Returns None if no valid token is provided (for optional auth), and for
    deactivated or anonymized accounts: an access token issued before the
    deactivation must not keep an open tab working until it expires.
    Handlers that need a user must turn None into a 401 (or use
    ``require_user``).

    An access key (``Authorization: Bearer bgr_...``) is checked first; a
    present but invalid key, or a key on a non-v1 path, raises 401 instead
    of degrading to anonymous.
    """
    api_key = extract_api_key(request)
    if api_key is not None:
        return _authenticate_api_key(request, db, api_key)
    try:
        payload = verify_token_cookie_or_header(
            request, header_first=_is_v1_path(_request_path(request))
        )
        user_id: str = payload.get("user_id")
        if user_id is None:
            return None

        db_user = get_user_by_id(db, user_id)
        if db_user is None or not db_user.is_active or is_service_account(db_user):
            return None

        _set_principal(request, session_principal(db_user.id))
        return db_user_to_user(db_user)
    except HTTPException:
        # Return None for optional auth instead of raising exception
        return None


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Require authenticated user (raises 401 if not authenticated)

    Accepts an access key (``Authorization: Bearer bgr_...``, checked first,
    ``/api/v1`` only) or a session JWT (cookie first; header first on
    ``/api/v1``). Stores the caller's ``Principal`` on
    ``request.state.principal``.
    """
    import logging

    logger = logging.getLogger(__name__)

    api_key = extract_api_key(request)
    if api_key is not None:
        return _authenticate_api_key(request, db, api_key)

    try:
        payload = verify_token_cookie_or_header(
            request, header_first=_is_v1_path(_request_path(request))
        )
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

        if not db_user.is_active or is_service_account(db_user):
            logger.warning(f"Inactive user attempted access: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user",
                headers={"WWW-Authenticate": "Bearer"},
            )

        _set_principal(request, session_principal(db_user.id))
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


def require_superadmin(
    current_user: User = Depends(require_user), request: Request = None
) -> User:
    """
    Require superadmin user (raises 403 if not superadmin). Access keys never
    pass, even a superadmin's personal key.
    """
    principal = get_principal(request) if request is not None else None
    if principal is not None and principal.is_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required"
        )
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
        organization_id: The organization to check. Required: without it the
                        dependency answers 400.
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

        # The organization is named by the route, never taken from the
        # client's selected context.
        check_org_id = organization_id
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
                OrganizationMembership.is_active == True,  # noqa: E712
                Organization.is_active == True,  # noqa: E712
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
        organization_id: The organization to check. Required: without it the
                        dependency answers 400.
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

        # The organization is named by the route, never taken from the
        # client's selected context.
        check_org_id = organization_id
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
                OrganizationMembership.is_active == True,  # noqa: E712
                Organization.is_active == True,  # noqa: E712
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
