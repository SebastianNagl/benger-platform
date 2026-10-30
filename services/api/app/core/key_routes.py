"""Which routes an access key may call, and with which scopes.

``/api/v1`` is the small, versioned contract; its routes declare their
scopes themselves (``routers/v1/_deps.require_scope``). Every other route
of the app (the "full API", the same endpoints the browser uses) is open to
access keys only through the rule table below. ``middleware/key_gate.py``
looks up the matched route's rule for every request that carries a key.

Deny by default, like v1:

* A rule with ``scopes=None`` (:func:`never`) keeps keys out of a route
  (login, password, sign-up, LTI launches, SEB, test seeding, billing).
* Every platform route must resolve to a rule; :func:`assert_key_routes_covered`
  fails startup otherwise. Overlay packages declare rules for their own
  routes through the optional package attribute ``get_key_route_rules()``
  (core 2.45); an overlay route without a rule is closed to keys and logged.
* Rules only open a route. The handler's own checks (project roles, org
  admin, superadmin) still run for the key's user.

Rules match the route template (``/api/projects/{project_id}/tasks``), not
the raw path, with ``fnmatch`` patterns (``*`` also spans ``/``). The first
matching rule of the route's owner wins, so specific rules come first.

Project-restricted keys (a project list, or a group) may call a route only
when it names its project: a path parameter from :data:`PROJECT_PARAMS`
(resolved by ``middleware/key_gate.py``), or a query/body field listed in
the rule's ``bind``. Rules for account-level routes that touch no project
data carry ``neutral=True`` and stay open to restricted keys.

Routes that return task content need ``tasks:read_reference``: unlike
v1, the full API does not blind reference solutions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

PLATFORM_OWNER = "platform"
V1_PREFIX = "/api/v1"

READ_METHODS = frozenset({"GET"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ALL_METHODS = READ_METHODS | WRITE_METHODS

#: Path parameters that name (or lead to) a project. ``middleware/key_gate``
#: resolves each to its project id; overlays add more for their own routes
#: through :func:`register_project_param`.
PROJECT_PARAMS: Dict[str, str] = {
    "project_id": "project",
    "task_id": "task",
    "annotation_id": "annotation",
    "evaluation_id": "evaluation_run",
    "generation_id": "response_generation",
    "report_id": "report",
}


@dataclass(frozen=True)
class KeyRule:
    pattern: str
    methods: frozenset
    #: Scopes the key needs (all of them); ``()`` = any authenticated key,
    #: ``None`` = never for keys.
    scopes: Optional[Tuple[str, ...]]
    neutral: bool = False
    #: Extra project bindings: ``"query:<name>"`` or ``"body:<name>"`` (a
    #: string or a list of project ids in the JSON body).
    bind: Tuple[str, ...] = ()
    note: str = ""

    @property
    def allowed(self) -> bool:
        return self.scopes is not None

    def matches(self, method: str, template: str) -> bool:
        return method in self.methods and fnmatchcase(template, self.pattern)


def _methods(methods) -> frozenset:
    if methods in (None, "*"):
        return ALL_METHODS
    if isinstance(methods, str):
        if methods == "read":
            return READ_METHODS
        if methods == "write":
            return WRITE_METHODS
        return frozenset({methods.upper()})
    return frozenset(m.upper() for m in methods)


def allow(
    pattern: str,
    *scopes: str,
    methods="*",
    neutral: bool = False,
    bind: Sequence[str] = (),
    note: str = "",
) -> KeyRule:
    return KeyRule(pattern, _methods(methods), tuple(scopes), neutral, tuple(bind), note)


def never(pattern: str, methods="*", note: str = "") -> KeyRule:
    return KeyRule(pattern, _methods(methods), None, False, (), note)


def area(
    pattern: str,
    read: Sequence[str],
    write: Sequence[str],
    *,
    neutral: bool = False,
    bind: Sequence[str] = (),
) -> List[KeyRule]:
    """GET needs ``read``, every other method ``write``."""
    return [
        allow(pattern, *read, methods="read", neutral=neutral, bind=bind),
        allow(pattern, *write, methods="write", neutral=neutral, bind=bind),
    ]


def _flatten(items) -> List[KeyRule]:
    out: List[KeyRule] = []
    for item in items:
        if isinstance(item, KeyRule):
            out.append(item)
        else:
            out.extend(item)
    return out


REF = "tasks:read_reference"

# --------------------------------------------------------------------------- #
# Platform rules (first match wins)
# --------------------------------------------------------------------------- #

PLATFORM_RULES: List[KeyRule] = _flatten(
    [
        # -- probes: the gate lets keys through without checking them ------- #
        allow("/", methods="read", neutral=True),
        allow("/health", methods="read", neutral=True),
        allow("/healthz", methods="read", neutral=True),
        # -- never: sessions, credentials, onboarding, test/debug ---------- #
        allow("/api/auth/me", "account:read", methods="read", neutral=True),
        allow("/api/auth/me/contexts", "account:read", methods="read", neutral=True),
        allow(
            "/api/auth/me/exam-layout", "account:write", methods="PUT", neutral=True
        ),
        allow("/api/auth/me/ui-mode", "account:write", methods="PUT", neutral=True),
        allow("/api/auth/profile", "account:read", methods="read", neutral=True),
        allow("/api/auth/profile-history", "account:read", methods="read", neutral=True),
        allow("/api/auth/*-profile-status", "account:read", methods="read", neutral=True),
        never(
            "/api/auth/*",
            note="login, tokens, password, sign-up, verification and the profile "
            "update (it changes the e-mail address) stay browser-only",
        ),
        never("/api/test/*", note="test seeding"),
        never("/api/debug/*"),
        never("/performance/*"),
        never("/health/*", note="diagnostics; /health and /healthz accept keys"),
        never("/api/invitations/accept/*", note="accepting joins an account"),
        never("/api/invitations/token/*"),
        never("/api/invitations/validate/*"),
        never("/api/notifications/test*"),
        never("/api/notifications/*/test"),
        never("/api/notifications/test/*"),
        # -- access keys --------------------------------------------------- #
        allow("/api/access-keys/availability", methods="read", neutral=True),
        allow("/api/access-keys/scopes", methods="read", neutral=True),
        allow("/api/users/me/access-keys*", "keys:manage", neutral=True),
        allow("/api/organizations/{org_id}/access-keys*", "keys:manage", neutral=True),
        allow("/api/admin/access-keys*", "keys:manage", "admin:platform", neutral=True),
        # -- superadmin ----------------------------------------------------- #
        area("/api/admin/lti*", ["org:read"], ["org:manage"], neutral=True),
        allow("/api/admin/*", "admin:platform", neutral=True),
        allow("/api/feature-flags/me", methods="read", neutral=True),
        allow("/api/ext/feature-flags/me", methods="read", neutral=True),
        allow("/api/feature-flags*", "admin:platform", neutral=True),
        allow("/api/ext/feature-flags*", "admin:platform", neutral=True),
        allow("/api/organizations/manage/*", "admin:platform", neutral=True),
        allow("/api/users", "admin:platform", methods="read", neutral=True),
        allow("/api/users/{user_id}*", "admin:platform", neutral=True),
        allow("/storage/cdn/invalidate", "admin:platform", neutral=True),
        # -- account -------------------------------------------------------- #
        area(
            "/api/notifications*",
            ["account:read"],
            ["account:write"],
            neutral=True,
        ),
        area(
            "/api/users/api-keys*",
            ["models:read"],
            ["models:manage"],
            neutral=True,
        ),
        allow("/api/shares/discover", "projects:read", methods="read", neutral=True),
        area("/api/shares/{token}*", ["projects:read"], ["account:write"], neutral=True),
        area(
            "/api/projects/{project_id}/participation",
            ["account:read"],
            ["account:write"],
        ),
        allow("/api/student/*", "results:read", methods="read", neutral=True),
        allow("/api/dashboard/*", "results:read", methods="read", neutral=True),
        allow("/api/defaults/*", "projects:read", methods="read", neutral=True),
        # -- organizations -------------------------------------------------- #
        area(
            "/api/organizations/{org_id}/api-keys*",
            ["models:read"],
            ["models:manage"],
            neutral=True,
        ),
        area(
            "/api/organizations/{organization_id}/custom-models*",
            ["models:read"],
            ["models:manage"],
            neutral=True,
        ),
        area(
            "/api/organizations/{org_id}/storage-connections*",
            ["org:read"],
            ["org:manage"],
            neutral=True,
        ),
        area(
            "/api/invitations/organizations/{organization_id}/invitations*",
            ["org:read"],
            ["org:manage"],
            neutral=True,
        ),
        area("/api/invitations/{invitation_id}*", ["org:read"], ["org:manage"], neutral=True),
        area("/api/organizations*", ["org:read"], ["org:manage"], neutral=True),
        # -- models ---------------------------------------------------------- #
        area("/api/custom-models*", ["models:read"], ["models:manage"], neutral=True),
        allow("/api/llm_models/public/*", "models:read", methods="read", neutral=True),
        allow(
            "/api/llm-models/cost-estimate",
            "runs:read",
            methods="POST",
            bind=("body:project_id",),
        ),
        # -- marketplace (vendor listings) ----------------------------------- #
        area("/api/marketplace*", ["projects:read"], ["projects:write"], neutral=True),
        # -- files ----------------------------------------------------------- #
        area("/api/files*", ["files:read"], ["files:write"], neutral=True),
        allow("/storage/upload-url", "files:write", methods="POST", neutral=True),
        area("/storage/*", ["files:read"], ["files:write"], neutral=True),
        # -- leaderboards, reports ------------------------------------------ #
        allow("/api/leaderboards*", "results:read", methods="read", neutral=True),
        allow("/api/reports", "results:read", methods="read", neutral=True),
        allow("/api/reports/{report_id}/data", "results:read", methods="read"),
        # -- generation ------------------------------------------------------ #
        allow("/api/runs", "runs:read", methods="read", bind=("query:project_id",)),
        allow("/api/runs/generations/{generation_id}", "runs:read", methods="read"),
        allow("/api/generation/parse-metrics", "runs:read", methods="read"),
        allow("/api/generation/status/{generation_id}", "runs:read", methods="read"),
        area("/api/generation/{generation_id}*", ["runs:read"], ["runs:write"]),
        allow(
            "/api/generation-tasks/generation-result",
            "runs:read",
            REF,
            methods="read",
            bind=("query:task_id",),
        ),
        area("/api/generation-tasks/projects/{project_id}/*", ["runs:read"], ["runs:write"]),
        # -- evaluation ------------------------------------------------------ #
        allow(
            "/api/evaluations/run",
            "evaluations:run",
            methods="POST",
            bind=("body:project_id",),
        ),
        allow(
            "/api/evaluations/validate-config",
            "evaluations:read",
            methods="POST",
            neutral=True,
        ),
        allow("/api/evaluations/evaluation-types*", "evaluations:read", methods="read", neutral=True),
        allow("/api/evaluations/supported-metrics", "evaluations:read", methods="read", neutral=True),
        allow("/api/evaluations/sample-result", "results:read", REF, methods="read"),
        allow("/api/evaluations/", "evaluations:read", methods="read", bind=("query:project_id",)),
        allow(
            "/api/evaluations/export/{project_id}", "exports:read", "results:read", REF,
            methods="POST",
        ),
        allow(
            "/api/evaluations/projects/{project_id}/statistics",
            "results:read",
            methods="POST",
        ),
        area(
            "/api/evaluations/human/*",
            ["annotations:read"],
            ["annotations:write"],
            bind=("query:project_id", "body:project_id"),
        ),
        allow("/api/evaluations/{evaluation_id}/samples", "results:read", REF, methods="read"),
        allow("/api/evaluations/*/results*", "results:read", methods="read"),
        allow("/api/evaluations/results/{project_id}", "results:read", methods="read"),
        allow("/api/evaluations/significance/{project_id}", "results:read", methods="read"),
        allow("/api/evaluations/{evaluation_id}/*", "results:read", methods="read"),
        allow("/api/evaluations/run/results/*", "results:read", methods="read"),
        area("/api/evaluations/run/{evaluation_id}/*", ["evaluations:read"], ["evaluations:run"]),
        area("/api/evaluations/projects/{project_id}/*", ["evaluations:read"], ["evaluations:run"]),
        allow("/api/evaluations/evaluation/status/{evaluation_id}", "evaluations:read", methods="read"),
        allow("/api/evaluations/stream/{evaluation_id}", "evaluations:read", methods="read"),
        # -- legacy data API (tasks.py) -------------------------------------- #
        allow("/api/data/export", "exports:read", REF, methods="POST"),
        allow("/api/data/", REF, methods="read"),
        allow("/api/data/*", "tasks:write", methods="write"),
        allow("/api/task-rubrics/parse", "tasks:write", methods="POST", neutral=True),
        # -- projects: collection-level ------------------------------------- #
        allow("/api/projects/", "projects:read", methods="read"),
        allow("/api/projects/", "projects:write", methods="POST"),
        allow(
            "/api/projects/bulk-export*",
            "exports:read",
            REF,
            methods="POST",
            bind=("body:project_ids",),
        ),
        allow("/api/projects/bulk-*", "projects:write", methods="POST", bind=("body:project_ids",)),
        area("/api/projects/project-imports*", ["projects:read"], ["projects:write", "tasks:write"]),
        allow("/api/projects/tasks/bulk-metadata", "tasks:write", methods="PATCH"),
        allow("/api/projects/tasks/{task_id}", REF, methods="read"),
        area("/api/projects/tasks/{task_id}/annotations", ["annotations:read"], ["annotations:write"]),
        allow("/api/projects/tasks/{task_id}/metadata", "tasks:write", methods="PATCH"),
        allow("/api/projects/annotations/{annotation_id}", "annotations:write", methods="PATCH"),
        # -- projects: one project ------------------------------------------ #
        area(
            "/api/projects/{project_id}/exports*",
            ["exports:read", REF],
            ["exports:read", REF],
        ),
        area("/api/projects/{project_id}/imports*", ["projects:read"], ["projects:write", "tasks:write"]),
        area("/api/projects/{project_id}/cloud-imports", ["projects:read"], ["projects:write", "tasks:write"]),
        area("/api/projects/{project_id}/generation-config*", ["runs:read"], ["runs:write"]),
        allow("/api/projects/{project_id}/generation-status", "runs:read", methods="read"),
        allow("/api/projects/{project_id}/generations/*", "runs:read", methods="read"),
        allow("/api/projects/{project_id}/cohort-leaderboard", "results:read", methods="read"),
        allow("/api/projects/{project_id}/completion-stats", "results:read", methods="read"),
        allow("/api/projects/{project_id}/grading-feedback/*", "results:read", methods="read"),
        area("/api/projects/{project_id}/report*", ["results:read"], ["projects:write"]),
        area("/api/projects/{project_id}/shares*", ["projects:read"], ["projects:write"]),
        area("/api/projects/{project_id}/task-rubrics*", [REF], ["tasks:write"]),
        area("/api/projects/{project_id}/srs/*", ["annotations:read"], ["annotations:write"]),
        allow(
            "/api/projects/{project_id}/questionnaire-responses",
            "annotations:read",
            methods="read",
        ),
        allow("/api/projects/{project_id}/my-tasks", REF, methods="read"),
        allow("/api/projects/{project_id}/next", REF, methods="read"),
        allow("/api/projects/{project_id}/tasks/bulk-export", "exports:read", REF, methods="POST"),
        area(
            "/api/projects/{project_id}/tasks/{task_id}/checkpoint*",
            ["annotations:read"],
            ["annotations:write"],
        ),
        allow("/api/projects/{project_id}/tasks/{task_id}/draft", "annotations:write", methods="PUT"),
        allow(
            "/api/projects/{project_id}/tasks/{task_id}/questionnaire-response",
            "annotations:write",
            methods="POST",
        ),
        allow("/api/projects/{project_id}/tasks/{task_id}/skip", "annotations:write", methods="POST"),
        area("/api/projects/{project_id}/tasks/{task_id}/assignments*", ["tasks:read"], ["tasks:write"]),
        area("/api/projects/{project_id}/tasks*", [REF], ["tasks:write"]),
        allow("/api/projects/{project_id}/task-fields", "projects:read", methods="read"),
        allow("/api/projects/{project_id}/label-config/*", "projects:read", methods="read"),
        area("/api/projects/{project_id}*", ["projects:read"], ["projects:write"]),
    ]
)

_overlay_rules: Dict[str, List[KeyRule]] = {}


def register_overlay_rules(owner: str, rules: Iterable) -> None:
    """Rules an overlay package declares for its own routes. Entries are
    :class:`KeyRule` objects or dicts ``{pattern, scopes, methods?,
    neutral?, bind?}`` (``scopes: null`` = never)."""
    parsed: List[KeyRule] = []
    for item in rules or ():
        if isinstance(item, KeyRule):
            parsed.append(item)
            continue
        if not isinstance(item, dict) or "pattern" not in item or "scopes" not in item:
            raise ValueError(f"Invalid key route rule from {owner}: {item!r}")
        scopes = item.get("scopes")
        parsed.append(
            KeyRule(
                pattern=str(item["pattern"]),
                methods=_methods(item.get("methods", "*")),
                scopes=None if scopes is None else tuple(scopes),
                neutral=bool(item.get("neutral", False)),
                bind=tuple(item.get("bind") or ()),
                note=str(item.get("note") or ""),
            )
        )
    _overlay_rules[owner] = parsed


def unregister_overlay_rules(owner: str) -> None:
    _overlay_rules.pop(owner, None)


_overlay_params: Dict[str, Dict[str, str]] = {}


def register_project_param(name: str, kind: str, owner: str) -> None:
    """Teach the gate that path parameter ``name`` of ``owner``'s routes
    leads to a project via resolver ``kind`` (``middleware/key_gate``).
    Per owner, so an overlay's ``file_id`` never changes how platform
    routes with the same parameter name resolve."""
    _overlay_params.setdefault(owner, {})[name] = kind


def unregister_project_params(owner: str) -> None:
    _overlay_params.pop(owner, None)


def project_params_for(owner: str) -> Dict[str, str]:
    """The parameter map for ``owner``'s routes: the platform's, plus the
    owner's own (which cannot override a platform name)."""
    if owner == PLATFORM_OWNER or owner not in _overlay_params:
        return PROJECT_PARAMS
    return {**_overlay_params[owner], **PROJECT_PARAMS}


