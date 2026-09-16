"""Account activation for passwordless (LTI-provisioned) accounts.

Shared by the api (request/confirm endpoints) and the workers (the
``emails.send_account_activation`` task), like ``models`` and ``mailer.*``.

Two entry paths, one flow:
- Auto: an account the LMS consent step creates (or a re-consented one
  without a password) with a routable claim email queues the mail.
- Fallback: a sub-only account (synthetic ``@lti.invalid`` address) enters an
  address in the app; it parks in ``users.pending_activation_email`` and is
  adopted only when the link is clicked (mailbox-ownership proof).

Token storage reuses the ``password_reset_token``/``password_reset_expires``
columns — the activation confirm endpoint is the only consumer that also
flips ``password_set`` and adopts a pending email. Opaque token (no JWT: the
workers have no JWT machinery).

Linking an LMS identity to an existing account needs proof of ownership
(owner decision D6). One proof is a confirmation link mailed to the account's
address (``emails.send_account_link_confirmation``). The helpers below decide
whether an address counts as proven, build that link and mask addresses for
display. The token itself lives in the extended overlay's store; the platform
only mails it.
"""

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

ACTIVATION_TOKEN_EXPIRY = timedelta(days=7)
# Validity of an account-link confirmation token. The extended token store
# uses it as its TTL, and the mail states it.
ACCOUNT_LINK_TOKEN_EXPIRY = timedelta(hours=24)

# ``users.email_verification_method`` of an address an LMS supplied at
# provisioning. It stays unverified until a link mailed to it is used.
EMAIL_METHOD_LMS_CLAIM = "lti_claim"
# Methods that do not prove the account holder owns the mailbox:
# ``system`` (set by provisioning code), ``lti_claim`` (an LMS said so) and
# ``admin`` (an org admin clicked "verify", which any org admin can do for
# their members). An address verified this way never qualifies for the
# email proof of an account link.
UNPROVEN_EMAIL_METHODS = frozenset({"system", EMAIL_METHOD_LMS_CLAIM, "admin"})

# Mail languages the templates exist in, and the default (plan default: the
# activation and link-confirmation mails are German unless the user prefers
# otherwise).
MAIL_LANGUAGES = ("de", "en")
DEFAULT_MAIL_LANGUAGE = "de"

# Upper bound for free-text names (connection, organization) shown in a mail.
_DISPLAY_NAME_LIMIT = 120
_WHITESPACE_RE = re.compile(r"\s+")

# RFC 2606 reserves .invalid; LTI provisioning uses `<user>@lti.invalid` for
# sub-only accounts. Anything under .invalid is by definition unroutable.
_UNROUTABLE_SUFFIX = ".invalid"


def email_is_routable(email: Optional[str]) -> bool:
    return bool(email) and not email.rsplit("@", 1)[-1].endswith(_UNROUTABLE_SUFFIX)


def email_ownership_proven(user) -> bool:
    """True when the account holder has proven they own ``user.email``.

    That is: the address is verified, it was not verified by a method in
    :data:`UNPROVEN_EMAIL_METHODS`, and it is routable. Only such an account
    may be offered the email proof when an LMS identity is linked to it.
    A verified address without a recorded method predates method tracking
    and counts as self-verified.
    """
    if user is None or not getattr(user, "email_verified", False):
        return False
    method = (getattr(user, "email_verification_method", None) or "").strip().lower()
    if method in UNPROVEN_EMAIL_METHODS:
        return False
    return email_is_routable(getattr(user, "email", None))


def mask_email(email: Optional[str]) -> str:
    """Display hint for an address, e.g. ``st…@uni.de``.

    Keeps the first two characters of the local part (one for local parts of
    up to two characters) and the full domain. Never returns the full local
    part.
    """
    if not email:
        return ""
    local, _, domain = email.partition("@")
    keep = 1 if len(local) <= 2 else 2
    hint = local[:keep] + "…"
    return f"{hint}@{domain}" if domain else hint


def build_account_link_url(frontend_base: str, token: str) -> str:
    """Link of the account-link confirmation mail.

    It opens the confirmation page, where a button (not the page load) uses
    the token, so mail scanners that fetch links do not consume it.
    """
    return f"{frontend_base.rstrip('/')}/lti/link-confirm/{token}"


