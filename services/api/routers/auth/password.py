"""Auth: password change / reset handlers."""
import asyncio

from account_activation import mask_email
from fastapi import Request
from sqlalchemy import func

from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)
from auth_module.service import forbid_service_account
from services import auth_rate_limit

@router.post("/change-password")
def change_password(
    password_data: PasswordUpdate,
    request: Request = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Change current user's password. Every other session of the user ends;
    the one sending this request keeps its refresh cookie."""
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    success = change_user_password(
        db=db,
        user_id=current_user.id,
        current_password=password_data.current_password,
        new_password=password_data.new_password,
        keep_refresh_token=request.cookies.get("refresh_token") if request else None,
    )

    if success:
        return {"message": "Password changed successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )


@router.post("/request-password-reset")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Request a password reset email.

    Limited to 60 requests per hour per client IP by default
    (``AUTH_IP_LIMIT_RESET_MAIL``) and 3 per hour per
    submitted address (429 ``rate_limited``), counted whether or not the
    address exists so the limit is no account oracle.
    """
    from app.auth_module.password_reset import password_reset_service
    from mailer.branding import resolve_email_brand
    from models import User as DBUser

    # This handler stays async (it awaits the mail coroutine): the blocking
    # limiter calls run in a worker thread.
    await asyncio.to_thread(
        auth_rate_limit.enforce_ip_limit, request, auth_rate_limit.PASSWORD_RESET_MAIL
    )
    await asyncio.to_thread(
        auth_rate_limit.enforce_account_limit,
        request,
        reset_request.email,
        auth_rate_limit.PASSWORD_RESET_MAIL,
        auth_rate_limit.MAIL_ACCOUNT_LIMIT,
    )

    # Case-insensitive: signup stores the address lowercased, but people
    # type it as they like (T.Name@...), and a miss here is silent.
    user = (
        db.query(DBUser)
        .filter(func.lower(DBUser.email) == reset_request.email.strip().lower())
        .first()
    )

    # Always return success to prevent email enumeration
    if not user:
        logger.info(
            f"Password reset requested for non-existent email: {mask_email(reset_request.email)}"
        )
        return {"message": "If the email exists, a password reset link has been sent"}
    forbid_service_account(user)

    try:
        # Host-aware like verification/invitation links: a Vertretbar student
        # must land on vertretbar.net. resolve_email_brand falls back to the
        # configured FRONTEND_URL for BenGER hosts, preserving old behavior.
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        brand = resolve_email_brand(host)
        success = await password_reset_service.send_password_reset_email(
            db=db, user=user, base_url=brand.frontend_url, language=reset_request.language
        )
        if success:
            logger.info(f"Password reset email sent to user: {user.id}")
        else:
            logger.warning(f"Failed to send password reset email to user: {user.id}")
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
def reset_password(
    reset_confirm: PasswordResetConfirm,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Reset password using a valid reset token (40 submits per hour per
    client IP by default, ``AUTH_IP_LIMIT_RESET_PASSWORD``). A successful
    reset ends every session of the account."""
    from app.auth_module.password_reset import password_reset_service

    auth_rate_limit.enforce_ip_limit(request, auth_rate_limit.PASSWORD_RESET_TOKEN)

    if reset_confirm.new_password != reset_confirm.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    success = password_reset_service.reset_password(
        db=db, token=reset_confirm.token, new_password=reset_confirm.new_password
    )

    if success:
        logger.info("Password reset successful")
        return {"message": "Password has been reset successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
