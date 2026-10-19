"""The legal system an organization teaches and examines in.

Stored as ``organizations.settings["jurisdiction"]`` (JSON column, no
migration). It decides which jurisdiction-specific project types and
templates the project wizard offers to the organization's members, e.g.
the French exam types (commentaire d'arrêt, dissertation, ...) that the
extended edition registers for ``"FR"``. Organizations without the key are
German, the platform's historical default.
"""

from typing import Any, Mapping, Optional

JURISDICTIONS = ("DE", "FR")
DEFAULT_JURISDICTION = "DE"
SETTINGS_KEY = "jurisdiction"


def is_valid_jurisdiction(value: Any) -> bool:
    return isinstance(value, str) and value in JURISDICTIONS


def org_jurisdiction(settings: Optional[Mapping[str, Any]]) -> str:
    """The organization's jurisdiction, falling back to the default for
    missing settings, a missing key or an unknown stored value."""
    if isinstance(settings, Mapping):
        value = settings.get(SETTINGS_KEY)
        if is_valid_jurisdiction(value):
            return value
    return DEFAULT_JURISDICTION


def with_jurisdiction(settings: Optional[Mapping[str, Any]], jurisdiction: str) -> dict:
    """A copy of ``settings`` with the jurisdiction set (other keys kept)."""
    if not is_valid_jurisdiction(jurisdiction):
        raise ValueError(f"unknown jurisdiction {jurisdiction!r}")
    out = dict(settings) if isinstance(settings, Mapping) else {}
    out[SETTINGS_KEY] = jurisdiction
    return out
