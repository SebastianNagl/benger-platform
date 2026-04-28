"""
Extension loader for BenGER extended features.

At startup, attempts to import benger_extended and register additional
routers, evaluators, and services. If the extended package is not
installed, all extension points are no-ops and the platform runs as
the community edition.
"""

import importlib
import logging

logger = logging.getLogger(__name__)

CORE_API_VERSION = "2.0"

_extended = None


def load_extended():
    """Try to import the extended package. Returns True if loaded.

    Performs a version compatibility check: if the extended package declares
    COMPATIBLE_CORE_VERSIONS, the core API version must be in that list.
    """
    global _extended
    try:
        _extended = importlib.import_module("benger_extended")
    except ImportError:
        logger.info("BenGER community edition (extended package not installed)")
        return False

    if hasattr(_extended, "COMPATIBLE_CORE_VERSIONS"):
        if CORE_API_VERSION not in _extended.COMPATIBLE_CORE_VERSIONS:
            logger.error(
                f"BenGER extended package incompatible: "
                f"requires core API {_extended.COMPATIBLE_CORE_VERSIONS}, "
                f"but core is {CORE_API_VERSION}. Extended features disabled."
            )
            _extended = None
            return False

    _register_extension_field_types()

    logger.info(
        f"BenGER extended features loaded (core API {CORE_API_VERSION})"
    )
    return True


def _register_extension_field_types():
    """Forward extended-declared label-studio field types into the validator.

    Extended packages declare ``get_field_type_registrations()`` returning
    ``{"types": [...], "named_types": [...]}``. This is the only way custom
    XML elements (e.g. ``<Angabe>``, ``<Gliederung>``) get accepted by the
    validator.
    """
    if not _extended or not hasattr(_extended, "get_field_type_registrations"):
        return
    try:
        registrations = _extended.get_field_type_registrations() or {}
        from services.label_config.validator import LabelConfigValidator

        LabelConfigValidator.register_field_types(
            registrations.get("types", []),
            named_types=registrations.get("named_types"),
        )
        types = registrations.get("types")
        if types:
            logger.info(f"Registered {len(types)} extension field types: {sorted(types)}")
    except Exception:
        logger.exception("Failed to register extension field types")


def get_extended_routers():
    """Return list of (router, kwargs) tuples to include in the app."""
    if _extended and hasattr(_extended, "get_routers"):
        return _extended.get_routers()
    return []


def on_annotation_created(db, task_id, user_id, annotation_id, project_id):
    """Hook called after an annotation is created.

    Extended package uses this to complete timer sessions and clean up drafts.
    No-op if extended is not loaded.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("on_annotation_created")
        if hook:
            hook(db, task_id, user_id, annotation_id, project_id)


def on_draft_saved(db, task_id, user_id, project_id, draft_result):
    """Hook called after a draft is saved.

    Extended package uses this to mirror drafts to timer sessions
    for server-side auto-submit. No-op if extended is not loaded.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("on_draft_saved")
        if hook:
            hook(db, task_id, user_id, project_id, draft_result)
