"""
Test suite for email verification URL generation (Issue #377)

This test suite verifies that email verification links use the correct frontend URL:
1. Links use FRONTEND_URL environment variable
2. Default to http://localhost:3000 when not set
3. Work correctly in different environments
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from auth_module.email_verification import EmailVerificationService
from models import User


class TestEmailVerificationURL:
    """Test email verification URL generation"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        db = MagicMock(spec=Session)
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create a mock user"""
        user = MagicMock(spec=User)
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"
        user.email_verified = False
        user.email_verification_sent_at = None
        user.email_verification_token = None
        return user

    @pytest.fixture
    def email_service(self):
        """Create email verification service with mocked email sending"""
        with patch("auth_module.email_verification.EmailService") as mock_email_service:
            mock_email_service.return_value.send_verification_email = AsyncMock(return_value=True)
            service = EmailVerificationService()
            yield service

    @pytest.mark.asyncio
    async def test_verification_url_uses_frontend_url_env(self, mock_db, mock_user, email_service):
        """Test that verification URL uses FRONTEND_URL from environment"""

        # Set FRONTEND_URL environment variable
        test_frontend_url = "https://app.example.com"
        with patch.dict(os.environ, {"FRONTEND_URL": test_frontend_url}):
            # Patch the logging to avoid JSON serialization issues
            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email
                    result = await email_service.send_verification_email(db=mock_db, user=mock_user)

                    assert result is True

                    # Verify the verification link was created with correct URL
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    # Check that the verification_link argument contains the correct frontend URL
                    verification_link = call_args.kwargs["verification_link"]
                    assert verification_link.startswith(test_frontend_url)
                    assert "/verify-email/" in verification_link

    @pytest.mark.asyncio
    async def test_verification_url_defaults_to_localhost(self, mock_db, mock_user, email_service):
        """Test that verification URL defaults to localhost:3000 when FRONTEND_URL not set"""

        # Ensure FRONTEND_URL is not set
        with patch.dict(os.environ, {}, clear=True):
            # Remove FRONTEND_URL if it exists
            os.environ.pop("FRONTEND_URL", None)

            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email
                    result = await email_service.send_verification_email(db=mock_db, user=mock_user)

                    assert result is True

                    # Verify the verification link uses default localhost URL
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    verification_link = call_args.kwargs["verification_link"]
                    assert verification_link.startswith("http://localhost:3000")
                    assert "/verify-email/" in verification_link

    @pytest.mark.asyncio
    async def test_verification_url_for_docker_environment(self, mock_db, mock_user, email_service):
        """Test verification URL for Docker environment"""

        # Set FRONTEND_URL for Docker environment
        docker_frontend_url = "http://benger.localhost"
        with patch.dict(os.environ, {"FRONTEND_URL": docker_frontend_url}):
            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email
                    result = await email_service.send_verification_email(db=mock_db, user=mock_user)

                    assert result is True

                    # Verify the verification link uses Docker frontend URL
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    verification_link = call_args.kwargs["verification_link"]
                    assert verification_link.startswith(docker_frontend_url)
                    assert "/verify-email/" in verification_link

    @pytest.mark.asyncio
    async def test_verification_url_for_production(self, mock_db, mock_user, email_service):
        """Test verification URL for production environment"""

        # Set FRONTEND_URL for production
        production_url = "https://what-a-benger.net"
        with patch.dict(os.environ, {"FRONTEND_URL": production_url}):
            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email
                    result = await email_service.send_verification_email(db=mock_db, user=mock_user)

                    assert result is True

                    # Verify the verification link uses production URL
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    verification_link = call_args.kwargs["verification_link"]
                    assert verification_link.startswith(production_url)
                    assert "/verify-email/" in verification_link

    @pytest.mark.asyncio
    async def test_base_url_parameter_ignored(self, mock_db, mock_user, email_service):
        """Test that the deprecated base_url parameter is ignored"""

        # Set FRONTEND_URL
        expected_url = "https://app.example.com"
        with patch.dict(os.environ, {"FRONTEND_URL": expected_url}):
            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email with deprecated base_url parameter
                    result = await email_service.send_verification_email(
                        db=mock_db,
                        user=mock_user,
                        base_url="http://wrong-url.com",  # This should be ignored
                    )

                    assert result is True

                    # Verify the verification link still uses FRONTEND_URL, not base_url
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    verification_link = call_args.kwargs["verification_link"]
                    assert verification_link.startswith(expected_url)
                    assert "wrong-url.com" not in verification_link

    @pytest.mark.asyncio
    async def test_verification_token_included_in_url(self, mock_db, mock_user, email_service):
        """Test that verification token is properly included in the URL"""

        with patch.dict(os.environ, {"FRONTEND_URL": "https://app.example.com"}):
            with patch.object(email_service, "_log_email_event"):
                with patch.object(
                    email_service.email_service,
                    "send_verification_email",
                    new=AsyncMock(return_value=True),
                ) as mock_send:
                    # Send verification email
                    result = await email_service.send_verification_email(db=mock_db, user=mock_user)

                    assert result is True

                    # Verify token is in the URL
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    verification_link = call_args.kwargs["verification_link"]
                    # URL should be: https://app.example.com/verify-email/{token}
                    assert verification_link.startswith("https://app.example.com/verify-email/")

                    # Extract token from URL
                    token = verification_link.split("/verify-email/")[1]
                    assert len(token) > 0  # Token should not be empty

    @pytest.mark.asyncio
    async def test_rate_limiting_still_works(self, mock_db, mock_user, email_service):
        """Test that rate limiting still works with new URL generation"""

        # Set user as having recently sent verification email
        mock_user.email_verification_sent_at = datetime.now(timezone.utc)

        with patch.dict(os.environ, {"FRONTEND_URL": "https://app.example.com"}):
            # Attempt to send another email immediately
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await email_service.send_verification_email(db=mock_db, user=mock_user)

            assert exc_info.value.status_code == 429  # Too Many Requests
            assert "Please wait" in str(exc_info.value.detail)
