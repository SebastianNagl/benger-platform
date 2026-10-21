"""
Postmark client for BenGER, the fallback for account-critical mail.

Same call and result contract as ``SendGridClient.send_message`` (``status``,
``message_id``, ``recipients``, ``status_code``, ``error``, ``details``;
``status_code=None`` on a transport failure).

Postmark only steps in when Cloudflare rejects a message, and only for mail a
user is waiting on (invitations, activation, verification, password reset,
account links; callers pass ``essential=True``). The plan allows few mails a
month, so a burst of notifications must not use them up. A monthly counter in
Redis (``POSTMARK_MONTHLY_LIMIT``, default 100, counted per recipient) keeps
the client from sending past the plan; over budget it rejects without calling
Postmark and ``RoutedMailClient`` moves on to SendGrid. Without Redis the
counter is skipped and Postmark's own limit answers with a rejection instead.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import requests

from account_activation import email_is_routable
from mailer.cloudflare_client import _format_address, html_to_text
from mailer.sendgrid_client import mask_addresses

logger = logging.getLogger(__name__)

API_BASE = "https://api.postmarkapp.com"
DEFAULT_MONTHLY_LIMIT = 100

_redis_client = None


def _redis():
    """A shared Redis client from ``REDIS_URI``, or None when unavailable."""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URI")
        if not url:
            return None
        import redis

        _redis_client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    return _redis_client


class PostmarkEmailClient:
    """Postmark REST client with a monthly send budget."""

    provider = "postmark"

    def __init__(self):
        self.api_key = os.getenv("POSTMARK_SERVER_TOKEN", "").strip()
        self.message_stream = os.getenv("POSTMARK_MESSAGE_STREAM") or "outbound"
        self.from_email = os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "BenGER Platform")
        self.api_url = f"{API_BASE}/email"
        try:
            self.monthly_limit = int(os.getenv("POSTMARK_MONTHLY_LIMIT") or DEFAULT_MONTHLY_LIMIT)
        except ValueError:
            logger.error("POSTMARK_MONTHLY_LIMIT is not a number; using the default")
            self.monthly_limit = DEFAULT_MONTHLY_LIMIT

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _budget_key() -> str:
        return f"mail:postmark:sent:{datetime.now(timezone.utc):%Y-%m}"

    def _reserve(self, count: int) -> bool:
        """Count ``count`` mails against this month; False when over budget."""
        try:
            client = _redis()
            if client is None:
                return True
            key = self._budget_key()
            used = client.incrby(key, count)
            if used == count:
                client.expire(key, 40 * 24 * 3600)
            if used > self.monthly_limit:
                client.decrby(key, count)
                return False
            return True
        except Exception as e:
            # Fail open: Postmark's own limit still rejects past the plan.
            logger.warning(f"Postmark budget check unavailable: {type(e).__name__}")
            return True

    def _release(self, count: int) -> None:
        """Give back a reservation for a mail Postmark did not take."""
        try:
            client = _redis()
            if client is not None:
                client.decrby(self._budget_key(), count)
        except Exception:
            pass

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
        essential: bool = False,
    ) -> dict:
        """Send an email via Postmark.

        Tracking is always off (no open pixel, no link rewriting).
        ``essential`` is accepted for contract parity. Rejections, including
        an exhausted budget, carry ``provider_rejected=True`` so
        ``RoutedMailClient`` may hand the message on without a duplicate.
        """
        if not self.is_configured():
            logger.error("Postmark not configured")
            return {
                "status": "error",
                "error": "Postmark not configured",
                "provider_rejected": True,
            }

        requested = len(to)
        to = [email for email in to if email_is_routable(email)]
        cc = [email for email in cc or [] if email_is_routable(email)]
        bcc = [email for email in bcc or [] if email_is_routable(email)]
        if requested and not to:
            return {
                "status": "error",
                "status_code": 400,
                "error": "No deliverable recipient (reserved .invalid address)",
            }

        # Postmark bills every recipient as one mail.
        count = len(to) + len(cc) + len(bcc)
        if not self._reserve(count):
            logger.warning(f"Postmark monthly budget ({self.monthly_limit}) used up; skipping")
            return {
                "status": "error",
                "error": "Postmark monthly budget used up",
                "recipients": to,
                "provider_rejected": True,
            }

        payload = {
            "From": _format_address(from_address or self.from_email, from_name or self.from_name),
            "To": ", ".join(to),
            "Subject": subject,
            "MessageStream": self.message_stream,
            "TrackOpens": False,
            "TrackLinks": "None",
        }
        if cc:
            payload["Cc"] = ", ".join(cc)
        if bcc:
            payload["Bcc"] = ", ".join(bcc)
        if html_body:
            payload["HtmlBody"] = html_body
        if plain_body or html_body:
            payload["TextBody"] = plain_body or html_to_text(html_body)
        if reply_to:
            payload["ReplyTo"] = reply_to
        if headers:
            payload["Headers"] = [{"Name": k, "Value": v} for k, v in headers.items()]

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": self.api_key,
                },
                json=payload,
                timeout=(5, 15),
            )
        except Exception as e:
            error = mask_addresses(str(e))
            logger.error(f"Failed to send email via Postmark: {error}")
            # The message may have gone out, so the reservation stays.
            return {"status": "error", "status_code": None, "error": error, "recipients": to}

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code == 200 and body.get("ErrorCode") == 0:
            logger.info(f"Email sent successfully via Postmark to {len(to)} recipient(s)")
            return {
                "status": "success",
                "message_id": body.get("MessageID", "unknown"),
                "recipients": to,
                "status_code": response.status_code,
            }

        self._release(count)
        details = mask_addresses(
            f"{body.get('ErrorCode')}: {body.get('Message')}" if body else response.text
        )
        logger.error(f"Postmark API error: {response.status_code} - {details}")
        return {
            "status": "error",
            "error": f"Postmark API error: {response.status_code}",
            "details": details,
            "recipients": to,
            "status_code": response.status_code,
            "provider_rejected": True,
        }

    def _check_token(self) -> bool:
        response = requests.get(
            f"{API_BASE}/server",
            headers={"Accept": "application/json", "X-Postmark-Server-Token": self.api_key},
            timeout=(5, 15),
        )
        return response.status_code == 200

    async def test_connection(self) -> bool:
        """True when the server token is accepted by Postmark."""
        if not self.is_configured():
            return False
        return await asyncio.to_thread(self._check_token)
