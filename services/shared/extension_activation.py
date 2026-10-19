"""Runtime activation of extension packages (core 2.41).

A process-level load (``BENGER_EXTENSIONS``, see ``extension_registry``)
means a package is *installed*. Whether it is *active* is decided per
request or task by its master feature flag ``extension.<EXTENSION_ID>``
(``feature_flags.registry.register_master_flag``), evaluated for the caller
in the current :class:`ExtContext`.

Gating classes
--------------
Turning a package off must never weaken privacy or billing rules it
enforces, so every surface (hook key, worker getter, router) has a class:

``ALWAYS``
    Runs whenever the package is loaded (privacy hooks, billing/settlement
    getters, LMS grade sync, ...). Never checks the flag.
``POLICY_GLOBAL``
    Runs while the master state is anything but ``off``; needs no user
    (``validate_signup``, ``after_user_signup``).
``GATED``
    Runs only when the package is active for the caller of the current
    context. Everything else.

Context
-------
:class:`ExtContext` (``user_id``, ``org_ids``, ``project_id``, ``kind``,
``memo``) lives in a ContextVar. The API sets it per request
(``middleware/extension_context.py``, user from the JWT, no DB access), the
workers per task (``worker_celery.py``, from the ``benger_ext_ctx`` message
header). Rules for GATED:

* listed user, or any active membership of the user in a listed org (the
  rule every flag uses);
* ``org_ids`` (an organization key, a project's organizations) replaces the
  membership lookup: any listed org among them counts;
* anonymous or system context: only ``everyone`` counts.

``memo`` is a plain dict shared by reference, so ``run_in_threadpool``
copies of the context (and nested :func:`use_context` blocks) reuse the one
snapshot read, the membership query and the results of the request.

The community edition (no package loaded, no master flag registered)
returns without touching Redis or the database.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

ALWAYS = "always"
POLICY_GLOBAL = "policy_global"
GATED = "gated"
GATING_CLASSES = (ALWAYS, POLICY_GLOBAL, GATED)

PLATFORM = "platform"

KIND_REQUEST = "request"
KIND_TASK = "task"
KIND_SYSTEM = "system"

#: Celery message header carrying ``{"user_id", "project_id"}``.
CELERY_HEADER = "benger_ext_ctx"

_SNAPSHOT = "snapshot"


@dataclass
class ExtContext:
    user_id: Optional[str] = None
    org_ids: Optional[FrozenSet[str]] = None
    project_id: Optional[str] = None
    kind: str = KIND_SYSTEM
    memo: Dict[Any, Any] = field(default_factory=dict)


_current: ContextVar[Optional[ExtContext]] = ContextVar("benger_ext_ctx", default=None)


def current_context() -> ExtContext:
    """The context of this request/task; a fresh system context outside one
    (not stored, so its memo lives for one call)."""
    ctx = _current.get()
    return ctx if ctx is not None else ExtContext()


def set_context(ctx: Optional[ExtContext]) -> Token:
    return _current.set(ctx)


def reset_context(token: Token) -> None:
    _current.reset(token)


def new_context(
    *,
    user_id: Optional[str] = None,
    org_ids: Optional[Iterable[str]] = None,
    project_id: Optional[str] = None,
    kind: str = KIND_SYSTEM,
) -> ExtContext:
    return ExtContext(
        user_id=str(user_id) if user_id else None,
        org_ids=frozenset(str(o) for o in org_ids if o) if org_ids is not None else None,
        project_id=str(project_id) if project_id else None,
        kind=kind,
    )


_UNSET: Any = object()


@contextlib.contextmanager
def use_context(
    *,
    user_id: Any = _UNSET,
    org_ids: Any = _UNSET,
    project_id: Any = _UNSET,
    kind: Optional[str] = None,
    inherit: bool = True,
) -> Iterator[ExtContext]:
    """Run the block in a derived context.

    With ``inherit`` (default) the current context's user, kind and memo are
    kept and only the given fields change; a ``project_id`` resolves to the
    project's organizations lazily (and replaces the membership lookup).
    """
    parent = _current.get()
    base = parent if (inherit and parent is not None) else ExtContext()
    ctx = ExtContext(
        user_id=base.user_id if user_id is _UNSET else (str(user_id) if user_id else None),
        org_ids=(
            base.org_ids
            if org_ids is _UNSET
            else (frozenset(str(o) for o in org_ids if o) if org_ids is not None else None)
        ),
        project_id=(
            base.project_id
            if project_id is _UNSET
            else (str(project_id) if project_id else None)
        ),
        kind=kind or base.kind,
        memo=base.memo if (inherit and parent is not None) else {},
    )
    if project_id is not _UNSET and org_ids is _UNSET:
        # A new project replaces inherited org ids; they resolve from it.
        ctx.org_ids = None
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


# --------------------------------------------------------------------------- #
# Loading (memoized per context)
# --------------------------------------------------------------------------- #
def _session():
    from database import SessionLocal

    return SessionLocal()


def _snapshot(ctx: ExtContext) -> Dict[str, Dict]:
    memo = ctx.memo
    snapshot = memo.get(_SNAPSHOT)
    if snapshot is not None:
        return snapshot
    from feature_flags import service

    snapshot = service.cache_get()
    if snapshot is None:
        db = None
        try:
            db = _session()
            snapshot = service.load_snapshot_sync(db, use_cache=False, sync=False)
            service.cache_set(snapshot)
        except Exception:
            logger.warning(
                "extension activation: flag snapshot unavailable, using the "
                "registered defaults",
                exc_info=True,
            )
            snapshot = service.defaults_snapshot()
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
    memo[_SNAPSHOT] = snapshot
    return snapshot


def prime_snapshot(snapshot: Dict[str, Dict], ctx: Optional[ExtContext] = None) -> None:
    """Store an already loaded snapshot in the context's memo (the async
    API lane loads it with its own session)."""
    ctx = ctx or _current.get()
    if ctx is not None and snapshot is not None:
        ctx.memo.setdefault(_SNAPSHOT, snapshot)


def _membership_org_ids(ctx: ExtContext, user_id: str) -> FrozenSet[str]:
    key = ("memberships", user_id)
    if key in ctx.memo:
        return ctx.memo[key]
    from feature_flags.service import select_membership_org_ids

    db = None
    orgs: FrozenSet[str] = frozenset()
    try:
        db = _session()
        orgs = frozenset(str(r[0]) for r in db.execute(select_membership_org_ids(user_id)).all())
    except Exception:
        logger.warning("extension activation: membership lookup failed", exc_info=True)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    ctx.memo[key] = orgs
    return orgs


def project_org_ids(project_id: str, db=None) -> FrozenSet[str]:
    """The organizations a project belongs to (``ProjectOrganization``)."""
    from sqlalchemy import select

    from project_models import ProjectOrganization

    stmt = select(ProjectOrganization.organization_id).where(
        ProjectOrganization.project_id == str(project_id)
    )
    own = db is None
    session = _session() if own else db
    try:
        return frozenset(str(r[0]) for r in session.execute(stmt).all() if r[0])
    finally:
        if own:
            try:
                session.close()
            except Exception:
                pass


def _context_org_ids(ctx: ExtContext) -> Optional[FrozenSet[str]]:
    """The context's org override (explicit, or resolved from its project),
    or None when the caller's memberships decide."""
    if ctx.org_ids is not None:
        return ctx.org_ids
    if not ctx.project_id:
        return None
    key = ("project_orgs", ctx.project_id)
    if key not in ctx.memo:
        try:
            ctx.memo[key] = project_org_ids(ctx.project_id)
        except Exception:
            logger.warning("extension activation: project org lookup failed", exc_info=True)
            ctx.memo[key] = frozenset()
    return ctx.memo[key]


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def _master_for(package: str) -> Optional[str]:
    from feature_flags import registry

    return registry.master_for_owner(package)


