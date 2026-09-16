"""
Extension loader for BenGER extended features.

At startup, attempts to import benger_extended and register additional
routers, evaluators, and services. If the extended package is not
installed, all extension points are no-ops and the platform runs as
the community edition.
"""

import importlib
import logging

from core_version import CORE_API_VERSION, extended_required

logger = logging.getLogger(__name__)

_extended = None


def load_extended():
    """Try to import the extended package. Returns True if loaded.

    Performs a version compatibility check: if the extended package declares
    COMPATIBLE_CORE_VERSIONS, the core API version must be in that list.

    With BENGER_REQUIRE_EXTENDED set (prod/staging), an import failure or a
    handshake mismatch raises instead of degrading to the community edition,
    so a broken overlay fails the rollout loudly rather than shipping with
    extended features silently missing.
    """
    global _extended
    try:
        _extended = importlib.import_module("benger_extended")
    except ImportError as exc:
        if extended_required():
            raise RuntimeError(
                "BENGER_REQUIRE_EXTENDED is set but the benger_extended "
                f"package failed to import: {exc}. Refusing to start as "
                "community edition."
            ) from exc
        logger.info("BenGER community edition (extended package not installed)")
        return False

    if getattr(_extended, "__file__", None) is None and not hasattr(
        _extended, "COMPATIBLE_CORE_VERSIONS"
    ):
        # A bare directory named benger_extended on sys.path (e.g. an empty
        # build-context mount point when the extended overlay is missing)
        # imports as an empty namespace package. Treating it as installed
        # would skip the version handshake, register no routers, and still
        # log "loaded" — every extended route would 404 while the logs claim
        # the extended edition is running.
        message = (
            "benger_extended resolved to an empty namespace package "
            f"({list(getattr(_extended, '__path__', []))}) — the extended "
            "package is not actually installed/mounted."
        )
        _extended = None
        if extended_required():
            raise RuntimeError(
                f"{message} BENGER_REQUIRE_EXTENDED is set — refusing to "
                "start as community edition."
            )
        logger.warning(f"{message} Continuing as community edition.")
        return False

    if hasattr(_extended, "COMPATIBLE_CORE_VERSIONS"):
        if CORE_API_VERSION not in _extended.COMPATIBLE_CORE_VERSIONS:
            message = (
                "BenGER extended package incompatible: "
                f"requires core API {_extended.COMPATIBLE_CORE_VERSIONS}, "
                f"but core is {CORE_API_VERSION}."
            )
            _extended = None
            if extended_required():
                raise RuntimeError(
                    f"{message} BENGER_REQUIRE_EXTENDED is set — refusing "
                    "to start with extended features disabled."
                )
            logger.error(f"{message} Extended features disabled.")
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


def run_after_eval_config_save(db, project, config):
    """Hook called after a project's evaluation_config is persisted.

    Extended package uses this to derive proprietary project flags from
    the new evaluation_configs (e.g. korrektur_enabled, korrektur_config).
    Receives the SQLAlchemy session, the Project model instance, and the
    just-saved config dict. The hook may mutate the project; the caller
    is responsible for the final commit.

    No-op if extended is not loaded or doesn't register the hook.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("after_eval_config_save")
        if hook:
            hook(db, project, config)


def validate_signup(db, user_create):
    """Hook called during /auth/signup before the user row is created.

    Extended edition uses this to enforce its research-data-consent policy
    (raises HTTPException(400) if user_create.research_data_consent_accepted
    is not True). No-op in community edition — the column stays NULL and
    no checkbox is rendered, which is the correct default there.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("validate_signup")
        if hook:
            hook(db, user_create)


def after_user_signup(db, user, signup_context):
    """Hook called during /auth/signup after the user row is committed.

    ``signup_context`` is a dict describing the request origin
    (``{"host": ..., "origin": ...}``) derived server-side from the request
    headers. The extended edition uses this to onboard a student who signed up
    via a student-locked host (vertretbar.net): set ``preferred_ui_mode`` and
    attach the Vertretbar organization membership. The hook may mutate ``user``
    and persist its own rows; it owns its commit.

    No-op in community edition (no student-locked product) or when the extended
    package doesn't register the hook.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("after_user_signup")
        if hook:
            hook(db, user, signup_context)


def after_user_login(db, user, login_context):
    """Hook called during /auth/login after credentials are verified.

    ``user`` is the ORM ``models.User`` row (NOT the Pydantic auth schema —
    the hook may mutate and persist it, mirroring the signup hook contract).
    ``login_context`` mirrors the signup hook's context (``{"host": ...,
    "origin": ...}``, derived server-side from the request headers). The
    extended edition uses this to onboard EXISTING accounts that sign in on a
    student-locked host (vertretbar.net): pre-existing platform users never
    pass through /auth/signup, so the signup hook alone leaves them without
    the Vertretbar org membership that tier metering and cohort views key on.
    The hook may mutate ``user`` and persist its own rows; it owns its commit.

    No-op in community edition or when the extended package doesn't register
    the hook.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("after_user_login")
        if hook:
            hook(db, user, login_context)


def tasks_with_feedback_for_user(db, project_id, user_id, task_ids):
    """Return the subset of task_ids on which the given user has feedback.

    "Feedback" is whatever proprietary signal the extended package owns
    (Korrektur comments on the user's annotations, falloesung grades, etc.).
    Used by `/my-tasks` to render a "feedback available" badge.

    Returns an empty set when extended is not loaded — community edition
    has no human-feedback workflow, so no badge.
    """
    if not task_ids:
        return set()
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("tasks_with_feedback_for_user")
        if hook:
            result = hook(db, project_id, user_id, list(task_ids))
            return set(result or ())
    return set()


