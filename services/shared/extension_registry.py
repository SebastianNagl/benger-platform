"""N-package extension registry (core 2.37).

The platform used to know exactly one overlay, ``benger_extended``: the API
loader (``services/api/extensions.py``) and both worker entry points
(``services/workers/ml_evaluation/__init__.py``, ``services/workers/tasks.py``)
each imported it by name and ran their own copy of the version handshake.
This module is the one place that now decides which extension packages a
process runs and in which order; the three entry points call :func:`load_all`
and loop over :func:`loaded`.

Configuration (environment)
---------------------------
``BENGER_EXTENSIONS``
    Ordered, comma separated list of importable package names. Default:
    ``benger_extended``. Order is load order and therefore hook order, router
    order and the order in which worker registrations run.
``BENGER_REQUIRE_EXTENSIONS``
    Comma separated subset of the configured packages that must load; a
    failure of one of these raises :class:`RuntimeError` at startup instead
    of degrading. When the variable is unset the legacy
    ``BENGER_REQUIRE_EXTENDED`` keeps its meaning ("every configured package
    is required", see ``core_version.extended_required``). Set, even to an
    empty string, it is authoritative.

What a package may declare (all optional)
-----------------------------------------
``COMPATIBLE_CORE_VERSIONS``
    Core API versions the package was built against; ``CORE_API_VERSION``
    must be in it (the handshake every overlay already knows).
``EXTENSION_ID``
    Short identifier (``compliance``) used for the router prefix policy,
    the Celery task namespace and registration ownership. Defaults to the
    package name without its ``benger_`` prefix.
``EXTENSION_API_VERSION``
    The version of the package's own contract that OTHER overlays may depend
    on (a string, ``"1"``).
``REQUIRES_EXTENSIONS``
    ``{package_name: [compatible EXTENSION_API_VERSIONs]}``: packages that
    must be loaded earlier (so they must come first in ``BENGER_EXTENSIONS``)
    and whose ``EXTENSION_API_VERSION`` must be one of the listed values.
``get_task_queues()``
    ``{celery task name: queue}`` fed into ``celery_queues.register_task_queue``
    in both the API and the worker process. A package owns the task names
    under ``<EXTENSION_ID>.*`` (``compliance.run_suite``); the historic
    ``tasks.*`` names of benger_extended stay in the platform table.

The API-side contract (``get_routers``, ``get_hooks``, ``get_api_scopes``,
``get_v1_routers``, ``get_field_type_registrations``, ``configure_app``) is
documented in ``services/api/extensions.py``; the worker-side contract
(``<package>.workers`` with ``register_evaluators``,
``register_metric_handlers``, ``register_tasks`` and the ``get_*_fn``
getters) in the two worker entry points.

Worker attributes are resolved lazily by configured name
(:func:`worker_attrs`): a process that never called :func:`load_all` (a
test that injects a fake ``benger_extended.workers`` into ``sys.modules``)
still finds them, while a package the handshake or the dependency check
refused never contributes any.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

from core_version import CORE_API_VERSION, extended_required

logger = logging.getLogger(__name__)

EXTENSIONS_ENV = "BENGER_EXTENSIONS"
REQUIRE_EXTENSIONS_ENV = "BENGER_REQUIRE_EXTENSIONS"
LEGACY_REQUIRE_ENV = "BENGER_REQUIRE_EXTENDED"
DEFAULT_EXTENSIONS: Tuple[str, ...] = ("benger_extended",)

#: Rejection reasons. ``REJECTED_IMPORT`` is the only one :func:`worker_attrs`
#: retries lazily: a package that was not importable at load time is simply
#: absent, while the other three mean "present but refused".
REJECTED_IMPORT = "import"
REJECTED_NAMESPACE = "namespace"
REJECTED_HANDSHAKE = "handshake"
REJECTED_DEPENDENCY = "dependency"


@dataclass(frozen=True)
class LoadedExtension:
    """One accepted package."""

    name: str
    module: Any
    short: str

    @property
    def api_version(self) -> str:
        """The package's ``EXTENSION_API_VERSION`` (``""`` when undeclared)."""
        return extension_api_version(self.module)


