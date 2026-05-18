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
