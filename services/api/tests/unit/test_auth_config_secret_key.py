"""Regression coverage for auth_module.config SECRET_KEY resolution.

In prod, helm historically set only SECRET_KEY (not JWT_SECRET_KEY).
email_verification.py used to read JWT_SECRET_KEY directly with a
hardcoded "your-secret-key-here" literal fallback — verification
tokens were signed with that literal string in prod. Both modules
now resolve through auth_module.config to a single source.
"""

import importlib
import logging
import os
import sys
from unittest.mock import patch

import pytest


def _reload_config():
    """Re-import the config module so module-level os.getenv re-runs."""
    if "auth_module.config" in sys.modules:
        del sys.modules["auth_module.config"]
    return importlib.import_module("auth_module.config")


class TestSecretKeyResolution:
    """SECRET_KEY accepts either env var name."""

    def test_jwt_secret_key_takes_precedence(self):
        with patch.dict(
            os.environ,
            {"JWT_SECRET_KEY": "jwt-value", "SECRET_KEY": "secret-value"},
            clear=False,
        ):
            config = _reload_config()
            assert config.SECRET_KEY == "jwt-value"

    def test_falls_back_to_secret_key(self):
        env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET_KEY"}
        env["SECRET_KEY"] = "only-secret-value"
        with patch.dict(os.environ, env, clear=True):
            config = _reload_config()
            assert config.SECRET_KEY == "only-secret-value"

    def test_random_fallback_when_neither_set(self, caplog):
        """Missing both env vars must surface as a CRITICAL log line
        — silently regenerating per-process keys is the worst-case UX
        (every JWT invalid after restart, different per replica).
        """
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("JWT_SECRET_KEY", "SECRET_KEY", "PYTEST_CURRENT_TEST")
        }
        with patch.dict(os.environ, env, clear=True), \
             caplog.at_level(logging.CRITICAL, logger="auth_module.config"):
            config = _reload_config()

            assert config.SECRET_KEY  # something got assigned
            assert len(config.SECRET_KEY) >= 32  # token_urlsafe(32) → at least 43 chars
            assert "Neither JWT_SECRET_KEY nor SECRET_KEY" in caplog.text


class TestEmailVerificationSharesConfigKey:
    """email_verification.py used to do its own os.getenv with a literal
    fallback. Now it imports from auth_module.config so the key never
    diverges between modules."""

    def test_jwt_secret_traces_back_to_config(self):
        """The module-level JWT_SECRET in email_verification must equal
        auth_module.config.SECRET_KEY when both modules are loaded under
        the same env. Forces a fresh import of both so we're not just
        observing values captured by earlier tests in the module."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("JWT_SECRET_KEY", "SECRET_KEY")
        }
        env["JWT_SECRET_KEY"] = "shared-canonical-value"
        with patch.dict(os.environ, env, clear=True):
            # Drop the whole auth_module subtree so __init__.py's
            # re-imports pick up the fresh env. Leaving any cached entry
            # behind defeats the os.getenv re-evaluation.
            for mod in list(sys.modules.keys()):
                if mod == "auth_module" or mod.startswith("auth_module."):
                    sys.modules.pop(mod, None)

            from auth_module import config as auth_config
            from auth_module import email_verification

            assert auth_config.SECRET_KEY == "shared-canonical-value"
            assert email_verification.JWT_SECRET == auth_config.SECRET_KEY
            # Hard-fail if the prior literal fallback ever sneaks back in.
            assert email_verification.JWT_SECRET != "your-secret-key-here"

    def test_email_verification_source_imports_from_config(self):
        """Source-level guard: email_verification.py must import
        SECRET_KEY from .config rather than do its own os.getenv.
        If a future commit reverts to os.getenv("JWT_SECRET_KEY", ...),
        this test fails loudly."""
        import inspect
        import re

        from auth_module import email_verification

        source = inspect.getsource(email_verification)
        assert "from .config import" in source, (
            "email_verification must import the JWT secret from auth_module.config"
        )
        # Catch a CODE-level reintroduction of the literal fallback, but
        # tolerate it appearing in comments/docstrings (the comment about
        # the bug includes the literal string by design).
        code_only = re.sub(r"#.*$", "", source, flags=re.MULTILINE)
        code_only = re.sub(r'""".*?"""', "", code_only, flags=re.DOTALL)
        assert "your-secret-key-here" not in code_only, (
            "literal JWT secret fallback re-introduced in code — "
            "use auth_module.config instead"
        )
