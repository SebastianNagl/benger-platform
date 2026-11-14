"""Auth: confirm, resend and cancel an email change from the profile page.

``PUT /auth/profile`` with a new address parks it as ``pending_email`` and
mails a confirmation link (``auth_module.email_change``). These handlers
finish that flow: the link's page confirms (unauthenticated: the mail may be
opened on another device), and the profile page resends or cancels.
"""
import asyncio

from fastapi import Request

from auth_module import email_change as email_change_service
from schemas.auth_schemas import EmailChangeConfirmRequest, EmailChangeResendRequest
from services import auth_rate_limit

from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)
from .user import (
    _build_user_profile_response,
    _enforce_email_change_mail_limits,
    _request_host,
)


def _load_db_user(db: Session, user_id: str):
    from models import User as DBUser

    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


@router.post("/email-change/confirm")
def confirm_email_change(
    body: EmailChangeConfirmRequest,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Make the pending address the account's (verified) login address.

    Limited to 40 submits per hour per client IP by default
    (``AUTH_IP_LIMIT_EMAIL_CHANGE_CONFIRM``; 429 ``rate_limited``). 400
    ``invalid_or_expired`` for an unknown, used, superseded or expired link;
    409 ``email_taken`` when another account took the address meanwhile.
    """
    auth_rate_limit.enforce_ip_limit(request, auth_rate_limit.EMAIL_CHANGE_TOKEN)
    user = email_change_service.confirm_email_change(db, body.token)
    return {"message": "Email address changed", "email": user.email}


@router.post("/email-change/resend", response_model=UserProfile)
async def resend_email_change(
    body: EmailChangeResendRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Mail a new confirmation link to the pending address (older links stop
    working). 409 ``no_pending_email`` without a pending change; 429 within
    five minutes of the last delivered link."""
    db_user = await asyncio.to_thread(_load_db_user, db, current_user.id)
    email_change_service.check_resend_allowed(db_user)
    await asyncio.to_thread(
        _enforce_email_change_mail_limits, request, db_user, db_user.pending_email
    )
    token = email_change_service.stage_email_change(db_user, db_user.pending_email)
    await asyncio.to_thread(db.commit)
    await email_change_service.send_email_change_mail(
        db, db_user, token, host=_request_host(request), language=body.language
    )
    return await asyncio.to_thread(_build_user_profile_response, db_user, db)


@router.delete("/email-change", response_model=UserProfile)
def cancel_email_change(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Drop the pending address; links already mailed stop working."""
    db_user = _load_db_user(db, current_user.id)
    email_change_service.clear_pending_email(db_user)
    db.commit()
    return _build_user_profile_response(db_user, db)
