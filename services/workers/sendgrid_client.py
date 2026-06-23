"""Thin re-export shim — canonical implementation in services/shared/mailer/sendgrid_client.py.

Kept so existing worker ``from sendgrid_client import SendGridClient`` callers
keep working unchanged. ``/shared`` is on ``sys.path`` in the workers container,
so ``mailer`` resolves bare.
"""
from mailer.sendgrid_client import *  # noqa: F401,F403
