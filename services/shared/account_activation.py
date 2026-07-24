"""Account activation for passwordless (LTI-provisioned) accounts.

Shared by the api (request/confirm endpoints) and the workers (the
``emails.send_account_activation`` task), like ``models`` and ``mailer.*``.

Two entry paths, one flow:
- Auto: first LTI provisioning with a real claim email queues the mail.
- Fallback: a sub-only account (synthetic ``@lti.invalid`` address) enters an
  address in the app; it parks in ``users.pending_activation_email`` and is
  adopted only when the link is clicked (mailbox-ownership proof).

Token storage reuses the ``password_reset_token``/``password_reset_expires``
columns — the activation confirm endpoint is the only consumer that also
flips ``password_set`` and adopts a pending email. Opaque token (no JWT: the
workers have no JWT machinery).
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

ACTIVATION_TOKEN_EXPIRY = timedelta(days=7)

# RFC 2606 reserves .invalid; LTI provisioning uses `<user>@lti.invalid` for
# sub-only accounts. Anything under .invalid is by definition unroutable.
_UNROUTABLE_SUFFIX = ".invalid"


def email_is_routable(email: Optional[str]) -> bool:
    return bool(email) and not email.rsplit("@", 1)[-1].endswith(_UNROUTABLE_SUFFIX)


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
