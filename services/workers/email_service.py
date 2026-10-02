"""Thin re-export shim — canonical implementation in services/shared/mailer/email_service.py.

Kept so existing worker ``from email_service import EmailService, email_service``
callers keep working unchanged. ``/shared`` is on ``sys.path`` in the workers
container, so ``mailer`` resolves bare.

The canonical ``EmailService`` never queries the database at construction, so
importing this module (and its module-level ``email_service`` global) triggers
no DB access, identical to the worker's old eager construction.
"""
from mailer.email_service import *  # noqa: F401,F403
