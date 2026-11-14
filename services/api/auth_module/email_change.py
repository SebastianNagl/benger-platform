"""Changing the account email address from the profile page.

The new address never replaces the login address directly. It parks in
``users.pending_email`` and a confirmation link goes to it; ``users.email``
stays the login address, verified, until that link is used. Then the two are
swapped and the new address counts as verified (receiving the mail proves the
mailbox). A mistyped or undeliverable new address therefore never locks
anyone out: the old address keeps working and the change can be resent or
cancelled from the profile page.

Before this flow the profile update set the new address and
``email_verified = False`` without mailing anything, so the next password
login was refused (403) and nothing could recover the account but "Forgot
password" or an admin.

The token is opaque (``secrets.token_urlsafe``); only its SHA-256 digest is
stored. A new send mints a new token, so a resend makes older links invalid.
The link expires :data:`EMAIL_CHANGE_LINK_EXPIRY` after the mail went out.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from account_activation import mask_email
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: How long a confirmation link stays valid after its mail went out.
EMAIL_CHANGE_LINK_EXPIRY = timedelta(hours=48)
#: Minimum time between two sends to the same pending address.
EMAIL_CHANGE_RESEND_INTERVAL = timedelta(minutes=5)
#: Verification method recorded when the confirmation link was used.
EMAIL_CHANGE_VERIFICATION_METHOD = "self"

_email_service = None


def _mail_service():
    """The shared mailer, created on first use (tests patch this)."""
    global _email_service
    if _email_service is None:
        from email_service import EmailService

        _email_service = EmailService()
    return _email_service


def normalize_email(email: str | None) -> str:
    """Addresses are stored and compared lowercased, as signup does."""
    return (email or "").strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _email_taken_by_other(db: Session, email: str, user_id: str) -> bool:
    from models import User

    return (
        db.query(User.id)
        .filter(func.lower(User.email) == normalize_email(email), User.id != user_id)
        .first()
        is not None
    )


def requested_email_change(db: Session, user, email: str | None) -> str | None:
    """The new address ``email`` asks for, validated, or None for no change.

    None when ``email`` is empty, equals the current address (in any letter
    case) or equals the address already pending (resending is a separate
    action, so saving the profile form again sends nothing). Raises 400 for an
    invalid address or one another account uses.
    """
    new_email = normalize_email(email)
    if not new_email or new_email == normalize_email(user.email):
        return None
    if new_email == normalize_email(getattr(user, "pending_email", None)):
        return None

    from email_validation import validate_email_with_details

    is_valid, error_msg = validate_email_with_details(new_email)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email address: {error_msg}",
        )
    if _email_taken_by_other(db, new_email, user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered to another user",
        )
    return new_email


def stage_email_change(user, new_email: str) -> str:
    """Park ``new_email`` as pending with a fresh token; return the raw token.

    Replaces any earlier pending address and token. The caller commits and
    then sends the mail (:func:`send_email_change_mail`).
    """
    token = secrets.token_urlsafe(32)
    user.pending_email = normalize_email(new_email)
    user.pending_email_token = hash_token(token)
    user.pending_email_sent_at = None
    return token


def clear_pending_email(user) -> None:
    user.pending_email = None
    user.pending_email_token = None
    user.pending_email_sent_at = None


def build_confirm_url(frontend_url: str, token: str) -> str:
    """Link of the confirmation mail. It opens a page where a button (not the
    page load) uses the token, so mail scanners that fetch links do not
    consume it."""
    return f"{frontend_url.rstrip('/')}/confirm-email-change/{token}"


async def send_email_change_mail(
    db: Session,
    user,
    token: str,
    *,
    host: str | None = None,
    language: str | None = None,
) -> bool:
    """Mail the confirmation link for ``user.pending_email``.

    On success ``pending_email_sent_at`` records the send (it starts the
    link's validity and tells the profile page the mail went out). On failure
    the token is dropped, since no one received it; the pending address stays
    so the profile page can offer a resend. Commits either way.
    """
    from mailer.branding import resolve_email_brand

    from extensions import emit_ops_event

    brand = resolve_email_brand(host)
    mail_language = language or brand.default_language
    frontend_host = urlparse(brand.frontend_url).netloc
    sent = False
    try:
        sent = await _mail_service().send_email_change_confirmation_email(
            to_email=user.pending_email,
            confirm_url=build_confirm_url(brand.frontend_url, token),
            user_name=user.name,
            language=mail_language,
            from_address=brand.from_address,
            from_name=brand.from_name,
            brand_name=brand.name,
            frontend_host=frontend_host,
            expiry_hours=int(EMAIL_CHANGE_LINK_EXPIRY.total_seconds() // 3600),
        )
    except Exception as e:
        logger.error(f"Error sending email change confirmation for user {user.id}: {e}")

    if sent:
        user.pending_email_sent_at = _now()
        logger.info(
            f"Email change confirmation sent for user {user.id} "
            f"to {mask_email(user.pending_email)}"
        )
    else:
        user.pending_email_token = None
        logger.warning(f"Email change confirmation not sent for user {user.id}")
    db.commit()
    emit_ops_event("mail_outcome", mail_type="verification", outcome="sent" if sent else "failed")
    return sent


def check_resend_allowed(user) -> None:
    """409 without a pending address; 429 within the resend interval of the
    last delivered mail."""
    if not getattr(user, "pending_email", None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "no_pending_email"},
        )
    sent_at = _as_utc(user.pending_email_sent_at)
    if sent_at is not None:
        wait = sent_at + EMAIL_CHANGE_RESEND_INTERVAL - _now()
        if wait.total_seconds() > 0:
            from services.auth_rate_limit import rate_limited

            raise rate_limited(int(wait.total_seconds()) + 1)


def confirm_email_change(db: Session, token: str):
    """Swap the pending address in for the mailed ``token``; return the user.

    400 ``invalid_or_expired`` for an unknown, superseded, used or expired
    token (one indistinguishable error); 409 ``email_taken`` when another
    account took the address in the meantime (the pending change is then
    dropped, it can never succeed).
    """
    from models import User

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "invalid_or_expired"},
    )
    if not token:
        raise invalid
    user = db.query(User).filter(User.pending_email_token == hash_token(token)).first()
    if user is None or not user.pending_email:
        raise invalid
    sent_at = _as_utc(user.pending_email_sent_at)
    now = _now()
    if sent_at is None or sent_at + EMAIL_CHANGE_LINK_EXPIRY <= now:
        raise invalid

    new_email = normalize_email(user.pending_email)
    if _email_taken_by_other(db, new_email, user.id):
        clear_pending_email(user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_taken"},
        )

    user.email = new_email
    user.email_verified = True
    user.email_verified_at = now
    user.email_verification_method = EMAIL_CHANGE_VERIFICATION_METHOD
    user.email_verified_by_id = None
    # Links mailed to the previous address must not act on the new one.
    user.email_verification_token = None
    user.email_verification_sent_at = None
    user.password_reset_token = None
    user.password_reset_expires = None
    clear_pending_email(user)

    from auth_module.user_service import record_profile_history

    record_profile_history(db, user, change_type="email_change", changed_fields=["email"])
    try:
        db.commit()
    except IntegrityError:
        # The unique email index lost a race against a signup.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_taken"},
        )
    db.refresh(user)
    logger.info(f"Email change confirmed for user {user.id}")

    # The new address is proven now: open invitations to it count as
    # accepted, as on every other path that proves an address.
    from auth_module.email_verification import email_verification_service

    email_verification_service.accept_pending_invitations(db, user)
    return user
