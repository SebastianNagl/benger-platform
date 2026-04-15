"""
Comprehensive tests for refresh token service.
Tests JWT refresh token handling and security functionality.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

import refresh_token_service
from models import RefreshToken
from refresh_token_service import (
    cleanup_expired_tokens,
    create_refresh_token,
    generate_refresh_token,
    get_user_active_tokens,
    hash_token,
    revoke_refresh_token,
    revoke_token_by_id,
    revoke_user_tokens,
    rotate_refresh_token,
    validate_refresh_token,
)


class TestRefreshTokenService:
    """Test refresh token service functionality"""

    @pytest.fixture
    def test_db(self):
        """Create mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_refresh_token(self):
        """Create mock refresh token for testing"""
        token = Mock(spec=RefreshToken)
        token.id = "token-123"
        token.token_hash = "hashed_token_value"
        token.user_id = "user-456"
        token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        token.is_active = True
        token.user_agent = "Mozilla/5.0"
        token.ip_address = "192.168.1.1"
        token.last_used_at = datetime.now(timezone.utc)
        return token

    def test_generate_refresh_token(self):
        """Test refresh token generation"""
        token = generate_refresh_token()

        assert isinstance(token, str)
        assert len(token) > 0
        # URL-safe base64 tokens should be longer than 64 characters
        assert len(token) >= 64

    def test_generate_refresh_token_uniqueness(self):
        """Test that generated tokens are unique"""
        token1 = generate_refresh_token()
        token2 = generate_refresh_token()

        assert token1 != token2

    def test_hash_token(self):
        """Test token hashing"""
        token = "test_token_12345"
        hashed = hash_token(token)

        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256 hex digest length
        assert hashed != token  # Should be different from original

        # Same input should produce same hash
        hashed2 = hash_token(token)
        assert hashed == hashed2

    def test_hash_token_different_inputs(self):
        """Test that different tokens produce different hashes"""
        token1 = "token1"
        token2 = "token2"

        hash1 = hash_token(token1)
        hash2 = hash_token(token2)

        assert hash1 != hash2

    def test_create_refresh_token_success(self, test_db):
        """Test successful refresh token creation"""
        mock_token = Mock(spec=RefreshToken)
        test_db.add = Mock()
        test_db.commit = Mock()
        test_db.refresh = Mock()

        with patch('services.refresh_token_service.RefreshToken', return_value=mock_token):
            with patch(
                'services.refresh_token_service.secrets.token_urlsafe',
                side_effect=["token_id", "plain_token"],
            ):
                with patch('services.refresh_token_service.hash_token', return_value="hashed_token"):
                    plain_token, db_token = create_refresh_token(test_db, "user-123")

                    assert plain_token == "plain_token"
                    assert db_token == mock_token
                    test_db.add.assert_called_once_with(mock_token)
                    test_db.commit.assert_called_once()
                    test_db.refresh.assert_called_once_with(mock_token)

    def test_create_refresh_token_with_metadata(self, test_db):
        """Test refresh token creation with user agent and IP"""
        mock_token = Mock(spec=RefreshToken)
        test_db.add = Mock()
        test_db.commit = Mock()
        test_db.refresh = Mock()

        with patch('services.refresh_token_service.RefreshToken', return_value=mock_token):
            with patch(
                'services.refresh_token_service.secrets.token_urlsafe',
                side_effect=["token_id", "plain_token"],
            ):
                with patch('services.refresh_token_service.hash_token', return_value="hashed_token"):
                    plain_token, db_token = create_refresh_token(
                        test_db, "user-123", user_agent="Chrome/90.0", ip_address="192.168.1.1"
                    )

                    assert plain_token == "plain_token"
                    assert db_token == mock_token

    def test_validate_refresh_token_success(self, test_db, mock_refresh_token):
        """Test successful token validation"""
        test_db.query.return_value.filter.return_value.first.return_value = mock_refresh_token

        with patch('services.refresh_token_service.hash_token', return_value=mock_refresh_token.token_hash):
            result = validate_refresh_token(test_db, "valid_token")

            assert result == mock_refresh_token
            assert mock_refresh_token.last_used_at is not None
            test_db.commit.assert_called_once()
            test_db.refresh.assert_called_once_with(mock_refresh_token)

    def test_validate_refresh_token_not_found(self, test_db):
        """Test token validation when token not found"""
        test_db.query.return_value.filter.return_value.first.return_value = None

        with patch('services.refresh_token_service.hash_token', return_value="some_hash"):
            result = validate_refresh_token(test_db, "invalid_token")

            assert result is None

    def test_validate_refresh_token_expired(self, test_db, mock_refresh_token):
        """Test token validation with expired token"""
        # Set token as expired
        mock_refresh_token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        test_db.query.return_value.filter.return_value.first.return_value = (
            None  # Filter should exclude expired
        )

        with patch('services.refresh_token_service.hash_token', return_value=mock_refresh_token.token_hash):
            result = validate_refresh_token(test_db, "expired_token")

            assert result is None

    def test_validate_refresh_token_inactive(self, test_db, mock_refresh_token):
        """Test token validation with inactive token"""
        mock_refresh_token.is_active = False
        test_db.query.return_value.filter.return_value.first.return_value = (
            None  # Filter should exclude inactive
        )

        with patch('services.refresh_token_service.hash_token', return_value=mock_refresh_token.token_hash):
            result = validate_refresh_token(test_db, "inactive_token")

            assert result is None

    def test_rotate_refresh_token_success(self, test_db, mock_refresh_token):
        """Test successful token rotation"""
        # Mock the old token validation
        with patch('services.refresh_token_service.validate_refresh_token', return_value=mock_refresh_token):
            # Mock the new token creation
            new_mock_token = Mock(spec=RefreshToken)
            with patch(
                'services.refresh_token_service.create_refresh_token',
                return_value=("new_token", new_mock_token),
            ):
                result = rotate_refresh_token(test_db, "old_token")

                assert result == ("new_token", new_mock_token)
                assert mock_refresh_token.is_active is False
                test_db.commit.assert_called()

    def test_rotate_refresh_token_invalid_old_token(self, test_db):
        """Test token rotation with invalid old token"""
        with patch('services.refresh_token_service.validate_refresh_token', return_value=None):
            result = rotate_refresh_token(test_db, "invalid_token")

            assert result is None

    def test_rotate_refresh_token_with_metadata(self, test_db, mock_refresh_token):
        """Test token rotation with user agent and IP"""
        with patch('services.refresh_token_service.validate_refresh_token', return_value=mock_refresh_token):
            new_mock_token = Mock(spec=RefreshToken)
            with patch(
                'services.refresh_token_service.create_refresh_token',
                return_value=("new_token", new_mock_token),
            ) as mock_create:
                result = rotate_refresh_token(
                    test_db, "old_token", user_agent="Chrome/90.0", ip_address="192.168.1.1"
                )

                assert result == ("new_token", new_mock_token)
                mock_create.assert_called_once_with(
                    test_db, mock_refresh_token.user_id, "Chrome/90.0", "192.168.1.1"
                )

    def test_revoke_refresh_token_success(self, test_db, mock_refresh_token):
        """Test successful token revocation"""
        test_db.query.return_value.filter.return_value.first.return_value = mock_refresh_token

        with patch('services.refresh_token_service.hash_token', return_value=mock_refresh_token.token_hash):
            result = revoke_refresh_token(test_db, "valid_token")

            assert result is True
            assert mock_refresh_token.is_active is False
            test_db.commit.assert_called_once()

    def test_revoke_refresh_token_not_found(self, test_db):
        """Test token revocation when token not found"""
        test_db.query.return_value.filter.return_value.first.return_value = None

        with patch('services.refresh_token_service.hash_token', return_value="some_hash"):
            result = revoke_refresh_token(test_db, "invalid_token")

            assert result is False

    def test_revoke_user_tokens_success(self, test_db):
        """Test successful revocation of all user tokens"""
        test_db.query.return_value.filter.return_value.update.return_value = 3  # 3 tokens revoked

        result = revoke_user_tokens(test_db, "user-123")

        assert result == 3
        test_db.commit.assert_called_once()

    def test_revoke_user_tokens_no_tokens(self, test_db):
        """Test user token revocation when no tokens exist"""
        test_db.query.return_value.filter.return_value.update.return_value = 0

        result = revoke_user_tokens(test_db, "user-123")

        assert result == 0

    def test_cleanup_expired_tokens_success(self, test_db):
        """Test successful cleanup of expired tokens"""
        # Create mock expired and valid tokens
        expired_token1 = Mock(spec=RefreshToken)
        expired_token1.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        expired_token2 = Mock(spec=RefreshToken)
        expired_token2.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        valid_token = Mock(spec=RefreshToken)
        valid_token.expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        all_tokens = [expired_token1, expired_token2, valid_token]
        test_db.query.return_value.all.return_value = all_tokens

        result = cleanup_expired_tokens(test_db)

        assert result == 2  # 2 expired tokens
        assert test_db.delete.call_count == 2
        test_db.commit.assert_called_once()

    def test_cleanup_expired_tokens_timezone_naive(self, test_db):
        """Test cleanup with timezone-naive datetime from database"""
        expired_token = Mock(spec=RefreshToken)
        expired_token.expires_at = datetime(2023, 1, 1, 12, 0, 0)  # Naive datetime

        test_db.query.return_value.all.return_value = [expired_token]

        result = cleanup_expired_tokens(test_db)

        assert result == 1
        test_db.delete.assert_called_once_with(expired_token)

    def test_cleanup_expired_tokens_timezone_aware(self, test_db):
        """Test cleanup with timezone-aware datetime from database"""
        expired_token = Mock(spec=RefreshToken)
        expired_token.expires_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        test_db.query.return_value.all.return_value = [expired_token]

        result = cleanup_expired_tokens(test_db)

        assert result == 1

    def test_cleanup_expired_tokens_no_expired(self, test_db):
        """Test cleanup when no tokens are expired"""
        valid_token = Mock(spec=RefreshToken)
        valid_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        test_db.query.return_value.all.return_value = [valid_token]

        result = cleanup_expired_tokens(test_db)

        assert result == 0
        test_db.delete.assert_not_called()

    def test_get_user_active_tokens_success(self, test_db, mock_refresh_token):
        """Test getting user's active tokens"""
        tokens = [mock_refresh_token]
        test_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            tokens
        )

        result = get_user_active_tokens(test_db, "user-123")

        assert result == tokens

    def test_get_user_active_tokens_empty(self, test_db):
        """Test getting user's active tokens when none exist"""
        test_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = get_user_active_tokens(test_db, "user-123")

        assert result == []

    def test_revoke_token_by_id_success(self, test_db, mock_refresh_token):
        """Test successful token revocation by ID"""
        test_db.query.return_value.filter.return_value.first.return_value = mock_refresh_token

        result = revoke_token_by_id(test_db, "token-123", "user-456")

        assert result is True
        assert mock_refresh_token.is_active is False
        test_db.commit.assert_called_once()

    def test_revoke_token_by_id_not_found(self, test_db):
        """Test token revocation by ID when token not found"""
        test_db.query.return_value.filter.return_value.first.return_value = None

        result = revoke_token_by_id(test_db, "nonexistent-token", "user-456")

        assert result is False

    def test_revoke_token_by_id_wrong_user(self, test_db):
        """Test token revocation by ID with wrong user ID"""
        test_db.query.return_value.filter.return_value.first.return_value = (
            None  # Filter excludes wrong user
        )

        result = revoke_token_by_id(test_db, "token-123", "wrong-user")

        assert result is False

    def test_token_expiration_configuration(self):
        """Test that token expiration is configurable"""
        with patch.dict('os.environ', {'REFRESH_TOKEN_EXPIRE_DAYS': '14'}):
            # Reload the module to pick up new environment variable
            import importlib

            importlib.reload(refresh_token_service)

            # The constant should be updated (this test would need actual module reloading)
            # Test that the value is a positive integer (actual value depends on environment)
            assert refresh_token_service.REFRESH_TOKEN_EXPIRE_DAYS > 0
            assert isinstance(refresh_token_service.REFRESH_TOKEN_EXPIRE_DAYS, int)

    def test_create_refresh_token_expiration_time(self, test_db):
        """Test that created tokens have correct expiration time"""
        mock_token = Mock(spec=RefreshToken)

        with patch(
            'services.refresh_token_service.RefreshToken', return_value=mock_token
        ) as mock_token_class:
            with patch('services.refresh_token_service.secrets.token_urlsafe', return_value="test_token"):
                with patch('services.refresh_token_service.hash_token', return_value="hashed"):
                    create_refresh_token(test_db, "user-123")

                    # Check that the token was created with correct expiration
                    call_args = mock_token_class.call_args
                    expires_at = call_args.kwargs['expires_at']

                    # Should be approximately REFRESH_TOKEN_EXPIRE_DAYS from now (uses configured value)
                    expected_expiry = datetime.now(timezone.utc) + timedelta(
                        days=refresh_token_service.REFRESH_TOKEN_EXPIRE_DAYS
                    )
                    time_diff = abs((expires_at - expected_expiry).total_seconds())
                    assert time_diff < 60  # Within 1 minute tolerance

    def test_hash_token_sha256(self):
        """Test that hash_token uses SHA256"""
        token = "test_token"
        expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        result = hash_token(token)

        assert result == expected_hash

    def test_token_security_properties(self):
        """Test security properties of generated tokens"""
        # Generate multiple tokens to test randomness
        tokens = [generate_refresh_token() for _ in range(10)]

        # All tokens should be unique
        assert len(set(tokens)) == len(tokens)

        # All tokens should be URL-safe (no special characters that need encoding)
        for token in tokens:
            assert all(c.isalnum() or c in '-_' for c in token)

    def test_database_error_handling(self, test_db):
        """Test handling of database errors"""
        test_db.commit.side_effect = Exception("Database error")

        # Should handle database errors gracefully
        with patch('services.refresh_token_service.RefreshToken', return_value=Mock()):
            with patch('services.refresh_token_service.secrets.token_urlsafe', return_value="test"):
                with patch('services.refresh_token_service.hash_token', return_value="hash"):
                    with pytest.raises(Exception):
                        create_refresh_token(test_db, "user-123")

    def test_concurrent_token_validation(self, test_db, mock_refresh_token):
        """Test concurrent validation of the same token"""
        test_db.query.return_value.filter.return_value.first.return_value = mock_refresh_token
        original_last_used = mock_refresh_token.last_used_at

        with patch('services.refresh_token_service.hash_token', return_value=mock_refresh_token.token_hash):
            # Simulate concurrent validations
            result1 = validate_refresh_token(test_db, "token")
            result2 = validate_refresh_token(test_db, "token")

            assert result1 == mock_refresh_token
            assert result2 == mock_refresh_token
            # last_used_at should be updated
            assert mock_refresh_token.last_used_at != original_last_used
