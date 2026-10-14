"""Per-key rate limiting: client_id override, header state, fixed windows,
429 with Retry-After, defaults from settings."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.core.config import settings
from auth_module.principal import Principal, session_principal
from services import rate_limiter as rl


@pytest.fixture
def memory_limiter(monkeypatch):
    """The real global limiter on its memory backend, TESTING bypass off."""
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setattr(rl.rate_limiter, "redis_client", None)
    monkeypatch.setattr(rl.rate_limiter, "_memory_store", {}, raising=False)
    return rl.rate_limiter


def _request():
    req = Mock()
    req.headers = {}
    req.client.host = "10.0.0.1"
    req.state = SimpleNamespace()
    return req


def _key(rpm=None, rpd=None, key_id="k1"):
    return Principal(
        kind="api_key", user_id="u1", api_key_id=key_id, key_prefix="bgr_test_x",
        rate_limit=(rpm, rpd),
    )


async def test_client_id_override_keys_the_bucket(memory_limiter):
    state = {}
    user = SimpleNamespace(id="user-1")
    await memory_limiter.check_rate_limit(
        _request(), "apikey", {"minute": (5, 60)}, user=user,
        client_id="apikey:abc", state=state,
    )
    keys = list(memory_limiter._memory_store)
    assert len(keys) == 1 and keys[0].startswith("ratelimit:apikey:abc:apikey:minute:")
    assert state["limit"] == 5 and state["remaining"] == 4
    assert state["reset"] % 60 == 0


async def test_state_reports_tightest_window(memory_limiter):
    state = {}
    await memory_limiter.check_rate_limit(
        _request(), "x", {"minute": (100, 60), "day": (2, 86400)},
        client_id="c", state=state,
    )
    assert state["limit"] == 2 and state["remaining"] == 1 and state["window"] == 86400


async def test_enforce_key_rate_limit_sets_state_and_raises_429(memory_limiter):
    req = _request()
    principal = _key(rpm=2)
    await rl.enforce_key_rate_limit(req, principal)
    assert req.state.rate_limit["remaining"] == 1
    await rl.enforce_key_rate_limit(req, principal)
    assert req.state.rate_limit["remaining"] == 0
    with pytest.raises(HTTPException) as ei:
        await rl.enforce_key_rate_limit(req, principal)
    assert ei.value.status_code == 429
    assert ei.value.detail["code"] == "rate_limited"
    assert 1 <= int(ei.value.headers["Retry-After"]) <= 60
    assert ei.value.headers["X-RateLimit-Remaining"] == "0"
    # Another key has its own bucket.
    await rl.enforce_key_rate_limit(_request(), _key(rpm=2, key_id="k2"))


async def test_defaults_come_from_settings(memory_limiter, monkeypatch):
    monkeypatch.setattr(settings, "api_key_default_rpm", 7)
    monkeypatch.setattr(settings, "api_key_default_rpd", 70)
    assert rl.api_key_limits(_key()) == {"minute": (7, 60), "day": (70, 86400)}
    assert rl.api_key_limits(_key(rpm=3, rpd=30)) == {"minute": (3, 60), "day": (30, 86400)}


async def test_sessions_are_not_limited(memory_limiter):
    assert await rl.enforce_key_rate_limit(_request(), session_principal("u")) is None
    assert await rl.enforce_key_rate_limit(_request(), None) is None
    assert memory_limiter._memory_store == {}


async def test_testing_env_skips(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    req = _request()
    assert await rl.enforce_key_rate_limit(req, _key(rpm=1)) == {}
    assert await rl.enforce_key_rate_limit(req, _key(rpm=1)) == {}


async def test_window_counter_resets_at_boundary(memory_limiter):
    limits = {"minute": (1, 60)}
    with patch.object(rl.time, "time", return_value=600.0):
        assert await memory_limiter.check_rate_limit(_request(), "w", limits, client_id="c") is None
        assert await memory_limiter.check_rate_limit(_request(), "w", limits, client_id="c")
    with patch.object(rl.time, "time", return_value=660.0):
        assert await memory_limiter.check_rate_limit(_request(), "w", limits, client_id="c") is None


async def test_memory_store_prunes_expired_entries(memory_limiter, monkeypatch):
    monkeypatch.setattr(rl, "_MEMORY_PRUNE_THRESHOLD", 3)
    for i in range(4):
        memory_limiter._memory_store[f"old{i}"] = {"count": 1, "expires": 0}
    await memory_limiter._increment_count("fresh", 60)
    assert set(memory_limiter._memory_store) == {"fresh"}
