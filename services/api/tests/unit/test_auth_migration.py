"""
Test authentication with PyJWT migration
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import jwt
import pytest

from auth_module import create_access_token, verify_token

# UserRole enum removed - now using is_superadmin boolean


@pytest.mark.unit
class TestAuthMigration:
    """Test PyJWT migration functionality"""

    def test_create_access_token(self):
        """Test JWT token creation with PyJWT"""
        # Test data
        user_data = {"sub": "test_user_id", "username": "test_user", "user_id": "test_user_id"}

        # Create token
        token = create_access_token(user_data)

        # Verify token is a string
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        from auth_module import ALGORITHM, SECRET_KEY

        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "test_user_id"
        assert decoded["username"] == "test_user"
        assert decoded["user_id"] == "test_user_id"
        assert "exp" in decoded

    def test_token_expiration(self):
        """Test JWT token expiration handling"""
        # Create token with short expiration
        user_data = {"sub": "test_user_id"}
        expires_delta = timedelta(seconds=-1)  # Already expired

        token = create_access_token(user_data, expires_delta)

        # Verify expired token is rejected
        from auth_module import ALGORITHM, SECRET_KEY

        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    @patch("user_service.get_user_by_id")
    def test_verify_token_success(self, mock_get_user):
        """Test successful token verification"""
        # Mock user
        mock_db_user = Mock()
        mock_db_user.id = "test_user_id"
        mock_db_user.username = "test_user"
        mock_db_user.email = "test@example.com"
        mock_db_user.name = "Test User"
        mock_db_user.is_superadmin = True
        mock_db_user.is_active = True
        mock_db_user.created_at = datetime.now()

        mock_get_user.return_value = mock_db_user

        # Create valid token
        token = create_access_token({"sub": "test_user_id"})

        # Mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Mock database session
        Mock()

        # Verify token
        payload = verify_token(token)

        assert payload["sub"] == "test_user_id"
        assert isinstance(payload, dict)

    @patch("user_service.get_user_by_id")
    def test_verify_token_invalid(self, mock_get_user):
        """Test invalid token verification"""
        # Mock credentials with invalid token
        mock_credentials = Mock()
        mock_credentials.credentials = "invalid.token.here"

        # Mock database session
        Mock()

        # Verify invalid token raises HTTPException
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.token.here")

        assert exc_info.value.status_code == 401

    def test_verify_token_with_different_user_id(self):
        """Test token verification with different user ID"""
        # Create valid token with different user ID
        token = create_access_token({"sub": "nonexistent_user_id"})

        # Verify token can be decoded even if user doesn't exist
        # (user existence check is done at a higher level)
        payload = verify_token(token)

        assert payload["sub"] == "nonexistent_user_id"
        assert isinstance(payload, dict)

    def test_jwt_algorithm_security(self):
        """Test that only secure algorithms are used"""
        from auth_module import ALGORITHM

        # Verify we're using a secure algorithm
        assert ALGORITHM == "HS256"

        # Test that algorithm is enforced
        user_data = {"sub": "test_user_id"}
        token = create_access_token(user_data)

        from auth_module import SECRET_KEY

        # Should work with correct algorithm
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "test_user_id"

        # Should fail with wrong algorithm
        with pytest.raises(jwt.InvalidAlgorithmError):
            jwt.decode(token, SECRET_KEY, algorithms=["HS512"])
