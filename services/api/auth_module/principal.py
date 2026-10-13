"""Who is calling: a browser session or an access key.

``require_user`` / ``get_current_user`` store a :class:`Principal` on
``request.state.principal`` for every authenticated request. Handlers that
only need the user keep using the returned ``User``; v1 routes read the
principal to enforce scopes, project allowlists and key rate limits
(``routers/v1/_deps.py``).

Access keys travel only as ``Authorization: Bearer bgr_...``; a key in a
cookie or query string is never read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Tuple

from app.core.scopes import SESSION_SCOPES

API_KEY_BEARER_PREFIX = "Bearer bgr_"

__all__ = [
    "API_KEY_BEARER_PREFIX",
    "Principal",
    "SESSION_SCOPES",
    "extract_api_key",
    "get_principal",
    "session_principal",
]


@dataclass(frozen=True)
class Principal:
    kind: Literal["session", "api_key"]
    user_id: str
    api_key_id: Optional[str] = None
    key_prefix: Optional[str] = None
    scopes: frozenset = frozenset()
    project_ids: Optional[frozenset] = None
    organization_id: Optional[str] = None
    group_id: Optional[str] = None
    # (per minute, per day); None = deployment default.
    rate_limit: Tuple[Optional[int], Optional[int]] = (None, None)

    @property
    def is_api_key(self) -> bool:
        return self.kind == "api_key"


def session_principal(user_id: str) -> Principal:
    return Principal(kind="session", user_id=str(user_id), scopes=SESSION_SCOPES)


def extract_api_key(request: Any) -> Optional[str]:
    """The ``bgr_`` key from the Authorization header, or None.

    Defensive about the header type: unit tests pass ``Mock()`` requests,
    whose ``headers.get`` returns a Mock.
    """
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("Authorization") or headers.get("authorization")
    except Exception:
        return None
    if not isinstance(value, str) or not value.startswith(API_KEY_BEARER_PREFIX):
        return None
    return value[len("Bearer "):].strip() or None


def get_principal(request: Any) -> Optional[Principal]:
    """The principal stored by the auth dependencies, if any."""
    state = getattr(request, "state", None)
    value = getattr(state, "principal", None) if state is not None else None
    return value if isinstance(value, Principal) else None
