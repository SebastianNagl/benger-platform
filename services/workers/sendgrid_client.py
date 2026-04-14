"""
SendGrid Email Client for BenGER
Uses SendGrid API for reliable email delivery
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
        self.api_url = "https://api.sendgrid.com/v3/mail/send"

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
            Dict with status and message
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
            # Send request to SendGrid
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully via SendGrid to {', '.join(to)}")
                return {
                    "status": "success",
                    "message_id": response.headers.get("X-Message-Id", "unknown"),
                    "recipients": to,
                }
            else:
                logger.error(f"SendGrid API error: {response.status_code} - {response.text}")
                return {
                    "status": "error",
                    "error": f"SendGrid API error: {response.status_code}",
                    "details": response.text,
                    "recipients": to,
                }

        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {e}")
            return {"status": "error", "error": str(e), "recipients": to}

    async def verify_webhook_signature(self, signature: str, payload: bytes) -> bool:
        """Verify SendGrid webhook signature if needed"""
        # SendGrid webhook verification can be implemented here if needed
        return True
