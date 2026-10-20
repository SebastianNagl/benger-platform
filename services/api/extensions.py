"""
Extension loader for BenGER extension packages.

At startup, loads every configured extension package (``BENGER_EXTENSIONS``,
default ``benger_extended``) through the shared registry
(``services/shared/extension_registry.py``) and registers their routers,
field types and services. If no package is installed, all extension points
are no-ops and the platform runs as the community edition.

What an API-side package may provide (all optional):

- ``get_routers()``: ``[(router, include_router kwargs)]``. Packages other
  than ``benger_extended`` must mount under ``/api/ext/<EXTENSION_ID>``.
- ``get_hooks()``: ``{hook key: callable}``; the keys and how several
  packages' implementations are combined are published in :data:`HOOK_SPECS`.
- ``get_field_type_registrations()``: label-studio field types.
- ``configure_app(app)``: app-level configuration (middleware).
- ``get_api_scopes()`` / ``get_v1_routers()``: API-key scopes and routers
  for the public ``/api/v1`` surface (collected by :func:`get_api_scopes_all`
  and :func:`get_v1_routers_all`).

Runtime switch (core 2.42): every loaded package gets a master feature flag
``extension.<EXTENSION_ID>`` (default: the optional package attribute
``DEFAULT_RUNTIME_STATE``, else ``everyone`` for benger_extended and ``off``
for the others). Hooks run per their class in :data:`HOOK_GATING`, package
routers answer 404 ``feature_disabled`` while the package is inactive for
the caller, except the ``(METHOD, path template)`` pairs in the optional
package attribute ``UNGATED_ROUTES`` (see ``extension_activation``).

``_extended`` stays the alias of the loaded ``benger_extended`` module
(``None`` when it is not loaded); tests monkeypatch it with stand-ins.
"""

import importlib  # noqa: F401  (tests patch extensions.importlib.import_module)
import inspect
import logging
import os

import extension_activation as activation
import extension_registry as registry
from core_version import CORE_API_VERSION, extended_required  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

_extended = None

# --------------------------------------------------------------------------- #
# Hook merge policies. A hook key may be implemented by several packages; the
# policy says how the platform combines their answers. Packages run in hook
# order: benger_extended first, then the others in load order.
# --------------------------------------------------------------------------- #
#: Every implementation runs, in order; an exception propagates to the caller.
CALL_ALL = "call_all"
#: Every implementation runs, each one isolated (logged, never raised).
CALL_ALL_ISOLATED = "call_all_isolated"
#: The answers (sets) are united.
UNION = "union"
#: The answers (dicts) are merged; on an overlapping key the earlier package
#: wins and the overlap is logged.
DICT_FIRST_WINS = "dict_first_wins"
#: Exactly one package may implement the hook. A second implementer fails
#: startup when any implementer is required, else it is logged and the first
#: one wins.
SINGLE_OWNER = "single_owner"

HOOK_SPECS = {
    "on_annotation_created": CALL_ALL,
    "on_draft_saved": CALL_ALL,
    "after_eval_config_save": CALL_ALL,
    "validate_signup": CALL_ALL,
    "after_user_signup": CALL_ALL,
    "after_user_login": CALL_ALL,
    "on_ops_event": CALL_ALL_ISOLATED,
    "tasks_with_feedback_for_user": UNION,
    "tasks_with_evaluation_for_user": UNION,
    "privacy_protected_member_ids": UNION,
    "lti_protected_org_ids": UNION,
    "task_grade_summaries_for_user": DICT_FIRST_WINS,
    "dispatch_lti_grade_sync": SINGLE_OWNER,
    "resend_all_lti_grades": SINGLE_OWNER,
    "project_real_name_viewer": SINGLE_OWNER,
    "project_real_name_user_ids": SINGLE_OWNER,
    "projects_real_name_user_ids": SINGLE_OWNER,
    "lti_anonymization_policy": SINGLE_OWNER,
    "public_api_enabled": SINGLE_OWNER,
    # Reserved for the next phases; the platform does not call them yet.
    "on_submission_finalized": CALL_ALL,
    "assessment_transition": SINGLE_OWNER,
    "external_run_policy": SINGLE_OWNER,
}

# --------------------------------------------------------------------------- #
# Hook gating classes (core 2.42). Every key in HOOK_SPECS has one; the check
# runs at import time (:func:`_validate_hook_gating`). See extension_activation:
# ALWAYS runs whenever the package is loaded (privacy, billing, LMS grade
# sync, monitoring, exam timer integrity), POLICY_GLOBAL while its master flag
# is not ``off``,
# GATED only when the package is active for the caller of the current
# request/task context. Moving a privacy or billing hook to GATED needs a
# test change (tests/unit/test_extension_runtime_gating.py pins the map).
# --------------------------------------------------------------------------- #
HOOK_GATING = {
    # Timer integrity: these close the open exam timer session on submit and
    # mirror drafts into it. The auto-submit task keeps running while the
    # package is off, so skipping them could hand in a stale draft over the
    # real submission.
    "on_annotation_created": activation.ALWAYS,
    "on_draft_saved": activation.ALWAYS,
    "after_eval_config_save": activation.ALWAYS,
    "validate_signup": activation.POLICY_GLOBAL,
    "after_user_signup": activation.POLICY_GLOBAL,
    "after_user_login": activation.GATED,
    "on_ops_event": activation.ALWAYS,
    "tasks_with_feedback_for_user": activation.GATED,
    "tasks_with_evaluation_for_user": activation.GATED,
    "privacy_protected_member_ids": activation.ALWAYS,
    "lti_protected_org_ids": activation.ALWAYS,
    "task_grade_summaries_for_user": activation.GATED,
    "dispatch_lti_grade_sync": activation.ALWAYS,
    "resend_all_lti_grades": activation.ALWAYS,
    "project_real_name_viewer": activation.ALWAYS,
    "project_real_name_user_ids": activation.ALWAYS,
    "projects_real_name_user_ids": activation.ALWAYS,
    "lti_anonymization_policy": activation.ALWAYS,
    "public_api_enabled": activation.ALWAYS,
    "on_submission_finalized": activation.GATED,
    "assessment_transition": activation.GATED,
    "external_run_policy": activation.GATED,
}