@dataclass(frozen=True)
class RejectedExtension:
    """One configured package that did not load."""

    name: str
    reason: str
    message: str


_lock = threading.RLock()
_loaded: List[LoadedExtension] = []
_rejected: Dict[str, RejectedExtension] = {}
_loaded_once = False
_owner_stack: List[str] = []


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _split_names(raw: Optional[str]) -> List[str]:
    names: List[str] = []
    for part in (raw or "").split(","):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def configured_names() -> List[str]:
    """The packages this process loads, in order (``BENGER_EXTENSIONS``)."""
    raw = os.environ.get(EXTENSIONS_ENV)
    if raw is None:
        return list(DEFAULT_EXTENSIONS)
    return _split_names(raw)


def required_names() -> List[str]:
    """The packages that must load (see the module docstring)."""
    raw = os.environ.get(REQUIRE_EXTENSIONS_ENV)
    if raw is not None:
        return _split_names(raw)
    if extended_required():
        return configured_names()
    return []


def requirement_source(name: str) -> Optional[str]:
    """The environment variable that makes ``name`` required, or None."""
    if os.environ.get(REQUIRE_EXTENSIONS_ENV) is not None:
        return REQUIRE_EXTENSIONS_ENV if name in required_names() else None
    if extended_required() and name in configured_names():
        return LEGACY_REQUIRE_ENV
    return None


def is_required(name: str) -> bool:
    return requirement_source(name) is not None


def short_name(name: str, module: Any = None) -> str:
    """``EXTENSION_ID`` of the package, else its name without ``benger_``."""
    declared = getattr(module, "EXTENSION_ID", None) if module is not None else None
    if declared:
        return str(declared)
    return name[len("benger_"):] if name.startswith("benger_") else name


def extension_api_version(module: Any) -> str:
    value = getattr(module, "EXTENSION_API_VERSION", None)
    return "" if value is None else str(value)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _refuse(name: str, reason: str, message: str) -> None:
    """Record a rejection, or raise when the package is required."""
    source = requirement_source(name)
    if source is not None:
        raise RuntimeError(f"{message} {source} is set: refusing to start.")
    _rejected[name] = RejectedExtension(name=name, reason=reason, message=message)
    if reason == REJECTED_IMPORT:
        logger.info("Extension package %s not installed (%s)", name, message)
    else:
        logger.error("%s Extension package %s disabled.", message, name)


def _check_dependencies(name: str, module: Any) -> Optional[str]:
    """None when every ``REQUIRES_EXTENSIONS`` entry is satisfied, else why not."""
    requires = getattr(module, "REQUIRES_EXTENSIONS", None) or {}
    loaded_by_name = {ext.name: ext for ext in _loaded}
    for dep_name, versions in dict(requires).items():
        wanted = [str(v) for v in (versions or ())]
        dep = loaded_by_name.get(str(dep_name))
        if dep is None:
            return (
                f"Extension package {name} requires {dep_name} "
                f"(EXTENSION_API_VERSION in {wanted}), which is not loaded "
                f"(it must come before {name} in {EXTENSIONS_ENV})."
            )
        have = dep.api_version
        if wanted and have not in wanted:
            return (
                f"Extension package {name} requires {dep_name} with "
                f"EXTENSION_API_VERSION in {wanted}, but the loaded {dep_name} "
                f"declares {have!r}."
            )
    return None


