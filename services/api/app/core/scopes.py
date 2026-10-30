"""Scope vocabulary for access keys (``bgr_...``).

A scope names one capability of the API. Keys carry a list of granted
scopes; v1 routes declare the scopes they need through
``routers/v1/_deps.require_scope``, every other route through the rule table
in ``app/core/key_routes.py`` (checked by ``middleware/key_gate.py``).
Browser sessions are not scoped: their principal carries
:data:`SESSION_SCOPES`, which satisfies every check.

Scopes imply others (``submissions:write`` implies ``submissions:read``);
:func:`expand` computes the transitive closure. Overlays add their own
scopes through :func:`register_scopes` with the shape their
``get_api_scopes()`` returns::

    {"compliance:read": {"description": "...", "implies": []}}

Who may grant a scope is data too (``ScopeDef.grantable``):

* ``any``: every key.
* ``full_data_role``: keys whose effective role sees unblinded task data
  (personal keys, whose owner's per-project role still applies at request
  time, and organization keys with role CONTRIBUTOR).
* ``org_admin``: organization keys created by an org-wide admin.
* ``org_admin_role``: personal keys (the owner's own role still applies at
  request time) and organization keys with role ORG_ADMIN.
* ``personal_only``: personal keys only.
* ``superadmin``: personal keys created by a superadmin.

Errors use the structured shape ``{"detail": {"code", "message"}}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from fastapi import HTTPException, status


class _AllScopes(frozenset):
    """Sentinel scope set of a browser session: satisfies every check."""

    def __contains__(self, item) -> bool:  # pragma: no cover - trivial
        return True

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return "SESSION_SCOPES"


#: Scope set of session (cookie/JWT) principals. Compare with ``is``.
SESSION_SCOPES: frozenset = _AllScopes()

GRANTABLE_VALUES = (
    "any",
    "full_data_role",
    "org_admin",
    "org_admin_role",
    "personal_only",
    "superadmin",
)


@dataclass(frozen=True)
class ScopeDef:
    name: str
    description_de: str
    description_en: str
    description_fr: str
    implies: Tuple[str, ...] = ()
    grantable: str = "any"
    source: str = "platform"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description_de": self.description_de,
            "description_en": self.description_en,
            "description_fr": self.description_fr,
            "implies": list(self.implies),
            "grantable": self.grantable,
            "source": self.source,
        }


_BUILTIN: Tuple[ScopeDef, ...] = (
    ScopeDef(
        "org:read",
        "Organisation und eigene Mitgliedschaft lesen",
        "Read the organization and the key's own membership",
        "Lire l'organisation et l'appartenance de la clé",
    ),
    ScopeDef("projects:read", "Projekte lesen", "Read projects", "Lire les projets"),
    ScopeDef(
        "tasks:read",
        "Aufgaben lesen (ohne Lösungshinweise)",
        "Read tasks (without reference solutions)",
        "Lire les tâches (sans corrigés types)",
    ),
    ScopeDef(
        "tasks:read_reference",
        "Aufgaben mit Musterlösungen lesen",
        "Read tasks including reference solutions",
        "Lire les tâches avec les corrigés types",
        implies=("tasks:read",),
        grantable="full_data_role",
    ),
    ScopeDef(
        "submissions:read",
        "Einreichungen lesen",
        "Read submissions",
        "Lire les soumissions",
    ),
    ScopeDef(
        "submissions:write",
        "Einreichungen anlegen",
        "Create submissions",
        "Créer des soumissions",
        implies=("submissions:read",),
    ),
    ScopeDef(
        "systems:read",
        "Registrierte Systeme lesen",
        "Read registered systems",
        "Lire les systèmes enregistrés",
    ),
    ScopeDef(
        "systems:manage",
        "Systeme registrieren und verwalten",
        "Register and manage systems",
        "Enregistrer et gérer des systèmes",
        implies=("systems:read",),
    ),
    ScopeDef("runs:read", "Läufe lesen", "Read runs", "Lire les exécutions"),
    ScopeDef(
        "runs:write",
        "Läufe anlegen",
        "Create runs",
        "Créer des exécutions",
        implies=("runs:read",),
    ),
    ScopeDef(
        "evaluations:read",
        "Evaluationen lesen",
        "Read evaluations",
        "Lire les évaluations",
    ),
    ScopeDef(
        "evaluations:run",
        "Evaluationen starten",
        "Start evaluations",
        "Lancer des évaluations",
        implies=("evaluations:read",),
    ),
    ScopeDef("results:read", "Ergebnisse lesen", "Read results", "Lire les résultats"),
    ScopeDef(
        "exports:read", "Exporte abrufen", "Download exports", "Télécharger les exports"
    ),
    ScopeDef(
        "account:read",
        "Eigenes Konto, Benachrichtigungen und Einstellungen lesen",
        "Read the own account, notifications and settings",
        "Lire son compte, ses notifications et ses paramètres",
    ),
    ScopeDef(
        "account:write",
        "Eigene Einstellungen und Benachrichtigungen ändern, Projekten beitreten",
        "Change the own settings and notifications, join projects",
        "Modifier ses paramètres et notifications, rejoindre des projets",
        implies=("account:read",),
    ),
    ScopeDef(
        "org:manage",
        "Organisation verwalten (Mitglieder, Gruppen, Einladungen, Einstellungen)",
        "Manage the organization (members, groups, invitations, settings)",
        "Gérer l'organisation (membres, groupes, invitations, paramètres)",
        implies=("org:read",),
        grantable="org_admin_role",
    ),
    ScopeDef(
        "projects:write",
        "Projekte anlegen, konfigurieren, teilen, importieren und löschen",
        "Create, configure, share, import and delete projects",
        "Créer, configurer, partager, importer et supprimer des projets",
        implies=("projects:read",),
    ),
    ScopeDef(
        "tasks:write",
        "Aufgaben anlegen, bearbeiten, zuweisen und löschen",
        "Create, edit, assign and delete tasks",
        "Créer, modifier, attribuer et supprimer des tâches",
        implies=("tasks:read",),
    ),
    ScopeDef(
        "annotations:read",
        "Annotationen, Entwürfe, Reviews und Korrekturen lesen",
        "Read annotations, drafts, reviews and gradings",
        "Lire les annotations, brouillons, relectures et corrections",
    ),
    ScopeDef(
        "annotations:write",
        "Annotieren, Entwürfe speichern, reviewen und korrigieren",
        "Annotate, save drafts, review and grade",
        "Annoter, enregistrer des brouillons, relire et corriger",
        implies=("annotations:read",),
    ),
    ScopeDef(
        "models:read",
        "Modellkatalog und eigene Modelle lesen",
        "Read the model catalog and own models",
        "Lire le catalogue de modèles et ses propres modèles",
    ),
    ScopeDef(
        "models:manage",
        "Eigene Modelle (BYOM) und Anbieter-Schlüssel verwalten",
        "Manage own models (BYOM) and provider keys",
        "Gérer ses propres modèles (BYOM) et les clés des fournisseurs",
        implies=("models:read",),
    ),
    ScopeDef(
        "files:read",
        "Hochgeladene Dateien lesen",
        "Read uploaded files",
        "Lire les fichiers téléversés",
    ),
    ScopeDef(
        "files:write",
        "Dateien hochladen und löschen",
        "Upload and delete files",
        "Téléverser et supprimer des fichiers",
        implies=("files:read",),
    ),
    ScopeDef(
        "admin:platform",
        "Superadmin-Rechte der Plattform",
        "Platform superadmin rights",
        "Droits de superadministrateur de la plateforme",
        grantable="superadmin",
    ),
    ScopeDef(
        "keys:manage",
        "Eigene Zugangsschlüssel verwalten",
        "Manage the owner's own access keys",
        "Gérer ses propres clés d'accès",
        grantable="personal_only",
    ),
)

_registry: Dict[str, ScopeDef] = {s.name: s for s in _BUILTIN}

#: Ready-made scope bundles offered by the UI.
SCOPE_PRESETS: Dict[str, List[str]] = {
    "benchmark_read": [
        "org:read",
        "projects:read",
        "tasks:read",
        "runs:read",
        "evaluations:read",
        "results:read",
    ],
    "benchmark_submit": [
        "org:read",
        "projects:read",
        "tasks:read",
        "submissions:write",
        "systems:manage",
        "runs:write",
        "evaluations:run",
        "results:read",
    ],
    "org_full": [
        "org:read",
        "projects:read",
        "tasks:read_reference",
        "submissions:write",
        "systems:manage",
        "runs:write",
        "evaluations:run",
        "results:read",
        "exports:read",
    ],
    # The whole app as the key's user sees it (research pipelines, scripts).
    "full_access": [
        "account:write",
        "org:read",
        "projects:write",
        "tasks:read_reference",
        "tasks:write",
        "annotations:write",
        "models:manage",
        "runs:write",
        "evaluations:run",
        "results:read",
        "exports:read",
        "files:write",
    ],
}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def register_scopes(mapping: Mapping[str, Mapping], source: str = "overlay") -> None:
    """Add overlay scopes. Re-registering the same name replaces it; a
    built-in scope cannot be overridden."""
    for name, spec in (mapping or {}).items():
        if not isinstance(name, str) or not name or ":" not in name:
            raise ValueError(f"Invalid scope name: {name!r}")
        existing = _registry.get(name)
        if existing is not None and existing.source == "platform":
            raise ValueError(f"Scope {name!r} is built in and cannot be overridden")
        spec = spec or {}
        description = str(spec.get("description") or name)
        grantable = spec.get("grantable", "any")
        if grantable not in GRANTABLE_VALUES:
            raise ValueError(f"Scope {name!r}: unknown grantable {grantable!r}")
        _registry[name] = ScopeDef(
            name=name,
            description_de=str(spec.get("description_de") or description),
            description_en=str(spec.get("description_en") or description),
            description_fr=str(spec.get("description_fr") or description),
            implies=tuple(spec.get("implies") or ()),
            grantable=grantable,
            source=source,
        )


def unregister_scopes(names: Iterable[str]) -> None:
    """Remove overlay scopes (tests)."""
    for name in names:
        existing = _registry.get(name)
        if existing is not None and existing.source != "platform":
            del _registry[name]


def get_scope(name: str) -> Optional[ScopeDef]:
    return _registry.get(name)


def all_scopes() -> List[ScopeDef]:
    return list(_registry.values())


def expand(granted: Iterable[str]) -> frozenset:
    """Granted scopes plus everything they imply, transitively."""
    if granted is SESSION_SCOPES:
        return SESSION_SCOPES
    seen: set = set()
    stack = list(granted or ())
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        scope = _registry.get(name)
        if scope is not None:
            stack.extend(scope.implies)
    return frozenset(seen)


def scopes_satisfied(granted: Iterable[str], needed: Iterable[str]) -> bool:
    """Whether ``granted`` (after implications) covers every ``needed``."""
    if granted is SESSION_SCOPES:
        return True
    return set(needed or ()) <= expand(granted)


@dataclass(frozen=True)
class GrantContext:
    """Who is granting: decides the ``org_admin`` scopes."""

    is_superadmin: bool = False
    is_org_admin: bool = False
    #: Scopes of the access key that is creating this key (``keys:manage``),
    #: or None when a browser session creates it. A key never grants more
    #: than it holds.
    creator_scopes: Optional[frozenset] = None


_FULL_DATA_ROLES = ("CONTRIBUTOR", "ORG_ADMIN")


def _role_value(role) -> Optional[str]:
    if role is None:
        return None
    return str(getattr(role, "value", role)).upper()


def validate_scopes_for_grant(
    ctx: GrantContext,
    owner_type: str,
    org_role,
    scopes: Iterable[str],
) -> List[str]:
    """Validate ``scopes`` for a new or edited key; return them sorted and
    de-duplicated. Raises 422 ``unknown_scope`` or 400 ``scope_not_grantable``.
    """
    requested = sorted(set(scopes or ()))
    unknown = [s for s in requested if s not in _registry]
    if unknown:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_scope",
            f"Unknown scope(s): {', '.join(unknown)}",
        )
    role = _role_value(org_role)
    for name in requested:
        grantable = _registry[name].grantable
        allowed = True
        if grantable == "personal_only":
            allowed = owner_type == "user"
        elif grantable == "full_data_role":
            allowed = owner_type == "user" or role in _FULL_DATA_ROLES
        elif grantable == "org_admin":
            allowed = owner_type == "org" and (ctx.is_org_admin or ctx.is_superadmin)
        elif grantable == "org_admin_role":
            allowed = owner_type == "user" or role == "ORG_ADMIN"
        elif grantable == "superadmin":
            allowed = owner_type == "user" and ctx.is_superadmin
        if allowed and ctx.creator_scopes is not None:
            allowed = scopes_satisfied(ctx.creator_scopes, (name,))
        if not allowed:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "scope_not_grantable",
                f"Scope {name} cannot be granted to this key",
            )
    return requested


def scope_catalog() -> dict:
    """Definitions and presets for the management UI."""
    return {
        "scopes": [s.to_dict() for s in all_scopes()],
        "presets": {k: list(v) for k, v in SCOPE_PRESETS.items()},
    }
