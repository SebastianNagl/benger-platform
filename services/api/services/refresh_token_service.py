"""
Refresh token service for persistent authentication
Handles refresh token generation, validation, rotation, and revocation

Rotation and reuse detection: every refresh replaces the presented token
with a successor in the same family (``rotate_refresh_token``). The replaced
token keeps ``rotated_at``. If it is presented again within
``REFRESH_TOKEN_REUSE_GRACE_SECONDS`` (two tabs or the SSE proxy refreshing
at the same moment), the caller gets a new access token but no new refresh
token, since the first call already set the successor cookie. After the
grace period such a presentation means the token was copied, so the whole
family is revoked (``resolve_rotated_refresh_token``).
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import RefreshToken

# Configuration
# runtime-mutable by design (tests patch os.environ + importlib.reload this
# module to re-evaluate the env var — see
# tests/unit/test_refresh_token_service.py). Routing through frozen settings
# would defeat that reload-based test mechanism.
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

#: How long a replaced refresh token may still mint an access token, so that
#: concurrent refreshes with the same cookie do not end the session.
REFRESH_TOKEN_REUSE_GRACE_SECONDS = 30

logger = logging.getLogger(__name__)


def generate_refresh_token() -> str:
    """Generate a secure random refresh token"""
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Hash a refresh token for secure storage"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def family_of(db_token: RefreshToken) -> str:
    """The family a token belongs to (rows from before rotation: their own id)."""
    return db_token.family_id or db_token.id


def _new_token_row(
    user_id: str,
    user_agent: Optional[str],
    ip_address: Optional[str],
    family_id: Optional[str] = None,
) -> tuple[str, RefreshToken]:
    token_id = secrets.token_urlsafe(32)
    plain_token = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db_token = RefreshToken(
        id=token_id,
        token_hash=hash_token(plain_token),
        user_id=user_id,
        expires_at=expires_at,
        is_active=True,
        user_agent=user_agent,
        ip_address=ip_address,
        # A new login starts a family named after its first token.
        family_id=family_id or token_id,
    )
    return plain_token, db_token


def create_refresh_token(
    db: Session,
    user_id: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[str, RefreshToken]:
    """
    Create a new refresh token for a user (a new login: a new family)
    Returns the plain token and the database record
    """
    plain_token, db_token = _new_token_row(user_id, user_agent, ip_address)

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
    in the same family, in one transaction.

    The old row is locked, so of two concurrent rotations of the same token
    exactly one succeeds; the other gets None and can fall back to
    ``resolve_rotated_refresh_token``. Returns None as well when the token is
    unknown, expired or no longer active.
    """
    now = datetime.now(timezone.utc)
    old_db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == hash_token(old_token),
            RefreshToken.is_active == True,  # noqa: E712
            RefreshToken.expires_at > now,
        )
        .with_for_update()
        .first()
    )
    if not old_db_token:
        return None

    old_db_token.is_active = False
    old_db_token.rotated_at = now
    old_db_token.last_used_at = now

    new_token, new_db_token = _new_token_row(
        old_db_token.user_id, user_agent, ip_address, family_id=family_of(old_db_token)
    )
    db.add(new_db_token)
    db.commit()
    db.refresh(new_db_token)

    return new_token, new_db_token


def revoke_token_family(db: Session, family_id: str) -> int:
    """Revoke every active token of a family. Returns the number revoked."""
    count = (
        db.query(RefreshToken)
        .filter(
            or_(RefreshToken.family_id == family_id, RefreshToken.id == family_id),
            RefreshToken.is_active == True,  # noqa: E712
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    db.commit()
    return count


def resolve_rotated_refresh_token(db: Session, token: str) -> Optional[RefreshToken]:
    """Decide about a presented refresh token that is no longer active.

    Returns the token's row when it was replaced by rotation less than
    ``REFRESH_TOKEN_REUSE_GRACE_SECONDS`` ago and its family still has a live
    token: a concurrent refresh, which may mint an access token but no new
    refresh token. Returns None in every other case. A replaced token
    presented after the grace period is treated as stolen: its whole family
    is revoked, so the legitimate holder of the successor has to log in
    again too.
    """
    now = datetime.now(timezone.utc)
    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(token))
        .first()
    )
    if db_token is None or db_token.is_active or db_token.rotated_at is None:
        # Unknown, still active (not this function's case) or ended by logout.
        return None
    if db_token.expires_at <= now:
        return None

    family = family_of(db_token)
    if now - db_token.rotated_at > timedelta(seconds=REFRESH_TOKEN_REUSE_GRACE_SECONDS):
        revoked = revoke_token_family(db, family)
        logger.warning(
            "Refresh token reuse detected for user %s: revoked %d token(s) of family %s",
            db_token.user_id,
            revoked,
            family,
        )
        return None

    live_successor = (
        db.query(RefreshToken.id)
        .filter(
            or_(RefreshToken.family_id == family, RefreshToken.id == family),
            RefreshToken.is_active == True,  # noqa: E712
            RefreshToken.expires_at > now,
        )
        .first()
    )
    return db_token if live_successor is not None else None


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


def revoke_user_tokens(
    db: Session, user_id: str, keep_token: Optional[str] = None, commit: bool = True
) -> int:
    """
    Revoke all refresh tokens for a user (logout from all devices)
    Returns the number of tokens revoked

    ``keep_token`` (a raw refresh token) is spared, so a password change
    ends every other session but not the one that made the change.
    ``commit=False`` leaves the commit to the caller, so the revocation lands
    in the same transaction as the password or status change behind it.
    """
    query = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.is_active == True  # noqa: E712
    )
    if keep_token:
        query = query.filter(RefreshToken.token_hash != hash_token(keep_token))
    count = query.update({"is_active": False})

    if commit:
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
        family_id=token_id,
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


async def revoke_user_tokens_async(db: AsyncSession, user_id: str, commit: bool = True) -> int:
    """Async twin of :func:`revoke_user_tokens` (without ``keep_token``)."""
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True,  # noqa: E712
        )
        .values(is_active=False)
    )
    if commit:
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