def master_state(package: str, ctx: Optional[ExtContext] = None) -> Optional[str]:
    """The master flag's state of ``package`` (None without a master flag)."""
    master = _master_for(package)
    if master is None:
        return None
    from feature_flags import service

    entry = service.entry_of(_snapshot(ctx or current_context()), master) or {}
    return entry.get("state")


def package_active(package: Optional[str], gating: str = GATED) -> bool:
    """Whether a package the caller already knows to be loaded may run a
    surface of class ``gating`` in the current context.

    The platform and ALWAYS surfaces are always active. A package without a
    registered master flag (a stand-in a test injects, or a process that
    never registered one) is treated as active: there is no switch for it.
    """
    if gating not in GATING_CLASSES:
        raise ValueError(f"unknown gating class {gating!r}")
    if not package or package == PLATFORM or gating == ALWAYS:
        return True
    master = _master_for(package)
    if master is None:
        return True
    ctx = current_context()
    org_override = ctx.org_ids if ctx.org_ids is not None else None
    key = ("active", package, gating, ctx.user_id, org_override, ctx.project_id)
    cached = ctx.memo.get(key)
    if cached is not None:
        return cached
    from feature_flags import service

    entry = service.entry_of(_snapshot(ctx), master)
    if gating == POLICY_GLOBAL:
        result = service.entry_on_globally(entry)
    else:
        user_id = ctx.user_id

        def _orgs():
            override = _context_org_ids(ctx)
            if override is not None:
                return set(override)
            if not user_id:
                return set()
            return set(_membership_org_ids(ctx, user_id))

        result = service.entry_allows(entry, user_id, _orgs)
    ctx.memo[key] = result
    return result


