"""Integration coverage for the notifications SSE stream + email diagnostics.

The branch suite (``test_notifications_branches.py``) and the two unit suites
(``tests/unit/test_notifications_coverage.py`` /
``test_notifications_deep_coverage.py``) already cover the CRUD, preferences,
bulk, groups, summary, test-notification and email endpoints. The one large
block they leave entirely uncovered is the Server-Sent-Events endpoint
``GET /api/notifications/stream`` (``notification_stream`` →
``event_generator``), plus a couple of email-status arms. This file is that
complement.

The SSE handler can't run unbounded under the test client (it loops up to an
hour at 2 s intervals), so these tests call ``notification_stream`` directly and
drive its async ``event_generator`` one ``__anext__`` at a time:

  * ``routers.notifications.get_db`` is patched to yield the test session (the
    handler opens its OWN session via ``next(get_db())`` rather than via DI).
  * ``request.is_disconnected`` is an AsyncMock we flip to True to end the loop.
  * ``asyncio.sleep`` is patched to a no-op so the 2 s wait is instant.

We assert the exact SSE frames (connected, unread_count, new_notification) and
the cursor-advance behaviour, plus the disconnect and per-iteration error
branches — all against real persisted ``Notification`` rows.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from models import Notification, NotificationType, User


def _uid() -> str:
    return str(uuid.uuid4())


def _seed(
    test_db: Session,
    user: User,
    *,
    is_read: bool = False,
    title: str = "Stream Note",
    created_at: datetime = None,
) -> Notification:
    n = Notification(
        id=_uid(),
        user_id=user.id,
        organization_id=None,
        type=NotificationType.SYSTEM_ALERT,
        title=title,
        message="streamed",
        data={"k": "v"},
        is_read=is_read,
    )
    if created_at is not None:
        n.created_at = created_at
    test_db.add(n)
    test_db.commit()
    return n


def _make_request(disconnect_after: int):
    """A fake Request whose is_disconnected() returns False for the first
    ``disconnect_after`` calls, then True (ending the generator loop)."""
    request = Mock()
    state = {"calls": 0}

    async def _is_disconnected():
        state["calls"] += 1
        return state["calls"] > disconnect_after

    request.is_disconnected = AsyncMock(side_effect=_is_disconnected)
    return request


class _CloseGuardedSession:
    """Transparent proxy over the shared ``test_db`` session that turns the
    handler's per-iteration ``db_session.close()`` into a no-op.

    ``notification_stream`` opens its own session via ``next(get_db())`` and
    closes it in a ``finally`` each loop iteration. If that close hit the real
    SAVEPOINT-wrapped fixture session it would end the test transaction
    mid-test (breaking later assertions and the rollback teardown). Every other
    attribute/method delegates straight through so the handler's queries run on
    the same connection that can see the test's committed-into-savepoint rows.
    """

    def __init__(self, session):
        self._session = session

    def close(self):  # swallow the handler's cleanup
        return None

    def __getattr__(self, name):
        return getattr(self._session, name)


def _fresh_db_iter(test_db):
    """The handler calls ``next(get_db())`` once per loop iteration, so each
    ``get_db()`` invocation must hand back a NEW single-item iterator yielding a
    close-guarded view of the test session — a single shared ``iter([...])``
    would StopIteration on the second iteration. Patch with this as
    ``side_effect``."""
    guarded = _CloseGuardedSession(test_db)

    def _factory(*args, **kwargs):
        return iter([guarded])

    return _factory


async def _drain(gen, max_frames: int = 50):
    """Collect SSE 'data: {...}' frames from the generator into parsed dicts."""
    frames = []
    count = 0
    async for chunk in gen:
        count += 1
        if count > max_frames:
            break
        assert chunk.startswith("data: ")
        payload = chunk[len("data: "):].strip()
        frames.append(json.loads(payload))
    return frames


@pytest.mark.integration
class TestNotificationStream:
    @pytest.mark.asyncio
    async def test_first_iteration_emits_connected_and_unread_count(
        self, test_db, test_users
    ):
        """Iteration 1 with an existing unread row: emits the `connected` frame,
        then the `unread_count` frame carrying the real count, and seeds the
        cursor off the newest row (so it does NOT re-emit it as a new
        notification). The loop ends on the next is_disconnected() check."""
        admin = test_users[0]
        _seed(test_db, admin, is_read=False, title="existing")

        from routers.notifications import notification_stream

        request = _make_request(disconnect_after=1)
        with patch(
            "routers.notifications.get_db", side_effect=_fresh_db_iter(test_db)
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()):
            response = await notification_stream(request, current_user=admin)
            frames = await _drain(response.body_iterator)

        types = [f["type"] for f in frames]
        assert types[0] == "connected"
        assert "unread_count" in types
        unread_frame = next(f for f in frames if f["type"] == "unread_count")
        assert unread_frame["count"] == 1
        # The pre-existing row must NOT be re-delivered as a new_notification.
        assert "new_notification" not in types

    @pytest.mark.asyncio
    async def test_new_notification_delivered_on_second_iteration(
        self, test_db, test_users
    ):
        """Iteration 1 runs against an empty table → cursor seeds to the epoch.
        A row that first becomes visible on iteration 2 is strictly newer than
        the epoch cursor and is delivered as a `new_notification` frame with the
        full payload, and the cursor advances onto it.

        The handler opens a fresh ``next(get_db())`` per loop iteration. We
        exploit that: the row is inserted on the SECOND ``get_db()`` call, i.e.
        exactly in the window between iteration 1's cursor-init query and
        iteration 2's fetch query — the one place a real worker insert would
        land. Doing it any earlier would let iteration 1's cursor-init pick the
        row up and suppress delivery."""
        admin = test_users[0]

        from routers.notifications import notification_stream

        request = _make_request(disconnect_after=2)

        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        created = {}
        guarded = _CloseGuardedSession(test_db)
        state = {"calls": 0}

        def _get_db(*args, **kwargs):
            state["calls"] += 1
            # On the 2nd call (start of iteration 2) the cursor is already the
            # epoch; now make the fresh row visible so the iteration-2 fetch
            # returns it.
            if state["calls"] == 2:
                n = _seed(
                    test_db, admin, is_read=False, title="brand-new",
                    created_at=future,
                )
                created["id"] = n.id
            return iter([guarded])

        with patch(
            "routers.notifications.get_db", side_effect=_get_db
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()):
            response = await notification_stream(request, current_user=admin)
            frames = await _drain(response.body_iterator)

        new_frames = [f for f in frames if f["type"] == "new_notification"]
        assert len(new_frames) == 1
        delivered = new_frames[0]["notification"]
        assert delivered["id"] == created["id"]
        assert delivered["title"] == "brand-new"
        assert delivered["type"] == NotificationType.SYSTEM_ALERT.value
        assert delivered["is_read"] is False

    @pytest.mark.asyncio
    async def test_immediate_disconnect_emits_only_connected(
        self, test_db, test_users
    ):
        """If the client is already gone before the first loop check, only the
        initial `connected` frame is sent and the loop breaks immediately."""
        admin = test_users[0]

        from routers.notifications import notification_stream

        request = _make_request(disconnect_after=0)
        with patch(
            "routers.notifications.get_db", side_effect=_fresh_db_iter(test_db)
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()):
            response = await notification_stream(request, current_user=admin)
            frames = await _drain(response.body_iterator)

        assert [f["type"] for f in frames] == ["connected"]

    @pytest.mark.asyncio
    async def test_per_iteration_db_error_emits_error_frame(
        self, test_db, test_users
    ):
        """If opening the per-iteration DB session raises, the handler catches
        it inside the loop and emits an `error` frame instead of crashing the
        stream."""
        admin = test_users[0]

        from routers.notifications import notification_stream

        request = _make_request(disconnect_after=1)

        def _boom():
            raise RuntimeError("db down")

        with patch(
            "routers.notifications.get_db", side_effect=_boom
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()):
            response = await notification_stream(request, current_user=admin)
            frames = await _drain(response.body_iterator)

        types = [f["type"] for f in frames]
        assert types[0] == "connected"
        assert "error" in types
        err = next(f for f in frames if f["type"] == "error")
        assert "error" in err["message"].lower()

    @pytest.mark.asyncio
    async def test_stream_returns_event_stream_media_type(
        self, test_db, test_users
    ):
        """The StreamingResponse advertises the SSE content type + no-cache
        headers."""
        admin = test_users[0]
        from routers.notifications import notification_stream

        request = _make_request(disconnect_after=0)
        with patch(
            "routers.notifications.get_db", side_effect=_fresh_db_iter(test_db)
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()):
            response = await notification_stream(request, current_user=admin)

        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        # Drain so the generator's finally-block runs cleanly.
        await _drain(response.body_iterator)


@pytest.mark.integration
class TestEmailStatusEndpoint:
    def test_email_status_configured(self, client, test_users, auth_headers):
        """EMAIL_SERVICE_AVAILABLE + is_available()==True → ready message."""
        with patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True), patch(
            "routers.notifications.email_service"
        ) as mock_es:
            mock_es.is_available.return_value = True
            resp = client.get(
                "/api/notifications/email/status",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["available"] is True
        assert body["configured"] is True
        assert "ready" in body["message"].lower()

    def test_email_status_unconfigured(self, client, test_users, auth_headers):
        with patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True), patch(
            "routers.notifications.email_service"
        ) as mock_es:
            mock_es.is_available.return_value = False
            resp = client.get(
                "/api/notifications/email/status",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["available"] is True
        assert body["configured"] is False
        assert "not configured" in body["message"].lower()

    def test_email_status_check_raises_returns_unconfigured(
        self, client, test_users, auth_headers
    ):
        """An exception from is_available() is swallowed → available=False."""
        with patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True), patch(
            "routers.notifications.email_service"
        ) as mock_es:
            mock_es.is_available.side_effect = RuntimeError("probe failed")
            resp = client.get(
                "/api/notifications/email/status",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["available"] is False

    def test_digest_test_alias_returns_501(
        self, client, test_users, auth_headers
    ):
        """The removed digest feature stub returns 501 Not Implemented."""
        resp = client.post(
            "/api/notifications/digest/test",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 501, resp.text
        assert "removed" in resp.json()["detail"].lower()
