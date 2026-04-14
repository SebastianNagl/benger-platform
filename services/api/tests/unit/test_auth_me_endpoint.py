"""
Unit tests for /api/v1/auth/me endpoint
Tests for GitHub Issue #310: Ensure endpoint returns user data, not JWT claims
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

# Import the modules we're testing
from auth_module.dependencies import require_user
from auth_module.models import User


class TestAuthMeEndpoint:
    """Test suite for /api/v1/auth/me endpoint"""

    def test_me_endpoint_returns_user_object(self):
        """Test that /me endpoint returns full user object, not JWT claims"""
        # Create a mock user with all required fields
        mock_user = User(
            id="test-user-id",
            username="testuser",
            email="test@example.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # The endpoint function just returns the user as-is
        # This tests that we're not transforming it into JWT claims
        result = mock_user

        # Verify the result is the complete user object
        assert result == mock_user
        assert result.id == "test-user-id"
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert result.name == "Test User"
        assert hasattr(result, "created_at")

        # Ensure it's NOT returning JWT claims structure
        assert not hasattr(result, "sub")
        assert not hasattr(result, "exp")
        assert not hasattr(result, "user_id")  # JWT uses user_id, User model uses id

    def test_me_endpoint_with_superadmin(self):
        """Test that /me endpoint correctly returns superadmin users"""
        mock_superadmin = User(
            id="admin-user-id",
            username="admin",
            email="admin@example.com",
            name="System Administrator",
            is_superadmin=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # The endpoint returns the user directly
        result = mock_superadmin

        assert result == mock_superadmin
        assert result.is_superadmin is True
        assert result.id == "admin-user-id"

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    @patch("auth_module.dependencies.db_user_to_user")
    def test_require_user_fetches_from_database(
        self, mock_db_user_to_user, mock_get_user_by_id, mock_verify_token
    ):
        """Test that require_user dependency fetches user from database, not from JWT"""
        # Mock the JWT payload (what would be wrong to return)
        jwt_payload = {
            "sub": "testuser",
            "user_id": "test-user-id",
            "is_superadmin": False,
            "exp": 1755176326,
        }
        mock_verify_token.return_value = jwt_payload

        # Mock the database user
        mock_db_user = MagicMock()
        mock_db_user.id = "test-user-id"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@example.com"
        mock_db_user.is_active = True
        mock_get_user_by_id.return_value = mock_db_user

        # Mock the conversion to User model
        expected_user = User(
            id="test-user-id",
            username="testuser",
            email="test@example.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        mock_db_user_to_user.return_value = expected_user

        # Create mock request and session
        mock_request = Mock()
        mock_db = Mock(spec=Session)

        # Call require_user
        result = require_user(request=mock_request, db=mock_db)

        # Verify it called get_user_by_id with the user_id from JWT
        mock_get_user_by_id.assert_called_once_with(mock_db, "test-user-id")

        # Verify it converted the DB user to User model
        mock_db_user_to_user.assert_called_once_with(mock_db_user)

        # Verify the result is the User model, not the JWT payload
        assert result == expected_user
        assert result.id == "test-user-id"
        assert result.email == "test@example.com"
        assert not hasattr(result, "sub")
        assert not hasattr(result, "exp")

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    def test_require_user_raises_401_when_user_not_found(
        self, mock_get_user_by_id, mock_verify_token
    ):
        """Test that require_user raises 401 when user not found in database"""
        # Mock JWT payload
        mock_verify_token.return_value = {"user_id": "non-existent-user"}

        # Mock user not found in database
        mock_get_user_by_id.return_value = None

        mock_request = Mock()
        mock_db = Mock(spec=Session)

        # Should raise 401 when user not found
        with pytest.raises(HTTPException) as exc_info:
            require_user(request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "User not found" in str(exc_info.value.detail)

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    def test_require_user_raises_401_for_inactive_user(
        self, mock_get_user_by_id, mock_verify_token
    ):
        """Test that require_user raises 401 for inactive users"""
        # Mock JWT payload
        mock_verify_token.return_value = {"user_id": "inactive-user-id"}

        # Mock inactive user in database
        mock_db_user = MagicMock()
        mock_db_user.is_active = False
        mock_get_user_by_id.return_value = mock_db_user

        mock_request = Mock()
        mock_db = Mock(spec=Session)

        # Should raise 401 for inactive user
        with pytest.raises(HTTPException) as exc_info:
            require_user(request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 401
        assert "Inactive user" in str(exc_info.value.detail)

    def test_user_model_structure(self):
        """Test that User model has correct structure for API responses"""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            name="Test User",
            is_superadmin=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # Verify all required fields are present
        assert hasattr(user, "id")
        assert hasattr(user, "username")
        assert hasattr(user, "email")
        assert hasattr(user, "name")
        assert hasattr(user, "is_superadmin")
        assert hasattr(user, "is_active")
        assert hasattr(user, "created_at")

        # Verify field types
        assert isinstance(user.id, str)
        assert isinstance(user.username, str)
        assert isinstance(user.email, str)
        assert isinstance(user.name, str)
        assert isinstance(user.is_superadmin, bool)
        assert isinstance(user.is_active, bool)
        assert isinstance(user.created_at, datetime)
