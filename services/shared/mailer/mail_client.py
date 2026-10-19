"""
Mail provider selection for BenGER (api + workers).

``EMAIL_PROVIDER`` picks the provider: ``sendgrid`` (default) or
``cloudflare``. With ``cloudflare``, mail whose sender domain is listed in
``CLOUDFLARE_EMAIL_DOMAINS`` (comma-separated; defaults to the domain of
``EMAIL_FROM_ADDRESS``) goes out through Cloudflare Email Sending, everything
else (e.g. the Vertretbar brand's vertretbar.net) through SendGrid. When
Cloudflare answers with a rejection, the message falls back to SendGrid; a
transport failure does not fall back (the message may have been accepted) and
stays retryable for the caller.

Callers pass their own ``SendGridClient`` class into ``build_mail_client`` so
existing tests that patch ``mailer.email_service.SendGridClient`` or
``sendgrid_client.SendGridClient`` keep intercepting the SendGrid side.
"""

import logging
import os
from typing import Callable, List, Optional

from mailer.cloudflare_client import CloudflareEmailClient

logger = logging.getLogger(__name__)

PROVIDERS = ("sendgrid", "cloudflare")


def mail_provider_name() -> str:
    """The configured provider; unknown values fall back to ``sendgrid``."""
    name = (os.getenv("EMAIL_PROVIDER") or "sendgrid").strip().lower()
    if name not in PROVIDERS:
        logger.error(f"Unknown EMAIL_PROVIDER {name!r}; using sendgrid")
        return "sendgrid"
    return name


def _domain(address: Optional[str]) -> str:
    return (address or "").rsplit("@", 1)[-1].strip().lower()


def cloudflare_domains() -> set:
    raw = os.getenv("CLOUDFLARE_EMAIL_DOMAINS") or _domain(
        os.getenv("EMAIL_FROM_ADDRESS", "noreply@what-a-benger.net")
    )
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


class RoutedMailClient:
    """Sends through Cloudflare for its domains, SendGrid for the rest."""

    provider = "cloudflare"

    def __init__(self, primary, fallback, primary_domains: set):
        self.primary = primary
        self.fallback = fallback
        self.primary_domains = primary_domains
        # EmailService.is_available() checks for a configured key.
        self.api_key = primary.api_key or fallback.api_key
        self.from_email = primary.from_email
        self.from_name = primary.from_name

    def _uses_primary(self, from_address: Optional[str]) -> bool:
        return _domain(from_address or self.primary.from_email) in self.primary_domains

    def send_message(self, to: List[str], subject: str, **kwargs) -> dict:
        if not self._uses_primary(kwargs.get("from_address")):
            return self.fallback.send_message(to=to, subject=subject, **kwargs)

        result = self.primary.send_message(to=to, subject=subject, **kwargs)
        if result.get("status") == "success" or not result.pop("provider_rejected", False):
            return result

        logger.warning(
            f"Cloudflare rejected the message ({result.get('error')}); sending via SendGrid"
        )
        return self.fallback.send_message(to=to, subject=subject, **kwargs)

    async def test_connection(self) -> bool:
        return await self.primary.test_connection()


def build_mail_client(sendgrid_class: Callable):
    """The mail client for the configured provider."""
    if mail_provider_name() == "cloudflare":
        return RoutedMailClient(CloudflareEmailClient(), sendgrid_class(), cloudflare_domains())
    return sendgrid_class()
