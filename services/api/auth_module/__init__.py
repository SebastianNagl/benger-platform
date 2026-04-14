"""
Consolidated authentication module for BenGER API

This module consolidates all authentication-related functionality into a single,
well-organized package structure for better maintainability.

Public API:
- Authentication functions: authenticate_user, create_access_token, verify_token
- User management: create_user, get_user_by_id, update_user_profile
- Token management: create_tokens_with_refresh, refresh_access_token, revoke_refresh_token
- Security: require_user, require_superadmin, logout_user
- Models: User, Token, UserCreate, UserLogin, etc.
"""

# Configuration constants
from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, REFRESH_TOKEN_EXPIRE_DAYS, SECRET_KEY
from .dependencies import (
    get_current_user,
    require_org_admin,
    require_org_contributor,
    require_superadmin,
    require_user,
)
from .models import (
    PasswordUpdate,
    Token,
    TokenData,
    User,
    UserCreate,
    UserCreateWithInvitation,
    UserLogin,
    UserProfile,
    UserUpdate,
)

# Import all public functions and classes for easy access
from .service import (
    authenticate_user,
    create_access_token,
    create_tokens_with_refresh,
    logout_user,
    refresh_access_token,
    revoke_refresh_token,
    verify_token,
    verify_token_cookie_or_header,
)
from .token_service import RefreshTokenService, TokenService
from .user_service import (
    change_user_password,
    check_confirmation_due,
    confirm_profile,
    create_profile_snapshot,
    create_user,
    delete_user,
    get_all_users,
    get_mandatory_profile_fields,
    get_password_hash,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    get_user_by_username_or_email,
    get_users,
    hash_password,
    init_demo_users,
    init_feature_flags,
    initialize_database,
    update_user_profile,
    update_user_status,
    update_user_superadmin_status,
    verify_password,
)

__all__ = [
    # Authentication functions
    "authenticate_user",
    "create_access_token",
    "create_tokens_with_refresh",
    "refresh_access_token",
    "revoke_refresh_token",
    "verify_token",
    "verify_token_cookie_or_header",
    "logout_user",
    # Dependencies
    "require_user",
    "require_superadmin",
    "require_org_admin",
    "require_org_contributor",
    "get_current_user",
    # Models
    "User",
    "UserCreate",
    "UserCreateWithInvitation",
    "UserLogin",
    "Token",
    "TokenData",
    "PasswordUpdate",
    "UserProfile",
    "UserUpdate",
    # User service
    "create_user",
    "get_user_by_id",
    "get_user_by_username",
    "get_user_by_email",
    "get_user_by_username_or_email",
    "get_users",
    "update_user_profile",
    "change_user_password",
    "update_user_superadmin_status",
    "update_user_status",
    "delete_user",
    "get_all_users",
    "init_demo_users",
    "init_feature_flags",
    "initialize_database",
    "get_password_hash",
    "hash_password",
    "verify_password",
    # Issue #1206: Mandatory profile
    "get_mandatory_profile_fields",
    "check_confirmation_due",
    "create_profile_snapshot",
    "confirm_profile",
    # Token service
    "TokenService",
    "RefreshTokenService",
    # Configuration
    "SECRET_KEY",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
]
