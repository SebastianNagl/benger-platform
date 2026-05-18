"""Tests for the per-cell / per-row progress pub/sub helper.

The publish path replaces a 2 s Postgres count(*) polling loop on the
API-side WS handler. Each per-cell evaluation commit and each
batched-10 generation commit fires a Redis publish on a project-scoped
channel; the API's evaluation_progress_websocket subscribes there.

Failure must be silent — a Redis hiccup never fails the underlying DB
commit. These tests exercise the happy path and the error-swallow path.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset the lazy redis client between tests so mocks don't leak."""
    import tasks as workers_tasks

    workers_tasks._progress_redis_client = None
    yield
    workers_tasks._progress_redis_client = None


def test_publish_progress_sends_json_to_redis():
    """Happy path: a publish call lands on the redis client with the
    channel and a json-serialized payload."""
    import tasks as workers_tasks

    fake_client = MagicMock()
    with patch.object(workers_tasks.redis.Redis, "from_url", return_value=fake_client):
        workers_tasks._publish_progress(
            "evaluation:progress:abc",
            {"type": "cell_complete", "samples_added": 7},
        )

    fake_client.publish.assert_called_once()
    channel, body = fake_client.publish.call_args[0]
    assert channel == "evaluation:progress:abc"
    parsed = json.loads(body)
    assert parsed == {"type": "cell_complete", "samples_added": 7}


def test_publish_progress_caches_client_across_calls():
    """The lazy client is built once, then reused — avoids one
    connection per cell commit."""
    import tasks as workers_tasks

    fake_client = MagicMock()
    with patch.object(
        workers_tasks.redis.Redis, "from_url", return_value=fake_client
    ) as from_url:
        workers_tasks._publish_progress("c", {})
        workers_tasks._publish_progress("c", {})
        workers_tasks._publish_progress("c", {})

    assert from_url.call_count == 1
    assert fake_client.publish.call_count == 3


def test_publish_progress_swallows_client_init_error():
    """If from_url raises (broker URL bad, etc.), the helper returns
    None without propagating. The commit path must not fail."""
    import tasks as workers_tasks

    with patch.object(
        workers_tasks.redis.Redis,
        "from_url",
        side_effect=RuntimeError("boom"),
    ):
        # Should not raise.
        workers_tasks._publish_progress("c", {"x": 1})


def test_publish_progress_swallows_publish_error():
    """If publish itself raises (network blip), the helper logs and
    returns. The commit path proceeds."""
    import tasks as workers_tasks

    fake_client = MagicMock()
    fake_client.publish.side_effect = RuntimeError("network blip")
    with patch.object(workers_tasks.redis.Redis, "from_url", return_value=fake_client):
        workers_tasks._publish_progress("c", {"x": 1})


def test_get_progress_redis_returns_none_on_error():
    """The lazy-client builder returns None on failure so callers can
    short-circuit cleanly."""
    import tasks as workers_tasks

    with patch.object(
        workers_tasks.redis.Redis,
        "from_url",
        side_effect=RuntimeError("config"),
    ):
        assert workers_tasks._get_progress_redis() is None
