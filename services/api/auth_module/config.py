"""
Authentication configuration
"""

import logging
import os
import secrets

logger = logging.getLogger(__name__)

# JWT Configuration
#
# Both env-var names are accepted because the deployment surfaces are
# inconsistent: infra/docker-compose.yml sets JWT_SECRET_KEY, while
# infra/helm/benger/values.yaml sets SECRET_KEY. Code that needs the
# signing key MUST import SECRET_KEY from this module — do NOT call
# os.getenv("JWT_SECRET_KEY", "your-secret-key-here") in new code (the
# literal fallback was the email_verification.py bug fixed 2026-05-19).
#
# Without either env var the module falls back to a random key per process
# so that imports (tests, doc generators, one-off scripts) keep working, but
# the API refuses to start with it: ``assert_jwt_secret_configured`` runs in
# the app lifespan. A random key would invalidate every issued JWT on restart
# and differ between replicas. Tests set TESTING (and their own key).
_jwt_env = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY")
SECRET_KEY_FROM_ENV = bool(_jwt_env)
SECRET_KEY = _jwt_env if _jwt_env else secrets.token_urlsafe(32)


def assert_jwt_secret_configured() -> None:
    """Fail API startup when no JWT signing secret is configured.

    Allowed only under tests (``TESTING`` true), which run without a real
    deployment config. Local development sets ``JWT_SECRET_KEY`` through
    infra/docker-compose.yml.
    """
    if SECRET_KEY_FROM_ENV:
        return
    if os.getenv("TESTING", "").lower() in ("1", "true", "yes", "on"):
        logger.warning("No JWT secret configured; using a random key (tests only)")
        return
    raise RuntimeError(
        "Neither JWT_SECRET_KEY nor SECRET_KEY is set. Set one of them to a "
        "long random value; the API does not start with a random per-process "
        "signing key."
    )


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
