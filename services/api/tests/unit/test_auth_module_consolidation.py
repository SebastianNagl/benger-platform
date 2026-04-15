"""
Test for Issue #111: Consolidate authentication code into single module

This test verifies that the new auth_module consolidates all authentication
functionality correctly and maintains backward compatibility.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from auth_module import (
    RefreshTokenService,
    Token,
    TokenService,
    User,
    UserCreate,
    UserLogin,
    authenticate_user,
    create_access_token,
    create_tokens_with_refresh,
    get_current_user,
    refresh_access_token,
    require_superadmin,
    require_user,
    revoke_refresh_token,
    verify_token,
    verify_token_cookie_or_header,
)
from auth_module.service import db_user_to_user
from models import User as DBUser


class TestAuthModuleConsolidation:
    """Test the consolidated authentication module"""

    def test_all_imports_available(self):
        """Test that all expected functions and classes are importable"""
        # Core authentication functions
        assert callable(authenticate_user)
        assert callable(create_access_token)
        assert callable(create_tokens_with_refresh)
        assert callable(refresh_access_token)
        assert callable(revoke_refresh_token)
        assert callable(verify_token)
        assert callable(verify_token_cookie_or_header)

        # Dependencies
        assert callable(require_user)
        assert callable(require_superadmin)
        assert callable(get_current_user)

        # Models
        assert User is not None
        assert UserCreate is not None
        assert UserLogin is not None
        assert Token is not None

        # Services
        assert TokenService is not None
        assert RefreshTokenService is not None

    def test_db_user_to_user_conversion(self):
        """Test conversion from database user to API user model"""
        db_user = Mock(spec=DBUser)
        db_user.id = "test-id"
        db_user.username = "testuser"
        db_user.email = "test@example.com"
        db_user.name = "Test User"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = datetime.now(timezone.utc)
        db_user.organization_memberships = []

        user = db_user_to_user(db_user)

        assert isinstance(user, User)
        assert user.id == "test-id"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.is_superadmin is False
        assert user.is_active is True

    @patch("auth_module.service.db_authenticate_user")
    def test_authenticate_user_success(self, mock_db_auth):
        """Test successful user authentication"""
        # Mock database user
        mock_db_user = Mock(spec=DBUser)
        mock_db_user.id = "test-id"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@example.com"
        mock_db_user.name = "Test User"
        mock_db_user.is_superadmin = False
        mock_db_user.is_active = True
        mock_db_user.email_verified = True
        mock_db_user.created_at = datetime.now(timezone.utc)
        mock_db_user.organization_memberships = []

        mock_db_auth.return_value = mock_db_user
        mock_db = Mock(spec=Session)

        user = authenticate_user("testuser", "password", mock_db)

        assert isinstance(user, User)
        assert user.username == "testuser"
        mock_db_auth.assert_called_once_with(mock_db, "testuser", "password")

    @patch("auth_module.service.db_authenticate_user")
    def test_authenticate_user_failure(self, mock_db_auth):
        """Test failed user authentication"""
        mock_db_auth.return_value = None
        mock_db = Mock(spec=Session)

        user = authenticate_user("testuser", "wrongpassword", mock_db)

        assert user is None
        mock_db_auth.assert_called_once_with(mock_db, "testuser", "wrongpassword")

    def test_create_access_token(self):
        """Test JWT access token creation"""
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0
        # Token should be JWT format (3 parts separated by dots)
        assert len(token.split(".")) == 3

    def test_create_access_token_with_expiry(self):
        """Test JWT access token creation with custom expiry"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data, expires_delta)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_token_valid(self):
        """Test JWT token verification with valid token"""
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        payload = verify_token(token)

        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "test-id"
        assert "exp" in payload

    def test_verify_token_invalid(self):
        """Test JWT token verification with invalid token"""
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.token.here")

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)

    @patch("auth_module.service.refresh_token_service")
    def test_create_tokens_with_refresh(self, mock_refresh_service):
        """Test creating tokens with refresh token"""
        # Mock to return tuple as real implementation does (plain_token, db_token)
        mock_refresh_service.create_refresh_token.return_value = (
            "refresh_token_123",
            Mock(),
        )

        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        mock_db = Mock(spec=Session)

        token = create_tokens_with_refresh(
            user=user, db=mock_db, user_agent="test-agent", ip_address="127.0.0.1"
        )

        assert isinstance(token, Token)
        assert token.access_token is not None
        assert token.refresh_token == "refresh_token_123"
        assert token.token_type == "bearer"
        assert token.expires_in > 0
        assert token.user.username == "testuser"

        mock_refresh_service.create_refresh_token.assert_called_once_with(
            db=mock_db,
            user_id="test-id",
            user_agent="test-agent",
            ip_address="127.0.0.1",
        )

    def test_verify_token_cookie_or_header_cookie(self):
        """Test token verification from cookie"""
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": token}
        mock_request.headers = {}

        payload = verify_token_cookie_or_header(mock_request)

        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "test-id"

    def test_verify_token_cookie_or_header_bearer(self):
        """Test token verification from Authorization header"""
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        mock_headers = Mock()
        mock_headers.get.return_value = f"Bearer {token}"
        mock_request.headers = mock_headers

        payload = verify_token_cookie_or_header(mock_request)

        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "test-id"

    def test_verify_token_cookie_or_header_missing(self):
        """Test token verification when no token provided"""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        mock_headers = Mock()
        mock_headers.get.return_value = None
        mock_request.headers = mock_headers

        with pytest.raises(HTTPException) as exc_info:
            verify_token_cookie_or_header(mock_request)

        assert exc_info.value.status_code == 401
        assert "No access token provided" in str(exc_info.value.detail)

    @patch("auth_module.dependencies.get_user_by_id")
    def test_get_current_user_success(self, mock_get_user):
        """Test getting current user with valid token"""
        # Mock database user
        mock_db_user = Mock(spec=DBUser)
        mock_db_user.id = "test-id"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@example.com"
        mock_db_user.name = "Test User"
        mock_db_user.is_superadmin = False
        mock_db_user.is_active = True
        mock_db_user.email_verified = True
        mock_db_user.created_at = datetime.now(timezone.utc)
        mock_db_user.organization_memberships = []

        mock_get_user.return_value = mock_db_user

        # Create valid token
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": token}
        mock_request.headers = {}

        mock_db = Mock(spec=Session)

        user = get_current_user(mock_request, mock_db)

        assert isinstance(user, User)
        assert user.username == "testuser"
        mock_get_user.assert_called_once_with(mock_db, "test-id")

    def test_get_current_user_no_token(self):
        """Test getting current user when no token provided"""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        mock_headers = Mock()
        mock_headers.get.return_value = None
        mock_request.headers = mock_headers

        mock_db = Mock(spec=Session)

        user = get_current_user(mock_request, mock_db)

        assert user is None

    @patch("auth_module.dependencies.get_user_by_id")
    def test_require_user_success(self, mock_get_user):
        """Test require_user with valid authenticated user"""
        # Mock database user
        mock_db_user = Mock(spec=DBUser)
        mock_db_user.id = "test-id"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@example.com"
        mock_db_user.name = "Test User"
        mock_db_user.is_superadmin = False
        mock_db_user.is_active = True
        mock_db_user.email_verified = True
        mock_db_user.created_at = datetime.now(timezone.utc)
        mock_db_user.organization_memberships = []

        mock_get_user.return_value = mock_db_user

        # Create valid token
        data = {"sub": "testuser", "user_id": "test-id"}
        token = create_access_token(data)

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"access_token": token}
        mock_request.headers = {}

        mock_db = Mock(spec=Session)

        user = require_user(mock_request, mock_db)

        assert isinstance(user, User)
        assert user.username == "testuser"

    def test_require_user_no_token(self):
        """Test require_user when no token provided"""
        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        mock_headers = Mock()
        mock_headers.get.return_value = None
        mock_request.headers = mock_headers

        mock_db = Mock(spec=Session)

        with pytest.raises(HTTPException) as exc_info:
            require_user(mock_request, mock_db)

        assert exc_info.value.status_code == 401

    def test_require_superadmin_success(self):
        """Test require_superadmin with superadmin user"""
        superadmin_user = User(
            id="admin-id",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            is_superadmin=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        user = require_superadmin(superadmin_user)

        assert user.is_superadmin is True

    def test_require_superadmin_failure(self):
        """Test require_superadmin with regular user"""
        regular_user = User(
            id="user-id",
            username="user",
            email="user@example.com",
            name="Regular User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        with pytest.raises(HTTPException) as exc_info:
            require_superadmin(regular_user)

        assert exc_info.value.status_code == 403
        assert "Superadmin access required" in str(exc_info.value.detail)

    def test_token_service_create_access_token(self):
        """Test TokenService.create_access_token_for_user"""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        mock_db = Mock(spec=Session)

        with patch("auth_module.token_service.create_tokens_with_refresh") as mock_create:
            mock_token = Mock(spec=Token)
            mock_create.return_value = mock_token

            result = TokenService.create_access_token_for_user(
                user=user, db=mock_db, user_agent="test-agent", ip_address="127.0.0.1"
            )

            assert result == mock_token
            mock_create.assert_called_once_with(
                user=user,
                db=mock_db,
                user_agent="test-agent",
                ip_address="127.0.0.1",
                include_refresh_token=True,
            )

    @patch("auth_module.token_service.refresh_token_service")
    def test_refresh_token_service_methods(self, mock_refresh_service):
        """Test RefreshTokenService wrapper methods"""
        mock_db = Mock(spec=Session)

        # Test create_refresh_token
        mock_refresh_service.create_refresh_token.return_value = "token123"
        result = RefreshTokenService.create_refresh_token(
            db=mock_db,
            user_id="user-id",
            user_agent="test-agent",
            ip_address="127.0.0.1",
        )
        assert result == "token123"

        # Test validate_refresh_token
        mock_refresh_service.validate_refresh_token.return_value = "user-id"
        result = RefreshTokenService.validate_refresh_token(mock_db, "token123")
        assert result == "user-id"

        # Test revoke_refresh_token
        mock_refresh_service.revoke_refresh_token.return_value = True
        result = RefreshTokenService.revoke_refresh_token(mock_db, "token123")
        assert result is True

        # Test revoke_all_user_tokens
        mock_refresh_service.revoke_all_user_tokens.return_value = True
        result = RefreshTokenService.revoke_all_user_tokens(mock_db, "user-id")
        assert result is True

        # Test cleanup_expired_tokens
        mock_refresh_service.cleanup_expired_tokens.return_value = 5
        result = RefreshTokenService.cleanup_expired_tokens(mock_db)
        assert result == 5

    def test_user_models_validation(self):
        """Test Pydantic model validation"""
        # Test User model
        user_data = {
            "id": "test-id",
            "username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "is_superadmin": False,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }
        user = User(**user_data)
        assert user.username == "testuser"

        # Test UserCreate model (includes required legal expertise fields)
        create_data = {
            "username": "newuser",
            "email": "new@example.com",
            "name": "New User",
            "password": "password123",
            "legal_expertise_level": "layperson",
            "german_proficiency": "native",
        }
        user_create = UserCreate(**create_data)
        assert user_create.username == "newuser"

        # Test UserLogin model
        login_data = {"username": "testuser", "password": "password123"}
        user_login = UserLogin(**login_data)
        assert user_login.username == "testuser"

    def test_module_public_api_completeness(self):
        """Test that the module exposes all expected public API functions"""
        import auth_module

        # Check that all functions listed in __all__ are actually exported
        for name in auth_module.__all__:
            assert hasattr(auth_module, name), f"Missing export: {name}"

        # Check key authentication functions
        assert hasattr(auth_module, "authenticate_user")
        assert hasattr(auth_module, "create_access_token")
        assert hasattr(auth_module, "require_user")
        assert hasattr(auth_module, "require_superadmin")

        # Check models
        assert hasattr(auth_module, "User")
        assert hasattr(auth_module, "Token")
        assert hasattr(auth_module, "UserCreate")

        # Check services
        assert hasattr(auth_module, "TokenService")
        assert hasattr(auth_module, "RefreshTokenService")