def rules_for(owner: str) -> List[KeyRule]:
    if owner == PLATFORM_OWNER:
        return PLATFORM_RULES
    return _overlay_rules.get(owner, [])


def resolve_rule(owner: str, method: str, template: str) -> Optional[KeyRule]:
    for rule in rules_for(owner):
        if rule.matches(method, template):
            return rule
    return None


# --------------------------------------------------------------------------- #
# Route index
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IndexedRoute:
    template: str
    method: str
    owner: str
    rule: Optional[KeyRule]
    regex: "re.Pattern"
    convertors: dict


def _owner_of(endpoint, packages: Sequence[Tuple[str, str]]) -> str:
    module = getattr(endpoint, "__module__", "") or ""
    for name, module_prefix in packages:
        if module == module_prefix or module.startswith(module_prefix + "."):
            return name
    return PLATFORM_OWNER


def _package_modules() -> List[Tuple[str, str]]:
    try:
        from extensions import _packages
    except Exception:  # pragma: no cover - extensions not importable
        return []
    out = []
    for name, package in _packages():
        out.append((name, getattr(package, "__name__", name)))
    return out


def _iter_api_routes(app):
    from fastapi.routing import APIRoute

    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # pragma: no cover - older FastAPI flattens itself
        for route in app.routes:
            if isinstance(route, APIRoute):
                yield route, route.path, route.methods
        return
    for context in iter_route_contexts(app.routes):
        original = context.original_route
        if isinstance(original, APIRoute):
            yield original, context.path, getattr(context, "methods", None) or original.methods


