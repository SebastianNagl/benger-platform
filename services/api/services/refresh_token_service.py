"""
Refresh token service for persistent authentication
Handles refresh token generation, validation, rotation, and revocation
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import RefreshToken

# Configuration
# runtime-mutable by design (tests patch os.environ + importlib.reload this
# module to re-evaluate the env var — see
# tests/unit/test_refresh_token_service.py). Routing through frozen settings
# would defeat that reload-based test mechanism.
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def generate_refresh_token() -> str:
    """Generate a secure random refresh token"""
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Hash a refresh token for secure storage"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(
    db: Session,
    user_id: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[str, RefreshToken]:
    """
    Create a new refresh token for a user
    Returns the plain token and the database record
    """
    # Generate unique ID for the token
    token_id = secrets.token_urlsafe(32)

    # Generate the actual refresh token
    plain_token = generate_refresh_token()
    token_hash = hash_token(plain_token)

    # Calculate expiration time
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Create database record
    db_token = RefreshToken(
        id=token_id,
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
        is_active=True,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    db.add(db_token)
    db.commit()
    db.refresh(db_token)

    return plain_token, db_token


def validate_refresh_token(db: Session, token: str) -> Optional[RefreshToken]:
    """
    Validate a refresh token and return the token record if valid
    """
    token_hash = hash_token(token)

    # Find the token in database
    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_active == True,  # noqa: E712
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    if db_token:
        # Update last used timestamp
        db_token.last_used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_token)

    return db_token


def rotate_refresh_token(
    db: Session,
    old_token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[tuple[str, RefreshToken]]:
    """
    Rotate a refresh token - invalidate the old one and create a new one
    This is a security best practice to prevent token reuse attacks
    """
    # Validate the old token
    old_db_token = validate_refresh_token(db, old_token)
    if not old_db_token:
        return None

    # Invalidate the old token
    old_db_token.is_active = False
    db.commit()

    # Create a new refresh token for the same user
    new_token, new_db_token = create_refresh_token(db, old_db_token.user_id, user_agent, ip_address)

    return new_token, new_db_token


def revoke_refresh_token(db: Session, token: str) -> bool:
    """
    Revoke a specific refresh token
    """
    token_hash = hash_token(token)

    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash, RefreshToken.is_active == True)  # noqa: E712
        .first()
    )

    if db_token:
        db_token.is_active = False
        db.commit()
        return True

    return False


def revoke_user_tokens(db: Session, user_id: str) -> int:
    """
    Revoke all refresh tokens for a user (logout from all devices)
    Returns the number of tokens revoked
    """
    count = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.is_active == True)  # noqa: E712
        .update({"is_active": False})
    )

    db.commit()
    return count


def cleanup_expired_tokens(db: Session) -> int:
    """
    Clean up expired refresh tokens from the database
    Returns the number of tokens cleaned up
    """
    # Get current time - handle timezone compatibility
    now = datetime.now(timezone.utc)

    # Find expired tokens manually to handle timezone issues
    all_tokens = db.query(RefreshToken).all()
    expired_tokens = []

    for token in all_tokens:
        # Handle both timezone-aware and naive datetimes
        token_expires = token.expires_at
        if token_expires.tzinfo == None:  # noqa: E711
            # Database returned naive datetime, make comparison datetime naive too
            compare_time = now.replace(tzinfo=None)
        else:
            # Database returned timezone-aware datetime
            compare_time = now

        if token_expires <= compare_time:
            expired_tokens.append(token)

    # Delete expired tokens
    count = 0
    for token in expired_tokens:
        db.delete(token)
        count += 1

    db.commit()
    return count


def get_user_active_tokens(db: Session, user_id: str) -> list[RefreshToken]:
    """
    Get all active refresh tokens for a user
    Useful for showing active sessions in user settings
    """
    return (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True,  # noqa: E712
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(RefreshToken.last_used_at.desc())
        .all()
    )


def revoke_token_by_id(db: Session, token_id: str, user_id: str) -> bool:
    """
    Revoke a specific refresh token by its ID
    Includes user_id check for security
    """
    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.id == token_id,
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True,  # noqa: E712
        )
        .first()
    )

    if db_token:
        db_token.is_active = False
        db.commit()
        return True

    return False


# ---------------------------------------------------------------------------
# Async twins (async DB lane).
#
# Each twin shares a pure ``_build_select_*`` builder with its sync sibling so
# the WHERE/ORDER semantics can never drift. The sync entry points above stay
# byte-identical — other sync callers and ``importlib.reload`` tests depend on
# them. See CLAUDE.md "Converting an existing sync service to dual-mode".
# ---------------------------------------------------------------------------


def _build_select_token_by_hash_active(token_hash: str):
    return select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_active == True,  # noqa: E712
        RefreshToken.expires_at > datetime.now(timezone.utc),
    )


def _build_select_token_by_hash_for_revoke(token_hash: str):
    return select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_active == True,  # noqa: E712
    )


def _build_select_user_active_tokens(user_id: str):
    return (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True,  # noqa: E712
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(RefreshToken.last_used_at.desc())
    )


def _build_select_token_by_id(token_id: str, user_id: str):
    return select(RefreshToken).where(
        RefreshToken.id == token_id,
        RefreshToken.user_id == user_id,
        RefreshToken.is_active == True,  # noqa: E712
    )


async def create_refresh_token_async(
    db: AsyncSession,
    user_id: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[str, RefreshToken]:
    """Async twin of :func:`create_refresh_token`."""
    token_id = secrets.token_urlsafe(32)
    plain_token = generate_refresh_token()
    token_hash = hash_token(plain_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    db_token = RefreshToken(
        id=token_id,
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
        is_active=True,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)

    return plain_token, db_token


async def validate_refresh_token_async(db: AsyncSession, token: str) -> Optional[RefreshToken]:
    """Async twin of :func:`validate_refresh_token`."""
    token_hash = hash_token(token)
    result = await db.execute(_build_select_token_by_hash_active(token_hash))
    db_token = result.scalar_one_or_none()

    if db_token:
        db_token.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(db_token)

    return db_token


async def revoke_refresh_token_async(db: AsyncSession, token: str) -> bool:
    """Async twin of :func:`revoke_refresh_token`."""
    token_hash = hash_token(token)
    result = await db.execute(_build_select_token_by_hash_for_revoke(token_hash))
    db_token = result.scalar_one_or_none()

    if db_token:
        db_token.is_active = False
        await db.commit()
        return True

    return False


async def revoke_user_tokens_async(db: AsyncSession, user_id: str) -> int:
    """Async twin of :func:`revoke_user_tokens`."""
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True,  # noqa: E712
        )
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount


async def get_user_active_tokens_async(db: AsyncSession, user_id: str) -> list[RefreshToken]:
    """Async twin of :func:`get_user_active_tokens`."""
    result = await db.execute(_build_select_user_active_tokens(user_id))
    return list(result.scalars().all())


async def revoke_token_by_id_async(db: AsyncSession, token_id: str, user_id: str) -> bool:
    """Async twin of :func:`revoke_token_by_id`."""
    result = await db.execute(_build_select_token_by_id(token_id, user_id))
    db_token = result.scalar_one_or_none()

    if db_token:
        db_token.is_active = False
        await db.commit()
        return True

    return False
