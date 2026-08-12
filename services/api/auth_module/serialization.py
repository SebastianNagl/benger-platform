"""Defensive DB-value -> wire-format converters shared by the lean auth User
(auth_module.service.db_user_to_user) and the /auth/me hydration extras
(routers.auth.user). Guards are isinstance-based so non-ORM inputs (unit-test
Mocks, legacy JSON-as-string rows) degrade to None instead of raising.
"""

import json
from datetime import datetime
from typing import Optional


def iso_or_none(value) -> Optional[str]:
    """datetime -> ISO-8601 string; anything else (None, Mock, str) -> None."""
    return value.isoformat() if isinstance(value, datetime) else None


def ensure_dict(value) -> Optional[dict]:
    """Convert JSON string to dict if needed. Handles DB columns that may
    store JSON as a string instead of a native dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return None
