"""
Host-driven email branding.

Transactional emails (e.g. account verification) are sent by the one platform on
behalf of two products living on two hosts:
  - what-a-benger.net → BenGER
  - vertretbar.net     → Vertretbar (student product)

The sending host decides the From identity, the verify-link host, and the brand
name in the copy. This mirrors STUDENT_LOCKED_DOMAINS in the frontend
(services/frontend/src/lib/utils/subdomain.ts) — keep the two lists in sync.

Values are env-overridable so ops can retarget them without a code change; the
defaults are the production identities. Benger keeps ``from_address=None`` so the
mailer falls back to its configured EMAIL_FROM_ADDRESS (unchanged behavior).
"""

import os
from dataclasses import dataclass

# Mirror STUDENT_LOCKED_DOMAINS in the frontend subdomain util.
_STUDENT_LOCKED_HOSTS = ("vertretbar.net", "staging.vertretbar.net", "vertretbar.localhost")


def is_student_locked_host(host: str | None) -> bool:
    """True when ``host`` is (a subdomain of) a Vertretbar apex."""
    if not host:
        return False
    bare = host.split(":")[0].lower()
    return any(bare == d or bare.endswith("." + d) for d in _STUDENT_LOCKED_HOSTS)


def _url_from_host(host: str) -> str:
    """Browser-facing origin for a request host. Derived from the actual host so
    a staging.vertretbar.net signup links back to staging (not prod) and dev to
    localhost — https everywhere except *.localhost."""
    bare = host.split(":")[0].lower()
    scheme = "http" if (bare == "localhost" or bare.endswith(".localhost")) else "https"
    return f"{scheme}://{host}"


@dataclass(frozen=True)
class EmailBrand:
    name: str
    frontend_url: str
    from_address: str | None  # None → mailer default (EMAIL_FROM_ADDRESS)
    from_name: str | None
    tagline: str  # one-line product description used in email bodies
    default_language: str  # transactional-email language when the caller sets none


_BENGER_TAGLINE = (
    "BenGER is a comprehensive evaluation framework for Large Language Models "
    "in the German legal domain."
)
_VERTRETBAR_TAGLINE = (
    "Vertretbar hilft Jurastudierenden, Klausuren mit sofortiger KI-Korrektur zu üben."
)


def resolve_email_brand(host: str | None = None) -> EmailBrand:
    """Resolve the email brand (From identity, verify-link host, display name,
    tagline) from the sending/signup host. Vertretbar on vertretbar.net; BenGER
    otherwise."""
    if is_student_locked_host(host):
        return EmailBrand(
            name="Vertretbar",
            # Link back to the host they signed up on (staging→staging, prod→prod,
            # dev→localhost); env override kept as an escape hatch.
            frontend_url=os.getenv("VERTRETBAR_FRONTEND_URL") or _url_from_host(host),
            from_address=os.getenv("VERTRETBAR_EMAIL_FROM_ADDRESS", "noreply@vertretbar.net"),
            from_name=os.getenv("VERTRETBAR_EMAIL_FROM_NAME", "Vertretbar"),
            tagline=_VERTRETBAR_TAGLINE,
            default_language="de",  # Vertretbar is a German student product
        )
    return EmailBrand(
        name="BenGER",
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000"),
        from_address=None,
        from_name=None,
        tagline=_BENGER_TAGLINE,
        default_language="en",
    )
