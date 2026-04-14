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
            base_url: Base URL for reset link
            language: Language for email template

        Returns:
            True if email was sent successfully, False otherwise
        """
        import os

        from app.email_service import EmailService

        # Generate reset token
        token = self.create_password_reset_token(db, user)

        # Use FRONTEND_URL from environment
        frontend_url = os.getenv("FRONTEND_URL", base_url)
        reset_link = f"{frontend_url}/reset-password/{token}"

        # Prepare email content
        if language == "de":
            subject = "Passwort zurücksetzen - BenGER"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Passwort zurücksetzen</h2>
                <p>Hallo {user.name or user.username},</p>
                <p>Sie haben eine Anfrage zum Zurücksetzen Ihres Passworts gestellt.</p>
                <p>Klicken Sie auf den folgenden Link, um Ihr Passwort zurückzusetzen:</p>
                <div style="margin: 30px 0;">
                    <a href="{reset_link}" 
                       style="background-color: #10b981; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 6px; display: inline-block;">
                        Passwort zurücksetzen
                    </a>
                </div>
                <p>Oder kopieren Sie diesen Link in Ihren Browser:</p>
                <p style="word-break: break-all; color: #6b7280;">{reset_link}</p>
                <p>Dieser Link ist 24 Stunden gültig.</p>
                <p>Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.</p>
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #e5e7eb;">
                <p style="color: #6b7280; font-size: 14px;">
                    BenGER - Benchmark for German Legal Reasoning
                </p>
            </div>
            """
        else:
            subject = "Reset Your Password - BenGER"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Reset Your Password</h2>
                <p>Hello {user.name or user.username},</p>
                <p>You have requested to reset your password.</p>
                <p>Click the following link to reset your password:</p>
                <div style="margin: 30px 0;">
                    <a href="{reset_link}" 
                       style="background-color: #10b981; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 6px; display: inline-block;">
                        Reset Password
                    </a>
                </div>
                <p>Or copy this link to your browser:</p>
                <p style="word-break: break-all; color: #6b7280;">{reset_link}</p>
                <p>This link will expire in 24 hours.</p>
                <p>If you didn't request this, you can safely ignore this email.</p>
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #e5e7eb;">
                <p style="color: #6b7280; font-size: 14px;">
                    BenGER - Benchmark for German Legal Reasoning
                </p>
            </div>
            """

        # Send email
        email_service = EmailService()
        success = await email_service.send_email(
            to_email=user.email, subject=subject, html_body=html_body
        )

        return success


# Create a singleton instance
password_reset_service = PasswordResetService()
