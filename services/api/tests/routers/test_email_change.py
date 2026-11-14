"""Changing the account email on the profile page (pending address + mailed link).

Regression for the lockout reported on 2026-11-14: ``PUT /api/auth/profile``
used to set the new address and ``email_verified = False`` without mailing
anything, so the next password login was refused (403), the old address no
longer matched (401) and the new one could not be registered again. Now the
new address waits in ``pending_email`` until the link mailed to it is used,
and the current address stays the verified login address until then.
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PASSWORD = "Email-Change-Passw0rd!"


def _make_user(db, *, email=None, email_verified=True, **fields):
    from auth_module.user_service import get_password_hash

    suffix = uuid.uuid4().hex[:10]
    user = User(
        id=f"ec-{suffix}",
        username=f"ec-{suffix}",
        email=email or f"ec-a-{suffix}@example.org",
        name="Email Changer",
        hashed_password=get_password_hash(_PASSWORD),
        password_set=True,
        is_superadmin=False,
        is_active=True,
        email_verified=email_verified,
        email_verification_method="self" if email_verified else None,
        created_at=datetime.now(UTC),
        **fields,
    )
    db.add(user)
    db.commit()
    return user


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
        email_verified=bool(db_user.email_verified),
        created_at=db_user.created_at or datetime.now(UTC),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


@contextmanager
def _mailer(sent=True):
    """Fake mail service; ``calls`` records each confirmation mail."""
    service = MagicMock()
    service.send_email_change_confirmation_email = AsyncMock(return_value=sent)
    with patch("auth_module.email_change._mail_service", return_value=service):
        yield service.send_email_change_confirmation_email


def _token_of(mail_call) -> str:
    return mail_call.kwargs["confirm_url"].rsplit("/confirm-email-change/", 1)[1]


async def _login(async_client, login):
    return await async_client.post(
        "/api/auth/login", json={"username": login, "password": _PASSWORD}
    )


async def _change_email(async_client, user, email, **extra):
    with _as_user(user):
        return await async_client.put(
            "/api/auth/profile", json={"name": user.name, "email": email, **extra}
        )


class TestEmailChangeKeepsLoginUntilConfirmed:
    async def test_full_flow_old_address_works_until_link_is_used(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        old_email = user.email
        typed = f"EC-New-{uuid.uuid4().hex[:8]}@Example.org"
        new_email = typed.lower()

        with _mailer() as send:
            r = await _change_email(
                async_client, user, typed, language="de"
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == old_email
        assert body["pending_email"] == new_email
        assert body["pending_email_sent_at"] is not None
        send.assert_awaited_once()
        assert send.call_args.kwargs["to_email"] == new_email
        assert send.call_args.kwargs["language"] == "de"
        token = _token_of(send.call_args)

        test_db.refresh(user)
        assert user.email == old_email
        assert user.email_verified is True
        assert user.pending_email == new_email
        # Only a digest of the token is stored.
        assert user.pending_email_token and token not in user.pending_email_token

        # Before confirming: the old address logs in, the new one does not.
        assert (await _login(async_client, old_email)).status_code == 200
        assert (await _login(async_client, new_email)).status_code == 401

        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": token}
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == new_email

        test_db.refresh(user)
        assert user.email == new_email
        assert user.email_verified is True
        assert user.email_verification_method == "self"
        assert user.email_verified_at is not None
        assert user.pending_email is None
        assert user.pending_email_token is None
        assert user.pending_email_sent_at is None

        assert (await _login(async_client, new_email)).status_code == 200
        assert (await _login(async_client, old_email)).status_code == 401

        # The link works once.
        again = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": token}
        )
        assert again.status_code == 400
        assert again.json()["detail"]["code"] == "invalid_or_expired"

    async def test_confirm_records_profile_history(self, async_client, test_db):
        from models import UserProfileHistory

        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-hist-{uuid.uuid4().hex[:8]}@example.org"
            )
        await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )

        entries = (
            test_db.query(UserProfileHistory)
            .filter(
                UserProfileHistory.user_id == user.id,
                UserProfileHistory.change_type == "email_change",
            )
            .all()
        )
        assert len(entries) == 1
        assert entries[0].changed_fields == ["email"]

    async def test_other_profile_fields_are_saved_with_the_request(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        with _mailer():
            with _as_user(user):
                r = await async_client.put(
                    "/api/auth/profile",
                    json={
                        "name": "Renamed Person",
                        "email": f"ec-f-{uuid.uuid4().hex[:8]}@example.org",
                        "job": "Richterin",
                    },
                )
        assert r.status_code == 200, r.text
        test_db.refresh(user)
        assert user.name == "Renamed Person"
        assert user.job == "Richterin"


class TestEmailChangeNoChange:
    async def test_same_address_in_other_case_is_no_change(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send:
            r = await _change_email(async_client, user, user.email.upper())
        assert r.status_code == 200, r.text
        assert r.json()["pending_email"] is None
        send.assert_not_awaited()
        test_db.refresh(user)
        assert user.email_verified is True

    async def test_saving_again_with_the_pending_address_sends_nothing(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        new_email = f"ec-again-{uuid.uuid4().hex[:8]}@example.org"
        with _mailer() as send:
            await _change_email(async_client, user, new_email)
            first_token = _token_of(send.call_args)
            r = await _change_email(async_client, user, new_email.upper())
        assert r.status_code == 200, r.text
        assert send.await_count == 1
        # The link already mailed keeps working.
        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": first_token}
        )
        assert r.status_code == 200, r.text

    async def test_profile_without_email_field_keeps_pending_change(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        new_email = f"ec-keep-{uuid.uuid4().hex[:8]}@example.org"
        with _mailer():
            await _change_email(async_client, user, new_email)
            with _as_user(user):
                r = await async_client.put("/api/auth/profile", json={"job": "Anwalt"})
        assert r.status_code == 200, r.text
        assert r.json()["pending_email"] == new_email


class TestEmailChangeRefused:
    async def test_address_of_another_account_is_refused_case_insensitively(
        self, async_client, test_db
    ):
        other = _make_user(test_db)
        user = _make_user(test_db)
        with _mailer() as send:
            with _as_user(user):
                r = await async_client.put(
                    "/api/auth/profile",
                    json={"name": "Not Saved", "email": other.email.upper()},
                )
        assert r.status_code == 400
        assert r.json()["detail"] == "Email already registered to another user"
        send.assert_not_awaited()
        test_db.refresh(user)
        assert user.name == "Email Changer"
        assert user.pending_email is None

    async def test_address_taken_before_confirm_is_409_and_drops_the_change(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        new_email = f"ec-race-{uuid.uuid4().hex[:8]}@example.org"
        with _mailer() as send:
            await _change_email(async_client, user, new_email)
        _make_user(test_db, email=new_email)

        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "email_taken"
        test_db.refresh(user)
        assert user.email != new_email
        assert user.pending_email is None

    async def test_expired_link_is_refused(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-old-{uuid.uuid4().hex[:8]}@example.org"
            )
        test_db.refresh(user)
        user.pending_email_sent_at = datetime.now(UTC) - timedelta(hours=49)
        test_db.commit()

        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_or_expired"
        test_db.refresh(user)
        assert user.pending_email is not None

    async def test_unknown_token_is_refused(self, async_client, test_db):
        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": "not-a-token"}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_or_expired"


class TestEmailChangeMailFailure:
    async def test_failed_mail_keeps_the_old_login_and_offers_resend(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        new_email = f"ec-fail-{uuid.uuid4().hex[:8]}@example.org"
        with _mailer(sent=False) as send:
            r = await _change_email(async_client, user, new_email)
        assert r.status_code == 200, r.text
        assert r.json()["pending_email"] == new_email
        assert r.json()["pending_email_sent_at"] is None
        undelivered = _token_of(send.call_args)

        test_db.refresh(user)
        assert user.pending_email_token is None
        assert (await _login(async_client, user.email)).status_code == 200
        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": undelivered}
        )
        assert r.status_code == 400

        # No delivered mail, so no wait before the resend.
        with _mailer() as send:
            with _as_user(user):
                r = await async_client.post("/api/auth/email-change/resend", json={})
        assert r.status_code == 200, r.text
        assert r.json()["pending_email_sent_at"] is not None
        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        assert r.status_code == 200, r.text


class TestEmailChangeResendAndCancel:
    async def test_resend_replaces_the_link(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-re-{uuid.uuid4().hex[:8]}@example.org"
            )
            first = _token_of(send.call_args)
        test_db.refresh(user)
        user.pending_email_sent_at = datetime.now(UTC) - timedelta(minutes=6)
        test_db.commit()

        with _mailer() as send:
            with _as_user(user):
                r = await async_client.post(
                    "/api/auth/email-change/resend", json={"language": "fr"}
                )
        assert r.status_code == 200, r.text
        assert send.call_args.kwargs["language"] == "fr"
        second = _token_of(send.call_args)

        old = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": first}
        )
        assert old.status_code == 400
        new = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": second}
        )
        assert new.status_code == 200, new.text

    async def test_resend_within_five_minutes_is_429(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-429-{uuid.uuid4().hex[:8]}@example.org"
            )
            with _as_user(user):
                r = await async_client.post("/api/auth/email-change/resend", json={})
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == "rate_limited"
        assert send.await_count == 1

    async def test_resend_without_pending_change_is_409(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send, _as_user(user):
            r = await async_client.post("/api/auth/email-change/resend", json={})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "no_pending_email"
        send.assert_not_awaited()

    async def test_cancel_drops_the_change_and_its_link(self, async_client, test_db):
        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-cancel-{uuid.uuid4().hex[:8]}@example.org"
            )
        with _as_user(user):
            r = await async_client.delete("/api/auth/email-change")
        assert r.status_code == 200, r.text
        assert r.json()["pending_email"] is None

        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        assert r.status_code == 400
        test_db.refresh(user)
        assert user.email_verified is True


class TestEmailChangeAndOtherLinks:
    async def test_password_reset_keeps_working_on_the_current_address(
        self, async_client, test_db
    ):
        user = _make_user(test_db)
        old_email = user.email
        with _mailer():
            await _change_email(
                async_client, user, f"ec-reset-{uuid.uuid4().hex[:8]}@example.org"
            )
        from app.auth_module.password_reset import password_reset_service

        with patch.object(
            password_reset_service,
            "send_password_reset_email",
            new=AsyncMock(return_value=True),
        ) as send_reset:
            r = await async_client.post(
                "/api/auth/request-password-reset", json={"email": old_email}
            )
        assert r.status_code == 200, r.text
        send_reset.assert_awaited_once()
        assert send_reset.call_args.kwargs["user"].email == old_email
        test_db.refresh(user)
        assert user.email == old_email
        assert user.email_verified is True

    async def test_confirm_drops_links_mailed_to_the_old_address(
        self, async_client, test_db
    ):
        user = _make_user(
            test_db,
            password_reset_token=f"reset-{uuid.uuid4().hex}",
            password_reset_expires=datetime.now(UTC) + timedelta(hours=1),
        )
        with _mailer() as send:
            await _change_email(
                async_client, user, f"ec-links-{uuid.uuid4().hex[:8]}@example.org"
            )
        test_db.refresh(user)
        # Requesting the change does not touch them: the old address is
        # still the account's address.
        assert user.password_reset_token is not None

        await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        test_db.refresh(user)
        assert user.password_reset_token is None
        assert user.password_reset_expires is None

    async def test_confirm_accepts_open_invitations_to_the_new_address(
        self, async_client, test_db
    ):
        from models import (
            Invitation,
            Organization,
            OrganizationMembership,
            OrganizationRole,
        )

        inviter = _make_user(test_db)
        org = Organization(
            id=f"org-{uuid.uuid4().hex[:10]}",
            name="Inviting Org",
            slug=f"inviting-{uuid.uuid4().hex[:8]}",
            display_name="Inviting Org",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        test_db.add(org)
        test_db.flush()
        new_email = f"ec-inv-{uuid.uuid4().hex[:8]}@example.org"
        test_db.add(
            Invitation(
                id=f"inv-{uuid.uuid4().hex[:10]}",
                organization_id=org.id,
                email=new_email,
                role=OrganizationRole.ANNOTATOR,
                token=f"inv-{uuid.uuid4().hex}",
                invited_by=inviter.id,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                accepted=False,
            )
        )
        test_db.commit()

        user = _make_user(test_db)
        with _mailer() as send:
            await _change_email(async_client, user, new_email)
        # Only a pending address: no membership yet.
        assert (
            test_db.query(OrganizationMembership)
            .filter_by(user_id=user.id, organization_id=org.id)
            .first()
            is None
        )
        r = await async_client.post(
            "/api/auth/email-change/confirm", json={"token": _token_of(send.call_args)}
        )
        assert r.status_code == 200, r.text
        test_db.expire_all()
        assert (
            test_db.query(OrganizationMembership)
            .filter_by(user_id=user.id, organization_id=org.id, is_active=True)
            .first()
            is not None
        )


class TestStrandedAccountsRecover:
    """Accounts an earlier profile change left unverified (address swapped,
    no mail ever sent) are not rewritten by the migration; the resend that
    the verification page now always offers mails them a working link."""

    async def test_resend_then_verify_lets_the_stranded_account_log_in(
        self, async_client, test_db
    ):
        from auth_module.email_verification import email_verification_service

        user = _make_user(test_db, email_verified=False)
        assert user.email_verification_token is None
        assert (await _login(async_client, user.email)).status_code == 403

        with patch.object(
            email_verification_service.email_service,
            "send_verification_email",
            new=AsyncMock(return_value=True),
        ) as send:
            r = await async_client.post(
                "/api/auth/resend-verification",
                json={"email": user.email.upper(), "language": "de"},
            )
        assert r.status_code == 200, r.text
        send.assert_awaited_once()
        test_db.refresh(user)
        token = user.email_verification_token
        assert token

        r = await async_client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        assert (await _login(async_client, user.email)).status_code == 200


class TestConfirmationMail:
    def test_mail_names_only_the_new_address_and_escapes_the_name(self):
        from email_service import EmailService

        subject, body = EmailService().build_email_change_confirmation_email(
            confirm_url="https://benger.example/confirm-email-change/tok123",
            new_email="new@example.org",
            user_name="D&#x27;Amico <b>",
            brand_name="BenGER",
            frontend_host="benger.example",
            language="de",
            expiry_hours=48,
        )
        assert "neue E-Mail-Adresse" in subject
        assert "new@example.org" in body
        assert "https://benger.example/confirm-email-change/tok123" in body
        assert "48 Stunden" in body
        assert "D&#39;Amico &lt;b&gt;" in body

    @pytest.mark.parametrize("language,phrase", [("en", "Confirm"), ("fr", "Confirmez")])
    def test_mail_exists_in_every_language(self, language, phrase):
        from email_service import EmailService

        subject, _ = EmailService().build_email_change_confirmation_email(
            confirm_url="https://x/confirm-email-change/t",
            new_email="n@example.org",
            language=language,
        )
        assert phrase in subject
