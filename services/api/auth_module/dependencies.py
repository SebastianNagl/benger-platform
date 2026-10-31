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
    scope = getattr(request, "scope", None)
    root = None
    if isinstance(scope, dict):
        path = scope.get("path")
        root = scope.get("root_path")
    else:
        try:
            path = request.url.path
        except Exception:
            return None
    if not isinstance(path, str):
        return None
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


#: Scope that lets a superadmin's personal key keep superadmin rights.
SUPERADMIN_SCOPE = "admin:platform"


def key_keeps_superadmin(principal) -> bool:
    """A key acts as superadmin only with ``admin:platform`` (grantable to
    superadmins' personal keys alone); the owner's flag is not enough."""
    from app.core.scopes import scopes_satisfied

    return principal is not None and scopes_satisfied(principal.scopes, (SUPERADMIN_SCOPE,))


def _key_user(user: User, principal) -> User:
    if user.is_superadmin and not key_keeps_superadmin(principal):
        user = user.model_copy(update={"is_superadmin": False})
    return user


def _gate_user(request) -> Optional[User]:
    state = getattr(request, "state", None)
    user = getattr(state, "key_gate_user", None) if state is not None else None
    return user if isinstance(user, User) else None


def _authenticate_api_key(request, db: Session, plain: str) -> User:
    """Resolve an access key to its user.

    On ``/api/v1`` the key is checked here (the routes check scopes
    themselves). Everywhere else ``middleware/key_gate.py`` already checked
    the key, the route's rule, the scopes and the projects, and left the
    user on ``request.state.key_gate_user``; without that the route is
    closed to keys."""
    path = _request_path(request)
    if not _is_v1_path(path):
        user = _gate_user(request)
        principal = get_principal(request)
        if user is None or principal is None or not principal.is_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "api_key_not_allowed_here",
                    "message": "Access keys cannot be used on this endpoint",
                },
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        return _key_user(user, principal)

    from services.api_key_service import authenticate_api_key_sync

    auth = authenticate_api_key_sync(db, plain, path=path)
    _set_principal(request, auth.principal)
    return _key_user(db_user_to_user(auth.user), auth.principal)


def _session_idle(db) -> bool:
    """True when ``db`` is a real Session with no open transaction and no
    unflushed changes, i.e. nothing ran on it yet in this request. Mocks and
    ``None`` answer False (their ``in_transaction()`` is truthy or missing)."""
    in_tx = getattr(db, "in_transaction", None)
    if not callable(in_tx):
        return False
    try:
        if in_tx():
            return False
        return not (db.new or db.dirty or db.deleted)
    except Exception:
        return False


def _end_auth_read(db, began_idle: bool) -> None:
    """End the transaction the user lookup itself opened.

    ``require_user`` is a sync dependency on the shared request session, so
    before this every request, async-lane ones included, held a pooled sync
    connection idle in transaction (AccessShareLock on ``users`` and
    ``organization_memberships``) for its whole duration. When the lookup was
    the first thing to touch the session (``began_idle``) and left no
    changes behind, the transaction holds nothing but our SELECTs, so
    committing it is a no-op that returns the connection to the pool; a sync
    handler that uses ``db`` afterwards simply begins a new transaction.
    ``expire_on_commit`` is suspended for this one commit so the rows already
    loaded stay as they are (the caller only keeps the Pydantic ``User``).
    If anything else ran on the session first, it is left untouched.
    """
    if not began_idle:
        return
    try:
        if db.new or db.dirty or db.deleted or not db.in_transaction():
            return
        previous = db.expire_on_commit
        db.expire_on_commit = False
        try:
            db.commit()
        finally:
            db.expire_on_commit = previous
    except Exception as exc:  # pragma: no cover - connection already broken
        import logging

        logging.getLogger(__name__).debug("auth read transaction end failed: %s", exc)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Get current user from token (either cookie or header)
    Returns None if no valid token is provided (for optional auth), and for
    deactivated or anonymized accounts: an access token issued before the
    deactivation must not keep an open tab working until it expires.
    Handlers that need a user must turn None into a 401 (or use
    ``require_user``).

    An access key (``Authorization: Bearer bgr_...``) is checked first; a
    present but invalid key, or a key on a route closed to keys, raises 401
    instead of degrading to anonymous.
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

        began_idle = _session_idle(db)
        db_user = get_user_by_id(db, user_id)
        if db_user is None or not db_user.is_active or is_service_account(db_user):
            _end_auth_read(db, began_idle)
            return None

        _set_principal(request, session_principal(db_user.id))
        user = db_user_to_user(db_user)
        _end_auth_read(db, began_idle)
        return user
    except HTTPException:
        # Return None for optional auth instead of raising exception
        return None


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Require authenticated user (raises 401 if not authenticated)

    Accepts an access key (``Authorization: Bearer bgr_...``, checked first;
    outside ``/api/v1`` by ``middleware/key_gate.py``) or a session JWT (cookie first; header first on
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

        began_idle = _session_idle(db)
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
        user = db_user_to_user(db_user)
        _end_auth_read(db, began_idle)
        return user
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
    Require superadmin user (raises 403 if not superadmin). An access key
    passes only with the ``admin:platform`` scope.
    """
    principal = get_principal(request) if request is not None else None
    if principal is not None and principal.is_api_key and not key_keeps_superadmin(principal):
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
