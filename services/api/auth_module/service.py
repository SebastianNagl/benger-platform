"""
Core authentication service functions

This module contains the core authentication logic consolidated from auth.py
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, WebSocket, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from services import refresh_token_service
from models import User as DBUser
from .user_service import authenticate_user as db_authenticate_user

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from .models import Token, User
from .serialization import ensure_dict, iso_or_none


def _preload_memberships(db_user) -> None:
    """Load a persistent user's memberships and their organizations at once.

    ``organization_memberships`` and ``membership.organization`` are lazy, so
    iterating them cost one query for the collection plus one per membership
    on every authenticated request. This loads both with one SELECT (joined
    organizations) and installs the result as the loaded collection. All
    memberships are loaded, inactive ones included, so the collection keeps
    its usual contents for any later code on the same session; the active
    filter is applied by ``db_user_to_user``. Anything that is not a
    persistent ORM user (unit-test Mocks, transient objects) or whose
    collection is already loaded is left alone.
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload
    from sqlalchemy.orm.attributes import set_committed_value
    from sqlalchemy.orm.state import InstanceState

    from models import OrganizationMembership

    state = sa_inspect(db_user, raiseerr=False)
    # A Mock answers inspect() with a Mock state; only a real one counts.
    if not isinstance(state, InstanceState) or not state.persistent:
        return
    if "organization_memberships" not in state.unloaded or state.session is None:
        return
    rows = (
        state.session.execute(
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.organization))
            .where(OrganizationMembership.user_id == db_user.id)
        )
        .scalars()
        .all()
    )
    set_committed_value(db_user, "organization_memberships", list(rows))


def db_user_to_user(db_user: DBUser) -> User:
    """Convert database user to API user model.

    ``organizations`` lists the user's ACTIVE memberships only, matching
    every backend permission check (they all filter
    ``OrganizationMembership.is_active``). Deactivated memberships, including
    those of soft-deleted organizations, used to be listed as well.
    """
    # Get user's organizations
    organizations = []
    # Before the hasattr below: hasattr reads the attribute, which would
    # trigger the lazy load this replaces.
    _preload_memberships(db_user)
    if hasattr(db_user, 'organization_memberships'):
        for membership in db_user.organization_memberships:
            # ``is False`` so unit-test Mocks (truthy attributes) still count.
            if getattr(membership, 'is_active', True) is False:
                continue
            organizations.append(
                {
                    'id': str(membership.organization_id),
                    'name': membership.organization.name if membership.organization else None,
                    'role': membership.role.value if membership.role else None,
                }
            )

    return User(
        id=str(db_user.id),  # Convert UUID to string
        username=db_user.username,
        email=db_user.email,
        email_verified=getattr(
            db_user, 'email_verified', True
        ),  # Default to True for existing users
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
        organizations=organizations if organizations else None,
        vertretbar_onboarding_completed_at=iso_or_none(
            getattr(db_user, 'vertretbar_onboarding_completed_at', None)
        ),
        exam_layout_prefs=ensure_dict(getattr(db_user, 'exam_layout_prefs', None)),
        exam_bundesland=getattr(db_user, 'exam_bundesland', None),
        onboarding_state=ensure_dict(getattr(db_user, 'onboarding_state', None)),
        pseudonym=getattr(db_user, 'pseudonym', None),
        use_pseudonym=getattr(db_user, 'use_pseudonym', True),
        is_service_account=getattr(db_user, 'is_service_account', False),
    )


SERVICE_ACCOUNT_FORBIDDEN_CODE = "service_account"


def is_service_account(db_user) -> bool:
    """Whether a user row (or schema) is an access-key service account.
    Strict ``is True`` so unit-test Mocks never count."""
    return getattr(db_user, "is_service_account", False) is True


def forbid_service_account(db_user) -> None:
    """403 for the machine users behind organization access keys: they never
    log in, refresh, reset or activate a password."""
    if db_user is not None and is_service_account(db_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": SERVICE_ACCOUNT_FORBIDDEN_CODE,
                "message": "Service accounts cannot sign in",
            },
        )


def authenticate_user(username_or_email: str, password: str, db: Session = None) -> Optional[User]:
    """Authenticate user with username/email and password"""
    if db is None:
        # This is for backward compatibility
        from database import SessionLocal

        db = SessionLocal()
        try:
            db_user = db_authenticate_user(db, username_or_email, password)
            return db_user_to_user(db_user) if db_user else None
        finally:
            db.close()
    else:
        db_user = db_authenticate_user(db, username_or_email, password)
        return db_user_to_user(db_user) if db_user else None


