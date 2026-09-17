"""Public tool hosts for LMS (LTI) connections.

Every LMS connection names the public host its tool URLs (login, launch,
JWKS, Dynamic Registration) point at. The host never comes from the browser
or the request; it is a key stored on the connection and resolved here from
the environment, at call time:

  * ``main``           -> ``FRONTEND_URL`` (the platform host; same default as
                          the mail branding).
  * ``student_locked`` -> ``VERTRETBAR_FRONTEND_URL`` (the student-only host,
                          see ``mailer.branding.is_student_locked_host``).
                          Available only when the variable is set.

Pure module: no FastAPI, no DB. The api (admin endpoints) and the extended
overlay (launch, Dynamic Registration, mail links) share it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit

TOOL_HOST_STUDENT_LOCKED = "student_locked"
TOOL_HOST_MAIN = "main"
# Every key the schema accepts (CHECK constraint, migration 105), in display
# order.
TOOL_HOSTS = (TOOL_HOST_STUDENT_LOCKED, TOOL_HOST_MAIN)
TOOL_HOST_PATTERN = "^(student_locked|main)$"

_MAIN_DEFAULT_URL = "http://localhost:3000"


class ToolHostUnavailable(ValueError):
    """The key is unknown, or its host is not configured in this deployment."""

    code = "tool_host_unavailable"

    def __init__(self, key: object):
        self.key = key
        super().__init__(f"Tool host {key!r} is not available.")


@dataclass(frozen=True)
class ToolHostOption:
    """One selectable tool host. Labels are left to the UI."""

    key: str
    base_url: str
    host: str
    is_default: bool

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "base_url": self.base_url,
            "host": self.host,
            "is_default": self.is_default,
        }


def _clean_url(value: Optional[str]) -> Optional[str]:
    """Strip whitespace and trailing slashes; empty means unset."""
    if value is None:
        return None
    value = value.strip().rstrip("/")
    return value or None


def main_frontend_url() -> str:
    return _clean_url(os.getenv("FRONTEND_URL")) or _MAIN_DEFAULT_URL


def student_locked_frontend_url() -> Optional[str]:
    return _clean_url(os.getenv("VERTRETBAR_FRONTEND_URL"))


def _resolve(key: object) -> Optional[str]:
    if key == TOOL_HOST_MAIN:
        return main_frontend_url()
    if key == TOOL_HOST_STUDENT_LOCKED:
        return student_locked_frontend_url()
    return None


def is_tool_host_available(key: object) -> bool:
    return _resolve(key) is not None


def default_tool_host() -> str:
    """The student-locked host when configured, else the main host.

    Existing connections were all created on the student-locked host, so it
    stays the default wherever it exists.
    """
    if is_tool_host_available(TOOL_HOST_STUDENT_LOCKED):
        return TOOL_HOST_STUDENT_LOCKED
    return TOOL_HOST_MAIN


def validate_tool_host(key: object) -> str:
    """Return ``key`` if it names an available host, else raise.

    ``None`` selects :func:`default_tool_host`.
    """
    if key is None:
        return default_tool_host()
    if not is_tool_host_available(key):
        raise ToolHostUnavailable(key)
    return str(key)


def tool_base_url(key: object) -> str:
    """Base URL (scheme + host, no trailing slash) for a stored key.

    Raises :class:`ToolHostUnavailable` for an unknown or unconfigured key,
    so a connection never silently falls back to another host.
    """
    url = _resolve(key)
    if url is None:
        raise ToolHostUnavailable(key)
    return url


def public_host(key: object) -> str:
    """The bare host (with port, if any) of :func:`tool_base_url`."""
    base = tool_base_url(key)
    return urlsplit(base).netloc or base


def available_tool_hosts() -> List[ToolHostOption]:
    """The hosts this deployment can serve tool URLs on, in display order."""
    default = default_tool_host()
    options = []
    for key in TOOL_HOSTS:
        base = _resolve(key)
        if base is None:
            continue
        options.append(
            ToolHostOption(
                key=key,
                base_url=base,
                host=urlsplit(base).netloc or base,
                is_default=key == default,
            )
        )
    return options


def tool_host_for_request_host(host: Optional[str]) -> str:
    """Which tool host key a request host belongs to.

    Used to notice (and log) an LMS calling a connection on the other host;
    it never decides which host a connection uses.
    """
    # Lazy: the mailer package pulls in the mail client, which the
    # URL helpers above do not need.
    from mailer.branding import is_student_locked_host

    return TOOL_HOST_STUDENT_LOCKED if is_student_locked_host(host) else TOOL_HOST_MAIN
