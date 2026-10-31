"""Sessions end when the credentials change (audit S7, revocation part).

A password reset, a password change and a deactivation revoke the user's
refresh tokens, so a stolen refresh cookie stops working. The password change
spares the caller's own session. Also covers the new-password minimum length.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from auth_module import UserCreate, UserLogin
from models import RefreshToken, User
from schemas.auth_schemas import AccountActivateConfirm, PasswordResetConfirm, PasswordUpdate
from schemas.profile_completion_schemas import ProfileCompletionRequest
from services.refresh_token_service import create_refresh_token, create_refresh_token_async

pytestmark = pytest.mark.integration

_OLD = "Altes-Passwort-1"
_NEW = "Neues-Passwort-1"


def _make_user(db, **extra):
    from auth_module.user_service import get_password_hash

    suffix = uuid.uuid4().hex[:10]
    user = User(
        id=f"rev-{suffix}",
        username=f"rev-{suffix}",
        email=f"rev-{suffix}@test.com",
        name="Revocation Tester",
        hashed_password=get_password_hash(_OLD),
        password_set=True,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        **extra,
    )
    db.add(user)
    db.commit()
    return user


def _active(db, user_id):
    db.expire_all()
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.is_active == True)  # noqa: E712
        .count()
    )


class TestPasswordResetRevokes:
    def test_service_reset_revokes_every_session(self, test_db):
        from app.auth_module.password_reset import password_reset_service

        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            password_reset_token=token,
            password_reset_expires=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        create_refresh_token(test_db, user.id)
        create_refresh_token(test_db, user.id)
        other = _make_user(test_db)
        create_refresh_token(test_db, other.id)

        assert password_reset_service.reset_password(test_db, token, _NEW) is True

        assert _active(test_db, user.id) == 0
        assert _active(test_db, other.id) == 1

    @pytest.mark.asyncio
    async def test_reset_endpoint_revokes(self, async_client, test_db):
        token = f"tok-{uuid.uuid4().hex}"
        user = _make_user(
            test_db,
            password_reset_token=token,
            password_reset_expires=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        create_refresh_token(test_db, user.id)

        r = await async_client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": _NEW, "confirm_password": _NEW},
        )
        assert r.status_code == 200, r.text
        assert _active(test_db, user.id) == 0

    def test_failed_reset_revokes_nothing(self, test_db):
        from app.auth_module.password_reset import password_reset_service

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        assert password_reset_service.reset_password(test_db, "wrong", _NEW) is False
        assert _active(test_db, user.id) == 1


class TestPasswordChangeRevokes:
    def test_change_keeps_the_callers_session_only(self, test_db):
        from auth_module.user_service import change_user_password

        user = _make_user(test_db)
        current, _ = create_refresh_token(test_db, user.id)
        create_refresh_token(test_db, user.id)
        create_refresh_token(test_db, user.id)

        assert change_user_password(
            test_db, user.id, _OLD, _NEW, keep_refresh_token=current
        )

        test_db.expire_all()
        remaining = (
            test_db.query(RefreshToken)
            .filter(RefreshToken.user_id == user.id, RefreshToken.is_active == True)  # noqa: E712
            .all()
        )
        from services.refresh_token_service import hash_token

        assert [t.token_hash for t in remaining] == [hash_token(current)]

    def test_change_without_cookie_revokes_all(self, test_db):
        from auth_module.user_service import change_user_password

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        assert change_user_password(test_db, user.id, _OLD, _NEW)
        assert _active(test_db, user.id) == 0

    def test_wrong_current_password_revokes_nothing(self, test_db):
        from fastapi import HTTPException

        from auth_module.user_service import change_user_password

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        with pytest.raises(HTTPException):
            change_user_password(test_db, user.id, "falsch-falsch-1", _NEW)
        assert _active(test_db, user.id) == 1


class TestDeactivationRevokes:
    def test_sync_deactivation_revokes(self, test_db):
        from auth_module.user_service import update_user_status

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        update_user_status(test_db, user.id, False)
        assert _active(test_db, user.id) == 0

    def test_activation_keeps_sessions(self, test_db):
        from auth_module.user_service import update_user_status

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        update_user_status(test_db, user.id, True)
        assert _active(test_db, user.id) == 1

    @pytest.mark.asyncio
    async def test_async_deactivation_revokes(self, async_test_db):
        from sqlalchemy import func, select

        from auth_module.user_service import update_user_status_async

        suffix = uuid.uuid4().hex[:10]
        user = User(
            id=f"rev-{suffix}",
            username=f"rev-{suffix}",
            email=f"rev-{suffix}@test.com",
            name="Revocation Tester",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(user)
        await async_test_db.commit()
        await create_refresh_token_async(async_test_db, user.id)

        await update_user_status_async(async_test_db, user.id, False)

        count = (
            await async_test_db.execute(
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_active == True,  # noqa: E712
                )
            )
        ).scalar()
        assert count == 0


class TestTokenServiceWrapper:
    def test_revoke_all_user_tokens_works(self, test_db):
        from auth_module import RefreshTokenService

        user = _make_user(test_db)
        create_refresh_token(test_db, user.id)
        create_refresh_token(test_db, user.id)
        assert RefreshTokenService.revoke_all_user_tokens(test_db, user.id) == 2
        assert _active(test_db, user.id) == 0


class TestMinimumPasswordLength:
    """New passwords need 12 characters; login does not check the length."""

    @pytest.mark.parametrize(
        "build",
        [
            lambda pw: UserCreate(
                username="newuser",
                email="new@example.com",
                name="New",
                password=pw,
                legal_expertise_level="layperson",
                german_proficiency="native",
            ),
            lambda pw: PasswordUpdate(current_password="x", new_password=pw, confirm_password=pw),
            lambda pw: PasswordResetConfirm(token="t", new_password=pw, confirm_password=pw),
            lambda pw: AccountActivateConfirm(token="t", new_password=pw, confirm_password=pw),
            lambda pw: ProfileCompletionRequest(username="newuser", password=pw),
        ],
        ids=["signup", "change", "reset", "activate", "complete-profile"],
    )
    def test_eleven_rejected_twelve_accepted(self, build):
        with pytest.raises(ValidationError):
            build("a" * 11)
        build("a" * 12)

    def test_login_accepts_short_existing_passwords(self):
        assert UserLogin(username="old", password="kurz").password == "kurz"
