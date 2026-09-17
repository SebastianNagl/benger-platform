"""Auth: account activation for passwordless (LTI-provisioned) accounts.

Request side (authed): enqueue the "Konto aktivieren" mail. The automatic
variant is queued by the LMS consent step (benger_extended); this endpoint is
the in-app fallback for sub-only accounts (synthetic ``@lti.invalid``
address, nothing to mail at provisioning time) and doubles as a resend lever.
Confirm side (unauthed): the mailed token sets the first password and
verifies the address the mail went to: the entered (pending) email on the
fallback path, the account's own LMS-supplied address otherwise. Receiving
the mail is the mailbox-ownership proof.
"""
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import func

from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from account_activation import email_is_routable, mask_email, verify_email_by_link
from schemas.auth_schemas import AccountActivateConfirm, AccountActivationRequest


def _email_taken_by_other(db, DBUser, email: str, user_id: str) -> bool:
    """True when another account already uses ``email``, in any letter case
    (signup stores addresses lowercased; LMS claims may not be)."""
    return (
        db.query(DBUser.id)
        .filter(func.lower(DBUser.email) == email.lower(), DBUser.id != user_id)
        .first()
        is not None
    )


# Rate limiting rides the global middleware ("api" bucket) like every other
# auth route — no endpoint decorator (none exists in the routers today, and
# the authed+guarded shape here bounds abuse to the caller's own account).
@router.post("/request-account-activation")
async def request_account_activation(
    request: Request,
    body: AccountActivationRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Queue the activation mail for the calling passwordless account."""
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == current_user.id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if db_user.hashed_password is not None or db_user.password_set:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "already_activated"},
        )

    # Stored lowercased like signup and LMS addresses: password reset,
    # verification resend and login match the address exactly.
    target_email = body.email.strip().lower() if body.email else None
    if target_email:
        # Entering an address is only for accounts that have none to mail —
        # routable-email accounts must not use this as an email-change lever
        # (the profile flow with re-verification owns that).
        if email_is_routable(db_user.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "email_change_not_allowed"},
            )
        if _email_taken_by_other(db, DBUser, target_email, db_user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "email_taken"},
            )
    elif not email_is_routable(db_user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "email_required"},
        )

    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    recipient = target_email or db_user.email
    try:
        from celery_client import get_celery_app

        get_celery_app().send_task(
            "emails.send_account_activation",
            kwargs={
                "user_id": db_user.id,
                "host": host,
                "target_email": target_email,
                "force": True,
            },
        )
        logger.info(f"Queued account-activation email for user {db_user.id}")
    except Exception as e:
        # Redis/broker down must not 500 the student's request — the mail
        # just doesn't arrive and they can retry.
        logger.error(f"Failed to queue activation email for {db_user.id}: {e}")

    return {
        "message": "Activation email queued",
        "email_hint": mask_email(recipient),
    }


@router.post("/activate-account")
async def activate_account(
    confirm: AccountActivateConfirm,
    db: Session = Depends(get_db),
):
    """Set the first password (and adopt a pending email) via the mailed token."""
    from auth_module.user_service import get_password_hash
    from models import User as DBUser

    if confirm.new_password != confirm.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    now = datetime.now(timezone.utc)
    user = (
        db.query(DBUser)
        .filter(
            DBUser.password_reset_token == confirm.token,
            DBUser.password_reset_expires > now,
            DBUser.hashed_password.is_(None),
        )
        .first()
    )
    if user is None:
        # Covers expired, unknown, and already-used tokens alike (activation
        # clears the token and sets the password, so a second click lands
        # here) — one indistinguishable error, no token oracle.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_or_expired"},
        )

    if user.pending_activation_email:
        if _email_taken_by_other(db, DBUser, user.pending_activation_email, user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "email_taken"},
            )
        user.email = user.pending_activation_email.strip().lower()
        user.email_verified = True
        user.email_verification_method = "activation"
        user.email_verified_at = now
        user.pending_activation_email = None
    else:
        # Auto path: the link went to the account's own address, so using
        # it proves the mailbox (an LMS-supplied address starts unverified).
        verify_email_by_link(user, method="activation", now=now)

    user.hashed_password = get_password_hash(confirm.new_password)
    user.password_set = True
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()

    logger.info(f"Account activated for user {user.id}")
    return {"message": "Account activated"}