def _load_one(name: str) -> Optional[LoadedExtension]:
    try:
        # Import-time registrations (metrics, flags, ...) are attributed to
        # the package (core 2.41), so registries can gate them by owner.
        with owner(name):
            module = importlib.import_module(name)
    except ImportError as exc:
        source = requirement_source(name)
        if source is not None:
            raise RuntimeError(
                f"{source} is set but the {name} package failed to import: "
                f"{exc}. Refusing to start without it (community edition "
                "fallback disabled)."
            ) from exc
        _refuse(name, REJECTED_IMPORT, f"{name} failed to import: {exc}")
        return None

    if getattr(module, "__file__", None) is None and not hasattr(
        module, "COMPATIBLE_CORE_VERSIONS"
    ):
        # A bare directory named like the package on sys.path (an empty
        # build-context mount point when the overlay is missing) imports as
        # an empty namespace package. Treating it as installed would skip the
        # handshake, register nothing and still log "loaded".
        _refuse(
            name,
            REJECTED_NAMESPACE,
            f"{name} resolved to an empty namespace package "
            f"({list(getattr(module, '__path__', []))}): the package is not "
            "actually installed/mounted.",
        )
        return None

    compatible = getattr(module, "COMPATIBLE_CORE_VERSIONS", None)
    if compatible is not None and CORE_API_VERSION not in compatible:
        _refuse(
            name,
            REJECTED_HANDSHAKE,
            f"BenGER extension package {name} incompatible: requires core API "
            f"{compatible}, but core is {CORE_API_VERSION}.",
        )
        return None

    problem = _check_dependencies(name, module)
    if problem is not None:
        _refuse(name, REJECTED_DEPENDENCY, problem)
        return None

    return LoadedExtension(name=name, module=module, short=short_name(name, module))


def _register_task_queues(ext: LoadedExtension) -> None:
    getter = getattr(ext.module, "get_task_queues", None)
    if getter is None:
        return
    import celery_queues

    try:
        table = getter() or {}
        for task_name, queue in dict(table).items():
            celery_queues.register_task_queue(str(task_name), str(queue), owner=ext.name)
    except Exception as exc:
        if is_required(ext.name):
            raise RuntimeError(
                f"Extension package {ext.name}: get_task_queues() could not be "
                f"applied: {exc}. {requirement_source(ext.name)} is set: refusing to start."
            ) from exc
        logger.exception("Extension package %s: get_task_queues() ignored", ext.name)


def load_all() -> List[LoadedExtension]:
    """Import, check and record every configured package, in order.

    Idempotent: the second call returns the first call's result. Raises
    :class:`RuntimeError` when a required package fails any check; an
    optional failure is logged and recorded (:func:`rejected`).
    """
    global _loaded_once
    with _lock:
        if _loaded_once:
            return list(_loaded)
        configured = configured_names()
        unknown = [n for n in required_names() if n not in configured]
        if unknown:
            raise RuntimeError(
                f"{REQUIRE_EXTENSIONS_ENV} names {unknown} which {EXTENSIONS_ENV} "
                f"does not list ({configured}). Refusing to start."
            )
        for name in configured:
            ext = _load_one(name)
            if ext is None:
                continue
            _loaded.append(ext)
            _register_task_queues(ext)
            logger.info(
                "Extension package %s loaded (id %s, core API %s)",
                name,
                ext.short,
                CORE_API_VERSION,
            )
        _loaded_once = True
        return list(_loaded)


def reset() -> None:
    """Forget everything (tests, and the API loader before a reload)."""
    global _loaded_once
    with _lock:
        _loaded.clear()
        _rejected.clear()
        _owner_stack.clear()
        _loaded_once = False


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def loaded() -> List[LoadedExtension]:
    """The accepted packages in load order (empty before :func:`load_all`)."""
    return list(_loaded)


def rejected() -> Dict[str, RejectedExtension]:
    return dict(_rejected)


def is_loaded(name: str) -> bool:
    return any(ext.name == name for ext in _loaded)


def module(name: str) -> Any:
    """The loaded package's module, or None."""
    for ext in _loaded:
        if ext.name == name:
            return ext.module
    return None


def loaded_names() -> List[str]:
    return [ext.name for ext in _loaded]


# --------------------------------------------------------------------------- #
# Worker-side attributes (lazy, by configured name)
# --------------------------------------------------------------------------- #
def _skipped_lazily(name: str) -> bool:
    rej = _rejected.get(name)
    return rej is not None and rej.reason != REJECTED_IMPORT


