"""
Password reset service for handling password reset requests and token validation
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from auth_module.user_service import get_password_hash
from models import User


class PasswordResetService:
    """Service for handling password reset functionality"""

    TOKEN_EXPIRY_HOURS = 24  # Password reset tokens expire after 24 hours

    def __init__(self):
        pass

    def generate_reset_token(self) -> str:
        """Generate a secure random reset token"""
        return secrets.token_urlsafe(32)

    def create_password_reset_token(self, db: Session, user: User) -> str:
        """
        Create a password reset token for a user

        Args:
            db: Database session
            user: User requesting password reset

        Returns:
            Reset token string
        """
        token = self.generate_reset_token()
        expiry = datetime.now(timezone.utc) + timedelta(hours=self.TOKEN_EXPIRY_HOURS)

        # Store token in user record (you may want to create a separate table for this)
        user.password_reset_token = token
        user.password_reset_expires = expiry
        db.commit()

        return token

    def validate_reset_token(self, db: Session, token: str) -> Optional[User]:
        """
        Validate a password reset token and return the associated user

        Args:
            db: Database session
            token: Reset token to validate

        Returns:
            User if token is valid, None otherwise
        """
        user = (
            db.query(User)
            .filter(
                and_(
                    User.password_reset_token == token,
                    User.password_reset_expires > datetime.now(timezone.utc),
                )
            )
            .first()
        )

        return user

    def reset_password(self, db: Session, token: str, new_password: str) -> bool:
        """
        Reset a user's password using a valid reset token

        Args:
            db: Database session
            token: Reset token
            new_password: New password to set

        Returns:
            True if password was reset successfully, False otherwise
        """
        user = self.validate_reset_token(db, token)
        if not user:
            return False

        # Update password
        user.hashed_password = get_password_hash(new_password)

        # Clear reset token
        user.password_reset_token = None
        user.password_reset_expires = None

        db.commit()
        return True

    def clear_expired_tokens(self, db: Session) -> int:
        """
        Clear expired password reset tokens from the database

        Args:
            db: Database session

        Returns:
            Number of tokens cleared
        """
        expired_users = (
            db.query(User)
            .filter(
                and_(
                    User.password_reset_token.isnot(None),
                    User.password_reset_expires < datetime.now(timezone.utc),
                )
            )
            .all()
        )

        for user in expired_users:
            user.password_reset_token = None
            user.password_reset_expires = None

        db.commit()
        return len(expired_users)

    async def send_password_reset_email(
        self, db: Session, user: User, base_url: str, language: str = "en"
    ) -> bool:
        """
        Send password reset email to user

        Args:
            db: Database session
            user: User to send email to
            base_url: Base URL for reset link (used as fallback if FRONTEND_URL is unset)
            language: Language for email template

        Returns:
            True if email was sent successfully, False otherwise
        """
        import os

        from email_service import EmailService

        token = self.create_password_reset_token(db, user)

        frontend_url = os.getenv("FRONTEND_URL", base_url)
        reset_link = f"{frontend_url}/reset-password/{token}"

        email_service = EmailService()
        return await email_service.send_password_reset_email(
            to_email=user.email,
            user_name=user.name or user.username,
            reset_link=reset_link,
            language=language,
        )


# Create a singleton instance
password_reset_service = PasswordResetService()