#: Keys in :data:`HOOK_SPECS` without a platform caller yet. An overlay's
#: handshake test should expect every other key to be implemented.
PENDING_HOOK_KEYS = frozenset(
    {"on_submission_finalized", "assessment_transition", "external_run_policy"}
)

#: Routers of packages other than benger_extended must mount below this.
EXTENSION_ROUTE_ROOT = "/api/ext"
#: ``error`` (default) fails startup on a route two packages both claim when
#: the later one is required; ``warn`` only logs it.
ROUTE_POLICY_ENV = "BENGER_EXTENSION_ROUTE_POLICY"


def load_extended():
    """Load every configured extension package. Returns True if any loaded.

    Runs the registry (import, namespace guard, ``COMPATIBLE_CORE_VERSIONS``
    handshake and ``REQUIRES_EXTENSIONS`` check per package, in order),
    registers the packages' field types and validates hook ownership.

    With a package required (``BENGER_REQUIRE_EXTENSIONS``, or the legacy
    ``BENGER_REQUIRE_EXTENDED`` for every configured package) an import
    failure or a handshake mismatch raises instead of degrading to the
    community edition, so a broken overlay fails the rollout loudly rather
    than shipping with its features silently missing.
    """
    global _extended
    from feature_flags import registry as flag_registry

    registry.reset()
    flag_registry.reset_master_flags()
    _extended = None
    loaded = registry.load_all()
    _extended = registry.module("benger_extended")
    if not loaded:
        logger.info("BenGER community edition (no extension package loaded)")
        return False

    _register_master_flags(loaded)
    _register_extension_field_types()
    _validate_hook_ownership()
    _register_extension_scopes()

    logger.info(
        "BenGER extension packages loaded: %s (core API %s)",
        [ext.name for ext in loaded],
        CORE_API_VERSION,
    )
    return True


def _validate_hook_gating():
    """Every hook key needs a gating class (and only known classes)."""
    missing = sorted(set(HOOK_SPECS) - set(HOOK_GATING))
    extra = sorted(set(HOOK_GATING) - set(HOOK_SPECS))
    bad = sorted(k for k, v in HOOK_GATING.items() if v not in activation.GATING_CLASSES)
    if missing or extra or bad:
        raise RuntimeError(
            f"HOOK_GATING out of sync with HOOK_SPECS: missing {missing}, "
            f"unknown {extra}, invalid classes {bad}"
        )


_validate_hook_gating()


def _register_master_flags(loaded):
    """Register ``extension.<EXTENSION_ID>`` for every loaded package
    (``extension_activation.register_master_flags``)."""
    activation.register_master_flags(loaded)


def is_loaded(name):
    """True when the package ``name`` is loaded in this process.

    ``benger_extended`` follows the ``_extended`` alias (so a test stand-in
    counts); the other packages follow the registry.
    """
    if name == "benger_extended":
        return _extended is not None
    return registry.is_loaded(name)


def _packages():
    """``[(package_name, module)]`` in hook order: benger_extended first
    (the ``_extended`` alias is authoritative), then the other loaded
    packages in load order."""
    packages = []
    if _extended:
        packages.append(("benger_extended", _extended))
    for ext in registry.loaded():
        if ext.name == "benger_extended":
            continue
        packages.append((ext.name, ext.module))
    return packages


def _hook_impls(key):
    """``[(package_name, callable)]`` implementing ``key``, in hook order.

    Each package's ``get_hooks()`` runs on every call (as the single-package
    loader did); an exception from it propagates to the wrapper, whose
    try/except shell decides what that means for the caller. Packages that
    are not active for the hook's gating class (:data:`HOOK_GATING`) in the
    current context are skipped (core 2.42).
    """
    gating = HOOK_GATING.get(key, activation.GATED)
    impls = []
    for name, package in _packages():
        get_hooks = getattr(package, "get_hooks", None)
        if get_hooks is None:
            continue
        if not activation.package_active(name, gating):
            continue
        hook = (get_hooks() or {}).get(key)
        if hook:
            impls.append((name, hook))
    return impls


def _single_hook(key):
    """The owning package's implementation of a SINGLE_OWNER hook, or None."""
    impls = _hook_impls(key)
    return impls[0][1] if impls else None