def tasks_with_evaluation_for_user(db, project_id, user_id, task_ids):
    """Return the subset of task_ids on which the user has any evaluation.

    "Evaluation" = at least one TaskEvaluation row on one of the user's
    annotations — immediate-eval, LLM-judge, or deterministic metric. Broader
    than `tasks_with_feedback_for_user` (which is human-Korrektur only). Used by
    `/my-tasks` to render an "evaluation available" badge and let the row open
    the submission+scores modal.

    Returns an empty set when extended is not loaded — community edition has no
    evaluation-on-own-annotation workflow surfaced in Meine Aufgaben.
    """
    if not task_ids:
        return set()
    if _extended and hasattr(_extended, "get_hooks"):
        hooks = _extended.get_hooks()
        hook = hooks.get("tasks_with_evaluation_for_user")
        if hook:
            result = hook(db, project_id, user_id, list(task_ids))
            return set(result or ())
    return set()


# --------------------------------------------------------------------------- #
# LMS (LTI) connection hooks. The extended edition implements them with sync
# SQLAlchemy sessions and never commits; async callers pass a sync session via
# ``await db.run_sync(lambda s: extensions.<hook>(s, ...))``. A failing hook
# is logged and answered with the safe value documented per wrapper, never
# raised into the request.
# --------------------------------------------------------------------------- #
def dispatch_lti_grade_sync(sync_id):
    """Queue the grade push for one ``lti_grade_syncs`` row right away.

    Returns True when the extended edition accepted the dispatch. False in
    the community edition (no LMS grade transfer) and when the hook fails;
    the row then waits for the next sweep.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("dispatch_lti_grade_sync")
            if hook:
                return bool(hook(sync_id))
        except Exception:
            logger.exception("dispatch_lti_grade_sync hook failed for %s", sync_id)
    return False


def privacy_protected_member_ids(db, organization_id, user_ids):
    """Subset of ``user_ids`` that count as LMS users.

    An LMS user is an account an LMS launch provisioned (even after an admin
    unlink, since it keeps the LMS clear name), or an existing account with a
    live link to an LMS identity. ``organization_id`` limits the check to
    connections owned by that org; None means any connection counts.

    Calling rule for a list of users:

    - mask ``privacy_protected_member_ids(db, None, ids)``;
    - a viewer with admin rights in org X may unmask
      ``privacy_protected_member_ids(db, X, ids)``; superadmins unmask all.

    So an LMS user of org B who is also a member of org A stays masked in
    org A's lists, even for A's admins. Project-scoped views use
    :func:`project_real_name_viewer` instead of the org admin check.

    Community edition: empty set (there are no LMS accounts). If the hook
    fails, both calls fail closed: the None call returns every given id
    (everyone masked) and an org call returns an empty set (nobody
    unmasked), so a failure never reveals a name.
    """
    ids = {str(uid) for uid in (user_ids or ()) if uid is not None}
    if not ids:
        return set()
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("privacy_protected_member_ids")
            if hook:
                result = hook(db, organization_id, sorted(ids))
                return {str(uid) for uid in (result or ())} & ids
        except Exception:
            logger.exception("privacy_protected_member_ids hook failed")
            return ids if organization_id is None else set()
    return set()


def project_real_name_viewer(db, viewer, project_id):
    """True when ``viewer`` may see real names of the LMS accounts on
    ``project_id`` (for example staff who grade the linked exam).

    False in the community edition and when the hook fails.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("project_real_name_viewer")
            if hook:
                return bool(hook(db, viewer, project_id))
        except Exception:
            logger.exception(
                "project_real_name_viewer hook failed for project %s", project_id
            )
    return False


def lti_anonymization_policy(db, user_id):
    """Extra anonymization rules for one account.

    Returns ``{"implicit_org_ids": set[str], "blockers": list[str]}``:
    ``implicit_org_ids`` are orgs whose ANNOTATOR membership the LMS launch
    added on its own (it does not count as "member elsewhere");
    ``blockers`` are reasons that forbid anonymizing the account.

    Community edition: no implicit orgs, no blockers. If the hook fails the
    answer carries the blocker ``policy_unavailable``, so nothing is
    anonymized on an unchecked policy.
    """
    policy = {"implicit_org_ids": set(), "blockers": []}
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("lti_anonymization_policy")
            if hook:
                result = hook(db, user_id) or {}
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


def lti_protected_org_ids(db):
    """Orgs whose LMS connections only superadmins may manage.

    Community edition: empty set. If the hook fails the result is empty too,
    so use it for filtering and display only; gate access with
    :func:`is_lti_protected_org`, which fails closed.
    """
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("lti_protected_org_ids")
            if hook:
                return {str(oid) for oid in (hook(db) or ())}
        except Exception:
            logger.exception("lti_protected_org_ids hook failed")
    return set()


def is_lti_protected_org(db, organization_id):
    """True when the LMS connections of ``organization_id`` are
    superadmin-only. False in the community edition; True when the hook
    fails, so a broken hook never opens those connections to org admins.
    """
    if not organization_id:
        return False
    if _extended and hasattr(_extended, "get_hooks"):
        try:
            hooks = _extended.get_hooks()
            hook = hooks.get("lti_protected_org_ids")
            if hook:
                return str(organization_id) in {str(oid) for oid in (hook(db) or ())}
        except Exception:
            logger.exception("lti_protected_org_ids hook failed")
            return True
    return False
