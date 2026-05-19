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
# In non-testing environments without either env var, fall back to a
# random key per process and log a CRITICAL. That random key invalidates
# every previously-issued JWT on restart and differs between replicas —
# we'd rather see one loud log line than silently break sign-in.
_jwt_env = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY")
if _jwt_env:
    SECRET_KEY = _jwt_env
else:
    SECRET_KEY = secrets.token_urlsafe(32)
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "staging") or os.getenv("PYTEST_CURRENT_TEST") is None:
        # PYTEST_CURRENT_TEST is set by pytest only during a test run; outside
        # of tests, missing JWT secret in any environment is loud-bad.
        logger.critical(
            "🚨 Neither JWT_SECRET_KEY nor SECRET_KEY is set — falling back to a "
            "random per-process key. This invalidates every issued JWT on restart "
            "and differs between replicas. Set one of these env vars before "
            "going live."
        )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
