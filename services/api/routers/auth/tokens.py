"""Auth: token refresh and logout handlers."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract request metadata for security tracking
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    # Refresh the access token (with token rotation)
    token_response = refresh_access_token(
        refresh_token=refresh_token, db=db, user_agent=user_agent, ip_address=ip_address
    )

    _settings = get_settings()
    if not token_response:
        # Clear invalid refresh token cookie
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set new access token cookie
    response.set_cookie(
        key="access_token",
        value=token_response.access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )

    # Set new refresh token cookie (token rotation)
    if token_response.refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=token_response.refresh_token,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )

    return token_response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Logout endpoint that clears cookies and revokes refresh token"""
    from services.refresh_token_service import revoke_refresh_token_async

    # Get refresh token from cookie to revoke it
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await revoke_refresh_token_async(db, refresh_token)

    # Clear both cookies
    _settings = get_settings()
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=_settings.is_production,
        samesite="lax",
        path="/",
        domain=_settings.cookie_domain,
    )

    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all_devices(
    current_user: User = Depends(require_user),
    response: Response = None,
    db: AsyncSession = Depends(get_async_db),
):
    """Logout from all devices by revoking all refresh tokens"""
    from services.refresh_token_service import revoke_user_tokens_async
    revoked_count = await revoke_user_tokens_async(db, str(current_user.id))

    if response:
        _settings = get_settings()
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=_settings.is_production,
            samesite="lax",
            path="/",
            domain=_settings.cookie_domain,
        )

    return {
        "message": "Logged out from all devices successfully",
        "revoked_sessions": revoked_count,
    }
