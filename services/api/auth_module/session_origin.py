"""
Session origin marker.

A session opened somewhere other than the password login (an overlay's LMS
launch, for example) can carry a readable ``benger_session_origin`` cookie
next to the HttpOnly token cookies, so the frontend can tell such sessions
apart (the onboarding tour stays quiet in them). The overlay that opens the
session sets the cookie; the platform owns its end of life: the password
login and the logouts clear it, so a regular sign-in is never mistaken for
one. Token refreshes leave it alone.
"""

from fastapi import Response

SESSION_ORIGIN_COOKIE = "benger_session_origin"


def clear_session_origin(response: Response) -> None:
    """Drop the marker with the attributes it was set with."""
    from app.core.config import get_settings

    settings = get_settings()
    response.delete_cookie(
        key=SESSION_ORIGIN_COOKIE,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
