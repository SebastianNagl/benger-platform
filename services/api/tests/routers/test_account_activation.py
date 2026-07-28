"""Router tests for the account-activation endpoints (LTI "Konto aktivieren").

Covers the authed request endpoint (guards, enqueue shape, broker-down
resilience) and the unauthed confirm endpoint (first password, pending-email
adoption + verification, token reuse/expiry, uniqueness at click time), plus
the reset-flow ``password_set`` regression.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


def _make_user(db, *, email=None, hashed_password=None, password_set=False,
               token=None, expires=None, pending=None):
    suffix = uuid.uuid4().hex[:10]
    u = User(
        id=f"act-{suffix}",
        username=f"act-{suffix}",
        email=email or f"act-{suffix}@test.com",
        name="Activation Tester",
        hashed_password=hashed_password,
        password_set=password_set,
        password_reset_token=token,
        password_reset_expires=expires,
        pending_activation_email=pending,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    db.flush()
    return u


class TestRequestAccountActivation:
    async def test_sub_only_account_with_email_enqueues(
        self, async_client, test_db
    ):
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        fake_app = MagicMock()
        with _as_user(user), patch(
            "celery_client.get_celery_app", return_value=fake_app
        ):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": "real@uni-x.de"},
                headers={"x-forwarded-host": "vertretbar.net"},
            )
        assert r.status_code == 200, r.text
        assert "…" in r.json()["email_hint"]
        assert fake_app.send_task.call_count == 1
        name = fake_app.send_task.call_args.args[0]
        kwargs = fake_app.send_task.call_args.kwargs["kwargs"]
        assert name == "emails.send_account_activation"
        assert kwargs["target_email"] == "real@uni-x.de"
        assert kwargs["force"] is True
        assert kwargs["host"] == "vertretbar.net"

    async def test_password_holder_409(self, async_client, test_db):
        user = _make_user(test_db, hashed_password="hash")
        with _as_user(user):
            r = await async_client.post(
                "/api/auth/request-account-activation", json={}
            )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "already_activated"

    async def test_routable_email_account_may_not_change_email(
        self, async_client, test_db
    ):
        user = _make_user(test_db, email=f"real-{uuid.uuid4().hex[:6]}@uni-x.de")
        with _as_user(user):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": "other@uni-x.de"},
            )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "email_change_not_allowed"

    async def test_sub_only_without_email_400(self, async_client, test_db):
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        with _as_user(user):
            r = await async_client.post(
                "/api/auth/request-account-activation", json={}
            )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "email_required"

    async def test_taken_email_409(self, async_client, test_db):
        other = _make_user(test_db, email="taken@uni-x.de", hashed_password="x")
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        with _as_user(user):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": other.email},
            )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "email_taken"

    async def test_broker_down_still_200(self, async_client, test_db):
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        with _as_user(user), patch(
            "celery_client.get_celery_app", side_effect=RuntimeError("redis down")
        ):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": "real2@uni-x.de"},
            )
        assert r.status_code == 200


class TestActivateAccount:
    async def test_activation_sets_first_password(
        self, async_client, test_db
    ):
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
        )
        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": "NeuesPasswort1!",
                "confirm_password": "NeuesPasswort1!",
            },
        )
        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.hashed_password is not None
        assert user.password_set is True
        assert user.password_reset_token is None
        assert user.password_reset_expires is None
        # Auto-path: email untouched.
        assert user.email_verification_method != "activation"

    async def test_activation_adopts_pending_email(
        self, async_client, test_db
    ):
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid",
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
            pending="claimed@uni-x.de",
        )
        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": "NeuesPasswort1!",
                "confirm_password": "NeuesPasswort1!",
            },
        )
        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email == "claimed@uni-x.de"
        assert user.email_verified is True
        assert user.email_verification_method == "activation"
        assert user.pending_activation_email is None
        assert user.password_set is True

    async def test_pending_email_taken_at_click_time_409(
        self, async_client, test_db
    ):
        _make_user(test_db, email="raced@uni-x.de", hashed_password="x")
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid",
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
            pending="raced@uni-x.de",
        )
        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": "NeuesPasswort1!",
                "confirm_password": "NeuesPasswort1!",
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "email_taken"
        test_db.refresh(user)
        assert user.hashed_password is None  # nothing half-applied

    async def test_expired_and_reused_tokens_rejected(
        self, async_client, test_db
    ):
        expired = f"tok-{uuid.uuid4().hex}"
        _make_user(
            test_db,
            token=expired,
            expires=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": expired,
                "new_password": "NeuesPasswort1!",
                "confirm_password": "NeuesPasswort1!",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_or_expired"

        # Happy activation, then the same token again -> rejected.
        token = f"tok-{uuid.uuid4().hex}"
        _make_user(
            test_db,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
        )
        body = {
            "token": token,
            "new_password": "NeuesPasswort1!",
            "confirm_password": "NeuesPasswort1!",
        }
        first = await async_client.post("/api/auth/activate-account", json=body)
        assert first.status_code == 200
        second = await async_client.post("/api/auth/activate-account", json=body)
        assert second.status_code == 400
        assert second.json()["detail"]["code"] == "invalid_or_expired"

    async def test_password_mismatch_400(self, async_client, test_db):
        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": "whatever",
                "new_password": "abcdef1",
                "confirm_password": "abcdef2",
            },
        )
        assert r.status_code == 400


class TestResetFlowPasswordSetRegression:
    async def test_reset_password_also_sets_password_set(
        self, async_client, test_db
    ):
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        r = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": "NeuesPasswort1!",
                "confirm_password": "NeuesPasswort1!",
            },
        )
        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.password_set is True
        assert user.hashed_password is not None