class ExtensionInactive(RuntimeError):
    """A surface of an inactive package was asked to run (worker side).
    ``reason`` is ``feature_disabled``; ``flag`` the package's master flag."""

    reason = "feature_disabled"

    def __init__(self, package: str):
        self.package = package
        self.flag = _master_for(package) or package
        super().__init__(f"feature_disabled: {self.flag} is off for this task")


def ensure_active(package: str, gating: str = GATED) -> None:
    """Raise :class:`ExtensionInactive` unless :func:`package_active`."""
    if not package_active(package, gating):
        raise ExtensionInactive(package)


def feature_disabled_result(package: str) -> Dict[str, Any]:
    """The metric/cell result for a metric whose owning package is inactive
    in the task's context: no value, flagged, never computed."""
    flag = _master_for(package) or package
    return {
        "value": None,
        "method": None,
        "details": {"skipped": True, "reason": "feature_disabled", "flag": flag},
        "error": "feature_disabled",
    }


def _is_loaded(package: str) -> bool:
    try:
        import extension_registry

        if extension_registry.is_loaded(package):
            return True
    except ImportError:  # pragma: no cover - /shared not on sys.path
        return False
    return _master_for(package) is not None


def extension_active(package: Optional[str], gating: str = GATED) -> bool:
    """Whether ``package`` is active in the current context.

    ``platform`` is always active; a package that is not loaded never is.
    """
    if not package or package == PLATFORM:
        return True
    if not _is_loaded(package):
        return False
    return package_active(package, gating)


def active_packages(gating: str = GATED) -> Dict[str, bool]:
    """``{package: active}`` for every package with a master flag."""
    from feature_flags import registry

    return {pkg: package_active(pkg, gating) for pkg in registry.masters()}


# --------------------------------------------------------------------------- #
# Master flag registration (API and workers)
# --------------------------------------------------------------------------- #
def register_master_flags(loaded=None) -> Dict[str, str]:
    """Register ``extension.<EXTENSION_ID>`` for every loaded package
    (owner: the package). Returns ``{package: flag name}``. Called after
    ``extension_registry.load_all()`` by the API loader and both worker
    entry points; idempotent. An invalid ``DEFAULT_RUNTIME_STATE`` fails
    startup for a required package; an optional one gets the fallback
    default."""
    import extension_registry
    from feature_flags import registry

    names: Dict[str, str] = {}
    for ext in loaded if loaded is not None else extension_registry.loaded():
        try:
            default = registry.master_default_state(ext.name, ext.module)
        except ValueError:
            if extension_registry.is_required(ext.name):
                raise
            logger.exception("Extension package %s: DEFAULT_RUNTIME_STATE ignored", ext.name)
            default = None
        names[ext.name] = registry.register_master_flag(ext.name, ext.short, default)
    return names


