"""Thin re-export shim — canonical implementation in services/shared/mailer/email_service.py.

Kept so existing worker ``from email_service import EmailService, email_service``
callers keep working unchanged. ``/shared`` is on ``sys.path`` in the workers
container, so ``mailer`` resolves bare.

The worker's former standalone copy hardcoded ``mail_enabled = True`` (no DB to
query a feature flag from a Celery task). The canonical ``EmailService`` keeps
that behavior available via ``EmailService(check_feature_flag=False)`` and the
module-level ``email_service`` global is constructed that way, so importing this
module triggers no DB access — identical to the worker's old eager construction.
"""
from mailer.email_service import *  # noqa: F401,F403