def build_index(app) -> List[IndexedRoute]:
    """Every HTTP API route outside ``/api/v1`` with its rule, in routing
    order."""
    from starlette.routing import compile_path

    packages = _package_modules()
    index: List[IndexedRoute] = []
    for original, path, methods in _iter_api_routes(app):
        if path == V1_PREFIX or path.startswith(V1_PREFIX + "/"):
            continue
        owner = _owner_of(original.endpoint, packages)
        regex, _fmt, convertors = compile_path(path)
        for method in sorted((methods or set()) - {"HEAD", "OPTIONS"}):
            index.append(
                IndexedRoute(
                    template=path,
                    method=method,
                    owner=owner,
                    rule=resolve_rule(owner, method, path),
                    regex=regex,
                    convertors=convertors,
                )
            )
    return index


def match(index: Sequence[IndexedRoute], method: str, path: str):
    """``(IndexedRoute, path_params)`` of the first route matching
    ``method`` and ``path``, or ``(None, None)``."""
    method = "GET" if method == "HEAD" else method
    for entry in index:
        if entry.method != method:
            continue
        found = entry.regex.match(path)
        if found is None:
            continue
        params = {}
        for key, value in found.groupdict().items():
            convertor = entry.convertors.get(key)
            params[key] = convertor.convert(value) if convertor else value
        return entry, params
    return None, None