def _validate_hook_ownership():
    """Warn about unknown hook keys; enforce SINGLE_OWNER at load time."""
    implementers = {}
    for name, package in _packages():
        get_hooks = getattr(package, "get_hooks", None)
        if get_hooks is None:
            continue
        try:
            keys = list((get_hooks() or {}).keys())
        except Exception:
            logger.exception("Extension package %s: get_hooks() failed", name)
            continue
        unknown = sorted(k for k in keys if k not in HOOK_SPECS)
        if unknown:
            logger.warning(
                "Extension package %s registers hooks the platform does not "
                "call: %s",
                name,
                unknown,
            )
        for key in keys:
            implementers.setdefault(key, []).append(name)
    for key, names in implementers.items():
        if HOOK_SPECS.get(key) != SINGLE_OWNER or len(names) < 2:
            continue
        message = (
            f"Hook {key!r} may have one implementer, but {names} all register it."
        )
        if any(registry.is_required(n) for n in names):
            raise RuntimeError(f"{message} Refusing to start.")
        logger.warning("%s Using %s.", message, names[0])


def _register_extension_field_types():
    """Forward every package's label-studio field types into the validator.

    Packages declare ``get_field_type_registrations()`` returning
    ``{"types": [...], "named_types": [...]}``. This is the only way custom
    XML elements (e.g. ``<Angabe>``, ``<Gliederung>``) get accepted by the
    validator. The registrations of all packages are united.
    """
    for name, package in _packages():
        getter = getattr(package, "get_field_type_registrations", None)
        if getter is None:
            continue
        try:
            registrations = getter() or {}
            from services.label_config.parser import LabelConfigParser
            from services.label_config.validator import LabelConfigValidator

            types = registrations.get("types", [])
            LabelConfigValidator.register_field_types(
                types,
                named_types=registrations.get("named_types"),
            )
            # Mirror the registration into the parser so extracted field lists
            # (used by /api/projects/{id}/evaluation-fields) include the same
            # extension-contributed tags the validator now accepts.
            LabelConfigParser.register_field_types(types)
            if types:
                logger.info(
                    "Registered %d extension field types from %s: %s",
                    len(types),
                    name,
                    sorted(types),
                )
        except Exception:
            logger.exception("Failed to register extension field types of %s", name)


def configure_app(app):
    """Let every loaded package configure the FastAPI app itself.

    Called once from ``main.py`` after :func:`include_extension_routers`,
    before the app serves. Routers go through :func:`get_routers`; this
    hook is for what a router cannot do (middleware, e.g. the extended
    monitoring's HTTP metrics). No-op in the community edition. Packages run
    in load order, each isolated: a failing hook is logged and never stops
    the app from starting.
    """
    for name, package in _packages():
        hook = getattr(package, "configure_app", None)
        if hook is None:
            continue
        try:
            hook(app)
        except Exception:
            logger.exception("Extension package %s: configure_app hook failed", name)


def emit_ops_event(event, **labels):
    """Report an operational event to the extensions (monitoring).

    Events and their labels (aggregate values only, never a recipient,
    address or token):

    - ``mail_outcome``: ``mail_type`` (``verification``, ``password_reset``)
      and ``outcome`` (``sent``, ``failed``) for mail the API sends inline.
      Mail sent by the workers is observed through Celery signals instead.
    - ``health_check_failed``: ``dependency`` (``redis``, ``database``,
      ``celery``) when ``/health`` answers 503 or degraded.

    Optional hook ``on_ops_event(event, **labels)``, CALL_ALL_ISOLATED. No-op
    in the community edition; never raises, because monitoring must not
    break the caller.
    """
    try:
        impls = _hook_impls("on_ops_event")
    except Exception:
        logger.exception("on_ops_event hook failed for %s (hook lookup)", event)
        return
    for name, hook in impls:
        try:
            hook(event, **labels)
        except Exception:
            logger.exception("on_ops_event hook failed for %s (package %s)", event, name)


# --------------------------------------------------------------------------- #
# Routers
# --------------------------------------------------------------------------- #
def get_extended_routers():
    """Return list of (router, kwargs) tuples of ``benger_extended`` only.

    Kept for callers and tests of the single-package loader;
    :func:`include_extension_routers` mounts every package.
    """
    if _extended and hasattr(_extended, "get_routers"):
        return _extended.get_routers()
    return []


def _route_signatures(routes, prefix=""):
    """``{(method, path)}`` of ``routes``, nested includes flattened.

    Starlette >= 1.0 keeps an ``include_router`` call as one wrapper route
    (``original_router`` + ``include_context.prefix``) instead of copying the
    sub-routes, so the wrapper is unwrapped here; older versions and plain
    ``APIRoute`` lists are read as they are.
    """
    signatures = set()
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            context = getattr(route, "include_context", None)
            inner_prefix = getattr(context, "prefix", "") or ""
            signatures |= _route_signatures(
                getattr(inner, "routes", []), prefix + inner_prefix
            )
            continue
        path = getattr(route, "path", None)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or {"*"}
        for method in methods:
            signatures.add((str(method).upper(), prefix + path))
    return signatures


def _router_signatures(router, kwargs):
    prefix = (kwargs or {}).get("prefix", "") or ""
    return _route_signatures(getattr(router, "routes", []), prefix)


def _routers_of(package):
    getter = getattr(package, "get_routers", None)
    if getter is None:
        return []
    return list(getter() or [])


