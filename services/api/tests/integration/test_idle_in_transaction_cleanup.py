"""Real-Postgres proof for the idle-in-transaction cleanup crash.

Production sets ``idle_in_transaction_session_timeout=30000``. A request that
reads through the request session (the ``require_user`` pattern) and then waits
on something slow has its backend terminated; the dependency cleanup used to
ROLLBACK on the dead socket and raise out of the ASGI app after the response.

These tests use engines with a 1 s timeout, wait past it, and check:
* the ``get_db`` / ``get_async_db`` cleanup no longer raises and the pool
  recovers (control test: the old unguarded ``close()`` does raise here);
* a handler that calls ``release_db_sessions`` first keeps a healthy
  connection (nothing to discard);
* the notification SSE endpoint no longer leaves its request session idle
  in transaction for the life of the stream.
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

import database

IDLE_TIMEOUT_MS = 1000
PAST_TIMEOUT_S = 2.5

pytestmark = pytest.mark.integration


@pytest.fixture
def short_sync_sessions():
    # No pre-ping: the next checkout must be healthy because cleanup
    # invalidated the dead connection, not because the pool re-pinged it.
    engine = create_engine(
        os.environ["DATABASE_URL"],
        connect_args={"options": f"-c idle_in_transaction_session_timeout={IDLE_TIMEOUT_MS}"},
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=False,
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with patch.object(database, "SessionLocal", factory):
        yield factory
    engine.dispose()


@pytest_asyncio.fixture
async def short_async_sessions():
    engine = create_async_engine(
        os.environ["ASYNC_DATABASE_URL"],
        connect_args={
            "server_settings": {"idle_in_transaction_session_timeout": str(IDLE_TIMEOUT_MS)}
        },
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=False,
    )
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(database, "AsyncSessionLocal", factory):
        yield factory
    await engine.dispose()


def _auth_then_slow_app(release: bool) -> FastAPI:
    """``require_user``-shaped dependency, then a slow non-DB await."""
    app = FastAPI()

    def fake_require_user(db: Session = Depends(database.get_db)):
        db.execute(text("SELECT 1"))  # the user lookup opens the transaction
        return "user-1"

    @app.get("/slow")
    async def slow(
        user_id: str = Depends(fake_require_user),
        db: Session = Depends(database.get_db),  # same cached request session
    ):
        if release:
            await database.release_db_sessions(db)
        await asyncio.sleep(PAST_TIMEOUT_S)  # e.g. a provider call
        return {"user": user_id}

    return app


async def _get(app: FastAPI, path: str):
    # raise_app_exceptions (default True) re-raises anything that escapes the
    # app, including dependency teardown after the response was sent.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(path)


class TestSyncRequestSession:
    @pytest.mark.asyncio
    async def test_control_old_unguarded_close_raises(self, short_sync_sessions):
        """Guards the harness: without the fix this scenario really crashes."""
        with patch.object(database, "close_session_safely", lambda db: db.close()):
            with pytest.raises(OperationalError):
                await _get(_auth_then_slow_app(release=False), "/slow")

    @pytest.mark.asyncio
    async def test_killed_backend_cleanup_does_not_raise(self, short_sync_sessions):
        with patch.object(database, "logger") as log:
            response = await _get(_auth_then_slow_app(release=False), "/slow")

        assert response.status_code == 200
        # The backend really was killed and the connection discarded.
        log.warning.assert_called_once()
        # The single pooled slot is usable again without pre-ping.
        db = short_sync_sessions()
        try:
            assert db.execute(text("SELECT 1")).scalar() == 1
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_released_session_survives_the_slow_call(self, short_sync_sessions):
        with patch.object(database, "logger") as log:
            response = await _get(_auth_then_slow_app(release=True), "/slow")

        assert response.status_code == 200
        log.warning.assert_not_called()
        log.error.assert_not_called()


class TestAsyncRequestSession:
    @pytest.mark.asyncio
    async def test_killed_backend_cleanup_does_not_raise(self, short_async_sessions):
        app = FastAPI()

        @app.get("/slow")
        async def slow(db: AsyncSession = Depends(database.get_async_db)):
            await db.execute(text("SELECT 1"))
            await asyncio.sleep(PAST_TIMEOUT_S)
            return {"ok": True}

        with patch.object(database, "logger") as log:
            response = await _get(app, "/slow")

        assert response.status_code == 200
        log.warning.assert_called_once()
        async with short_async_sessions() as db:
            assert (await db.execute(text("SELECT 1"))).scalar() == 1

    @pytest.mark.asyncio
    async def test_released_session_survives_the_slow_call(self, short_async_sessions):
        app = FastAPI()

        @app.get("/slow")
        async def slow(db: AsyncSession = Depends(database.get_async_db)):
            await db.execute(text("SELECT 1"))
            await database.release_db_sessions(db)
            await asyncio.sleep(PAST_TIMEOUT_S)
            await db.execute(text("SELECT 1"))  # session still usable
            return {"ok": True}

        with patch.object(database, "logger") as log:
            response = await _get(app, "/slow")

        assert response.status_code == 200
        log.warning.assert_not_called()


class TestNotificationStreamSession:
    @pytest.mark.asyncio
    async def test_stream_outliving_the_timeout_leaves_request_session_healthy(
        self, test_db, short_sync_sessions
    ):
        """``test_db`` only guarantees the schema; every session here comes
        from the short-timeout engine (request session and per-poll ones)."""
        from routers.notifications import notification_stream

        request_db = short_sync_sessions()
        request_db.execute(text("SELECT 1"))  # what require_user leaves behind

        request = Mock()
        # Three polls with the real 2 s sleep in between: well past 1 s.
        request.is_disconnected = AsyncMock(side_effect=[False, False, True])
        user = Mock(id="w3-stream-user")

        response = await notification_stream(request, current_user=user, db=request_db)
        chunks = [chunk async for chunk in response.body_iterator]

        assert not any('"type": "error"' in c for c in chunks), chunks
        # FastAPI's teardown of the request session, unguarded: before the
        # fix the stream held it idle in transaction and this raised.
        request_db.close()
        with patch.object(database, "logger"):
            # Cleanup of the (released) session must also be quiet.
            database.close_session_safely(request_db)
