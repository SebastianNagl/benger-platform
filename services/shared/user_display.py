"""How a user's name is shown to another user.

Accounts carry the real name, and most accounts also carry a pseudonym that
the app shows by default (``use_pseudonym``). Whether a viewer may see the
real name is decided by the caller (org admins, graders of a linked exam,
the user themself, ...); these helpers only turn that decision into a label,
so every surface applies the same precedence:

  * real name allowed    -> ``name``, else ``username``
  * real name not allowed -> ``pseudonym`` when ``use_pseudonym`` is on and a
    pseudonym exists, else ``name``, else ``username``

The second rule is the long-standing default of the platform and the
extended views: a user who turned the pseudonym off is shown by name.

Lists that hide LMS users' real names (``masked_name``) never fall back to
the name: they show the pseudonym or a neutral id-based label.

Pure functions (attribute access only), safe for the api and the workers.
"""

from __future__ import annotations

from typing import Any, Optional

_UNSET: Any = object()


def _pick(user: Any, attr: str, override: Any, default: Any = None) -> Any:
    if override is not _UNSET:
        return override
    if user is None:
        return default
    return getattr(user, attr, default)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def display_name(
    user: Any = None,
    reveal_real_name: bool = False,
    *,
    name: Any = _UNSET,
    username: Any = _UNSET,
    pseudonym: Any = _UNSET,
    use_pseudonym: Any = _UNSET,
) -> str:
    """Label for ``user`` as seen by a viewer.

    ``user`` is any object with ``name`` / ``username`` / ``pseudonym`` /
    ``use_pseudonym`` attributes (ORM row, auth schema, namespace). The
    keyword arguments override single attributes, for callers that only
    selected columns. Returns ``""`` when nothing usable is set.
    """
    real = _text(_pick(user, "name", name))
    login = _text(_pick(user, "username", username))
    if not reveal_real_name:
        alias = _text(_pick(user, "pseudonym", pseudonym))
        if alias and prefers_pseudonym(user, use_pseudonym=use_pseudonym):
            return alias
    return real or login or ""


def prefers_pseudonym(user: Any = None, *, use_pseudonym: Any = _UNSET) -> bool:
    """True when the user shows their pseudonym by default.

    NULL in the DB means the column default (pseudonym on).
    """
    wants_alias = _pick(user, "use_pseudonym", use_pseudonym, default=True)
    return wants_alias is None or bool(wants_alias)


def masked_name(
    user: Any = None,
    *,
    user_id: Any = _UNSET,
    pseudonym: Any = _UNSET,
) -> str:
    """Label for a user whose real name the viewer may not see.

    The pseudonym, or a neutral label built from the account id when the
    account has none, so a masked row never falls back to the real name or
    the login name.
    """
    alias = _text(_pick(user, "pseudonym", pseudonym))
    if alias:
        return alias
    uid = _text(_pick(user, "id", user_id)) or ""
    return f"User {uid[:8]}" if uid else "User"


def pseudonym_hint(
    user: Any = None,
    reveal_real_name: bool = False,
    *,
    pseudonym: Any = _UNSET,
) -> Optional[str]:
    """The pseudonym to show next to a revealed real name, else ``None``.

    Lets privileged views read "Real Name · Pseudonym" so they can match the
    pseudonym other users see.
    """
    if not reveal_real_name:
        return None
    return _text(_pick(user, "pseudonym", pseudonym))