def mail_language_for(user, default: str = DEFAULT_MAIL_LANGUAGE) -> str:
    """Language of a transactional mail to ``user``: the user's stored
    preference when there is one the templates support, else ``default``.

    No user column stores a language today (the UI keeps it in the browser),
    so this returns ``default`` until one exists.
    """
    preferred = getattr(user, "language_preference", None)
    if isinstance(preferred, str):
        code = preferred.strip().lower()[:2]
        if code in MAIL_LANGUAGES:
            return code
    return default


def clean_display_name(value: Optional[str], limit: int = _DISPLAY_NAME_LIMIT) -> str:
    """Free text (a connection or organization name) made fit for a mail
    body: whitespace and line breaks collapsed to single spaces, trimmed and
    cut to ``limit`` characters. HTML escaping is the template's job."""
    text = _WHITESPACE_RE.sub(" ", value or "").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def account_link_mail_eligibility(user) -> Optional[str]:
    """Return a skip reason, or ``None`` when the link-confirmation mail may
    be sent to ``user``.

    The extended overlay offers the email proof only to eligible accounts;
    the mail task checks again when it runs. Superadmin accounts are never
    linkable, so they never get this mail.
    """
    if user is None:
        return "user_not_found"
    if not getattr(user, "is_active", True):
        return "user_inactive"
    if getattr(user, "anonymized_at", None) is not None:
        return "user_anonymized"
    if getattr(user, "is_superadmin", False):
        return "not_linkable"
    if not email_is_routable(getattr(user, "email", None)):
        return "email_not_routable"
    if not email_ownership_proven(user):
        return "email_not_proven"
    return None


def verify_email_by_link(user, *, method: str, now=None) -> bool:
    """Mark ``user.email`` verified because a link mailed to it was used.

    For the activation and password-reset confirm paths. An LMS-supplied
    address is stored unverified (method ``lti_claim``) and login refuses
    unverified accounts, so using a link sent to that address is what makes
    the account usable. Applies only to an unverified, routable address and
    never while a pending address is parked (the link then went there, not
    to ``user.email``). Caller commits. Returns True when it changed the row.
    """
    if getattr(user, "email_verified", False):
        return False
    if getattr(user, "pending_activation_email", None):
        return False
    if not email_is_routable(user.email):
        return False
    user.email_verified = True
    user.email_verification_method = method
    user.email_verified_at = now or datetime.now(timezone.utc)
    return True


def activation_eligibility(
    user, *, target_email: Optional[str] = None, now=None
) -> Optional[str]:
    """Return a skip-reason string, or ``None`` when a mail may be sent.

    Belt-and-braces guard shared by the enqueue sites and the worker task —
    activated accounts are never mailed, unroutable targets never enqueued.
    A still-pending token is NOT a skip reason: the sender reuses it (see
    ``current_or_new_activation_token``) so worker retries after a transient
    SendGrid failure can resend the same link.
    """
    now = now or datetime.now(timezone.utc)
    if not getattr(user, "is_active", True):
        return "user_inactive"
    if user.hashed_password is not None:
        return "already_has_password"
    if getattr(user, "password_set", False):
        return "password_already_set"
    if not email_is_routable(target_email or user.email):
        return "email_not_routable"
    return None


def current_or_new_activation_token(
    user, *, pending_email: Optional[str] = None, force: bool = False, now=None
) -> str:
    """Reuse a still-valid token, else mint a fresh one (caller commits).

    ``force`` (the fallback/resend path) always re-mints — the student may
    have mistyped the address; the new token + pending email replace the old
    link atomically. The auto path reuses so a delivered link stays valid
    across worker retries and duplicate enqueues.
    """
    now = now or datetime.now(timezone.utc)
    existing = getattr(user, "password_reset_token", None)
    expires = getattr(user, "password_reset_expires", None)
    if (
        not force
        and not pending_email
        and existing
        and expires is not None
        and expires > now
    ):
        return existing
    return issue_activation_token(user, pending_email=pending_email, now=now)


def issue_activation_token(user, *, pending_email: Optional[str] = None, now=None) -> str:
    """Mint + store an activation token on the user row. Caller commits."""
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    user.password_reset_token = token
    user.password_reset_expires = now + ACTIVATION_TOKEN_EXPIRY
    if pending_email:
        user.pending_activation_email = pending_email
    return token


def build_activation_link(brand, token: str) -> str:
    return f"{brand.frontend_url}/activate/{token}"
