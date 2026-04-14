"""
Unit tests for uncovered lines in auth_module/email_verification.py.

Targets: detect_user_language, _auto_accept_invitations, _log_email_event,
_log_rate_limit_event, generate_verification_token, validate_verification_token,
mark_email_verified, can_send_verification_email, send_verification_email,
verify_email_with_token, resend_verification_email, get_verification_statistics,
cleanup_expired_tokens.
"""


from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Module-level logger initialization (lines 33-40)
# ---------------------------------------------------------------------------

class TestModuleInit:
    """Test that the module initializes correctly."""

    def test_import_module(self):
        """Importing the module should set up loggers."""
        import auth_module.email_verification as ev
        assert ev.email_monitoring_logger is not None
        assert ev.JWT_SECRET is not None
        assert ev.VERIFICATION_TOKEN_EXPIRE_HOURS == 48
        assert ev.RATE_LIMIT_MINUTES == 5


# ---------------------------------------------------------------------------
# detect_user_language (lines 60-70)
# ---------------------------------------------------------------------------

class TestDetectUserLanguage:
    """Test detect_user_language method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_user_has_language_preference(self):
        svc = self._make_service()
        user = Mock()
        user.language_preference = "de"

        with patch("auth_module.email_verification.LanguageDetector") as mock_detector:
            mock_detector.detect_from_user_profile.return_value = "de"
            result = svc.detect_user_language(user)
        assert result == "de"

    def test_user_no_preference_uses_headers(self):
        svc = self._make_service()
        user = Mock()
        user.language_preference = None

        headers = {"user-agent": "Mozilla/5.0", "accept-language": "de-DE,de;q=0.9"}
        with patch("auth_module.email_verification.LanguageDetector") as mock_detector:
            mock_detector.detect_from_request_headers.return_value = "de"
            result = svc.detect_user_language(user, request_headers=headers)
        assert result == "de"

    def test_no_preference_no_headers_defaults_to_en(self):
        svc = self._make_service()
        user = Mock()
        user.language_preference = None

        result = svc.detect_user_language(user, request_headers=None)
        assert result == "en"

    def test_no_language_preference_attribute(self):
        svc = self._make_service()
        user = Mock(spec=[])  # no attributes at all

        result = svc.detect_user_language(user, request_headers=None)
        assert result == "en"


# ---------------------------------------------------------------------------
# _log_email_event (lines 201-205, 208)
# ---------------------------------------------------------------------------

class TestLogEmailEvent:
    """Test _log_email_event method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_log_success_event(self):
        svc = self._make_service()
        with patch("auth_module.email_verification.email_monitoring_logger") as mock_logger:
            svc._log_email_event(
                event_type="test_event",
                user_id="user-1",
                email="test@test.com",
                success=True,
                metadata={"key": "value"},
            )
            mock_logger.info.assert_called_once()

    def test_log_failure_event(self):
        svc = self._make_service()
        with patch("auth_module.email_verification.email_monitoring_logger") as mock_logger:
            svc._log_email_event(
                event_type="test_event",
                user_id="user-1",
                email="test@test.com",
                success=False,
                error="Something went wrong",
            )
            mock_logger.error.assert_called_once()

    def test_log_event_with_error(self):
        svc = self._make_service()
        with patch("auth_module.email_verification.email_monitoring_logger") as mock_logger:
            svc._log_email_event(
                event_type="test_event",
                user_id="user-1",
                email="test@test.com",
                success=False,
                error="Error message",
                metadata={"extra": "data"},
            )
            call_args = mock_logger.error.call_args[0][0]
            assert "Error message" in call_args

    def test_log_event_without_metadata(self):
        svc = self._make_service()
        with patch("auth_module.email_verification.email_monitoring_logger") as mock_logger:
            svc._log_email_event(
                event_type="test_event",
                user_id="user-1",
                email="test@test.com",
                success=True,
            )
            mock_logger.info.assert_called_once()


# ---------------------------------------------------------------------------
# _log_rate_limit_event
# ---------------------------------------------------------------------------

