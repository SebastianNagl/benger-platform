"""
Email verification module for user registration
Handles token generation, validation, and email sending with comprehensive monitoring
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from email_service import EmailService
from localization import LanguageDetector
from models import User

logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "your-secret-key-here")
JWT_ALGORITHM = "HS256"
VERIFICATION_TOKEN_EXPIRE_HOURS = 48
RATE_LIMIT_MINUTES = 5  # Minimum time between verification email sends

# Email delivery monitoring logger
email_monitoring_logger = logging.getLogger("email_verification_monitoring")
email_monitoring_logger.setLevel(logging.INFO)

# Create handler if not exists
if not email_monitoring_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    email_monitoring_logger.addHandler(handler)


class EmailVerificationService:
    """Service for handling email verification workflow with comprehensive monitoring"""

    def __init__(self):
        self.email_service = EmailService()

    def detect_user_language(
        self, user: User, request_headers: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Detect user's preferred language for email localization

        Args:
            user: User object
            request_headers: Optional HTTP request headers

        Returns:
            Language code (en or de)
        """
        # 1. Check if user has language preference stored
        if hasattr(user, "language_preference") and user.language_preference:
            return LanguageDetector.detect_from_user_profile(user.language_preference)

        # 2. Check request headers if available
        if request_headers:
            user_agent = request_headers.get("user-agent", "")
            accept_language = request_headers.get("accept-language", "")
            return LanguageDetector.detect_from_request_headers(user_agent, accept_language)

        # 3. Default to English
        return "en"

    def _auto_accept_invitations(self, db: Session, user_id: str, user_email: str) -> List[str]:
        """
        Automatically accept any pending invitations for the user

        Args:
            db: Database session
            user_id: User ID
            user_email: User's email address

        Returns:
            List of success messages for accepted invitations
        """
        from uuid import uuid4

        from models import Invitation, Organization, OrganizationMembership

        messages = []

        # Find pending invitations for this user (by email or pending_user_id)
        pending_invitations = (
            db.query(Invitation, Organization)
            .join(Organization, Invitation.organization_id == Organization.id)
            .filter(
                ((Invitation.email == user_email) | (Invitation.pending_user_id == user_id)),
                Invitation.accepted == False,
                Invitation.expires_at > datetime.now(timezone.utc),
            )
            .all()
        )

        for invitation, organization in pending_invitations:
            try:
                # Check if user is already a member of this organization
                existing_membership = (
                    db.query(OrganizationMembership)
                    .filter(
                        OrganizationMembership.user_id == user_id,
                        OrganizationMembership.organization_id == invitation.organization_id,
                        OrganizationMembership.is_active == True,
                    )
                    .first()
                )

                if existing_membership:
                    # User is already a member, just mark invitation as accepted
                    invitation.accepted = True
                    invitation.accepted_at = datetime.now(timezone.utc)
                    continue

                # Create organization membership
                membership = OrganizationMembership(
                    id=str(uuid4()),
                    user_id=user_id,
                    organization_id=invitation.organization_id,
                    role=invitation.role,
                    is_active=True,
                )

                # Mark invitation as accepted
                invitation.is_accepted = True
                invitation.accepted_at = datetime.now(timezone.utc)
                invitation.pending_user_id = user_id  # Ensure link is maintained

                db.add(membership)

                # Log successful invitation acceptance
                self._log_email_event(
                    event_type="invitation_auto_accepted",
                    user_id=user_id,
                    email=user_email,
                    success=True,
                    metadata={
                        "organization_id": invitation.organization_id,
                        "organization_name": organization.name,
                        "role": invitation.role.value,
                        "invitation_id": invitation.id,
                    },
                )

                messages.append(
                    f"You've been added to {organization.name} as {invitation.role.value}."
                )
                logger.info(
                    f"Auto-accepted invitation for user {user_id} to join {organization.name}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to auto-accept invitation {invitation.id} for user {user_id}: {e}"
                )
                # Don't fail the whole process if one invitation fails
                continue

        # Commit all changes
        if messages:
            db.commit()
            logger.info(f"Auto-accepted {len(messages)} invitations for user {user_id}")

        return messages

    def _log_email_event(
        self,
        event_type: str,
        user_id: str,
        email: str,
        success: bool = True,
        error: str = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Log email verification events for monitoring and analytics

        Args:
            event_type: Type of event (token_generated, email_sent, token_validated, etc.)
            user_id: User ID
            email: Email address
            success: Whether the operation was successful
            error: Error message if failed
            metadata: Additional metadata to log
        """
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "email": email,
            "success": success,
            "metadata": metadata or {},
        }

        if error:
            log_data["error"] = error

        # Log as structured JSON for easy parsing
        log_message = json.dumps(log_data)

        if success:
            email_monitoring_logger.info(log_message)
        else:
            email_monitoring_logger.error(log_message)

    def _log_rate_limit_event(self, user_id: str, email: str, minutes_remaining: int) -> None:
        """Log rate limiting events"""
        self._log_email_event(
            event_type="rate_limited",
            user_id=user_id,
            email=email,
            success=False,
            error=f"Rate limited - {minutes_remaining} minutes remaining",
            metadata={"minutes_remaining": minutes_remaining},
        )

    def generate_verification_token(self, user_id: str, email: str) -> str:
        """
        Generate a JWT token for email verification

        Args:
            user_id: The user's ID
            email: The email address to verify

        Returns:
            JWT token string
        """
        try:
            expiration = datetime.now(timezone.utc) + timedelta(
                hours=VERIFICATION_TOKEN_EXPIRE_HOURS
            )

            payload = {
                "user_id": user_id,
                "email": email,
                "purpose": "email_verification",
                "exp": expiration,
                "iat": datetime.now(timezone.utc),
            }

            token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            # Log successful token generation
            self._log_email_event(
                event_type="token_generated",
                user_id=user_id,
                email=email,
                success=True,
                metadata={
                    "token_expiration_hours": VERIFICATION_TOKEN_EXPIRE_HOURS,
                    "expiration_time": expiration.isoformat(),
                },
            )

            logger.info(f"Generated verification token for user {user_id}")
            return token

        except Exception as e:
            self._log_email_event(
                event_type="token_generated",
                user_id=user_id,
                email=email,
                success=False,
                error=str(e),
            )
            raise

    def validate_verification_token(self, token: str) -> Optional[Tuple[str, str]]:
        """
        Validate a verification token and extract user information

        Args:
            token: JWT token to validate

        Returns:
            Tuple of (user_id, email) if valid, None otherwise
        """
        user_id = None
        email = None

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

            # Verify this is an email verification token
            if payload.get("purpose") != "email_verification":
                logger.warning(f"Invalid token purpose: {payload.get('purpose')}")
                self._log_email_event(
                    event_type="token_validation_failed",
                    user_id="unknown",
                    email="unknown",
                    success=False,
                    error="Invalid token purpose",
                )
                return None

            user_id = payload.get("user_id")
            email = payload.get("email")

            if not user_id or not email:
                logger.warning("Token missing required fields")
                self._log_email_event(
                    event_type="token_validation_failed",
                    user_id=user_id or "unknown",
                    email=email or "unknown",
                    success=False,
                    error="Token missing required fields",
                )
                return None

            # Log successful validation
            self._log_email_event(
                event_type="token_validated",
                user_id=user_id,
                email=email,
                success=True,
                metadata={
                    "token_issued_at": payload.get("iat"),
                    "token_expires_at": payload.get("exp"),
                },
            )

            logger.info(f"Successfully validated token for user {user_id}")
            return (user_id, email)

        except jwt.ExpiredSignatureError:
            logger.info("Verification token has expired")
            self._log_email_event(
                event_type="token_validation_failed",
                user_id=user_id or "unknown",
                email=email or "unknown",
                success=False,
                error="Token expired",
            )
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid verification token: {e}")
            self._log_email_event(
                event_type="token_validation_failed",
                user_id=user_id or "unknown",
                email=email or "unknown",
                success=False,
                error=f"Invalid token: {str(e)}",
            )
            return None

    def mark_email_verified(
        self,
        db: Session,
        user_id: str,
        verified_by_id: Optional[str] = None,
        method: str = "self",
    ) -> bool:
        """
        Mark a user's email as verified

        Args:
            db: Database session
            user_id: User ID to mark as verified
            verified_by_id: Optional ID of user who verified (for admin verification)
            method: Verification method ('self', 'admin', 'system')

        Returns:
            True if successful, False otherwise
        """
        from datetime import datetime, timezone

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User {user_id} not found")
                self._log_email_event(
                    event_type="email_verification_failed",
                    user_id=user_id,
                    email="unknown",
                    success=False,
                    error="User not found",
                )
                return False

            # Track previous verification status for logging
            was_already_verified = user.email_verified

            user.email_verified = True
            user.email_verification_token = None  # Clear the token
            user.email_verification_sent_at = None  # Clear the sent timestamp

            # Set new fields for tracking verification
            user.email_verified_at = datetime.now(timezone.utc)
            user.email_verification_method = method
            if verified_by_id:
                user.email_verified_by_id = verified_by_id

            db.commit()

            # Log the verification event
            self._log_email_event(
                event_type="email_verified",
                user_id=user_id,
                email=user.email,
                success=True,
                metadata={
                    "was_already_verified": was_already_verified,
                    "verification_completed_at": datetime.now(timezone.utc).isoformat(),
                    "verification_method": method,
                    "verified_by": verified_by_id,
                },
            )

            logger.info(f"Email verified for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error marking email as verified: {e}")
            self._log_email_event(
                event_type="email_verification_failed",
                user_id=user_id,
                email="unknown",
                success=False,
                error=str(e),
            )
            db.rollback()
            return False

    def can_send_verification_email(self, user: User) -> bool:
        """
        Check if we can send a verification email (rate limiting)

        Args:
            user: User object

        Returns:
            True if we can send, False if rate limited
        """
        if not user.email_verification_sent_at:
            return True

        time_since_last = datetime.now(timezone.utc) - user.email_verification_sent_at.replace(
            tzinfo=timezone.utc
        )
        return time_since_last.total_seconds() >= (RATE_LIMIT_MINUTES * 60)

    async def send_verification_email(
        self, db: Session, user: User, base_url: str = None, language: str = "en"
    ) -> bool:
        """
        Send verification email to user with comprehensive monitoring

        Args:
            db: Database session
            user: User object
            base_url: Base URL for verification link (deprecated, will use FRONTEND_URL)
            language: Language code for email localization (en, de)

        Returns:
            True if email sent successfully
        """
        email_send_start_time = datetime.now(timezone.utc)

        try:
            # Check rate limiting
            if not self.can_send_verification_email(user):
                minutes_left = RATE_LIMIT_MINUTES - int(
                    (
                        datetime.now(timezone.utc)
                        - user.email_verification_sent_at.replace(tzinfo=timezone.utc)
                    ).total_seconds()
                    / 60
                )

                # Log rate limit hit
                self._log_rate_limit_event(user.id, user.email, minutes_left)

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {minutes_left} minutes before requesting another verification email",
                )

            # Generate token
            token = self.generate_verification_token(user.id, user.email)

            # Store token and timestamp in database
            user.email_verification_token = token
            user.email_verification_sent_at = datetime.now(timezone.utc)
            db.commit()

            # Create verification link using FRONTEND_URL environment variable
            # This ensures the link always points to the correct frontend, regardless of how the API is accessed
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            verification_link = f"{frontend_url}/verify-email/{token}"

            # Log email send attempt
            self._log_email_event(
                event_type="email_send_attempt",
                user_id=user.id,
                email=user.email,
                success=True,
                metadata={
                    "frontend_url": frontend_url,
                    "attempt_time": email_send_start_time.isoformat(),
                },
            )

            # Send email with language support
            success = await self.email_service.send_verification_email(
                to_email=user.email,
                user_name=user.name,
                verification_link=verification_link,
                language=language,
            )

            # Calculate send duration
            send_duration = (datetime.now(timezone.utc) - email_send_start_time).total_seconds()

            # Log email send result
            if success:
                self._log_email_event(
                    event_type="email_sent",
                    user_id=user.id,
                    email=user.email,
                    success=True,
                    metadata={
                        "send_duration_seconds": send_duration,
                        "email_service_provider": getattr(
                            self.email_service.config, "provider", "unknown"
                        ),
                        "verification_link_created": True,
                    },
                )
                logger.info(f"Verification email sent to {user.email}")
            else:
                self._log_email_event(
                    event_type="email_send_failed",
                    user_id=user.id,
                    email=user.email,
                    success=False,
                    error="Email service returned failure",
                    metadata={
                        "send_duration_seconds": send_duration,
                        "email_service_provider": getattr(
                            self.email_service.config, "provider", "unknown"
                        ),
                    },
                )
                logger.error(f"Failed to send verification email to {user.email}")

            return success

        except HTTPException:
            raise
        except Exception as e:
            send_duration = (datetime.now(timezone.utc) - email_send_start_time).total_seconds()
            self._log_email_event(
                event_type="email_send_error",
                user_id=user.id,
                email=user.email,
                success=False,
                error=str(e),
                metadata={
                    "send_duration_seconds": send_duration,
                    "exception_type": type(e).__name__,
                },
            )
            logger.error(f"Error sending verification email: {e}")
            db.rollback()
            return False

    def verify_email_with_token(self, db: Session, token: str) -> Tuple[bool, str]:
        """
        Verify email using the provided token with comprehensive monitoring

        Args:
            db: Database session
            token: Verification token

        Returns:
            Tuple of (success, message)
        """
        verification_start_time = datetime.now(timezone.utc)

        # Validate token
        token_data = self.validate_verification_token(token)
        if not token_data:
            self._log_email_event(
                event_type="verification_attempt_failed",
                user_id="unknown",
                email="unknown",
                success=False,
                error="Invalid or expired verification token",
                metadata={
                    "verification_duration_seconds": (
                        datetime.now(timezone.utc) - verification_start_time
                    ).total_seconds()
                },
            )
            return (False, "Invalid or expired verification token")

        user_id, email = token_data

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            self._log_email_event(
                event_type="verification_attempt_failed",
                user_id=user_id,
                email=email,
                success=False,
                error="User not found",
                metadata={
                    "verification_duration_seconds": (
                        datetime.now(timezone.utc) - verification_start_time
                    ).total_seconds()
                },
            )
            return (False, "User not found")

        # Check if email matches
        if user.email != email:
            logger.warning(f"Email mismatch for user {user_id}: {user.email} != {email}")
            self._log_email_event(
                event_type="verification_attempt_failed",
                user_id=user_id,
                email=email,
                success=False,
                error="Email mismatch between token and user",
                metadata={
                    "user_current_email": user.email,
                    "token_email": email,
                    "verification_duration_seconds": (
                        datetime.now(timezone.utc) - verification_start_time
                    ).total_seconds(),
                },
            )
            return (False, "Invalid verification token")

        # Check if already verified
        if user.email_verified:
            self._log_email_event(
                event_type="verification_attempt_already_verified",
                user_id=user_id,
                email=email,
                success=True,
                metadata={
                    "verification_duration_seconds": (
                        datetime.now(timezone.utc) - verification_start_time
                    ).total_seconds()
                },
            )
            return (True, "Email already verified")

        # Mark as verified
        if self.mark_email_verified(db, user_id):
            verification_duration = (
                datetime.now(timezone.utc) - verification_start_time
            ).total_seconds()

            # Check if user has any pending invitations and auto-accept them
            invitation_messages = []
            try:
                invitation_messages = self._auto_accept_invitations(db, user_id, email)
            except Exception as e:
                logger.error(f"Error auto-accepting invitations for user {user_id}: {e}")
                # Don't fail verification if invitation acceptance fails

            self._log_email_event(
                event_type="verification_completed",
                user_id=user_id,
                email=email,
                success=True,
                metadata={
                    "verification_duration_seconds": verification_duration,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "auto_accepted_invitations": len(invitation_messages),
                },
            )

            # Build success message
            base_message = "Email successfully verified"
            if invitation_messages:
                full_message = f"{base_message}. {' '.join(invitation_messages)}"
                return (True, full_message)
            else:
                return (True, base_message)
        else:
            self._log_email_event(
                event_type="verification_attempt_failed",
                user_id=user_id,
                email=email,
                success=False,
                error="Database update failed",
                metadata={
                    "verification_duration_seconds": (
                        datetime.now(timezone.utc) - verification_start_time
                    ).total_seconds()
                },
            )
            return (False, "Failed to verify email")

    async def resend_verification_email(
        self, db: Session, user: User, base_url: str, language: str = "en"
    ):
        """
        Resend verification email with rate limiting

        Args:
            db: Database session
            user: User object
            base_url: Base URL for verification link
            language: Language code for email localization (en, de)

        Returns:
            Success status and message
        """
        # Check if already verified
        if user.email_verified:
            self._log_email_event(
                event_type="resend_attempt_already_verified",
                user_id=user.id,
                email=user.email,
                success=False,
                error="User already verified",
            )
            return (False, "Email already verified")

        # Log resend attempt
        self._log_email_event(
            event_type="resend_attempt", user_id=user.id, email=user.email, success=True
        )

        # Send verification email (includes rate limit check)
        return await self.send_verification_email(db, user, base_url, language)

    def get_verification_statistics(self, db: Session, days: int = 7) -> Dict[str, Any]:
        """
        Get email verification statistics for monitoring dashboard

        Args:
            db: Database session
            days: Number of days to look back

        Returns:
            Dictionary with verification statistics
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Count unverified users
        unverified_count = db.query(User).filter(User.email_verified == False).count()

        # Count recently created unverified users
        recent_unverified = (
            db.query(User)
            .filter(User.email_verified == False, User.created_at >= cutoff_date)
            .count()
        )

        # Count users with pending verification emails
        pending_verification = (
            db.query(User)
            .filter(User.email_verification_token.isnot(None), User.email_verified == False)
            .count()
        )

        # Count users with expired verification tokens (over 48 hours)
        expired_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        expired_tokens = (
            db.query(User)
            .filter(
                User.email_verification_sent_at <= expired_cutoff,
                User.email_verified == False,
                User.email_verification_token.isnot(None),
            )
            .count()
        )

        total_users = db.query(User).count()
        verified_users = total_users - unverified_count
        verification_rate = (verified_users / total_users * 100) if total_users > 0 else 0

        stats = {
            "period_days": days,
            "total_users": total_users,
            "verified_users": verified_users,
            "unverified_users": unverified_count,
            "verification_rate_percent": round(verification_rate, 2),
            "recent_unverified": recent_unverified,
            "pending_verification": pending_verification,
            "expired_tokens": expired_tokens,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Log statistics request
        self._log_email_event(
            event_type="statistics_requested",
            user_id="system",
            email="system",
            success=True,
            metadata=stats,
        )

        return stats

    def cleanup_expired_tokens(self, db: Session) -> int:
        """
        Clean up expired verification tokens to maintain database health

        Args:
            db: Database session

        Returns:
            Number of tokens cleaned up
        """
        try:
            # Calculate expiration cutoff (48 hours ago)
            expiration_cutoff = datetime.now(timezone.utc) - timedelta(
                hours=VERIFICATION_TOKEN_EXPIRE_HOURS
            )

            # Find expired tokens
            expired_users = (
                db.query(User)
                .filter(
                    User.email_verification_sent_at <= expiration_cutoff,
                    User.email_verification_token.isnot(None),
                    User.email_verified == False,
                )
                .all()
            )

            cleanup_count = len(expired_users)

            # Clear expired tokens
            for user in expired_users:
                user.email_verification_token = None
                user.email_verification_sent_at = None

            db.commit()

            # Log cleanup operation
            self._log_email_event(
                event_type="token_cleanup",
                user_id="system",
                email="system",
                success=True,
                metadata={
                    "tokens_cleaned": cleanup_count,
                    "expiration_hours": VERIFICATION_TOKEN_EXPIRE_HOURS,
                    "cleanup_completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info(f"Cleaned up {cleanup_count} expired verification tokens")
            return cleanup_count

        except Exception as e:
            self._log_email_event(
                event_type="token_cleanup_failed",
                user_id="system",
                email="system",
                success=False,
                error=str(e),
            )
            logger.error(f"Failed to cleanup expired tokens: {e}")
            db.rollback()
            return 0


# Create singleton instance
email_verification_service = EmailVerificationService()
