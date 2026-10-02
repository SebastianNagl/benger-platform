"""Monitoring extension points (core 2.26, extended issue #125).

``extensions.configure_app`` and ``extensions.emit_ops_event`` are the only
platform pieces of the extended monitoring: the app hook lets the overlay add
its HTTP metrics middleware, the ops events report what only platform code
sees (mail the API sends inline, ``/health`` failures). The tests run the
real call sites against a stand-in extended package and record what reaches
its ``on_ops_event`` hook.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import extensions
from core_version import CORE_API_VERSION


class _FakeExtended:
    COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]

    def __init__(self, hooks=None, configure_app=None):
        self._hooks = hooks or {}
        if configure_app is not None:
            self.configure_app = configure_app

    def get_hooks(self):
        return self._hooks


@pytest.fixture
def events(monkeypatch):
    """Load a stand-in extended package whose on_ops_event records calls."""
    recorded = []

    def on_ops_event(event, **labels):
        recorded.append((event, labels))

    monkeypatch.setattr(
        extensions, "_extended", _FakeExtended({"on_ops_event": on_ops_event})
    )
    return recorded


def _boom(*args, **kwargs):
    raise RuntimeError("hook exploded")


class TestConfigureApp:
    def test_community_edition_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None)
        app = FastAPI()
        extensions.configure_app(app)
        assert app.user_middleware == []

    def test_package_receives_the_app(self, monkeypatch):
        seen = []
        monkeypatch.setattr(
            extensions, "_extended", _FakeExtended(configure_app=seen.append)
        )
        app = FastAPI()
        extensions.configure_app(app)
        assert seen == [app]

    def test_package_without_the_hook_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", _FakeExtended())
        extensions.configure_app(FastAPI())

    def test_failing_hook_does_not_stop_startup(self, monkeypatch, caplog):
        monkeypatch.setattr(extensions, "_extended", _FakeExtended(configure_app=_boom))
        extensions.configure_app(FastAPI())
        assert "configure_app hook failed" in caplog.text


class TestEmitOpsEvent:
    def test_community_edition_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None)
        extensions.emit_ops_event("mail_outcome", mail_type="verification", outcome="sent")

    def test_event_and_labels_reach_the_hook(self, events):
        extensions.emit_ops_event("health_check_failed", dependency="redis")
        assert events == [("health_check_failed", {"dependency": "redis"})]

    def test_package_without_the_hook_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", _FakeExtended())
        extensions.emit_ops_event("health_check_failed", dependency="redis")

    def test_failing_hook_never_raises(self, monkeypatch, caplog):
        monkeypatch.setattr(
            extensions, "_extended", _FakeExtended({"on_ops_event": _boom})
        )
        extensions.emit_ops_event("health_check_failed", dependency="redis")
        assert "on_ops_event hook failed" in caplog.text


class TestHealthEmitsFailures:
    """/health reports the dependency that made it 503 or degraded."""

    @pytest.fixture
    def client(self):
        from database import get_async_db
        from main import app

        self.db = AsyncMock()
        self.db.execute = AsyncMock(return_value=Mock())

        async def override():
            yield self.db

        app.dependency_overrides[get_async_db] = override
        yield TestClient(app)
        app.dependency_overrides.pop(get_async_db, None)

    def _get(self, client, pong):
        with patch("celery_client.get_celery_app") as get_app:
            get_app.return_value.control.inspect.return_value.ping.return_value = pong
            return client.get("/health")

    def test_healthy_emits_nothing(self, client, events):
        response = self._get(client, {"celery@w": {"ok": "pong"}})
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert events == []

    def test_redis_down(self, client, events):
        with patch("services.redis_cache.cache") as cache:
            cache.is_available = False
            response = self._get(client, {"celery@w": {"ok": "pong"}})
        assert response.status_code == 503
        assert events == [("health_check_failed", {"dependency": "redis"})]

    def test_database_down(self, client, events):
        self.db.execute = AsyncMock(side_effect=RuntimeError("db gone"))
        response = self._get(client, {"celery@w": {"ok": "pong"}})
        assert response.status_code == 503
        assert events == [("health_check_failed", {"dependency": "database"})]

    def test_no_workers_is_degraded(self, client, events):
        response = self._get(client, None)
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert events == [("health_check_failed", {"dependency": "celery"})]


def _verification_service():
    with patch("auth_module.email_verification.EmailService"):
        from auth_module.email_verification import EmailVerificationService

        return EmailVerificationService()


def _unverified_user():
    return Mock(id="user-1", email="a@b.de", name="A", email_verification_sent_at=None)


class TestVerificationMailOutcome:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sent, outcome", [(True, "sent"), (False, "failed")])
    async def test_outcome(self, events, sent, outcome):
        svc = _verification_service()
        svc.email_service.send_verification_email = AsyncMock(return_value=sent)
        assert await svc.send_verification_email(MagicMock(), _unverified_user()) is sent
        assert events == [
            ("mail_outcome", {"mail_type": "verification", "outcome": outcome})
        ]

    @pytest.mark.asyncio
    async def test_exception_counts_as_failed(self, events):
        svc = _verification_service()
        svc.email_service.send_verification_email = AsyncMock(
            side_effect=RuntimeError("smtp down")
        )
        assert await svc.send_verification_email(MagicMock(), _unverified_user()) is False
        assert events == [
            ("mail_outcome", {"mail_type": "verification", "outcome": "failed"})
        ]

    @pytest.mark.asyncio
    async def test_labels_carry_no_address(self, events):
        svc = _verification_service()
        svc.email_service.send_verification_email = AsyncMock(return_value=True)
        await svc.send_verification_email(MagicMock(), _unverified_user())
        assert "a@b.de" not in repr(events)


class TestPasswordResetMailOutcome:
    """Runs the real PasswordResetService -> EmailService chain; only the
    SendGrid client is stubbed."""

    @pytest.fixture
    def user(self):
        user = MagicMock()
        user.email = "user@example.com"
        user.name = "Test User"
        user.username = "test_user"
        return user

    async def _send(self, user, send_message):
        with patch("mailer.email_service.SendGridClient") as sg_class, patch(
            "database.SessionLocal"
        ):
            sg_class.return_value.send_message = send_message
            from app.auth_module.password_reset import password_reset_service

            return await password_reset_service.send_password_reset_email(
                db=MagicMock(), user=user, base_url="https://x.example", language="de"
            )

    @pytest.mark.asyncio
    async def test_sent(self, events, user):
        ok = await self._send(user, MagicMock(return_value={"status": "success"}))
        assert ok is True
        assert events == [
            ("mail_outcome", {"mail_type": "password_reset", "outcome": "sent"})
        ]

    @pytest.mark.asyncio
    async def test_provider_failure(self, events, user):
        ok = await self._send(
            user, MagicMock(return_value={"status": "error", "status_code": 500})
        )
        assert ok is False
        assert events == [
            ("mail_outcome", {"mail_type": "password_reset", "outcome": "failed"})
        ]
        assert "user@example.com" not in repr(events)