def _check_route_prefix(name, short, kwargs, required):
    """Packages other than benger_extended mount under ``/api/ext/<short>``.

    Returns True when the router may be mounted. A violation raises for a
    required package and is logged (router skipped) for an optional one.
    """
    if name == "benger_extended":
        return True
    expected = f"{EXTENSION_ROUTE_ROOT}/{short}"
    prefix = (kwargs or {}).get("prefix", "") or ""
    if prefix == expected or prefix.startswith(expected + "/"):
        return True
    message = (
        f"Extension package {name} mounts a router with prefix {prefix!r}; "
        f"packages other than benger_extended must mount under {expected!r}."
    )
    if required:
        raise RuntimeError(f"{message} Refusing to start.")
    logger.warning("%s Router skipped.", message)
    return False


def ungated_routes(package):
    """The package's ``UNGATED_ROUTES`` as ``{(METHOD, path template)}``."""
    out = set()
    for entry in getattr(package, "UNGATED_ROUTES", None) or ():
        method, path = entry
        out.add((str(method).upper(), str(path)))
    return out


def _check_ungated_routes(name, ungated, signatures, required):
    """Every ``UNGATED_ROUTES`` entry must name a route the package mounts:
    a typo would silently gate a webhook. Unknown entries fail startup for a
    required package and are logged otherwise."""
    unknown = sorted(ungated - signatures)
    if not unknown:
        return
    message = (
        f"Extension package {name} lists UNGATED_ROUTES it does not mount: "
        f"{unknown[:10]}."
    )
    if required:
        raise RuntimeError(f"{message} Refusing to start.")
    logger.error(message)


def include_extension_routers(app):
    """Mount every loaded package's routers on ``app``.

    Order: benger_extended first, then the other packages in load order.
    Enforces the prefix policy (:func:`_check_route_prefix`) and detects a
    ``(method, path)`` two packages both claim: that fails startup when the
    later package is required and ``BENGER_EXTENSION_ROUTE_POLICY`` is
    ``error`` (the default), else it is logged (FastAPI keeps the first
    route, so the later one would be dead). A path a package shares with the
    platform itself is logged as well.

    Every router gets ``Depends(require_extension_active(package))`` (core
    2.42): 404 ``feature_disabled`` while the package's master flag is off
    for the caller, except the routes the package lists in
    ``UNGATED_ROUTES`` (``(METHOD, full path template)``; webhooks, LMS
    launches and other routes that authenticate on their own).
    """
    from fastapi import Depends

    from feature_flags.deps import require_extension_active

    policy = (os.getenv(ROUTE_POLICY_ENV) or "error").strip().lower()
    platform_signatures = _route_signatures(getattr(app, "routes", []))
    claimed = {}
    mounted = 0
    for name, package in _packages():
        short = registry.short_name(name, package)
        required = registry.is_required(name)
        ungated = ungated_routes(package)
        package_signatures = set()
        for router, kwargs in _routers_of(package):
            kwargs = dict(kwargs or {})
            if not _check_route_prefix(name, short, kwargs, required):
                continue
            signatures = _router_signatures(router, kwargs)
            platform_overlap = sorted(signatures & platform_signatures)
            if platform_overlap:
                logger.warning(
                    "Extension package %s declares routes the platform already "
                    "serves (the platform's win): %s",
                    name,
                    platform_overlap[:10],
                )
            overlap = sorted(
                (sig, claimed[sig]) for sig in signatures if sig in claimed and claimed[sig] != name
            )
            if overlap:
                message = (
                    f"Extension package {name} declares routes another package "
                    f"already mounted: {overlap[:10]}."
                )
                if policy == "error" and required:
                    raise RuntimeError(
                        f"{message} Refusing to start ({ROUTE_POLICY_ENV}=error)."
                    )
                logger.warning("%s The earlier package's routes win.", message)
            for sig in signatures:
                claimed.setdefault(sig, name)
            package_signatures |= signatures
            kwargs["dependencies"] = [
                Depends(require_extension_active(name, ungated)),
                *(kwargs.get("dependencies") or ()),
            ]
            app.include_router(router, **kwargs)
            mounted += 1
        _check_ungated_routes(name, ungated, package_signatures, required)
    if mounted:
        logger.info("Mounted %d extension routers", mounted)
    return mounted


def get_api_scopes_all():
    """Union of every package's ``get_api_scopes()`` (``{scope: spec}``).

    A scope two packages both declare keeps the earlier package's spec and
    is logged. Empty in the community edition.
    """
    scopes = {}
    for name, package in _packages():
        getter = getattr(package, "get_api_scopes", None)
        if getter is None:
            continue
        for scope, spec in dict(getter() or {}).items():
            if scope in scopes:
                logger.warning(
                    "Extension package %s redeclares API scope %r; keeping the "
                    "earlier declaration",
                    name,
                    scope,
                )
                continue
            scopes[scope] = spec
    return scopes


def _register_extension_scopes():
    """Add every package's ``get_api_scopes()`` to the API-key scope vocabulary
    (``app.core.scopes``), attributed to the declaring package. A package
    without the attribute declares nothing; a failing getter is logged and
    skipped so one overlay cannot keep the app from starting."""
    try:
        from app.core.scopes import register_scopes
    except ImportError:
        return
    for name, package in _packages():
        getter = getattr(package, "get_api_scopes", None)
        if getter is None:
            continue
        try:
            register_scopes(dict(getter() or {}), source=name)
        except Exception:
            logger.exception("Extension package %s: get_api_scopes() failed", name)


