"""Thin re-export shim — canonical implementation in services/shared/mailer/notification_service.py.

Kept so existing ``from notification_service import NotificationService, notify_*``
callers (and the api-level ``services/api/notification_service.py`` shim that
re-exports this module) keep working unchanged. ``/shared`` is on ``sys.path``
in the api container, so ``mailer`` resolves bare.

NOTE for tests: unit tests that patch a *module-level name referenced inside*
the implementation (``get_celery_app``, ``EMAIL_SERVICE_AVAILABLE``,
``send_notification_email``) must target the canonical module —
``mailer.notification_service.<name>`` — not this shim, because the functions
look those names up in ``mailer.notification_service``'s namespace. Patches of
methods on the re-exported ``NotificationService`` class work against either
path.
"""
from mailer.notification_service import *  # noqa: F401,F403

# `import *` only re-exports public names (and respects ``__all__`` when set).
# ``check_notification_type_enum_drift`` is imported by name in main.py's
# startup path, so re-bind it explicitly to be robust regardless of how the
# canonical module's export surface evolves.
from mailer.notification_service import check_notification_type_enum_drift  # noqa: F401
