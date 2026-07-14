"""
SendGrid Email Client for BenGER — canonical shared implementation.

This is the single source of truth for the SendGrid HTTP client. It unifies
the two formerly-duplicated copies (``services/api/services/email/`` and
``services/workers/``) into a behavioral *superset* that preserves BOTH
callers' contracts:

* The api copy's request ``timeout=(5, 15)`` — a hanging SendGrid response
  used to be able to freeze the API event loop (the send path was originally
  driven via ``asyncio.create_task``); the timeout stays belt-and-suspenders
  now that the send path runs on a Celery worker.
* The workers copy's ``status_code`` key in the success/error return dicts and
  ``status_code=None`` on the transport-exception path. The workers use this
  to drive Celery retry decisions (``None`` signals a retryable network/
  transport failure). The api ignores the extra key — harmless.

Importable bare as ``from sendgrid_client import SendGridClient`` in both the
api and the workers because their thin shims re-export this module, and
directly as ``from mailer.sendgrid_client import SendGridClient`` (``/shared``
is on ``sys.path`` in both containers).
"""

import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class SendGridClient:
    """SendGrid API client for email delivery"""

    def __init__(self):
        """Initialize SendGrid client with API key from environment"""
        self.api_key = os.getenv("SENDGRID_API_KEY", "")
        self.from_email = os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "BenGER Platform")
        # Overridable so local dev / tests can point the SendGrid HTTP client
        # at a mail catcher that speaks the same /v3/mail/send contract
        # (no verified sender needed, links stay clickable on localhost).
        # Defaults to the real SendGrid endpoint in prod.
        self.api_url = os.getenv(
            "SENDGRID_API_URL", "https://api.sendgrid.com/v3/mail/send"
        )

        if not self.api_key:
            logger.warning("SendGrid API key not configured")

    def send_message(
        self,
        to: List[str],
        subject: str,
        html_body: Optional[str] = None,
        plain_body: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        headers: Optional[dict] = None,
        disable_tracking: bool = False,
    ) -> dict:
        """
        Send email via SendGrid API

        Returns:
            Dict with status and message. Success and SendGrid-error results
            also carry ``status_code`` (the HTTP status); transport failures
            carry ``status_code=None`` so Celery callers can distinguish a
            retryable network error from an application-level rejection.
        """
        if not self.api_key:
            logger.error("SendGrid API key not configured")
            return {"status": "error", "error": "SendGrid not configured"}

        # Build SendGrid payload
        payload = {
            "personalizations": [
                {
                    "to": [{"email": email} for email in to],
                }
            ],
            "from": {"email": from_address or self.from_email, "name": from_name or self.from_name},
            "subject": subject,
            "content": [],
        }

        # Add CC/BCC if provided
        if cc:
            payload["personalizations"][0]["cc"] = [{"email": email} for email in cc]
        if bcc:
            payload["personalizations"][0]["bcc"] = [{"email": email} for email in bcc]

        # Add content
        if plain_body:
            payload["content"].append({"type": "text/plain", "value": plain_body})
        if html_body:
            payload["content"].append({"type": "text/html", "value": html_body})

        # Add reply-to if provided
        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        # Add custom headers if provided
        if headers:
            payload["headers"] = headers

        # Disable click tracking for transactional emails if requested
        # This prevents SendGrid from rewriting links which can break verification flows
        if disable_tracking:
            payload["tracking_settings"] = {
                "click_tracking": {"enable": False, "enable_text": False},
                "open_tracking": {"enable": False},
            }

        try:
            # Send request to SendGrid. The timeout is critical: this used to
            # be called from an async handler via asyncio.create_task — a
            # hanging SendGrid response would freeze the event loop. The send
            # path now runs on a Celery worker, but the timeout stays
            # belt-and-suspenders.
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, 15),
            )

            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully via SendGrid to {', '.join(to)}")
                return {
                    "status": "success",
                    "message_id": response.headers.get("X-Message-Id", "unknown"),
                    "recipients": to,
                    "status_code": response.status_code,
                }
            else:
                logger.error(f"SendGrid API error: {response.status_code} - {response.text}")
                return {
                    "status": "error",
                    "error": f"SendGrid API error: {response.status_code}",
                    "details": response.text,
                    "recipients": to,
                    "status_code": response.status_code,
                }

        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {e}")
            # status_code=None signals a network/transport failure (retryable).
            return {"status": "error", "status_code": None, "error": str(e), "recipients": to}

    async def verify_webhook_signature(self, signature: str, payload: bytes) -> bool:
        """Verify SendGrid webhook signature if needed"""
        # SendGrid webhook verification can be implemented here if needed
        return True