class TestLogRateLimitEvent:
    """Test _log_rate_limit_event method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_logs_rate_limit(self):
        svc = self._make_service()
        with patch.object(svc, "_log_email_event") as mock_log:
            svc._log_rate_limit_event("user-1", "test@test.com", 3)
            mock_log.assert_called_once_with(
                event_type="rate_limited",
                user_id="user-1",
                email="test@test.com",
                success=False,
                error="Rate limited - 3 minutes remaining",
                metadata={"minutes_remaining": 3},
            )


# ---------------------------------------------------------------------------
# generate_verification_token (lines 264-272)
# ---------------------------------------------------------------------------

class TestGenerateVerificationToken:
    """Test generate_verification_token method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_generates_valid_token(self):
        svc = self._make_service()
        token = svc.generate_verification_token("user-1", "test@test.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_data(self):
        import jwt
        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        svc = self._make_service()
        token = svc.generate_verification_token("user-123", "test@example.com")

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["user_id"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["purpose"] == "email_verification"

    def test_token_generation_failure_logs_error(self):
        svc = self._make_service()
        with patch("auth_module.email_verification.jwt.encode", side_effect=Exception("encode error")):
            with pytest.raises(Exception, match="encode error"):
                svc.generate_verification_token("user-1", "test@test.com")


# ---------------------------------------------------------------------------
# validate_verification_token (lines 284-350)
# ---------------------------------------------------------------------------

class TestValidateVerificationToken:
    """Test validate_verification_token method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_valid_token(self):
        svc = self._make_service()
        token = svc.generate_verification_token("user-1", "test@test.com")
        result = svc.validate_verification_token(token)
        assert result is not None
        assert result == ("user-1", "test@test.com")

    def test_invalid_purpose(self):
        import jwt
        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        svc = self._make_service()
        payload = {
            "user_id": "user-1",
            "email": "test@test.com",
            "purpose": "password_reset",  # wrong purpose
            "exp": datetime.now(timezone.utc) + timedelta(hours=48),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        result = svc.validate_verification_token(token)
        assert result is None

    def test_missing_user_id(self):
        import jwt
        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        svc = self._make_service()
        payload = {
            "email": "test@test.com",
            "purpose": "email_verification",
            "exp": datetime.now(timezone.utc) + timedelta(hours=48),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        result = svc.validate_verification_token(token)
        assert result is None

    def test_missing_email(self):
        import jwt
        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        svc = self._make_service()
        payload = {
            "user_id": "user-1",
            "purpose": "email_verification",
            "exp": datetime.now(timezone.utc) + timedelta(hours=48),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        result = svc.validate_verification_token(token)
        assert result is None

    def test_expired_token(self):
        import jwt
        from auth_module.email_verification import JWT_ALGORITHM, JWT_SECRET

        svc = self._make_service()
        payload = {
            "user_id": "user-1",
            "email": "test@test.com",
            "purpose": "email_verification",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # expired
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        result = svc.validate_verification_token(token)
        assert result is None

    def test_invalid_token_string(self):
        svc = self._make_service()
        result = svc.validate_verification_token("totally.invalid.token")
        assert result is None

    def test_tampered_token(self):
        svc = self._make_service()
        token = svc.generate_verification_token("user-1", "test@test.com")
        # Tamper with the token
        result = svc.validate_verification_token(token + "tampered")
        assert result is None


# ---------------------------------------------------------------------------
# mark_email_verified (lines 371-428)
# ---------------------------------------------------------------------------

class TestMarkEmailVerified:
    """Test mark_email_verified method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_user_not_found(self):
        svc = self._make_service()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = svc.mark_email_verified(db, "nonexistent")
        assert result is False

    def test_success_self_verification(self):
        svc = self._make_service()
        db = MagicMock()
        user = MagicMock()
        user.email = "test@test.com"
        user.email_verified = False
        db.query.return_value.filter.return_value.first.return_value = user

        result = svc.mark_email_verified(db, "user-1")
        assert result is True
        assert user.email_verified is True
        assert user.email_verification_token is None
        assert user.email_verification_sent_at is None
        db.commit.assert_called_once()

    def test_admin_verification(self):
        svc = self._make_service()
        db = MagicMock()
        user = MagicMock()
        user.email = "test@test.com"
        user.email_verified = False
        db.query.return_value.filter.return_value.first.return_value = user

        result = svc.mark_email_verified(db, "user-1", verified_by_id="admin-1", method="admin")
        assert result is True
        assert user.email_verified_by_id == "admin-1"
        assert user.email_verification_method == "admin"

    def test_already_verified(self):
        svc = self._make_service()
        db = MagicMock()
        user = MagicMock()
        user.email = "test@test.com"
        user.email_verified = True
        db.query.return_value.filter.return_value.first.return_value = user

        result = svc.mark_email_verified(db, "user-1")
        # Should still succeed - it marks as verified regardless
        assert result is True

    def test_exception_rolls_back(self):
        svc = self._make_service()
        db = MagicMock()
        user = MagicMock()
        user.email = "test@test.com"
        user.email_verified = False
        db.query.return_value.filter.return_value.first.return_value = user
        db.commit.side_effect = Exception("DB error")

        result = svc.mark_email_verified(db, "user-1")
        assert result is False
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# can_send_verification_email
# ---------------------------------------------------------------------------

class TestCanSendVerificationEmail:
    """Test can_send_verification_email method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_no_previous_send(self):
        svc = self._make_service()
        user = Mock(email_verification_sent_at=None)
        assert svc.can_send_verification_email(user) is True

    def test_sent_recently_rate_limited(self):
        svc = self._make_service()
        user = Mock(email_verification_sent_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        assert svc.can_send_verification_email(user) is False

    def test_sent_long_ago_not_rate_limited(self):
        svc = self._make_service()
        user = Mock(email_verification_sent_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        assert svc.can_send_verification_email(user) is True


# ---------------------------------------------------------------------------
# send_verification_email (lines 537-571, async)
# ---------------------------------------------------------------------------

class TestSendVerificationEmail:
    """Test send_verification_email method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    @pytest.mark.asyncio
    async def test_rate_limited(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(
            id="user-1",
            email="test@test.com",
            name="Test",
            email_verification_sent_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.send_verification_email(db, user)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_success(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(
            id="user-1",
            email="test@test.com",
            name="Test",
            email_verification_sent_at=None,
        )
        svc.email_service.send_verification_email = AsyncMock(return_value=True)
        svc.email_service.config = Mock(provider="smtp")

        result = await svc.send_verification_email(db, user, language="de")
        assert result is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_service_returns_false(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(
            id="user-1",
            email="test@test.com",
            name="Test",
            email_verification_sent_at=None,
        )
        svc.email_service.send_verification_email = AsyncMock(return_value=False)
        svc.email_service.config = Mock(provider="smtp")

        result = await svc.send_verification_email(db, user)
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(
            id="user-1",
            email="test@test.com",
            name="Test",
            email_verification_sent_at=None,
        )
        svc.email_service.send_verification_email = AsyncMock(
            side_effect=RuntimeError("Network error")
        )

        result = await svc.send_verification_email(db, user)
        assert result is False
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# verify_email_with_token (lines 584-702)
# ---------------------------------------------------------------------------

class TestVerifyEmailWithToken:
    """Test verify_email_with_token method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_invalid_token(self):
        svc = self._make_service()
        db = MagicMock()

        success, message = svc.verify_email_with_token(db, "invalid.token.here")
        assert success is False
        assert "Invalid or expired" in message

    def test_user_not_found(self):
        svc = self._make_service()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        token = svc.generate_verification_token("user-1", "test@test.com")
        success, message = svc.verify_email_with_token(db, token)
        assert success is False
        assert "User not found" in message

    def test_email_mismatch(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="different@test.com", email_verified=False)
        db.query.return_value.filter.return_value.first.return_value = user

        token = svc.generate_verification_token("user-1", "test@test.com")
        success, message = svc.verify_email_with_token(db, token)
        assert success is False
        assert "Invalid verification token" in message

    def test_already_verified(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=True)
        db.query.return_value.filter.return_value.first.return_value = user

        token = svc.generate_verification_token("user-1", "test@test.com")
        success, message = svc.verify_email_with_token(db, token)
        assert success is True
        assert "already verified" in message

    def test_successful_verification(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=False)
        db.query.return_value.filter.return_value.first.return_value = user

        with patch.object(svc, "mark_email_verified", return_value=True):
            with patch.object(svc, "_auto_accept_invitations", return_value=[]):
                token = svc.generate_verification_token("user-1", "test@test.com")
                success, message = svc.verify_email_with_token(db, token)

        assert success is True
        assert "Email successfully verified" in message

    def test_successful_with_invitations(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=False)
        db.query.return_value.filter.return_value.first.return_value = user

        invitation_msgs = ["You've been added to Org1 as annotator."]
        with patch.object(svc, "mark_email_verified", return_value=True):
            with patch.object(svc, "_auto_accept_invitations", return_value=invitation_msgs):
                token = svc.generate_verification_token("user-1", "test@test.com")
                success, message = svc.verify_email_with_token(db, token)

        assert success is True
        assert "Org1" in message

    def test_invitation_acceptance_fails_silently(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=False)
        db.query.return_value.filter.return_value.first.return_value = user

        with patch.object(svc, "mark_email_verified", return_value=True):
            with patch.object(svc, "_auto_accept_invitations", side_effect=Exception("DB error")):
                token = svc.generate_verification_token("user-1", "test@test.com")
                success, message = svc.verify_email_with_token(db, token)

        assert success is True
        assert "Email successfully verified" in message

    def test_mark_verified_fails(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=False)
        db.query.return_value.filter.return_value.first.return_value = user

        with patch.object(svc, "mark_email_verified", return_value=False):
            token = svc.generate_verification_token("user-1", "test@test.com")
            success, message = svc.verify_email_with_token(db, token)

        assert success is False
        assert "Failed to verify email" in message


# ---------------------------------------------------------------------------
# resend_verification_email (lines 720-736)
# ---------------------------------------------------------------------------

class TestResendVerificationEmail:
    """Test resend_verification_email method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    @pytest.mark.asyncio
    async def test_already_verified(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(id="user-1", email="test@test.com", email_verified=True)

        result = await svc.resend_verification_email(db, user, "http://localhost")
        assert result == (False, "Email already verified")

    @pytest.mark.asyncio
    async def test_sends_verification(self):
        svc = self._make_service()
        db = MagicMock()
        user = Mock(
            id="user-1",
            email="test@test.com",
            name="Test",
            email_verified=False,
            email_verification_sent_at=None,
        )
        svc.email_service.send_verification_email = AsyncMock(return_value=True)
        svc.email_service.config = Mock(provider="smtp")

        result = await svc.resend_verification_email(db, user, "http://localhost", language="de")
        assert result is True


# ---------------------------------------------------------------------------
# get_verification_statistics (lines 749-805)
# ---------------------------------------------------------------------------

class TestGetVerificationStatistics:
    """Test get_verification_statistics method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_returns_stats(self):
        svc = self._make_service()
        db = MagicMock()

        # Mock the count queries
        db.query.return_value.filter.return_value.count.return_value = 5
        db.query.return_value.count.return_value = 100

        stats = svc.get_verification_statistics(db, days=7)

        assert "total_users" in stats
        assert "verified_users" in stats
        assert "unverified_users" in stats
        assert "verification_rate_percent" in stats
        assert "recent_unverified" in stats
        assert "pending_verification" in stats
        assert "expired_tokens" in stats
        assert stats["total_users"] == 100
        assert stats["unverified_users"] == 5

    def test_zero_users(self):
        svc = self._make_service()
        db = MagicMock()

        db.query.return_value.filter.return_value.count.return_value = 0
        db.query.return_value.count.return_value = 0

        stats = svc.get_verification_statistics(db, days=7)
        assert stats["verification_rate_percent"] == 0
        assert stats["total_users"] == 0


# ---------------------------------------------------------------------------
# cleanup_expired_tokens (lines 817-869)
# ---------------------------------------------------------------------------

class TestCleanupExpiredTokens:
    """Test cleanup_expired_tokens method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_no_expired_tokens(self):
        svc = self._make_service()
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        count = svc.cleanup_expired_tokens(db)
        assert count == 0
        db.commit.assert_called_once()

    def test_cleans_expired_tokens(self):
        svc = self._make_service()
        db = MagicMock()

        expired_user1 = MagicMock()
        expired_user2 = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [expired_user1, expired_user2]

        count = svc.cleanup_expired_tokens(db)
        assert count == 2
        assert expired_user1.email_verification_token is None
        assert expired_user1.email_verification_sent_at is None
        assert expired_user2.email_verification_token is None
        assert expired_user2.email_verification_sent_at is None
        db.commit.assert_called_once()

    def test_exception_rolls_back(self):
        svc = self._make_service()
        db = MagicMock()
        db.query.return_value.filter.return_value.all.side_effect = Exception("DB error")

        count = svc.cleanup_expired_tokens(db)
        assert count == 0
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _auto_accept_invitations (lines 84-170)
# ---------------------------------------------------------------------------

class TestAutoAcceptInvitations:
    """Test _auto_accept_invitations method."""

    def _make_service(self):
        with patch("auth_module.email_verification.EmailService"):
            from auth_module.email_verification import EmailVerificationService
            return EmailVerificationService()

    def test_no_pending_invitations(self):
        svc = self._make_service()
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.all.return_value = []

        messages = svc._auto_accept_invitations(db, "user-1", "test@test.com")
        assert messages == []

    def test_existing_membership_marks_accepted(self):
        svc = self._make_service()
        db = MagicMock()

        invitation = MagicMock()
        invitation.organization_id = "org-1"
        invitation.role = MagicMock(value="annotator")
        invitation.id = "inv-1"
        organization = MagicMock()
        organization.name = "Test Org"

        # Return one pending invitation
        db.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (invitation, organization)
        ]

        # Simulate existing membership
        inner_query = MagicMock()
        inner_query.filter.return_value.first.return_value = MagicMock()  # existing membership
        db.query.return_value = inner_query

        messages = svc._auto_accept_invitations(db, "user-1", "test@test.com")
        # If user already has membership, invitation is accepted silently
        assert len(messages) == 0

    def test_creates_membership_for_new_invitation(self):
        svc = self._make_service()
        db = MagicMock()

        invitation = MagicMock()
        invitation.organization_id = "org-1"
        invitation.role = MagicMock(value="annotator")
        invitation.id = "inv-1"
        organization = MagicMock()
        organization.name = "Test Org"

        # Use a flag to track query calls
        call_idx = [0]

        def mock_query(*args):
            result = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                # First query: pending invitations
                result.join.return_value.filter.return_value.all.return_value = [
                    (invitation, organization)
                ]
            else:
                # Subsequent queries: no existing membership
                result.filter.return_value.first.return_value = None
            return result

        db.query = mock_query

        messages = svc._auto_accept_invitations(db, "user-1", "test@test.com")
        assert len(messages) == 1
        assert "Test Org" in messages[0]

    def test_exception_during_acceptance_continues(self):
        svc = self._make_service()
        db = MagicMock()

        invitation = MagicMock()
        invitation.organization_id = "org-1"
        invitation.role = MagicMock(value="annotator")
        invitation.id = "inv-1"
        organization = MagicMock()
        organization.name = "Test Org"

        call_idx = [0]

        def mock_query(*args):
            result = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                result.join.return_value.filter.return_value.all.return_value = [
                    (invitation, organization)
                ]
            else:
                # Simulate exception
                result.filter.side_effect = Exception("DB error")
            return result

        db.query = mock_query

        # Should not raise, but return empty messages
        messages = svc._auto_accept_invitations(db, "user-1", "test@test.com")
        assert messages == []
