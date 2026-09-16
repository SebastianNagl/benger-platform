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
        wants_alias = _pick(user, "use_pseudonym", use_pseudonym, default=True)
        # NULL in the DB means the column default (pseudonym on).
        if alias and (wants_alias is None or bool(wants_alias)):
            return alias
    return real or login or ""


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
