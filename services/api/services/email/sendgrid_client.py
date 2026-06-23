"""Thin re-export shim — canonical implementation in services/shared/mailer/sendgrid_client.py.

Kept so existing ``from sendgrid_client import SendGridClient`` callers (and the
api-level ``services/api/sendgrid_client.py`` shim that re-exports this module)
keep working unchanged. ``/shared`` is on ``sys.path`` in the api container, so
``mailer`` resolves bare.
"""
from mailer.sendgrid_client import *  # noqa: F401,F403
