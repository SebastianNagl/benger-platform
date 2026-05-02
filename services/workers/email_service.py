"""
Email Service for BenGER — SendGrid integration (workers).

Outbound mail goes through the SendGrid HTTP API. Templates load from the
local templates/email directory and render via Jinja2.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from models import Notification, NotificationType
from sendgrid_client import SendGridClient

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SendGrid (workers)."""

    def __init__(self):
        """Initialize the email service."""
        self.from_email = os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "BenGER Platform")

        self.mail_enabled = True

        # Initialize SendGrid client for email delivery
        self.mail_client = SendGridClient()

        # Initialize template environment
        self.template_env = self._init_template_environment()

    def _init_template_environment(self) -> Environment:
        """Initialize Jinja2 template environment for email templates"""
        template_dir = Path(__file__).parent / "templates" / "email"

        if not template_dir.exists():
            logger.warning(f"Template directory not found: {template_dir}")
            template_dir.mkdir(parents=True, exist_ok=True)

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Add custom filters if needed
        env.filters["format_date"] = lambda dt: dt.strftime("%B %d, %Y") if dt else ""

        return env

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> tuple[str, str]:
        """
        Render an email template

        Args:
            template_name: Name of the template file
            context: Context variables for the template

        Returns:
            Tuple of (subject, html_body)
        """
        try:
            template = self.template_env.get_template(template_name)
            rendered = template.render(**context)

            # Extract subject from first line if present
            lines = rendered.split('\n', 1)
            if len(lines) > 1 and lines[0].startswith('Subject:'):
                subject = lines[0].replace('Subject:', '').strip()
                html_body = lines[1].strip()
            else:
                subject = "BenGER Notification"
                html_body = rendered

            return subject, html_body

        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {str(e)}")
            # Return fallback content
            return (
                "BenGER Notification",
                f"<p>{context.get('message', 'Notification from BenGER')}</p>",
            )

    async def test_connection(self) -> bool:
        """
        Test connection to mail server

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            return await self.mail_client.test_connection()
        except Exception as e:
            logger.error(f"Mail server connection test failed: {str(e)}")
            return False

    async def send_notification_email(
        self,
        user_email: str,
        notification: Notification,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send a notification email to a user

        Args:
            user_email: Recipient email address
            notification: Notification object
            context: Additional context for the email template

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        # Build template context
        template_context = {
            "notification": notification,
            "notification_type": notification.type.value if notification.type else "general",
            "user_email": user_email,
            **(context or {}),
        }

        # Select template based on notification type
        template_map = {
            NotificationType.TASK_CREATED: "task_assigned.html",
            NotificationType.TASK_COMPLETED: "task_completed.html",
            NotificationType.ANNOTATION_COMPLETED: "annotation_completed.html",
            NotificationType.ORGANIZATION_INVITATION_SENT: "organization_invite.html",
            NotificationType.DATA_UPLOAD_COMPLETED: "data_import_success.html",
            NotificationType.EVALUATION_COMPLETED: "evaluation_completed.html",
            NotificationType.LLM_GENERATION_COMPLETED: "llm_generation_completed.html",
        }

        template_name = template_map.get(notification.type, "default_notification.html")

        try:
            # Render template
            subject, html_body = self._render_template(template_name, template_context)

            # Send email
            result = self.mail_client.send_message(
                to=[user_email], subject=subject, html_body=html_body
            )

            if result.get("status") == "success":
                logger.info(f"Notification email sent to {user_email}")
                return True
            else:
                logger.error(f"Failed to send notification email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending notification email: {str(e)}")
            return False

    async def send_digest_email(
        self,
        user_email: str,
        notifications: List[Notification],
        digest_type: str = "daily",
    ) -> bool:
        """
        Send a digest email with multiple notifications

        Args:
            user_email: Recipient email address
            notifications: List of notifications to include
            digest_type: Type of digest (daily, weekly)

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        if not notifications:
            logger.info(f"No notifications to send in {digest_type} digest for {user_email}")
            return True

        # Group notifications by type
        grouped = {}
        for notification in notifications:
            type_key = notification.type.value if notification.type else "other"
            if type_key not in grouped:
                grouped[type_key] = []
            grouped[type_key].append(notification)

        # Build template context
        template_context = {
            "user_email": user_email,
            "digest_type": digest_type,
            "notifications": notifications,
            "grouped_notifications": grouped,
            "notification_count": len(notifications),
        }

        try:
            # Render digest template
            subject, html_body = self._render_template("digest.html", template_context)

            # Override subject with digest-specific one
            subject = (
                f"Your {digest_type.capitalize()} BenGER Digest - {len(notifications)} Updates"
            )

            # Send email
            result = self.mail_client.send_message(
                to=[user_email], subject=subject, html_body=html_body
            )

            if result.get("status") == "success":
                logger.info(f"{digest_type.capitalize()} digest sent to {user_email}")
                return True
            else:
                logger.error(f"Failed to send digest email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending digest email: {str(e)}")
            return False

    async def send_test_email(self, user_email: str, user_name: str = "Test User") -> bool:
        """
        Send a test email to verify configuration

        Args:
            user_email: Recipient email address
            user_name: Name of the recipient

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        subject = "BenGER Email Test"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Hello {user_name}!</h2>
            <p>This is a test email from BenGER to verify that our email service is working correctly.</p>
            <p>If you're receiving this email, it means our mail server is configured properly.</p>
            <p style="color: #666; font-size: 12px; margin-top: 30px;">
                Sent from BenGER Platform
            </p>
        </body>
        </html>
        """

        try:
            result = self.mail_client.send_message(
                to=[user_email], subject=subject, html_body=html_body
            )

            if result.get("status") == "success":
                logger.info(f"Test email sent to {user_email}")
                return True
            else:
                logger.error(f"Failed to send test email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending test email: {str(e)}")
            return False

    async def send_invitation_email(
        self,
        to_email: str,
        inviter_name: str,
        organization_name: str,
        invitation_url: str,
        role: str = "member",
    ) -> bool:
        """
        Send an organization invitation email

        Args:
            to_email: Invitee's email address
            inviter_name: Name of the person sending the invitation
            organization_name: Name of the organization
            invitation_url: URL to accept the invitation
            role: Role being offered

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        subject = f"Invitation to join {organization_name} on BenGER"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>You're invited to join {organization_name}</h2>
            <p>{inviter_name} has invited you to join {organization_name} as a {role} on BenGER.</p>
            <p>BenGER is a comprehensive evaluation framework for Large Language Models in the German legal domain.</p>
            <p style="margin: 30px 0;">
                <a href="{invitation_url}" style="background-color: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                    Accept Invitation
                </a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="color: #007bff;">{invitation_url}</p>
            <p style="color: #666; font-size: 12px; margin-top: 30px;">
                This invitation will expire in 7 days. If you did not expect this invitation, you can safely ignore this email.
            </p>
        </body>
        </html>
        """

        try:
            result = self.mail_client.send_message(
                to=[to_email], subject=subject, html_body=html_body, disable_tracking=True
            )

            if result.get("status") == "success":
                logger.info(f"Invitation email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send invitation email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending invitation email: {str(e)}")
            return False

    async def send_verification_email(
        self,
        to_email: str,
        user_name: str,
        verification_link: str,
        language: str = "en",
    ) -> bool:
        """
        Send email verification link

        Args:
            to_email: User's email address
            user_name: User's name
            verification_link: Email verification URL
            language: Language for the email (en/de)

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        if language == "de":
            subject = "Bestätigen Sie Ihre E-Mail-Adresse für BenGER"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Willkommen bei BenGER, {user_name}!</h2>
                <p>Bitte bestätigen Sie Ihre E-Mail-Adresse, um Ihr Konto zu aktivieren.</p>
                <p style="margin: 30px 0;">
                    <a href="{verification_link}" style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                        E-Mail-Adresse bestätigen
                    </a>
                </p>
                <p>Oder kopieren Sie diesen Link in Ihren Browser:</p>
                <p style="color: #007bff;">{verification_link}</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    Dieser Link ist 24 Stunden gültig. Falls Sie diese E-Mail nicht angefordert haben, können Sie sie ignorieren.
                </p>
            </body>
            </html>
            """
        else:
            subject = "Verify your email address for BenGER"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Welcome to BenGER, {user_name}!</h2>
                <p>Please verify your email address to activate your account.</p>
                <p style="margin: 30px 0;">
                    <a href="{verification_link}" style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                        Verify Email Address
                    </a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="color: #007bff;">{verification_link}</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    This link will expire in 24 hours. If you didn't request this email, you can safely ignore it.
                </p>
            </body>
            </html>
            """

        try:
            result = self.mail_client.send_message(
                to=[to_email], subject=subject, html_body=html_body, disable_tracking=True
            )

            if result.get("status") == "success":
                logger.info(f"Verification email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send verification email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending verification email: {str(e)}")
            return False

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_link: str,
        language: str = "en",
    ) -> bool:
        """
        Send password reset email

        Args:
            to_email: User's email address
            user_name: User's name
            reset_link: Password reset URL
            language: Language for the email (en/de)

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False


        if language == "de":
            subject = "Passwort zurücksetzen für BenGER"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Hallo {user_name},</h2>
                <p>Sie haben angefordert, Ihr Passwort zurückzusetzen.</p>
                <p style="margin: 30px 0;">
                    <a href="{reset_link}" style="background-color: #dc3545; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                        Passwort zurücksetzen
                    </a>
                </p>
                <p>Oder kopieren Sie diesen Link in Ihren Browser:</p>
                <p style="color: #007bff;">{reset_link}</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    Dieser Link ist 1 Stunde gültig. Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.
                </p>
            </body>
            </html>
            """
        else:
            subject = "Reset your password for BenGER"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Hello {user_name},</h2>
                <p>You requested to reset your password.</p>
                <p style="margin: 30px 0;">
                    <a href="{reset_link}" style="background-color: #dc3545; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                        Reset Password
                    </a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="color: #007bff;">{reset_link}</p>
                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    This link will expire in 1 hour. If you didn't request this, you can safely ignore this email.
                </p>
            </body>
            </html>
            """

        try:
            result = self.mail_client.send_message(
                to=[to_email], subject=subject, html_body=html_body, disable_tracking=True
            )

            if result.get("status") == "success":
                logger.info(f"Password reset email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send password reset email: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return False


# Global email service instance
email_service = EmailService()


# Convenience functions for backward compatibility
async def send_notification_email(
    user_email: str,
    notification: Notification,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send notification email using global email service"""
    return await email_service.send_notification_email(user_email, notification, context)


async def send_digest_email(
    user_email: str, notifications: List[Notification], digest_type: str = "daily"
) -> bool:
    """Send digest email using global email service"""
    return await email_service.send_digest_email(user_email, notifications, digest_type)


async def test_email_service() -> bool:
    """Test email service configuration"""
    return await email_service.test_connection()
