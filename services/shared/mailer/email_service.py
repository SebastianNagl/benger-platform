"""
Email Service for BenGER — SendGrid integration (canonical, shared).

All outbound mail goes through the SendGrid HTTP API. Templates are loaded
from the canonical ``/shared/email_templates/email`` directory and rendered
via Jinja2.

This module is the single source of truth for ``EmailService``. It used to
live as two divergent copies — ``services/api/services/email/email_service.py``
and ``services/workers/email_service.py`` — which both now re-export from here.
The two former copies are reconciled here as a behavioral *superset*:

* ``__init__(check_feature_flag=True)`` — the api copy queried the
  ``API_MAIL_SERVICE`` feature flag via a short-lived ``SessionLocal`` to
  decide ``mail_enabled``; the worker copy hardcoded ``mail_enabled = True``
  (no DB to query during a Celery task that builds the service eagerly at
  module import). The flag check is kept as the default; pass
  ``check_feature_flag=False`` to skip the DB query and force-enable (the
  worker's old behavior). The check also fails safe to enabled if the DB is
  unreachable, so ``check_feature_flag=True`` never crashes a worker.
* ``send_notification_email`` keeps the worker's enum-or-string
  ``notification.type`` handling — ``send_notification_batch_task`` hydrates
  an unattached ``Notification`` with ``type`` as a plain string from the
  JSON payload, and SQLAlchemy doesn't coerce it until commit.
* ``is_available()`` (api-only originally) is preserved.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from email_templates.template_map import template_for
from models import Notification
from sendgrid_client import SendGridClient

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SendGrid."""

    def __init__(self, check_feature_flag: bool = True):
        """Initialize the email service.

        Args:
            check_feature_flag: When True (default, the api's historical
                behavior) consult the ``API_MAIL_SERVICE`` feature flag to set
                ``mail_enabled``. When False (the worker's historical
                behavior) skip the DB query entirely and enable unconditionally
                — used where no DB session is appropriate at construction time.
        """
        self.from_email = os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "BenGER Platform")

        # Check if mail service is enabled via feature flag (unless skipped).
        self.mail_enabled = self._is_mail_enabled() if check_feature_flag else True

        # Initialize SendGrid client for email delivery
        self.mail_client = SendGridClient()

        # Initialize template environment
        self.template_env = self._init_template_environment()

        if not self.mail_enabled:
            logger.info("Mail service is disabled via feature flag")

    def _is_mail_enabled(self) -> bool:
        """Check if mail service is enabled via feature flag"""
        try:
            from database import SessionLocal
            from models import FeatureFlag

            db = SessionLocal()
            try:
                # Check for mail service feature flag
                flag = db.query(FeatureFlag).filter(FeatureFlag.name == "API_MAIL_SERVICE").first()
                return flag.is_enabled if flag else True  # Default to enabled
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not check mail service feature flag: {e}")
            return True  # Default to enabled if check fails

    def _init_template_environment(self) -> Environment:
        """Initialize Jinja2 template environment for email templates"""
        # Templates live in services/shared (mounted at /shared in both
        # Docker images) so the API and the workers render from the same
        # source. Previously each service had its own copy and the worker's
        # was empty, so every notification email dispatched from a Celery
        # task failed silently at template lookup.
        template_dir = Path(
            os.environ.get("EMAIL_TEMPLATE_DIR", "/shared/email_templates/email")
        )

        if not template_dir.exists():
            logger.warning(f"Template directory not found: {template_dir}")
            try:
                template_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning(
                    f"Cannot create template directory (read-only filesystem?): {template_dir}"
                )

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

    def is_available(self) -> bool:
        """
        Check if email service is available and configured

        Returns:
            True if email service is available and configured
        """
        # Check if mail is enabled and SendGrid is configured
        return self.mail_enabled and bool(self.mail_client.api_key)

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

        # notification.type can be a NotificationType enum OR a plain
        # string (send_notification_batch_task hydrates an unattached
        # Notification with `type=notif_dict["type"]` from the JSON
        # payload; SQLAlchemy doesn't coerce until commit and we never
        # add this instance to the session). template_for() handles both.
        type_value = (
            notification.type.value
            if hasattr(notification.type, "value")
            else (notification.type if isinstance(notification.type, str) else "general")
        )

        template_context = {
            "notification": notification,
            "notification_type": type_value,
            "user_email": user_email,
            **(context or {}),
        }

        template_name = template_for(notification.type)

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

    def build_invitation_email(
        self,
        *,
        organization_name: str,
        inviter_name: str,
        role: str,
        invitation_url: str,
    ) -> tuple[str, str]:
        """Render the invitee org-invitation email -> (subject, html_body).

        Single source of the invitee HTML: services/shared/email_templates/
        email/invitation_recipient.html. Not to be confused with
        organization_invite.html, which is the org-admin notification email.
        """
        return self._render_template(
            "invitation_recipient.html",
            {
                "organization_name": organization_name,
                "inviter_name": inviter_name,
                "role": role,
                "invitation_url": invitation_url,
            },
        )

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

        subject, html_body = self.build_invitation_email(
            organization_name=organization_name,
            inviter_name=inviter_name,
            role=role,
            invitation_url=invitation_url,
        )

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
        expiry_label: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Send password reset email

        Args:
            to_email: User's email address
            user_name: User's name
            reset_link: Password reset URL
            language: Language for the email (en/de)
            expiry_label: Optional ``{"en": ..., "de": ...}`` override for the
                "this link expires in N" copy. Defaults to the platform value
                of 24 hours / 24 Stunden. The worker copy historically said
                "1 hour"/"1 Stunde"; pass ``{"en": "1 hour", "de": "1 Stunde"}``
                to reproduce that wording for callers that mint short-lived
                reset links.

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.mail_enabled:
            logger.debug("Email not sent: Mail service is disabled")
            return False

        labels = {"en": "24 hours", "de": "24 Stunden"}
        if expiry_label:
            labels.update(expiry_label)

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
                    Dieser Link ist {labels["de"]} gültig. Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.
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
                    This link will expire in {labels["en"]}. If you didn't request this, you can safely ignore this email.
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


# Global email service instance. Constructed with check_feature_flag=False so
# importing this module never triggers a DB query at import time — matching the
# worker's historical eager construction. The api flips mail_enabled via the
# feature-flag check at request time where needed (and tests set it directly).
email_service = EmailService(check_feature_flag=False)


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