def get_v1_routers_all():
    """Concatenation of every package's ``get_v1_routers()``, in hook order.

    Each router's kwargs carry ``Depends(require_extension_active_v1(pkg))``
    (core 2.42): the package's master flag, evaluated for the access key's
    organization (org keys) or the caller."""
    from fastapi import Depends

    from feature_flags.deps import require_extension_active_v1

    routers = []
    for name, package in _packages():
        getter = getattr(package, "get_v1_routers", None)
        if getter is None:
            continue
        for router, kwargs in list(getter() or []):
            kwargs = dict(kwargs or {})
            kwargs["dependencies"] = [
                Depends(require_extension_active_v1(name)),
                *(kwargs.get("dependencies") or ()),
            ]
            routers.append((router, kwargs))
    return routers


# --------------------------------------------------------------------------- #
# Hooks
# --------------------------------------------------------------------------- #
def on_annotation_created(db, task_id, user_id, annotation_id, project_id):
    """Hook called after an annotation is created (CALL_ALL).

    Extended package uses this to complete timer sessions and clean up drafts.
    No-op if no package implements it.
    """
    for _name, hook in _hook_impls("on_annotation_created"):
        hook(db, task_id, user_id, annotation_id, project_id)


def on_draft_saved(db, task_id, user_id, project_id, draft_result):
    """Hook called after a draft is saved (CALL_ALL).

    Extended package uses this to mirror drafts to timer sessions
    for server-side auto-submit. No-op if no package implements it.
    """
    for _name, hook in _hook_impls("on_draft_saved"):
        hook(db, task_id, user_id, project_id, draft_result)


def run_after_eval_config_save(db, project, config):
    """Hook called after a project's evaluation_config is persisted (CALL_ALL).

    Extended package uses this to derive proprietary project flags from
    the new evaluation_configs (e.g. korrektur_enabled, korrektur_config).
    Receives the SQLAlchemy session, the Project model instance, and the
    just-saved config dict. The hook may mutate the project; the caller
    is responsible for the final commit.

    No-op if no package registers the hook.
    """
    for _name, hook in _hook_impls("after_eval_config_save"):
        hook(db, project, config)


def validate_signup(db, user_create):
    """Hook called during /auth/signup before the user row is created (CALL_ALL).

    Extended edition uses this to enforce its research-data-consent policy
    (raises HTTPException(400) if user_create.research_data_consent_accepted
    is not True). No-op in community edition: the column stays NULL and
    no checkbox is rendered, which is the correct default there.
    """
    for _name, hook in _hook_impls("validate_signup"):
        hook(db, user_create)


def after_user_signup(db, user, signup_context):
    """Hook called during /auth/signup after the user row is committed (CALL_ALL).

    ``signup_context`` is a dict describing the request origin
    (``{"host": ..., "origin": ...}``) derived server-side from the request
    headers. The extended edition uses this to onboard a student who signed up
    via a student-locked host (vertretbar.net): set ``preferred_ui_mode`` and
    attach the Vertretbar organization membership. The hook may mutate ``user``
    and persist its own rows; it owns its commit.

    No-op in community edition (no student-locked product) or when no
    package registers the hook.
    """
    for _name, hook in _hook_impls("after_user_signup"):
        hook(db, user, signup_context)


def after_user_login(db, user, login_context):
    """Hook called during /auth/login after credentials are verified (CALL_ALL).

    ``user`` is the ORM ``models.User`` row (NOT the Pydantic auth schema;
    the hook may mutate and persist it, mirroring the signup hook contract).
    ``login_context`` mirrors the signup hook's context (``{"host": ...,
    "origin": ...}``, derived server-side from the request headers). The
    extended edition uses this to onboard EXISTING accounts that sign in on a
    student-locked host (vertretbar.net): pre-existing platform users never
    pass through /auth/signup, so the signup hook alone leaves them without
    the Vertretbar org membership that tier metering and cohort views key on.
    The hook may mutate ``user`` and persist its own rows; it owns its commit.

    No-op in community edition or when no package registers the hook.
    """
    for _name, hook in _hook_impls("after_user_login"):
        hook(db, user, login_context)


def tasks_with_feedback_for_user(db, project_id, user_id, task_ids):
    """Return the subset of task_ids on which the given user has feedback (UNION).

    "Feedback" is whatever proprietary signal the extended package owns
    (Korrektur comments on the user's annotations, falloesung grades, etc.).
    Used by `/my-tasks` to render a "feedback available" badge.

    Returns an empty set when no package implements it: the community
    edition has no human-feedback workflow, so no badge.
    """
    if not task_ids:
        return set()
    found = set()
    for _name, hook in _hook_impls("tasks_with_feedback_for_user"):
        result = hook(db, project_id, user_id, list(task_ids))
        found |= set(result or ())
    return found