# --------------------------------------------------------------------------- #
# Celery propagation
# --------------------------------------------------------------------------- #
def celery_header(task_kwargs: Optional[dict] = None) -> Optional[dict]:
    """``{"user_id", "project_id"}`` for a task about to be sent, from the
    current context and the task's ``project_id`` / ``user_id`` kwargs.
    None when there is nothing to carry."""
    ctx = _current.get()
    kwargs = task_kwargs if isinstance(task_kwargs, dict) else {}
    user_id = (ctx.user_id if ctx else None) or kwargs.get("user_id")
    project_id = kwargs.get("project_id") or (ctx.project_id if ctx else None)
    if not user_id and not project_id:
        return None
    return {
        "user_id": str(user_id) if user_id else None,
        "project_id": str(project_id) if project_id else None,
    }


def _body_kwargs(body) -> Optional[dict]:
    # Celery message protocol 2: body = (args, kwargs, embed).
    if isinstance(body, (tuple, list)) and len(body) >= 2 and isinstance(body[1], dict):
        return body[1]
    if isinstance(body, dict):  # protocol 1
        kwargs = body.get("kwargs")
        return kwargs if isinstance(kwargs, dict) else None
    return None


def _before_task_publish(sender=None, body=None, headers=None, **_kwargs):
    if headers is None or CELERY_HEADER in headers:
        return
    try:
        header = celery_header(_body_kwargs(body))
    except Exception:  # pragma: no cover - never block a publish
        logger.debug("extension activation: header build failed", exc_info=True)
        return
    if header:
        headers[CELERY_HEADER] = header


_publish_signal_installed = False


def install_publish_signal() -> None:
    """Add the ``benger_ext_ctx`` header to every task this process sends
    (Celery ``before_task_publish``). Idempotent."""
    global _publish_signal_installed
    if _publish_signal_installed:
        return
    from celery.signals import before_task_publish

    before_task_publish.connect(_before_task_publish, weak=False)
    _publish_signal_installed = True


def context_from_task(request, kwargs: Optional[dict]) -> ExtContext:
    """The context for a task: its header, else its ``user_id`` /
    ``project_id`` kwargs, else system."""
    header = None
    if request is not None:
        header = getattr(request, CELERY_HEADER, None)
        if header is None:
            headers = getattr(request, "headers", None)
            if isinstance(headers, dict):
                header = headers.get(CELERY_HEADER)
    if not isinstance(header, dict):
        header = {}
    kwargs = kwargs if isinstance(kwargs, dict) else {}
    user_id = header.get("user_id") or kwargs.get("user_id")
    project_id = header.get("project_id") or kwargs.get("project_id")
    if not isinstance(user_id, (str, int)):
        user_id = None
    if not isinstance(project_id, (str, int)):
        project_id = None
    kind = KIND_TASK if (user_id or project_id) else KIND_SYSTEM
    return new_context(user_id=user_id, project_id=project_id, kind=kind)


__all__ = [
    "ALWAYS",
    "CELERY_HEADER",
    "ExtContext",
    "GATED",
    "GATING_CLASSES",
    "KIND_REQUEST",
    "KIND_SYSTEM",
    "KIND_TASK",
    "PLATFORM",
    "POLICY_GLOBAL",
    "active_packages",
    "celery_header",
    "context_from_task",
    "current_context",
    "extension_active",
    "install_publish_signal",
    "master_state",
    "new_context",
    "package_active",
    "prime_snapshot",
    "project_org_ids",
    "register_master_flags",
    "reset_context",
    "set_context",
    "use_context",
]
