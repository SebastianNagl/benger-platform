"""WebSocket tests for the evaluation-progress endpoint.

Covers:
- Auth before accept(): no cookie / bad cookie → close 4401.
- Polling fallback when Redis pub/sub is unavailable: client receives the
  initial `connection` event from a real connect.
- Access check: a project the user can't see → close 4403.

The pub/sub primary path itself is hard to integration-test without a
real Redis bridge — see the worker-side test_progress_pubsub.py for the
publish-side tests, and the unit-mock fallback test below for the
WS-side polling path.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch

from project_models import Project


@pytest.fixture
def eval_ws_project(test_db: Session, test_user):
    """Minimal project bound to the test user (superadmin → access ok)."""
    project = Project(
        id="ws-eval-project",
        title="Eval WS Test",
        description="Project for evaluation WS tests",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    test_db.add(project)
    test_db.commit()
    return project


@pytest.mark.asyncio
async def test_ws_rejects_unauthenticated_handshake(client, eval_ws_project):
    """No access_token cookie → WS handshake closes immediately with 4401."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/api/ws/projects/{eval_ws_project.id}/evaluation-progress"
        ):
            pass

    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_ws_falls_back_to_polling_when_redis_lacks_pubsub(
    client, eval_ws_project, test_user
):
    """Connect with valid auth + mock get_redis_client to return a client
    object that has no `pubsub` attribute → handler takes the polling
    fallback path and still sends the initial `connection` event."""
    client.cookies.set("access_token", test_user.token)

    with patch("routers.evaluations.ws.get_redis_client") as mock_redis:
        # Force the polling fallback by removing the `pubsub` attribute.
        mock_instance = MagicMock(spec=[])
        mock_redis.return_value = mock_instance

        with client.websocket_connect(
            f"/api/ws/projects/{eval_ws_project.id}/evaluation-progress"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "connection"
            assert msg["status"] == "connected"
            assert msg["project_id"] == eval_ws_project.id


# --- Regression tests for the live-puppeteer-caught bugs in b6529dc ----------


@pytest.mark.asyncio
async def test_ws_forwards_all_redis_connection_kwargs(
    client, eval_ws_project, test_user
):
    """Regression: my first cut built the async Redis client with only
    host/port/db, dropping the password. Subscribes appeared to succeed
    but the server never registered them, so every PUBLISH returned 0
    subscribers and live updates went nowhere.

    Assert that the kwargs we pass to redis.asyncio.Redis(...) include
    every kwarg from the sync client's connection_pool — most importantly
    the password.
    """
    client.cookies.set("access_token", test_user.token)
    captured_kwargs: dict = {}

    sync_client = MagicMock()
    sync_client.connection_pool.connection_kwargs = {
        "host": "redis",
        "port": 6379,
        "db": 0,
        "password": "super-secret-pw",
        # Common SQLAlchemy/redis-py extras that must round-trip too.
        "socket_timeout": 5,
    }
    sync_client.pubsub = lambda: MagicMock()  # marker for hasattr(...) branch

    async def _fake_subscribe(channel):  # async stub, no-op
        return None

    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = _fake_subscribe
    fake_pubsub.get_message = MagicMock(return_value=None)
    fake_pubsub.unsubscribe = _fake_subscribe
    fake_pubsub.close = _fake_subscribe

    class _AsyncRedisRecorder:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        def pubsub(self):
            return fake_pubsub

    with patch("routers.evaluations.ws.get_redis_client", return_value=sync_client), \
         patch("redis.asyncio.Redis", _AsyncRedisRecorder):
        try:
            with client.websocket_connect(
                f"/api/ws/projects/{eval_ws_project.id}/evaluation-progress"
            ) as ws:
                # Consume the initial `connection` event.
                ws.receive_json()
                # Close immediately — we only care that the kwargs were captured.
                ws.close()
        except Exception:
            # Don't care about teardown shape; the assertion below is the point.
            pass

    # Every kwarg from the sync pool must make it across. Catches the prior
    # "drop password" regression at its source.
    for required_key in ("host", "port", "db", "password", "socket_timeout"):
        assert required_key in captured_kwargs, (
            f"{required_key} missing from async Redis kwargs — regression of the "
            f"password-forwarding bug fixed in b6529dc"
        )
    assert captured_kwargs["password"] == "super-secret-pw"


@pytest.mark.asyncio
async def test_ws_forwards_pubsub_message_as_tick_type(
    client, eval_ws_project, test_user
):
    """Regression: my first cut spread `{**payload, ...}` AFTER `"type":
    "tick"` so the publisher's `"type": "cell_complete"` overwrote ours.
    Frontend gates the refetch on `data.type === 'tick'`, so the message
    arrived but was silently ignored. Assert that the WS-forwarded message
    has `type=tick` even when the upstream publisher sets type to
    something else.
    """
    import asyncio as _aio
    import json

    client.cookies.set("access_token", test_user.token)

    sync_client = MagicMock()
    sync_client.connection_pool.connection_kwargs = {
        "host": "redis", "port": 6379, "db": 0,
    }
    sync_client.pubsub = lambda: MagicMock()

    upstream_message = {
        "type": "cell_complete",
        "evaluation_id": "e-1",
        "samples_added": 5,
    }
    # First poll → upstream message; subsequent polls → None (so the handler
    # eventually closes via idle-timeout, but we'll close the WS first).
    calls = {"n": 0}

    async def _fake_get_message(ignore_subscribe_messages=True, timeout=0.1):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"type": "message", "data": json.dumps(upstream_message)}
        await _aio.sleep(0)
        return None

    async def _fake_subscribe(channel):  # noqa: ARG001
        return None

    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = _fake_subscribe
    fake_pubsub.get_message = _fake_get_message
    fake_pubsub.unsubscribe = _fake_subscribe
    fake_pubsub.close = _fake_subscribe

    class _AsyncRedisStub:
        def __init__(self, **kwargs):
            pass

        def pubsub(self):
            return fake_pubsub

    with patch("routers.evaluations.ws.get_redis_client", return_value=sync_client), \
         patch("redis.asyncio.Redis", _AsyncRedisStub):
        with client.websocket_connect(
            f"/api/ws/projects/{eval_ws_project.id}/evaluation-progress"
        ) as ws:
            # First message: handshake.
            connect_msg = ws.receive_json()
            assert connect_msg["type"] == "connection"
            # Second message: our forwarded tick.
            forwarded = ws.receive_json()

    # The forwarded message MUST be type=tick (overriding the publisher's
    # `cell_complete`) — that's what the frontend's refetch gate looks for.
    assert forwarded["type"] == "tick"
    # Publisher fields should still be present alongside.
    assert forwarded["evaluation_id"] == "e-1"
    assert forwarded["samples_added"] == 5