def tasks_with_evaluation_for_user(db, project_id, user_id, task_ids):
    """Return the subset of task_ids on which the user has any evaluation (UNION).

    "Evaluation" = at least one TaskEvaluation row on one of the user's
    annotations: immediate-eval, LLM-judge, or deterministic metric. Broader
    than `tasks_with_feedback_for_user` (which is human-Korrektur only). Used by
    `/my-tasks` to render an "evaluation available" badge and let the row open
    the submission+scores modal.

    Returns an empty set when no package implements it: the community
    edition has no evaluation-on-own-annotation workflow surfaced in Meine
    Aufgaben.
    """
    if not task_ids:
        return set()
    found = set()
    for _name, hook in _hook_impls("tasks_with_evaluation_for_user"):
        result = hook(db, project_id, user_id, list(task_ids))
        found |= set(result or ())
    return found


def task_grade_summaries_for_user(db, project_id, user_id, task_ids):
    """Return ``{task_id: summary}`` of the user's own grades on these tasks
    (DICT_FIRST_WINS).

    The extended edition grades submissions (KI and human Korrektur) and
    hands back one headline per submitted task, e.g. ``{"status",
    "grade_points", "passed", "total_score", "total_max", "has_human",
    ...}``; the values are opaque to the platform, which passes them through
    to the "Meine Aufgaben" rows. Only keys from ``task_ids`` are kept; when
    two packages answer for the same task the earlier package's answer is
    kept and the overlap is logged.

    Returns ``{}`` when no package implements it (the community edition has
    no grades on own submissions) and when a hook fails: a missing grade in
    a row must never break the list. The hooks run in a savepoint so a
    failed query leaves the caller's transaction usable.
    """
    if not task_ids:
        return {}
    try:
        impls = _hook_impls("task_grade_summaries_for_user")
        if impls:
            wanted = {str(t) for t in task_ids}
            merged = {}
            for name, hook in impls:
                result = _run_hook_in_savepoint(
                    db, hook, project_id, user_id, list(task_ids)
                )
                for key, value in (result or {}).items():
                    key = str(key)
                    if key not in wanted or not isinstance(value, dict):
                        continue
                    if key in merged:
                        logger.warning(
                            "task_grade_summaries_for_user: %s also answered "
                            "task %s; keeping the earlier answer",
                            name,
                            key,
                        )
                        continue
                    merged[key] = value
            return merged
    except Exception:
        logger.exception(
            "task_grade_summaries_for_user hook failed for project %s", project_id
        )
    return {}


# --------------------------------------------------------------------------- #
# LMS (LTI) connection hooks. The extended edition implements them with sync
# SQLAlchemy sessions and never commits; async callers pass a sync session via
# ``await db.run_sync(lambda s: extensions.<hook>(s, ...))``. A failing hook
# is logged and answered with the safe value documented per wrapper, never
# raised into the request. Hooks that query through ``db`` run inside a
# savepoint (:func:`_run_hook_in_savepoint`): a failed query rolls back to it,
# so the caller's transaction stays usable and the safe value really is the
# answer instead of a later ``InFailedSqlTransaction``.
# --------------------------------------------------------------------------- #
def _run_hook_in_savepoint(db, hook, *args, **kwargs):
    """Call ``hook(db, *args, **kwargs)`` inside ``db.begin_nested()``.

    Sessions without savepoints (``None``, test doubles) call the hook
    directly. Exceptions propagate after the rollback to the savepoint; the
    wrappers turn them into their safe values.
    """
    begin_nested = getattr(db, "begin_nested", None)
    if begin_nested is None:
        return hook(db, *args, **kwargs)
    with begin_nested():
        return hook(db, *args, **kwargs)


def dispatch_lti_grade_sync(sync_id):
    """Queue the grade push for one ``lti_grade_syncs`` row right away
    (SINGLE_OWNER).

    Returns True when the owning package accepted the dispatch. False in
    the community edition (no LMS grade transfer) and when the hook fails;
    the row then waits for the next sweep.
    """
    try:
        hook = _single_hook("dispatch_lti_grade_sync")
        if hook:
            return bool(hook(sync_id))
    except Exception:
        logger.exception("dispatch_lti_grade_sync hook failed for %s", sync_id)
    return False


#: ``status`` of :func:`resend_all_lti_grades` when the hook failed.
RESEND_ALL_FAILED = "failed"


def resend_all_lti_grades(db, registration_id):
    """Queue "resend all grades" for one LMS connection (SINGLE_OWNER).

    The extended hook checks the connection, counts what goes out and
    queues the transfers of every current grade of every activity, also
    unchanged ones. It returns a dict with ``status``:

    - ``queued``: the transfers are queued;
    - ``scheduled``: the queue was unreachable, so the hook marked the rows
      in ``db`` and committed them; the hourly sweep sends them;
    - ``nothing``: no grade to send;
    - ``refused``: with ``code``, ``message`` and ``http_status`` (unknown
      or switched-off connection, inactive organization, no switched-on
      deployment).

    The other keys are counts (``activities``, ``students``,
    ``transfers``, ``skipped``, ...). Call it before staging the caller's
    own changes: the hook may commit ``db``.

    Returns None in the community edition (no hook). A failing hook is
    logged, the session is rolled back, and the answer is
    ``{"status": "failed"}``. Not run in a savepoint, because the hook may
    commit.
    """
    try:
        hook = _single_hook("resend_all_lti_grades")
    except Exception:
        logger.exception("resend_all_lti_grades hook lookup failed")
        return {"status": RESEND_ALL_FAILED}
    if hook is None:
        return None
    try:
        result = hook(db, str(registration_id))
    except Exception:
        logger.exception("resend_all_lti_grades hook failed for %s", registration_id)
        rollback = getattr(db, "rollback", None)
        if rollback is not None:
            try:
                rollback()
            except Exception:
                logger.exception("rollback after resend_all_lti_grades failed")
        return {"status": RESEND_ALL_FAILED}
    if not isinstance(result, dict):
        logger.error(
            "resend_all_lti_grades hook returned %r for %s", type(result), registration_id
        )
        return {"status": RESEND_ALL_FAILED}
    return dict(result)


