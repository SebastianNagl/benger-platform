"""Startup fails in production without ``API_KEY_PEPPER``.

Without a pepper every access key is hashed unpeppered, and setting one
later invalidates every key already issued, so a new production namespace
must not silently start issuing keys without it. Staging, demo, development
and tests may run without a pepper (their deployments set no secret).
"""

import pytest

from app.core.config import Settings, assert_api_key_pepper_configured


@pytest.mark.parametrize("pepper", ["", "   "])
def test_production_without_pepper_fails(pepper):
    settings = Settings(environment="production", api_key_pepper=pepper)
    with pytest.raises(RuntimeError, match="API_KEY_PEPPER"):
        assert_api_key_pepper_configured(settings)


def test_production_with_pepper_passes():
    settings = Settings(environment="production", api_key_pepper="a" * 64)
    assert_api_key_pepper_configured(settings)


@pytest.mark.parametrize("environment", ["development", "staging", "demo", "test"])
def test_other_environments_may_run_without_pepper(environment):
    settings = Settings(environment=environment, api_key_pepper="")
    assert_api_key_pepper_configured(settings)


async def test_api_lifespan_refuses_to_start(monkeypatch):
    import main

    monkeypatch.setattr(main.settings, "environment", "production")
    monkeypatch.setattr(main.settings, "api_key_pepper", "")

    with pytest.raises(RuntimeError, match="API_KEY_PEPPER"):
        async with main.lifespan(main.app):
            pass  # pragma: no cover - startup must not get here
