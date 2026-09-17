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
               token=None, expires=None, pending=None, email_verified=True,
               verification_method=None):
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
        email_verified=email_verified,
        email_verification_method=verification_method,
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
        assert r.json()["email_hint"] == "re…@uni-x.de"
        assert fake_app.send_task.call_count == 1
        name = fake_app.send_task.call_args.args[0]
        kwargs = fake_app.send_task.call_args.kwargs["kwargs"]
        assert name == "emails.send_account_activation"
        assert kwargs["target_email"] == "real@uni-x.de"
        assert kwargs["force"] is True
        assert kwargs["host"] == "vertretbar.net"

    async def test_entered_email_is_sent_lowercased(self, async_client, test_db):
        """Reset, resend and login match addresses exactly, so the fallback
        stores what it adopts in lower case (like signup and the LMS)."""
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        fake_app = MagicMock()
        with _as_user(user), patch(
            "celery_client.get_celery_app", return_value=fake_app
        ):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": "Max.Mustermann@Uni-X.de"},
            )
        assert r.status_code == 200, r.text
        kwargs = fake_app.send_task.call_args.kwargs["kwargs"]
        assert kwargs["target_email"] == "max.mustermann@uni-x.de"
        assert r.json()["email_hint"] == "ma…@uni-x.de"

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

    async def test_taken_email_in_other_letter_case_409(
        self, async_client, test_db
    ):
        """Signup stores addresses lowercased; a differently cased entry of
        the same mailbox must not create a second account for it."""
        _make_user(test_db, email="casetaken@uni-x.de", hashed_password="x")
        user = _make_user(test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid")
        fake_app = MagicMock()
        with _as_user(user), patch(
            "celery_client.get_celery_app", return_value=fake_app
        ):
            r = await async_client.post(
                "/api/auth/request-account-activation",
                json={"email": "CaseTaken@uni-x.de"},
            )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "email_taken"
        fake_app.send_task.assert_not_called()

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

    async def test_adopted_pending_email_is_lowercased_and_reset_finds_it(
        self, async_client, test_db
    ):
        token = f"tok-{uuid.uuid4().hex}"
        pending = f"Mixed.{uuid.uuid4().hex[:6]}@Uni-X.de"
        user = _make_user(
            test_db,
            email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid",
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
            pending=pending,
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
        assert user.email == pending.lower()

        # "Passwort vergessen" with the lowercase address finds the account.
        from unittest.mock import AsyncMock

        send = AsyncMock(return_value=True)
        with patch(
            "app.auth_module.password_reset.password_reset_service."
            "send_password_reset_email",
            send,
        ):
            reset = await async_client.post(
                "/api/auth/request-password-reset",
                json={"email": pending.lower()},
            )
        assert reset.status_code == 200, reset.text
        assert send.await_count == 1
        assert send.await_args.kwargs["user"].id == user.id

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

    async def test_pending_email_taken_in_other_letter_case_409(
        self, async_client, test_db
    ):
        _make_user(test_db, email="raced-case@uni-x.de", hashed_password="x")
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid",
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(days=1),
            pending="Raced-Case@uni-x.de",
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
        assert user.hashed_password is None
        assert user.email.endswith("@lti.invalid")

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


_PASSWORD = "NeuesPasswort1!"


def _lms_claim_user(db, **overrides):
    """A passwordless account whose address came from an LMS and is not
    proven yet (migration 106 backfill / Phase 3 provisioning shape)."""
    token = f"tok-{uuid.uuid4().hex}"
    fields = dict(
        email=f"lms-{uuid.uuid4().hex[:8]}@uni-x.de",
        token=token,
        expires=datetime.now(timezone.utc) + timedelta(days=1),
        email_verified=False,
        verification_method="lti_claim",
    )
    fields.update(overrides)
    return _make_user(db, **fields), fields["token"]


async def _login(async_client, user):
    return await async_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": _PASSWORD},
    )


class TestLinkUseVerifiesUnprovenEmail:
    """Login refuses unverified accounts, so an LMS-supplied address must
    become verified when the link mailed to it is used. Otherwise a student
    who activates their account can never sign in."""

    async def test_activation_verifies_lms_claim_email_and_login_works(
        self, async_client, test_db
    ):
        user, token = _lms_claim_user(test_db)
        refused = await async_client.post(
            "/api/auth/login",
            json={"username": user.username, "password": "wrong"},
        )
        assert refused.status_code == 401

        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is True
        assert user.email_verification_method == "activation"
        assert user.email_verified_at is not None
        login = await _login(async_client, user)
        assert login.status_code == 200, login.text

    async def test_reset_password_verifies_lms_claim_email_and_login_works(
        self, async_client, test_db
    ):
        user, token = _lms_claim_user(test_db)

        r = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is True
        assert user.email_verification_method == "self"
        login = await _login(async_client, user)
        assert login.status_code == 200, login.text

    async def test_reset_does_not_verify_while_a_pending_address_is_parked(
        self, async_client, test_db
    ):
        """An activation token mailed to the parked address and redeemed at
        /reset-password: the link went there, not to user.email."""
        user, token = _lms_claim_user(test_db, pending="parked@uni-y.de")

        r = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is False
        assert user.email_verification_method == "lti_claim"
        login = await _login(async_client, user)
        assert login.status_code == 403

    async def test_requesting_a_reset_drops_the_parked_address(
        self, async_client, test_db
    ):
        """The reset mail goes to user.email and replaces the activation link
        of a parked address, so using it verifies user.email and login
        works (no lockout)."""
        from unittest.mock import AsyncMock

        user, old_token = _lms_claim_user(test_db, pending="parked@uni-y.de")
        send = AsyncMock(return_value=True)
        with patch("email_service.EmailService.send_password_reset_email", send):
            requested = await async_client.post(
                "/api/auth/request-password-reset", json={"email": user.email}
            )
        assert requested.status_code == 200, requested.text
        assert send.await_count == 1
        assert send.await_args.kwargs["to_email"] == user.email
        token = send.await_args.kwargs["reset_link"].rsplit("/", 1)[-1]
        assert token != old_token
        test_db.refresh(user)
        assert user.pending_activation_email is None

        r = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )
        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is True
        assert user.email_verification_method == "self"
        login = await _login(async_client, user)
        assert login.status_code == 200, login.text

    async def test_unroutable_address_is_never_verified(
        self, async_client, test_db
    ):
        user, token = _lms_claim_user(
            test_db, email=f"lti-{uuid.uuid4().hex[:8]}@lti.invalid"
        )

        r = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is False

    async def test_backfilled_verified_lms_claim_is_restamped(
        self, async_client, test_db
    ):
        """Migration 106 keeps the verified flag of older LMS accounts and
        only sets method ``lti_claim``. Activation still proves the address
        and replaces the method."""
        old = datetime(2026, 7, 1, tzinfo=timezone.utc)
        user, token = _lms_claim_user(test_db, email_verified=True)
        user.email_verified_at = old
        test_db.flush()

        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verified is True
        assert user.email_verification_method == "activation"
        assert user.email_verified_at is not None
        assert user.email_verified_at != old
        login = await _login(async_client, user)
        assert login.status_code == 200, login.text

    async def test_already_verified_method_is_kept(self, async_client, test_db):
        user, token = _lms_claim_user(
            test_db, email_verified=True, verification_method="admin"
        )

        r = await async_client.post(
            "/api/auth/activate-account",
            json={
                "token": token,
                "new_password": _PASSWORD,
                "confirm_password": _PASSWORD,
            },
        )

        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.email_verification_method == "admin"


class TestProfileEmailChangeDropsMailedLinks:
    async def test_email_change_clears_reset_token(self, test_db):
        """A reset or activation link sent to the old address must not
        verify the new one."""
        from auth_module.user_service import update_user_profile

        user, token = _lms_claim_user(test_db, email_verified=True)

        update_user_profile(
            test_db, user.id, email=f"new-{uuid.uuid4().hex[:6]}@uni-x.de"
        )

        test_db.refresh(user)
        assert user.password_reset_token is None
        assert user.password_reset_expires is None
        assert user.email_verified is False
