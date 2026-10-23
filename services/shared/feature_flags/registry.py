"""The feature flag registry: which flags exist, who owns them, and the
master flag of every extension package (core 2.42).

The ``feature_flags`` / ``feature_flag_targets`` tables only store each
flag's current state and allowlist; the registry says which names mean
something. Up to core 2.41 this module lived in ``benger_extended``; it is
back in the platform so the platform itself can register flags
(``public_api``) and switch whole extension packages at runtime.

Owners
    A flag belongs to the package that registered it (:data:`PLATFORM_OWNER`
    for the platform's own flags, else the package name, e.g.
    ``benger_extended``). Registering a name under a different owner than
    before raises ``ValueError``; the same owner may register again
    (idempotent, the definition is replaced).

Master flags
    Every loaded extension package gets one flag ``extension.<EXTENSION_ID>``
    (:func:`register_master_flag`), owned by the package itself. It decides
    whether the package is active for a request or task
    (``extension_activation``). A flag owned by a package P that has a master
    flag evaluates as ``master(P) AND flag`` (owner coupling, see
    ``service``); the master flag itself is not coupled to anything.

States:

* ``off`` - nobody gets the feature.
* ``everyone`` - everybody gets it, anonymous callers included.
* ``allowlist`` - only the listed users and members of the listed
  organizations get it. There is no implicit superadmin bypass; to try a
  feature, an admin allowlists their own user.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

STATE_OFF = "off"
STATE_EVERYONE = "everyone"
STATE_ALLOWLIST = "allowlist"
STATES: Tuple[str, ...] = (STATE_OFF, STATE_EVERYONE, STATE_ALLOWLIST)

# Error code for a request or job refused because its flag is off (API 404
# detail and worker result alike), and the worker result's message.
FEATURE_DISABLED = "feature_disabled"
FEATURE_DISABLED_MESSAGE = "Diese Funktion ist derzeit nicht verfügbar."

#: Owner of the platform's own flags.
PLATFORM_OWNER = "platform"

#: Prefix of the master flag names (``extension.<EXTENSION_ID>``).
MASTER_PREFIX = "extension."

#: Fallback default state of a master flag when the package declares no
#: ``DEFAULT_RUNTIME_STATE``: benger_extended stays on everywhere on deploy
#: (no behaviour change), every other package starts off.
MASTER_DEFAULT_FALLBACK: Dict[str, str] = {"benger_extended": STATE_EVERYONE}


@dataclass(frozen=True)
class FlagDefinition:
    name: str
    description: str
    default_state: str


PUBLIC_API = "public_api"


# ---------------------------------------------------------------------------
# Multi-owner registry
# ---------------------------------------------------------------------------

_lock = threading.RLock()
# name -> definition in registration order, and name -> owning package.
_definitions: Dict[str, FlagDefinition] = {}
_owners: Dict[str, str] = {}
# package name -> master flag name, and the reverse.
_masters: Dict[str, str] = {}
_master_packages: Dict[str, str] = {}
# master flag name -> EXTENSION_ID.
_master_ids: Dict[str, str] = {}


def register_flags(owner: str, flags: Iterable[FlagDefinition]) -> None:
    """Register ``flags`` as owned by ``owner`` (the registering package's
    name, or :data:`PLATFORM_OWNER`).

    Raises ``ValueError`` when a name is already registered by a different
    owner, when ``owner`` or a name is empty, or when a default state is not
    one of :data:`STATES`; nothing is registered in that case. The same owner
    may register a name again: the definition is replaced, the position in
    :func:`all_flags` is kept.
    """
    if not owner:
        raise ValueError("feature flags need an owner (the registering package's name)")
    incoming = list(flags)
    with _lock:
        for definition in incoming:
            if not isinstance(definition, FlagDefinition):
                raise TypeError(
                    f"register_flags expects FlagDefinition, got {type(definition).__name__}"
                )
            if not definition.name:
                raise ValueError("feature flag names must not be empty")
            if definition.default_state not in STATES:
                raise ValueError(
                    f"feature flag {definition.name!r}: default_state "
                    f"{definition.default_state!r} is not one of {STATES}"
                )
            current = _owners.get(definition.name)
            if current is not None and current != owner:
                raise ValueError(
                    f"feature flag {definition.name!r} is already registered by "
                    f"{current!r}; {owner!r} cannot register it too"
                )
        for definition in incoming:
            _definitions[definition.name] = definition
            _owners[definition.name] = owner


def unregister_flags(owner: str) -> None:
    """Forget every flag ``owner`` registered, its master flag included
    (tests and reloads only)."""
    with _lock:
        for name in [n for n, o in _owners.items() if o == owner]:
            del _definitions[name]
            del _owners[name]
            _master_ids.pop(name, None)
            package = _master_packages.pop(name, None)
            if package is not None:
                _masters.pop(package, None)


def all_flags() -> Tuple[FlagDefinition, ...]:
    """Every registered flag, in registration order."""
    return tuple(_definitions.values())


def flag(name: str) -> Optional[FlagDefinition]:
    """The registered definition of ``name``, or ``None``."""
    return _definitions.get(name)


def flag_owner(name: str) -> Optional[str]:
    """The package that registered ``name``, or ``None``."""
    return _owners.get(name)


# ---------------------------------------------------------------------------
# Master flags
# ---------------------------------------------------------------------------


def master_flag_name(extension_id: str) -> str:
    return f"{MASTER_PREFIX}{extension_id}"


def master_default_state(package: str, module=None) -> str:
    """The package's ``DEFAULT_RUNTIME_STATE``, else the fallback table."""
    declared = getattr(module, "DEFAULT_RUNTIME_STATE", None) if module is not None else None
    if declared:
        state = str(declared).strip().lower()
        if state not in STATES:
            raise ValueError(
                f"Extension package {package}: DEFAULT_RUNTIME_STATE {declared!r} "
                f"is not one of {STATES}"
            )
        return state
    return MASTER_DEFAULT_FALLBACK.get(package, STATE_OFF)