def uncovered_routes(app, owner: Optional[str] = PLATFORM_OWNER) -> List[str]:
    """``METHOD path`` of every route of ``owner`` (None: any owner) without
    a rule."""
    return [
        f"{e.method} {e.template}"
        for e in build_index(app)
        if e.rule is None and (owner is None or e.owner == owner)
    ]


def assert_key_routes_covered(app) -> None:
    """Fail startup when a platform route has no key rule; log overlay
    routes without one (they stay closed to keys)."""
    offenders = uncovered_routes(app, PLATFORM_OWNER)
    if offenders:
        raise RuntimeError(
            "These routes have no access-key rule (add one to "
            "app/core/key_routes.PLATFORM_RULES, never() to keep keys out): "
            + "; ".join(offenders)
        )
    overlay = [
        f"{e.owner}: {e.method} {e.template}"
        for e in build_index(app)
        if e.rule is None and e.owner != PLATFORM_OWNER
    ]
    if overlay:
        logger.warning(
            "%d overlay routes declare no access-key rule and stay closed to keys: %s",
            len(overlay),
            "; ".join(overlay[:20]),
        )


def route_table(app, owner: Optional[str] = PLATFORM_OWNER) -> List[dict]:
    """The rule of every route, for the docs snapshot and the reference
    endpoint."""
    rows = []
    for e in build_index(app):
        if owner is not None and e.owner != owner:
            continue
        rule = e.rule
        rows.append(
            {
                "method": e.method,
                "path": e.template,
                "owner": e.owner,
                "keys": bool(rule and rule.allowed),
                "scopes": list(rule.scopes) if rule and rule.allowed else None,
                "neutral": bool(rule and rule.neutral),
            }
        )
    return rows