def privacy_protected_member_ids(db, organization_id, user_ids, *, group_ids=None):
    """Subset of ``user_ids`` that count as LMS users (UNION).

    An LMS user is an account an LMS launch provisioned (even after an admin
    unlink or once its connection is deleted, since it keeps the LMS clear
    name: ``users.lms_provisioned_at``), or an existing account with a live
    link to an LMS identity. ``organization_id`` limits the check to
    connections owned by that org, plus accounts a deleted connection of that
    org created (``users.lms_origin_org_id``); None means any connection
    counts. ``group_ids`` (keyword, only with an org) further limits it to
    that org's connections scoped to one of these groups; org-wide
    connections, connections of other groups and deleted connections do not
    count.

    Calling rule for a list of users:

    - mask ``privacy_protected_member_ids(db, None, ids)``;
    - a viewer with admin rights in org X may unmask
      ``privacy_protected_member_ids(db, X, ids)``; superadmins unmask all;
    - a group admin (without org admin rights) of groups G in org X may
      unmask ``privacy_protected_member_ids(db, X, ids, group_ids=G)``: the
      LMS users of their groups' connections, whoever is in the group.

    So an LMS user of org B who is also a member of org A stays masked in
    org A's lists, even for A's admins. Project-scoped views use
    :func:`project_real_name_user_ids` instead of the org admin check.

    Community edition: empty set (there are no LMS accounts). If a hook
    fails, every call fails closed: the None call returns every given id
    (everyone masked) and an org call returns an empty set (nobody
    unmasked), so a failure never reveals a name. A group call also returns
    an empty set when a hook does not accept ``group_ids``, when
    ``group_ids`` is empty or when no org is given.
    """
    ids = {str(uid) for uid in (user_ids or ()) if uid is not None}
    if not ids:
        return set()
    kwargs = {}
    if group_ids is not None:
        groups = sorted({str(gid) for gid in group_ids if gid})
        if not groups or organization_id is None:
            return set()
        kwargs["group_ids"] = groups
    try:
        found = set()
        for _name, hook in _hook_impls("privacy_protected_member_ids"):
            result = _run_hook_in_savepoint(
                db, hook, organization_id, sorted(ids), **kwargs
            )
            found |= {str(uid) for uid in (result or ())}
        return found & ids
    except Exception:
        logger.exception("privacy_protected_member_ids hook failed")
        return ids if organization_id is None else set()


def project_real_name_viewer(db, viewer, project_id):
    """True when ``viewer`` may see real names of the LMS accounts on
    ``project_id`` (for example staff who grade the linked exam)
    (SINGLE_OWNER).

    False in the community edition and when the hook fails.
    """
    try:
        hook = _single_hook("project_real_name_viewer")
        if hook:
            return bool(_run_hook_in_savepoint(db, hook, viewer, project_id))
    except Exception:
        logger.exception(
            "project_real_name_viewer hook failed for project %s", project_id
        )
    return False


def project_real_name_user_ids(db, viewer, project_id, user_ids):
    """Subset of ``user_ids`` whose real names ``viewer`` may see on
    ``project_id`` (SINGLE_OWNER).

    Finer than :func:`project_real_name_viewer`: a person counts only when
    they hold an identity on a connection that links an activity to the
    project, the viewer may see that connection's students (staff who may
    grade the exam in its org, its course teachers) and the person takes
    part in the exam (a launch of one of its activities on that connection,
    or, for identities from before the participation table, a submission or
    assignment on the project). Project-scoped lists use this set to
    unmask, so an org-wide member list never unmasks the whole university.

    Community edition: empty set. If the hook fails the set is empty too,
    so nobody is unmasked.
    """
    ids = {str(uid) for uid in (user_ids or ()) if uid is not None}
    if not ids or viewer is None or not project_id:
        return set()
    try:
        hook = _single_hook("project_real_name_user_ids")
        if hook:
            result = _run_hook_in_savepoint(
                db, hook, viewer, str(project_id), sorted(ids)
            )
            return {str(uid) for uid in (result or ())} & ids
    except Exception:
        logger.exception(
            "project_real_name_user_ids hook failed for project %s", project_id
        )
    return set()