def register_master_flag(
    package: str, extension_id: str, default_state: Optional[str] = None
) -> str:
    """Register ``extension.<extension_id>`` as the master flag of
    ``package`` (owned by the package). Returns the flag name; idempotent."""
    name = master_flag_name(extension_id)
    state = default_state or MASTER_DEFAULT_FALLBACK.get(package, STATE_OFF)
    register_flags(
        package,
        [
            FlagDefinition(
                name,
                f"Erweiterungspaket {package} (Kennung {extension_id}): schaltet das "
                "ganze Paket zur Laufzeit an oder aus. Datenschutz-, Abrechnungs- "
                "und Notenübertragungsregeln des Pakets laufen unabhängig davon "
                "weiter.",
                state,
            )
        ],
    )
    with _lock:
        _masters[package] = name
        _master_packages[name] = package
        _master_ids[name] = str(extension_id)
    return name


def reset_master_flags() -> None:
    """Forget every master flag (the loaders call it before a (re)load, so
    a package that is no longer loaded keeps no master flag). The packages'
    other flags stay registered."""
    with _lock:
        for name in list(_master_packages):
            _definitions.pop(name, None)
            _owners.pop(name, None)
        _masters.clear()
        _master_packages.clear()
        _master_ids.clear()


def master_for_owner(package: Optional[str]) -> Optional[str]:
    """The master flag name of ``package``, or None (platform, or a package
    without a registered master flag)."""
    if not package or package == PLATFORM_OWNER:
        return None
    return _masters.get(package)


def is_master(name: str) -> bool:
    return name in _master_packages


def master_package(name: str) -> Optional[str]:
    """The package a master flag switches, or None."""
    return _master_packages.get(name)


def masters() -> Dict[str, str]:
    """``{package: master flag name}`` of every registered master flag."""
    return dict(_masters)


def master_extension_ids() -> Dict[str, str]:
    """``{master flag name: EXTENSION_ID}``."""
    return dict(_master_ids)


def coupled_master(name: str) -> Optional[str]:
    """The master flag ``name`` is coupled to (its owner's), or None."""
    if is_master(name):
        return None
    return master_for_owner(flag_owner(name))


# ---------------------------------------------------------------------------
# Platform flags
# ---------------------------------------------------------------------------


def _public_api_default() -> str:
    """``everyone`` when ``PUBLIC_API_ENABLED`` is on, else ``off``."""
    try:
        from app.core.config import get_settings

        enabled = bool(get_settings().public_api_enabled)
    except Exception:
        raw = os.environ.get("PUBLIC_API_ENABLED", "")
        enabled = raw.strip().lower() in ("1", "true", "yes", "on")
    return STATE_EVERYONE if enabled else STATE_OFF


def platform_flags() -> Tuple[FlagDefinition, ...]:
    return (
        FlagDefinition(
            PUBLIC_API,
            "API-Zugänge: persönliche und Organisations-Zugangsschlüssel und die "
            "öffentliche API unter /api/v1. Aus: Verwaltung, Einstiege und API "
            "antworten mit 404. Für Organisations-Schlüssel zählt die Freigabe "
            "der Organisation, für persönliche die der Person.",
            _public_api_default(),
        ),
    )


def register_platform_flags() -> None:
    """Register the platform's own flags (idempotent)."""
    register_flags(PLATFORM_OWNER, platform_flags())


register_platform_flags()
