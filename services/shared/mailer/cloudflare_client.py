"""
Cloudflare Email Sending client for BenGER.

Same call and result contract as ``SendGridClient.send_message`` (``status``,
``message_id``, ``recipients``, ``status_code``, ``error``, ``details``;
``status_code=None`` on a transport failure), so every caller, including the
workers' "4xx except 429 is permanent" retry rule, works unchanged.

Why it exists: several university mail servers (Potsdam, Hamburg) drop TCP
connections from SendGrid's shared IPs, so invitations sat in SendGrid's
deferred queue until they expired. Cloudflare's sending IPs get through.

The sending domain must be onboarded in Cloudflare Email Sending, which needs
the domain's DNS on Cloudflare. ``mail_client.RoutedMailClient`` therefore only
sends the domains listed in ``CLOUDFLARE_EMAIL_DOMAINS`` here and leaves the
rest (vertretbar.net) on SendGrid.
"""

import asyncio
import html
import logging
import os
import re
from typing import List, Optional

import requests

from account_activation import email_is_routable
from mailer.sendgrid_client import mask_addresses

logger = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"


def html_to_text(html_body: str) -> str:
    """A plain-text alternative for an HTML-only mail.

    HTML-only mail scores worse with spam filters, and every template here is
    HTML-only. Links keep their target: ``label (https://...)``.
    """
    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", html_body)
    text = re.sub(
        r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: (
            m.group(2) if m.group(1) in m.group(2) else f"{m.group(2).strip()} ({m.group(1)})"
        ),
        text,
    )
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _format_address(email: str, name: Optional[str]) -> str:
    if not name:
        return email
    # Quote names with characters that would break the address syntax.
    if any(ch in name for ch in ',;<>"@'):
        name = '"' + name.replace('"', "'") + '"'
    return f"{name} <{email}>"


class CloudflareEmailClient:
    """Cloudflare Email Sending REST client."""

    provider = "cloudflare"

    def __init__(self):
        self.api_key = os.getenv("CLOUDFLARE_EMAIL_API_TOKEN", "")
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        self.from_email = os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "BenGER Platform")
        self.api_url = f"{API_BASE}/accounts/{self.account_id}/email/sending/send"

        if not self.api_key or not self.account_id:
            logger.warning("Cloudflare Email Sending not configured")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.account_id)

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
        """Send an email via Cloudflare Email Sending.

        ``disable_tracking`` is accepted for contract parity; Cloudflare does
        not rewrite links or add open pixels. HTTP rejections additionally
        carry ``provider_rejected=True``: Cloudflare answered and did not take
        the message, so ``RoutedMailClient`` may hand it to the fallback
        provider without risking a duplicate.
        """
        if not self.is_configured():
            logger.error("Cloudflare Email Sending not configured")
            return {
                "status": "error",
                "error": "Cloudflare Email Sending not configured",
                "provider_rejected": True,
            }

        # Same rule as SendGridClient: reserved `.invalid` placeholders are
        # never mailed, and nobody left is a permanent 4xx.
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

        payload = {
            "from": _format_address(from_address or self.from_email, from_name or self.from_name),
            "to": to,
            "subject": subject,
        }
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if html_body:
            payload["html"] = html_body
        if plain_body or html_body:
            payload["text"] = plain_body or html_to_text(html_body)
        if reply_to:
            payload["reply_to"] = reply_to
        if headers:
            payload["headers"] = headers

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, 15),
            )
        except Exception as e:
            error = mask_addresses(str(e))
            logger.error(f"Failed to send email via Cloudflare: {error}")
            # status_code=None signals a network/transport failure (retryable).
            return {"status": "error", "status_code": None, "error": error, "recipients": to}

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code == 200 and body.get("success"):
            result = body.get("result") or {}
            # Cloudflare accepts the call even when it drops recipients it
            # already knows to bounce. All of them gone is a permanent failure.
            dropped = set(result.get("permanent_bounces") or []) | set(
                result.get("suppressed_recipients") or []
            )
            if dropped and all(email in dropped for email in to):
                details = mask_addresses(", ".join(sorted(dropped)))
                logger.error(f"Cloudflare dropped every recipient (bounce/suppressed): {details}")
                return {
                    "status": "error",
                    "status_code": 422,
                    "error": "Recipient permanently bounced or suppressed",
                    "details": details,
                    "recipients": to,
                }
            logger.info(f"Email sent successfully via Cloudflare to {len(to)} recipient(s)")
            return {
                "status": "success",
                "message_id": result.get("message_id", "unknown"),
                "recipients": to,
                "status_code": response.status_code,
            }

        errors = body.get("errors") or []
        details = mask_addresses(
            "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errors) or response.text
        )
        logger.error(f"Cloudflare email API error: {response.status_code} - {details}")
        return {
            "status": "error",
            "error": f"Cloudflare email API error: {response.status_code}",
            "details": details,
            "recipients": to,
            "status_code": response.status_code,
            "provider_rejected": True,
        }

    def _verify_token(self) -> bool:
        auth = {"Authorization": f"Bearer {self.api_key}"}
        # User-owned and account-owned API tokens verify on different paths.
        for url in (
            f"{API_BASE}/user/tokens/verify",
            f"{API_BASE}/accounts/{self.account_id}/tokens/verify",
        ):
            response = requests.get(url, headers=auth, timeout=(5, 15))
            if response.status_code == 200:
                return (response.json().get("result") or {}).get("status") == "active"
        return False

    async def test_connection(self) -> bool:
        """True when the API token is valid and active."""
        if not self.is_configured():
            return False
        return await asyncio.to_thread(self._verify_token)
