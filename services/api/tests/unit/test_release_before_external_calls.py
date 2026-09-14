"""Handlers end their read transactions before slow non-database calls.

A request session that loaded rows (``require_user`` alone does) and then
awaits a provider API, a bucket or a long stream sits idle in transaction;
Postgres kills that backend after ``idle_in_transaction_session_timeout``.
Each handler here must release the request's sync session (the cached
``get_db`` session ``require_user`` used) and, where it read through it, the
async session BEFORE the external call. The handlers are called directly with
recording sessions and a mocked external call, and the recorded order is
asserted.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


@pytest.fixture
def log():
    return []


@pytest.fixture
def sync_db(log):
    db = MagicMock(spec=Session)
    db.close.side_effect = lambda: log.append("release:sync")
    return db


@pytest.fixture
def async_db(log):
    db = MagicMock(spec=AsyncSession)
    db.close = AsyncMock(side_effect=lambda: log.append("release:async"))
    return db


def _step(log, name, result=None):
    """AsyncMock that records ``name`` when awaited and returns ``result``."""

    def _record(*args, **kwargs):
        log.append(name)
        return result

    return AsyncMock(side_effect=_record)


def _sync_step(log, name, result=None):
    def _record(*args, **kwargs):
        log.append(name)
        return result

    return Mock(side_effect=_record)


USER = SimpleNamespace(id="user-1", username="user-1", is_superadmin=True)


class TestUserApiKeys:
    @pytest.mark.asyncio
    async def test_set_key_releases_auth_session_before_validation(self, log, sync_db, async_db):
        from routers import api_keys

        svc = api_keys.user_api_key_service
        with patch.object(svc, "validate_api_key", _step(log, "external", (True, "ok", None))), patch.object(
            svc, "set_user_api_key_async", _step(log, "write", True)
        ):
            await api_keys.set_user_api_key(
                "openai",
                {"api_key": "sk-test-openai-key-1234567890"},
                current_user=USER,
                db=async_db,
                request_db=sync_db,
            )

        assert log == ["release:sync", "external", "write"]
        # The async session is untouched until the write; nothing to release.
        async_db.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_test_key_releases_auth_session_first(self, log, sync_db):
        from routers import api_keys

        with patch.object(
            api_keys.user_api_key_service,
            "validate_api_key",
            _step(log, "external", (True, "ok", None)),
        ):
            result = await api_keys.test_user_api_key(
                "openai", {"api_key": "sk-x"}, current_user=USER, request_db=sync_db
            )

        assert result["status"] == "success"
        assert log == ["release:sync", "external"]

    @pytest.mark.asyncio
    async def test_test_saved_key_releases_both_sessions_first(self, log, sync_db, async_db):
        from routers import api_keys

        svc = api_keys.user_api_key_service
        with patch.object(svc, "get_user_api_key_async", _step(log, "read", "sk-x")), patch.object(
            svc, "validate_api_key", _step(log, "external", (True, "ok", None))
        ):
            await api_keys.test_saved_user_api_key(
                "openai", current_user=USER, db=async_db, request_db=sync_db
            )

        assert log == ["read", "release:sync", "release:async", "external"]


class TestOrgApiKeys:
    @pytest.fixture
    def gates(self, log):
        from routers import org_api_keys

        with patch.object(org_api_keys, "_require_org_exists", _step(log, "read")), patch.object(
            org_api_keys, "_require_scope_admin", _step(log, "read")
        ):
            yield

    @pytest.fixture
    def external(self, log):
        from services.user_api_key_service import user_api_key_service

        with patch.object(
            user_api_key_service, "validate_api_key", _step(log, "external", (True, "ok", None))
        ):
            yield

    @pytest.mark.asyncio
    async def test_test_unsaved_releases_first(self, log, sync_db, async_db, gates, external):
        from routers import org_api_keys

        await org_api_keys.test_org_api_key(
            "org-1",
            "openai",
            {"api_key": "sk-x"},
            group_id=None,
            current_user=USER,
            db=async_db,
            request_db=sync_db,
        )

        assert log == ["read", "read", "release:sync", "release:async", "external"]

    @pytest.mark.asyncio
    async def test_test_saved_releases_first(self, log, sync_db, async_db, gates, external):
        from routers import org_api_keys

        with patch.object(
            org_api_keys.org_api_key_service, "get_org_api_key_async", _step(log, "read", "sk-x")
        ):
            await org_api_keys.test_saved_org_api_key(
                "org-1",
                "openai",
                group_id=None,
                current_user=USER,
                db=async_db,
                request_db=sync_db,
            )

        assert log == ["read", "read", "read", "release:sync", "release:async", "external"]


class TestCustomModels:
    @pytest.mark.asyncio
    async def test_unsaved_endpoint_probe_releases_first(self, log, sync_db):
        from routers import custom_models

        with patch.object(custom_models, "_enforce_test_rate_limit", AsyncMock()), patch.object(
            custom_models, "_validate_base_url_or_400", return_value="https://llm.example/v1"
        ), patch.object(
            custom_models,
            "validate_openai_compatible_endpoint",
            _step(log, "external", (True, "ok", None)),
        ):
            await custom_models.test_custom_endpoint(
                custom_models.EndpointTestRequest(base_url="https://llm.example/v1", api_key="k"),
                request=Mock(),
                current_user=USER,
                request_db=sync_db,
            )

        assert log == ["release:sync", "external"]

    @pytest.mark.asyncio
    async def test_saved_model_probe_releases_first_and_keeps_model_name(
        self, log, sync_db, async_db
    ):
        from routers import custom_models
        from routers.model_access import CustomModelAccess

        model = SimpleNamespace(base_url="https://llm.example/v1", endpoint_model_name="m-1")
        access = CustomModelAccess(model=model, user=USER)
        chat_ping = _step(log, "external:chat", {"status": "success"})

        with patch.object(custom_models, "_enforce_test_rate_limit", AsyncMock()), patch.object(
            custom_models, "_validate_base_url_or_400", return_value="https://llm.example/v1"
        ), patch.object(
            custom_models,
            "resolve_custom_model_credential_async",
            _step(log, "read", SimpleNamespace(api_key="k")),
        ), patch.object(
            custom_models,
            "validate_openai_compatible_endpoint",
            _step(log, "external", (True, "ok", None)),
        ), patch.object(custom_models, "_chat_ping", chat_ping):
            await custom_models.test_custom_model(
                custom_models.ModelTestRequest(chat_ping=True),
                request=Mock(),
                access=access,
                db=async_db,
                request_db=sync_db,
            )

        assert log == ["read", "release:sync", "release:async", "external", "external:chat"]
        chat_ping.assert_awaited_once_with("https://llm.example/v1", "m-1", "k")


class TestOrgStorageConnections:
    @pytest.fixture
    def gates(self, log):
        from routers import org_storage_connections as r

        with patch.object(r, "_require_org_exists", _step(log, "read")), patch.object(
            r, "_require_org_admin", _step(log, "read")
        ), patch.object(r, "_require_org_member", _step(log, "read")), patch.object(
            r, "_load_connection", _step(log, "read", SimpleNamespace(bucket="b"))
        ):
            yield r

    @pytest.mark.asyncio
    async def test_unsaved_test_releases_first(self, log, sync_db, async_db, gates):
        r = gates
        with patch.object(
            r.storage_conn_service,
            "test_connection",
            _sync_step(log, "external", {"ok": True, "message": "ok"}),
        ):
            await r.test_unsaved_storage_connection(
                "org-1",
                {"bucket": "b", "access_key": "a", "secret_key": "s"},
                current_user=USER,
                db=async_db,
                request_db=sync_db,
            )

        assert log == ["read", "read", "release:sync", "release:async", "external"]

    @pytest.mark.asyncio
    async def test_saved_test_releases_first(self, log, sync_db, async_db, gates):
        r = gates
        with patch.object(
            r.storage_conn_service,
            "test_connection",
            _sync_step(log, "external", {"ok": True, "message": "ok"}),
        ):
            await r.test_saved_storage_connection(
                "org-1", "conn-1", current_user=USER, db=async_db, request_db=sync_db
            )

        assert log == ["read", "read", "read", "release:sync", "release:async", "external"]

    @pytest.mark.asyncio
    async def test_browse_releases_first(self, log, sync_db, async_db, gates):
        r = gates
        with patch.object(
            r.storage_conn_service, "list_objects", _sync_step(log, "external", {"objects": []})
        ):
            await r.browse_storage_connection(
                "org-1",
                "conn-1",
                prefix=None,
                continuation_token=None,
                max_results=100,
                current_user=USER,
                db=async_db,
                request_db=sync_db,
            )

        assert log == ["read", "read", "read", "release:sync", "release:async", "external"]


class _CountingUser:
    """Auth user whose ``id`` reads are counted."""

    def __init__(self):
        self.reads = 0

    @property
    def id(self):
        self.reads += 1
        return "user-1"


class TestNotificationStream:
    @pytest.mark.asyncio
    async def test_request_session_released_before_stream_and_never_reused(self):
        from routers.notifications import notification_stream

        request_db = MagicMock(spec=Session)
        user = _CountingUser()

        poll_db = MagicMock()
        poll_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        request = Mock()
        request.is_disconnected = AsyncMock(side_effect=[False, True])

        with patch(
            "routers.notifications.get_db", side_effect=lambda: iter([poll_db])
        ), patch("routers.notifications.asyncio.sleep", new=AsyncMock()), patch(
            "routers.notifications.NotificationService.get_unread_count", return_value=0
        ):
            response = await notification_stream(request, current_user=user, db=request_db)

            # Released before the response (and so before the stream) exists.
            assert request_db.mock_calls == [call.close()]
            reads_before_stream = user.reads

            chunks = [chunk async for chunk in response.body_iterator]

        assert any("unread_count" in c for c in chunks)
        # The generator works on its own per-poll session only ...
        assert request_db.mock_calls == [call.close()]
        poll_db.close.assert_called()
        # ... and never goes back to the auth user object.
        assert user.reads == reads_before_stream