#: ``typ`` claim of a session access token. Every token signed with
#: SECRET_KEY names its kind in ``typ`` and is accepted by its own verifier
#: only (email verification tokens carry ``typ="email_verification"``, see
#: auth_module.email_verification), so a token minted for one purpose can
#: never be presented as another.
ACCESS_TOKEN_TYP = "access"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "typ": ACCESS_TOKEN_TYP})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def token_typ_accepted(payload: dict, expected_typ: str) -> bool:
    """Whether a decoded payload is a token of kind ``expected_typ``.

    Rejects any payload carrying a ``purpose`` claim (the single-purpose
    tokens, e.g. email verification, are never session tokens) and any
    ``typ`` other than the expected one.

    A MISSING ``typ`` is tolerated until the next release (grace added
    2026-10-13): access tokens issued before this change carry no ``typ``
    and must keep working for their remaining 60-minute lifetime across the
    deploy. Make ``typ`` mandatory (``payload.get("typ") == expected_typ``)
    in the release after this one.
    """
    if "purpose" in payload:
        return False
    typ = payload.get("typ")
    if typ is None:
        return True
    return typ == expected_typ


def verify_token(token: str, expected_typ: str = ACCESS_TOKEN_TYP) -> dict:
    """Verify and decode a JWT token of kind ``expected_typ``"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not token_typ_accepted(payload, expected_typ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def _bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if isinstance(auth_header, str) and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return None


def verify_token_cookie_or_header(
    request: Request, expected_typ: str = ACCESS_TOKEN_TYP, header_first: bool = False
) -> dict:
    """Verify token from cookie or Authorization header.

    The browser API reads the cookie first. ``header_first`` (used on
    ``/api/v1``) reads the Authorization header first, so a script that
    sends an explicit token is never overridden by a stale cookie.
    """
    token = None

    if header_first:
        token = _bearer_token(request)

    # Try to get token from cookie
    if not token and "access_token" in request.cookies:
        token = request.cookies["access_token"]

    # If no cookie, try Authorization header
    if not token:
        token = _bearer_token(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(token, expected_typ)


class WebSocketAuthError(Exception):
    """Raised when a WebSocket handshake fails authentication.

    WS handlers catch this and respond with `await websocket.close(code=4401)`
    before `accept()`, so unauthenticated clients never consume server
    resources (DB sessions, in-memory state) past the handshake.
    """


def verify_token_for_websocket(
    websocket: WebSocket, expected_typ: str = ACCESS_TOKEN_TYP
) -> dict:
    """Verify an access token presented during a WebSocket handshake.

    Reads the JWT from (in order):
      1. the `access_token` cookie — same-origin browser handshakes send this
         automatically; this is the primary path used by the frontend
      2. the `Authorization: Bearer <token>` header — non-browser callers

    Returns the decoded payload. Raises `WebSocketAuthError` on any failure;
    raising HTTPException would not work because there is no HTTP response
    cycle past the WS upgrade.
    """
    token = websocket.cookies.get("access_token")
    if not token:
        auth_header = websocket.headers.get("Authorization") or ""
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        raise WebSocketAuthError("No access token provided")
    if token.startswith("bgr_"):
        # Access keys are for the /api/v1 HTTP surface only.
        raise WebSocketAuthError("API keys are not accepted on WebSockets")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise WebSocketAuthError(f"Invalid token: {e}")
    if not token_typ_accepted(payload, expected_typ):
        raise WebSocketAuthError("Invalid token: wrong token type")
    return payload


def _lms_account_flag(db: Session, user_id: str) -> bool:
    """``is_lms_account`` for the token response (an LMS launch created the
    account); False when unknown."""
    from lms_name_masking import is_lms_provisioned_account_sync

    try:
        return is_lms_provisioned_account_sync(db, user_id) is True
    except Exception:
        return False


def create_tokens_with_refresh(
    user: User,
    db: Session,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    include_refresh_token: bool = True,
) -> Token:
    """Create access token with optional refresh token"""
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "is_superadmin": user.is_superadmin,
        },
        expires_delta=access_token_expires,
    )

    # The login/refresh user carries the same LMS flag as /auth/me, so the
    # header does not flip after the first hydration.
    user = user.model_copy(update={"is_lms_account": _lms_account_flag(db, user.id)})

    # Create refresh token if requested
    refresh_token = None
    if include_refresh_token:
        refresh_token_result = refresh_token_service.create_refresh_token(
            db=db, user_id=user.id, user_agent=user_agent, ip_address=ip_address
        )
        refresh_token = refresh_token_result[0]  # Extract string from tuple

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


def refresh_access_token(
    refresh_token: str, db: Session, user_agent: str = None, ip_address: str = None
) -> Token:
    """Create new access token using refresh token"""
    # Validate refresh token and get user
    db_refresh_token = refresh_token_service.validate_refresh_token(db, refresh_token)
    if not db_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    # Get user
    from .user_service import get_user_by_id

    db_user = get_user_by_id(db, db_refresh_token.user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    forbid_service_account(db_user)

    user = db_user_to_user(db_user)

    # Create new access token (without refresh token)
    return create_tokens_with_refresh(
        user=user,
        db=db,
        include_refresh_token=False,
        user_agent=user_agent,
        ip_address=ip_address,
    )


def revoke_refresh_token(refresh_token: str, db: Session) -> bool:
    """Revoke a refresh token"""
    return refresh_token_service.revoke_refresh_token(db, refresh_token)


def logout_user(request: Request, db: Session) -> bool:
    """Logout user by revoking refresh token if present"""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        return revoke_refresh_token(refresh_token, db)
    return True
