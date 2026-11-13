"""Startup fails when no JWT signing secret is configured.

Without ``JWT_SECRET_KEY`` or ``SECRET_KEY`` the auth config falls back to a
random per-process key, which logs every user out on each restart and
differs between replicas. Outside tests (``TESTING`` set by the test
config) the API now refuses to start in that state instead of only logging.
"""

import importlib

import pytest


def _config():
    # Resolved per test: other tests re-import auth_module.config, and the
    # app lifespan imports whatever module is current.
    return importlib.import_module("auth_module.config")


@pytest.fixture
def fallback_secret(monkeypatch):
    monkeypatch.setattr(_config(), "SECRET_KEY_FROM_ENV", False)


def test_missing_secret_fails_startup(fallback_secret, monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        _config().assert_jwt_secret_configured()


def test_missing_secret_fails_startup_in_development_too(fallback_secret, monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    with pytest.raises(RuntimeError):
        _config().assert_jwt_secret_configured()


def test_missing_secret_tolerated_under_testing(fallback_secret, monkeypatch):
    monkeypatch.setenv("TESTING", "true")

    _config().assert_jwt_secret_configured()


def test_configured_secret_passes(monkeypatch):
    monkeypatch.setattr(_config(), "SECRET_KEY_FROM_ENV", True)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    _config().assert_jwt_secret_configured()


async def test_api_lifespan_refuses_to_start(fallback_secret, monkeypatch):
    import main

    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        async with main.lifespan(main.app):
            pass  # pragma: no cover - startup must not get here
