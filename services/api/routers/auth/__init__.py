"""
Consolidated authentication endpoints.

Merges all auth functionality from both the legacy router and v1 auth router
into a single router (Issue #1207 Phase 3).

Tier 2.4 decomposition: the former single-file ``routers/auth.py`` (1306 lines)
was split into concern modules under this package. ``_common`` holds the shared
``router`` instance, the imported auth-service symbols, and the
response-building helpers; the handlers live in ``login`` (login / signup /
registration), ``tokens`` (refresh + logout), ``user`` (user info + profile +
mandatory-profile), ``password`` (change / reset) and ``verification`` (email
verification). Importing those modules attaches their handlers onto the shared
``router``.

The public surface (``router`` plus every helper, service symbol and handler)
is re-exported here so that ``from routers.auth import X`` and
``routers.auth.X`` continue to resolve exactly as before.
"""

from ._common import (  # noqa: F401
    router,
    logger,
    # Auth-service symbols re-exported so routers.auth.<sym> still resolves for
    # any patch site that targets the package namespace.
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
    require_user,
    revoke_refresh_token,
    logout_user,
    email_verification_service,
    change_user_password,
    update_user_profile,
)

# Importing the concern modules registers their handlers on ``router``.
from . import session  # noqa: E402,F401
from . import tokens  # noqa: E402,F401
from . import user  # noqa: E402,F401
from . import password  # noqa: E402,F401
from . import verification  # noqa: E402,F401

# Profile helpers live in the `user` concern module; re-export them so
# `from routers.auth import _build_user_profile_response` keeps working.
from .user import (  # noqa: E402,F401
    get_user_primary_role,
    _ensure_dict,
    _build_user_profile_response,
)

# Re-export handlers so existing ``from routers.auth import <name>`` imports and
# any test that references the handler by name keep working.
from .session import (  # noqa: E402,F401
    login,
    signup,
    register,
)
from .tokens import (  # noqa: E402,F401
    refresh_token_endpoint,
    logout,
    logout_all_devices,
)
from .user import (  # noqa: E402,F401
    get_current_user,
    get_user_contexts,
    verify_token_endpoint,
    get_user_profile,
    update_profile,
    complete_profile,
    check_profile_status,
    get_mandatory_profile_status,
    confirm_profile_endpoint,
    get_profile_history,
)
from .password import (  # noqa: E402,F401
    change_password,
    request_password_reset,
    reset_password,
)
from .verification import (  # noqa: E402,F401
    verify_email,
    verify_email_with_token,
    resend_verification_email,
    verify_email_enhanced,
)
