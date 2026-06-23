"""Auth: email verification handlers."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

@router.post("/verify-email")
async def verify_email(
    verification_request: EmailVerificationRequest,
    db: Session = Depends(get_db),
):
    """Verify email address using verification token (POST with body)"""
    success, message = email_verification_service.verify_email_with_token(
        db=db, token=verification_request.token
    )

    if success:
        logger.info(f"Email verification successful: {message}")
        return {"success": True, "message": message}
    else:
        logger.warning(f"Email verification failed: {message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


@router.post("/verify-email/{token}")
async def verify_email_with_token(token: str, db: Session = Depends(get_db)):
    """Verify email address using verification token (path parameter)"""
    try:
        success, message = email_verification_service.verify_email_with_token(db, token)

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying email with token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email",
        )


@router.post("/resend-verification")
async def resend_verification_email(
    resend_request: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """Resend email verification link"""
    from models import User as DBUser

    user = db.query(DBUser).filter(DBUser.email == resend_request.email).first()

    # Always return success to prevent email enumeration
    if not user:
        logger.info(f"Verification resend requested for non-existent email: {resend_request.email}")
        return {
            "message": "If the email exists and is unverified, a verification link has been sent"
        }

    if user.email_verified:
        logger.info(
            f"Verification resend requested for already verified email: {resend_request.email}"
        )
        return {
            "message": "If the email exists and is unverified, a verification link has been sent"
        }

    try:
        frontend_url = get_settings().frontend_url
        success = await email_verification_service.send_verification_email(
            db=db, user=user, base_url=frontend_url, language=resend_request.language
        )
        if success:
            logger.info(f"Verification email resent to: {user.email}")
        else:
            logger.warning(f"Failed to resend verification email to: {user.email}")
    except Exception as e:
        logger.error(f"Error resending verification email: {e}")

    return {"message": "If the email exists and is unverified, a verification link has been sent"}


@router.post("/verify-email-enhanced/{token}", response_model=EmailVerificationEnhancedResponse)
async def verify_email_enhanced(
    token: str,
    db: Session = Depends(get_db),
):
    """Enhanced email verification that returns user type info"""
    from models import Invitation
    from models import User as DBUser

    success, message = email_verification_service.verify_email_with_token(db, token)

    if not success:
        return EmailVerificationEnhancedResponse(
            success=False,
            message=message,
            user_type="unknown",
            profile_completed=False,
            redirect_url=None,
        )

    # Get user from token to determine type
    from auth_module.email_verification import email_verification_service as evs

    token_data = evs.validate_verification_token(token)
    if not token_data:
        return EmailVerificationEnhancedResponse(
            success=True,
            message=message,
            user_type="unknown",
            profile_completed=True,
            redirect_url="/login",
        )

    user_id, email = token_data
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if not db_user:
        return EmailVerificationEnhancedResponse(
            success=True,
            message=message,
            user_type="unknown",
            profile_completed=True,
            redirect_url="/login",
        )

    user_type = "invited" if db_user.created_via_invitation else "self_registered"

    # Check for pending invitations
    invitation_info = None
    if db_user.created_via_invitation and db_user.invitation_token:
        invitation = (
            db.query(Invitation).filter(Invitation.token == db_user.invitation_token).first()
        )
        if invitation:
            invitation_info = {
                "organization_id": invitation.organization_id,
                "role": invitation.role.value,
            }

    # Determine redirect URL
    if db_user.created_via_invitation and not db_user.profile_completed:
        redirect_url = "/complete-profile"
    elif db_user.created_via_invitation:
        redirect_url = (
            f"/organizations/{invitation_info['organization_id']}"
            if invitation_info
            else "/dashboard"
        )
    else:
        redirect_url = "/login"

    return EmailVerificationEnhancedResponse(
        success=True,
        message=message,
        user_type=user_type,
        profile_completed=db_user.profile_completed,
        redirect_url=redirect_url,
        invitation_info=invitation_info,
    )
