"""Request-session cleanup must survive a connection Postgres already killed.

``idle_in_transaction_session_timeout`` terminates a backend whose session sat
in an open transaction too long. The dependency cleanup in ``get_db`` /
``get_async_db`` then tries to ROLLBACK on a dead socket. That used to raise
out of the dependency teardown ("Exception in ASGI application"). Cleanup now
logs one warning line, invalidates the connection so the pool drops it, and
never raises.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import psycopg2
import pytest
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import database

_DEAD_MESSAGE = (
    "server closed the connection unexpectedly\n"
    "\tThis probably means the server terminated abnormally"
)


def _wrapped(cls=OperationalError):
    return cls("ROLLBACK", {}, psycopg2.OperationalError(_DEAD_MESSAGE))


def _sync_session(close_error=None):
    db = MagicMock(spec=Session)
    if close_error is not None:
        db.close.side_effect = close_error
    return db


def _async_session(close_error=None):
    db = MagicMock(spec=AsyncSession)
    db.close = AsyncMock(side_effect=close_error)
    db.invalidate = AsyncMock()
    return db


class TestCloseSessionSafely:
    @pytest.mark.parametrize(
        "error",
        [
            _wrapped(OperationalError),
            _wrapped(InterfaceError),
            psycopg2.OperationalError(_DEAD_MESSAGE),
            psycopg2.InterfaceError("connection already closed"),
            ConnectionResetError("reset by peer"),
        ],
        ids=["sa-operational", "sa-interface", "psycopg2-operational", "psycopg2-interface", "oserror"],
    )
    def test_dead_connection_is_invalidated_and_logged_once(self, error):
        db = _sync_session(error)
        with patch.object(database, "logger") as log:
            database.close_session_safely(db)  # must not raise

        db.invalidate.assert_called_once_with()
        log.warning.assert_called_once()
        message = log.warning.call_args.args[0] % log.warning.call_args.args[1:]
        assert "dead database connection" in message
        # One line, no stack trace.
        assert "\n" not in message
        assert "exc_info" not in log.warning.call_args.kwargs
        log.error.assert_not_called()

    def test_healthy_close_does_not_invalidate_or_log(self):
        db = _sync_session()
        with patch.object(database, "logger") as log:
            database.close_session_safely(db)
        db.close.assert_called_once_with()
        db.invalidate.assert_not_called()
        log.warning.assert_not_called()

    def test_unexpected_error_is_swallowed_too(self):
        db = _sync_session(RuntimeError("boom"))
        with patch.object(database, "logger") as log:
            database.close_session_safely(db)
        db.invalidate.assert_called_once_with()
        log.error.assert_called_once()

    def test_invalidate_failure_is_swallowed(self):
        db = _sync_session(_wrapped())
        db.invalidate.side_effect = _wrapped()
        with patch.object(database, "logger"):
            database.close_session_safely(db)


class TestAcloseSessionSafely:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error",
        [
            _wrapped(InterfaceError),
            _wrapped(OperationalError),
            asyncpg.exceptions.ConnectionDoesNotExistError("connection was closed"),
            asyncpg.exceptions.InterfaceError("cannot call Transaction.rollback()"),
            ConnectionResetError("reset by peer"),
        ],
        ids=["sa-interface", "sa-operational", "asyncpg-gone", "asyncpg-interface", "oserror"],
    )
    async def test_dead_connection_is_invalidated_and_logged_once(self, error):
        db = _async_session(error)
        with patch.object(database, "logger") as log:
            await database.aclose_session_safely(db)

        db.invalidate.assert_awaited_once_with()
        log.warning.assert_called_once()
        log.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_healthy_close_does_not_invalidate(self):
        db = _async_session()
        await database.aclose_session_safely(db)
        db.close.assert_awaited_once_with()
        db.invalidate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalidate_failure_is_swallowed(self):
        db = _async_session(_wrapped(InterfaceError))
        db.invalidate.side_effect = _wrapped(InterfaceError)
        with patch.object(database, "logger"):
            await database.aclose_session_safely(db)


class TestGetDbCleanup:
    def test_cleanup_swallows_dead_connection(self):
        db = _sync_session(_wrapped())
        with patch.object(database, "SessionLocal", return_value=db), patch.object(
            database, "logger"
        ):
            gen = database.get_db()
            assert next(gen) is db
            with pytest.raises(StopIteration):
                next(gen)  # runs the finally block; nothing may escape
        db.invalidate.assert_called_once_with()

    def test_handler_exception_still_propagates(self):
        db = _sync_session(_wrapped())
        with patch.object(database, "SessionLocal", return_value=db), patch.object(
            database, "logger"
        ):
            gen = database.get_db()
            next(gen)
            with pytest.raises(ValueError, match="handler failed"):
                gen.throw(ValueError("handler failed"))
        db.invalidate.assert_called_once_with()


class TestGetAsyncDbCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_swallows_dead_connection(self):
        db = _async_session(_wrapped(InterfaceError))
        with patch.object(database, "AsyncSessionLocal", MagicMock(return_value=db)), patch.object(
            database, "logger"
        ):
            agen = database.get_async_db()
            assert await agen.__anext__() is db
            with pytest.raises(StopAsyncIteration):
                await agen.__anext__()
        db.invalidate.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_handler_exception_still_propagates(self):
        db = _async_session(_wrapped(InterfaceError))
        with patch.object(database, "AsyncSessionLocal", MagicMock(return_value=db)), patch.object(
            database, "logger"
        ):
            agen = database.get_async_db()
            await agen.__anext__()
            with pytest.raises(ValueError, match="handler failed"):
                await agen.athrow(ValueError("handler failed"))
        db.invalidate.assert_awaited_once_with()


class TestReleaseDbSessions:
    @pytest.mark.asyncio
    async def test_closes_each_session_in_order_and_skips_none(self):
        order = []
        sync_db = _sync_session()
        sync_db.close.side_effect = lambda: order.append("sync")
        async_db = _async_session()
        async_db.close.side_effect = lambda: order.append("async")

        await database.release_db_sessions(sync_db, None, async_db)

        assert order == ["sync", "async"]

    @pytest.mark.asyncio
    async def test_dead_connection_during_release_does_not_raise(self):
        sync_db = _sync_session(_wrapped())
        async_db = _async_session(_wrapped(InterfaceError))
        with patch.object(database, "logger"):
            await database.release_db_sessions(sync_db, async_db)
        sync_db.invalidate.assert_called_once_with()
        async_db.invalidate.assert_awaited_once_with()
