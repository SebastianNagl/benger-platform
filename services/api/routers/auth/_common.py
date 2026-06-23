"""
Consolidated authentication endpoints — shared deps.

This package was split out of the former single-file ``routers/auth.py``
(Issue #1207 Phase 3 / Tier 2.4 router decomposition). ``_common`` holds the
shared imports, the ``router`` instance, and the response-building helpers.
The endpoint handlers live in the sibling concern modules (``login``,
``tokens``, ``user``, ``password``, ``verification``) and are aggregated in
``__init__``.

Symbols imported here (``create_user``, ``authenticate_user``,
``email_verification_service`` …) are re-exported from ``__init__`` so the
package-level names continue to exist, and each concern module pulls them in
via ``from ._common import *`` so that ``patch("routers.auth.<module>.<sym>")``
resolves to the name the handler actually calls.
"""

# NOTE: most names below are imported here purely to be re-exported through
# ``from ._common import *`` into the concern submodules (and patched by tests
# at ``routers.auth.<submodule>.<name>``). They are therefore flagged F401 by
# static analysis but are deliberately kept — hence the blanket ``# noqa: F401``.
import logging
import traceback
from datetime import datetime, timezone  # noqa: F401
from typing import Optional  # noqa: F401

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status  # noqa: F401
from sqlalchemy import select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
from sqlalchemy.orm import Session  # noqa: F401

from app.core.config import get_settings  # noqa: F401

from schemas.auth_schemas import (  # noqa: F401
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordUpdate,
    ResendVerificationRequest,
    UserProfile,
    UserUpdate,
)
from schemas.profile_completion_schemas import (  # noqa: F401
    EmailVerificationEnhancedResponse,
    MandatoryProfileStatusResponse,
    ProfileCompletionRequest,
    ProfileCompletionResponse,
    ProfileConfirmationResponse,
    ProfileStatusResponse,
)
from auth_module import (  # noqa: F401
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    Token,
    User,
    UserCreate,
    UserLogin,
    authenticate_user,
    create_tokens_with_refresh,
    create_user,
    refresh_access_token,
    require_superadmin,
    revoke_refresh_token,
)
# Re-exported for tests that patch routers.auth.logout_user — not directly
# used in this module but must be importable as an attribute.
from auth_module import logout_user  # noqa: F401
from auth_module.dependencies import require_user  # noqa: F401
from auth_module.email_verification import email_verification_service  # noqa: F401
from auth_module.user_service import change_user_password, update_user_profile  # noqa: F401
# Async twin used by migrated profile handlers (sync ``confirm_profile`` is
# re-exported above for tests; the async lane uses this).
from auth_module.user_service import confirm_profile_async  # noqa: F401
from database import get_async_db, get_db  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"], prefix="/api/auth")


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (session / tokens / user / password / verification)
# no longer need to repeat a 43-name explicit import block just to dodge F405 —
# this single list documents the shared surface once. It is the FULL set of
# public names this module already re-exported via ``*`` (every import above plus
# ``logger``/``router``), so the star binding is unchanged.
__all__ = [
    # stdlib / typing
    "logging",
    "traceback",
    "datetime",
    "timezone",
    "Optional",
    # fastapi
    "APIRouter",
    "Depends",
    "HTTPException",
    "Request",
    "Response",
    "status",
    # sqlalchemy
    "select",
    "AsyncSession",
    "Session",
    # config
    "get_settings",
    # schemas.auth_schemas
    "EmailVerificationRequest",
    "PasswordResetConfirm",
    "PasswordResetRequest",
    "PasswordUpdate",
    "ResendVerificationRequest",
    "UserProfile",
    "UserUpdate",
    # schemas.profile_completion_schemas
    "EmailVerificationEnhancedResponse",
    "MandatoryProfileStatusResponse",
    "ProfileCompletionRequest",
    "ProfileCompletionResponse",
    "ProfileConfirmationResponse",
    "ProfileStatusResponse",
    # auth_module
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "Token",
    "User",
    "UserCreate",
    "UserLogin",
    "authenticate_user",
    "create_tokens_with_refresh",
    "create_user",
    "refresh_access_token",
    "require_superadmin",
    "revoke_refresh_token",
    "logout_user",
    "require_user",
    "email_verification_service",
    "change_user_password",
    "update_user_profile",
    "confirm_profile_async",
    # database
    "get_async_db",
    "get_db",
    # this module
    "logger",
    "router",
]
