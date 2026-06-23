"""Canonical mailer package for BenGER (shared by api + workers).

This package is the single source of truth for outbound-mail plumbing that
used to be duplicated between ``services/api/services/email/`` and
``services/workers/``. It lives under ``services/shared`` so both the api and
the workers — each of which puts ``/shared`` first on ``sys.path`` — resolve
the same implementation via a bare ``from mailer.<module> import ...``.

Consolidated here:

* ``sendgrid_client`` — the SendGrid HTTP client. Both former copies are
  unified into a behavioral *superset*: the api copy's request ``timeout``
  plus the workers copy's ``status_code`` keys in the return dicts (the
  workers use ``status_code`` for Celery retry decisions; the api ignores
  the extra key).
* ``email_service`` — the ``EmailService`` + module-level helpers. Unified as
  a superset of the api and worker copies: ``EmailService(check_feature_flag)``
  controls whether ``__init__`` consults the ``API_MAIL_SERVICE`` feature flag
  (api behavior) or force-enables without a DB query (worker behavior); the
  enum-or-string ``notification.type`` handling and ``is_available()`` are both
  preserved.
* ``notification_service`` — the full ORM ``NotificationService`` and the
  ``notify_*`` helpers. Unified on the api ORM implementation; the worker's
  former raw-SQL stub now re-exports this. **Behavior change for workers**:
  worker-triggered notifications now respect the in_app preference (the stub
  always inserted).

The four former locations — ``services/api/services/email/{email_service,
notification_service}.py`` and ``services/workers/{email_service,
notification_service}.py`` — are thin ``from mailer.<module> import *`` shims
so no caller's import statement changes.
"""

from mailer.sendgrid_client import SendGridClient  # noqa: F401

__all__ = ["SendGridClient"]
