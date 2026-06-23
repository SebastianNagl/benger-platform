"""Auth: password change / reset handlers."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

@router.post("/change-password")
async def change_password(
    password_data: PasswordUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Change current user's password"""
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
    db: Session = Depends(get_db),
):
    """Request a password reset email"""
    from app.auth_module.password_reset import password_reset_service
    from models import User as DBUser

    user = db.query(DBUser).filter(DBUser.email == reset_request.email).first()

    # Always return success to prevent email enumeration
    if not user:
        logger.info(f"Password reset requested for non-existent email: {reset_request.email}")
        return {"message": "If the email exists, a password reset link has been sent"}

    try:
        frontend_url = get_settings().frontend_url
        success = await password_reset_service.send_password_reset_email(
            db=db, user=user, base_url=frontend_url, language=reset_request.language
        )
        if success:
            logger.info(f"Password reset email sent to: {user.email}")
        else:
            logger.warning(f"Failed to send password reset email to: {user.email}")
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    """Reset password using a valid reset token"""
    from app.auth_module.password_reset import password_reset_service

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
