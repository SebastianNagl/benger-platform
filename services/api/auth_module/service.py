"""
Core authentication service functions

This module contains the core authentication logic consolidated from auth.py
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import refresh_token_service
from models import User as DBUser
from .user_service import authenticate_user as db_authenticate_user

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from .models import Token, User


def db_user_to_user(db_user: DBUser) -> User:
    """Convert database user to API user model"""
    # Get user's organizations
    organizations = []
    if hasattr(db_user, 'organization_memberships'):
        for membership in db_user.organization_memberships:
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


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token_cookie_or_header(request: Request) -> dict:
    """Verify token from cookie or Authorization header"""
    token = None

    # Try to get token from cookie first
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]

    # If no cookie, try Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(token)


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