def worker_module(name: str, *, strict: bool = False) -> Any:
    """``<name>.workers``, or None when the package has no such module.

    ``strict`` tells a missing ``workers`` submodule apart from an import
    error inside it: with ``strict`` only the former is answered with None,
    any other :class:`ImportError` propagates (a startup registration must
    not swallow a broken overlay). Without ``strict`` every
    :class:`ImportError` means "not available", which is what the direct
    ``from benger_extended.workers import ...`` lookups did before.
    """
    target = f"{name}.workers"
    try:
        return importlib.import_module(target)
    except ImportError as exc:
        if strict and not (
            isinstance(exc, ModuleNotFoundError) and exc.name in (name, target)
        ):
            raise
        return None


#: Gating class (``extension_activation``) of each worker getter (core
#: 2.41). Billing, settlement and privacy getters are ALWAYS: switching a
#: package off must never skip a billing block or unmask a name. Getters not
#: listed here are GATED (active only for the task's caller/project).
WORKER_ATTR_GATING: Dict[str, str] = {
    "get_grading_dispatch_policy_fn": "always",
    "get_batch_evaluation_policy_fn": "always",
    "get_grading_finalize_fn": "always",
    "get_grading_block_fn": "always",
    "get_name_visibility_fns": "always",
    "get_notification_brand_host_fn": "gated",
    "get_falloesung_compute_fn": "gated",
    "get_falloesung_bulk_compute_fn": "gated",
}


def worker_attr_gating(attr: str) -> str:
    return WORKER_ATTR_GATING.get(attr, "gated")


def _package_active(name: str, gating: str) -> bool:
    if gating == "always":
        return True
    try:
        import extension_activation
    except ImportError:  # pragma: no cover - /shared always ships it
        return True
    return extension_activation.package_active(name, gating)


def worker_attrs(attr: str) -> List[Tuple[str, Any]]:
    """``[(package_name, value)]`` of ``<package>.workers.<attr>`` for every
    configured package that has it, in configured order.

    Resolved on every call, so a package injected into ``sys.modules`` after
    :func:`load_all` is found and one removed is not; packages the handshake
    or the dependency check refused are skipped, and so are packages that
    are not active for the attribute's gating class
    (:data:`WORKER_ATTR_GATING`) in the current task context.
    """
    gating = worker_attr_gating(attr)
    found: List[Tuple[str, Any]] = []
    for name in configured_names():
        if _skipped_lazily(name):
            continue
        workers = worker_module(name)
        if workers is None:
            continue
        value = getattr(workers, attr, None)
        if value is None:
            continue
        if not _package_active(name, gating):
            continue
        found.append((name, value))
    return found


def first_worker_attr(attr: str, *, call: bool = False) -> Any:
    """The first package's ``<package>.workers.<attr>`` (``None`` when none
    has it), called when ``call`` is set. Several providers log a warning:
    the attribute is meant to have one owner."""
    hits = worker_attrs(attr)
    if not hits:
        return None
    if len(hits) > 1:
        logger.warning(
            "%s is provided by %s; using %s and ignoring the others",
            attr,
            [name for name, _ in hits],
            hits[0][0],
        )
    value = hits[0][1]
    return value() if call else value


# --------------------------------------------------------------------------- #
# Registration ownership
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def owner(name: str) -> Iterator[None]:
    """Attribute registrations made inside the block to package ``name``
    (``current_owner``), so a registry can say who replaced whose entry."""
    _owner_stack.append(name)
    try:
        yield
    finally:
        _owner_stack.pop()


def current_owner() -> Optional[str]:
    """The package whose registrations are running, else None (platform)."""
    return _owner_stack[-1] if _owner_stack else None


def describe_owner(name: Optional[str]) -> str:
    return name or "the platform"


__all__ = [
    "DEFAULT_EXTENSIONS",
    "EXTENSIONS_ENV",
    "LEGACY_REQUIRE_ENV",
    "LoadedExtension",
    "REQUIRE_EXTENSIONS_ENV",
    "RejectedExtension",
    "configured_names",
    "current_owner",
    "describe_owner",
    "extension_api_version",
    "first_worker_attr",
    "is_loaded",
    "is_required",
    "load_all",
    "loaded",
    "loaded_names",
    "module",
    "owner",
    "rejected",
    "required_names",
    "requirement_source",
    "reset",
    "short_name",
    "WORKER_ATTR_GATING",
    "worker_attr_gating",
    "worker_attrs",
    "worker_module",
]
