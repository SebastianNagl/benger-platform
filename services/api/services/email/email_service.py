"""Thin re-export shim — canonical implementation in services/shared/mailer/email_service.py.

Kept so existing ``from email_service import EmailService`` callers (and the
api-level ``services/api/email_service.py`` shim that re-exports this module)
keep working unchanged. ``/shared`` is on ``sys.path`` in the api container, so
``mailer`` resolves bare.

NOTE for tests: unit tests that patch a *module-level name referenced inside*
the implementation (e.g. ``SendGridClient`` in ``EmailService.__init__`` or
``Path`` in ``_init_template_environment``) must target the canonical module —
``mailer.email_service.SendGridClient`` — not this shim, because the class body
looks names up in ``mailer.email_service``'s namespace. Patches of methods on
the re-exported ``EmailService`` class, or of the re-exported ``email_service``
global instance, work against either path.
"""
from mailer.email_service import *  # noqa: F401,F403