def projects_real_name_user_ids(db, viewer, user_ids_by_project):
    """Bulk form of :func:`project_real_name_user_ids` (SINGLE_OWNER).

    ``user_ids_by_project`` maps project ids to the user ids to check there;
    the result maps every given project id to the subset whose real names
    ``viewer`` may see on it. Lists call this once per page instead of once
    per row.

    Uses the bulk hook when it is registered, else calls the per-project
    hook for each project. Community edition: empty sets. If the bulk hook
    fails, every project gets an empty set (nobody unmasked).
    """
    wanted = {}
    for project_id, user_ids in (user_ids_by_project or {}).items():
        if not project_id:
            continue
        ids = {str(uid) for uid in (user_ids or ()) if uid is not None}
        wanted[str(project_id)] = ids
    empty = {pid: set() for pid in wanted}
    pending = {pid: ids for pid, ids in wanted.items() if ids}
    if not pending or viewer is None:
        return empty
    if not _packages():
        return empty
    try:
        hook = _single_hook("projects_real_name_user_ids")
    except Exception:
        logger.exception("projects_real_name_user_ids hook lookup failed")
        return empty
    if hook is None:
        result = dict(empty)
        for pid, ids in pending.items():
            result[pid] = project_real_name_user_ids(db, viewer, pid, ids)
        return result
    try:
        raw = _run_hook_in_savepoint(
            db, hook, viewer, {pid: sorted(ids) for pid, ids in pending.items()}
        )
    except Exception:
        logger.exception("projects_real_name_user_ids hook failed")
        return empty
    result = dict(empty)
    for pid, ids in pending.items():
        got = (raw or {}).get(pid) if isinstance(raw, dict) else None
        result[pid] = {str(uid) for uid in (got or ())} & ids
    return result


def lti_anonymization_policy(db, user_id):
    """Extra anonymization rules for one account (SINGLE_OWNER).

    Returns ``{"implicit_org_ids": set[str], "blockers": list[str]}``:
    ``implicit_org_ids`` are orgs whose ANNOTATOR membership the LMS launch
    added on its own (it does not count as "member elsewhere");
    ``blockers`` are reasons that forbid anonymizing the account.

    Community edition: no implicit orgs, no blockers. If the hook fails the
    answer carries the blocker ``policy_unavailable``, so nothing is
    anonymized on an unchecked policy.
    """
    policy = {"implicit_org_ids": set(), "blockers": []}
    try:
        hook = _single_hook("lti_anonymization_policy")
        if hook:
            result = _run_hook_in_savepoint(db, hook, user_id) or {}
            policy["implicit_org_ids"] = {
                str(oid) for oid in (result.get("implicit_org_ids") or ())
            }
            policy["blockers"] = [
                str(code) for code in (result.get("blockers") or ())
            ]
    except Exception:
        logger.exception("lti_anonymization_policy hook failed for %s", user_id)
        return {"implicit_org_ids": set(), "blockers": ["policy_unavailable"]}
    return policy


async def public_api_enabled(db, user, *, organization_id=None):
    """Whether the access-key feature (key management and ``/api/v1``) is
    available for ``user`` (SINGLE_OWNER, core 2.38).

    ``db`` is an ``AsyncSession``; ``user`` may be ``None`` (anonymous) or
    the service account behind an organization key, in which case
    ``organization_id`` names the key's organization. The hook may be sync
    or async and overrides the platform. Without an implementation the
    platform's ``public_api`` feature flag decides (core 2.42; its default
    follows ``PUBLIC_API_ENABLED``); if the hook or the evaluation fails the
    feature counts as off.
    """
    try:
        hook = _single_hook("public_api_enabled")
        if hook:
            result = hook(db, user, organization_id=organization_id)
            if inspect.isawaitable(result):
                result = await result
            return bool(result)
    except Exception:
        logger.exception("public_api_enabled hook failed")
        return False
    try:
        from feature_flags import service as flag_service

        return await flag_service.public_api_enabled(
            db, user, organization_id=organization_id
        )
    except Exception:
        logger.exception("public_api flag evaluation failed")
        return False


def _protected_org_ids(db):
    """Union of every package's ``lti_protected_org_ids`` answer; raises
    when one of them fails (the callers decide what that means)."""
    found = set()
    for _name, hook in _hook_impls("lti_protected_org_ids"):
        found |= {str(oid) for oid in (hook(db) or ())}
    return found


def lti_protected_org_ids(db):
    """Orgs whose LMS connections only superadmins may manage (UNION).

    Community edition: empty set. If a hook fails the result is empty too,
    so use it for filtering and display only; gate access with
    :func:`is_lti_protected_org`, which fails closed.
    """
    try:
        return _protected_org_ids(db)
    except Exception:
        logger.exception("lti_protected_org_ids hook failed")
    return set()


def is_lti_protected_org(db, organization_id):
    """True when the LMS connections of ``organization_id`` are
    superadmin-only. False in the community edition; True when a hook
    fails, so a broken hook never opens those connections to org admins.
    """
    if not organization_id:
        return False
    try:
        return str(organization_id) in _protected_org_ids(db)
    except Exception:
        logger.exception("lti_protected_org_ids hook failed")
        return True


def lti_protected_org_subset(db, organization_ids):
    """The orgs among ``organization_ids`` whose LMS connections are
    superadmin-only (see :func:`is_lti_protected_org`).

    Fails closed like :func:`is_lti_protected_org`: when a hook fails,
    every given org counts as protected, so an access decision never opens
    those connections' exams to the wrong people.
    """
    ids = {str(oid) for oid in (organization_ids or ()) if oid}
    if not ids:
        return set()
    try:
        return _protected_org_ids(db) & ids
    except Exception:
        logger.exception("lti_protected_org_ids hook failed")
        return ids
