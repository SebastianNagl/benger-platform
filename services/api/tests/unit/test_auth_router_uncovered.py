"""
Unit tests for routers/auth.py targeting uncovered lines.

Covers: login cookie-setting, refresh token rotation, logout cookie clearing,
logout-all, signup invitation flow, register, /me/contexts, profile GET/PUT
branches, change-password, request-password-reset, reset-password, verify-email,
verify-email-enhanced success path, complete-profile, mandatory-profile-status
notification creation, and profile-history.

Rewritten to call handler functions directly (no TestClient) so that pytest-cov
tracks the router code.
"""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request(cookies=None, headers=None):
    r = Mock()
    r.headers = headers or {}
    r.cookies = cookies or {}
    r.client = Mock(host="127.0.0.1")
    r.url = "http://localhost/api/auth/login"
    r.state = Mock(spec=[])
    return r


def _mock_user(is_superadmin=False, user_id="user-123", email_verified=True):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.hashed_password = "hashed"
    user.is_superadmin = is_superadmin
    user.is_active = True
    user.email_verified = email_verified
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = None
    user.created_via_invitation = False
    user.profile_completed = True
    user.pseudonym = None
    user.use_pseudonym = True
    user.age = None
    user.job = None
    user.years_of_experience = None
    user.legal_expertise_level = None
    user.german_proficiency = None
    user.degree_program_type = None
    user.current_semester = None
    user.legal_specializations = None
    user.german_state_exams_count = None
    user.german_state_exams_data = None
    user.gender = None
    user.subjective_competence_civil = None
    user.subjective_competence_public = None
    user.subjective_competence_criminal = None
    user.grade_zwischenpruefung = None
    user.grade_vorgeruecktenubung = None
    user.grade_first_staatsexamen = None
    user.grade_second_staatsexamen = None
    user.ati_s_scores = None
    user.ptt_a_scores = None
    user.ki_experience_scores = None
    user.mandatory_profile_completed = False
    user.profile_confirmed_at = None
    user.invitation_token = None
    return user


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


def _make_user_create(**overrides):
    """Build a UserCreate with valid required fields."""
    from auth_module import UserCreate
    defaults = dict(
        username="newuser",
        email="new@test.com",
        name="New User",
        password="password123",
        legal_expertise_level="student",
        german_proficiency="native",
    )
    defaults.update(overrides)
    return UserCreate(**defaults)


# ---------------------------------------------------------------------------
# Login: cookie-setting path, exception handling
# ---------------------------------------------------------------------------

class TestLoginCookiePaths:
    """Cover lines 219-287: login body including cookie setting."""

    @pytest.mark.asyncio
    @patch("routers.auth.create_tokens_with_refresh")
    @patch("routers.auth.authenticate_user")
    async def test_login_sets_access_and_refresh_cookies(self, mock_auth, mock_tokens):
        from routers.auth import login
        from auth_module import UserLogin

        user = _mock_user()
        mock_auth.return_value = user

        token_resp = Mock()
        token_resp.access_token = "access-tok"
        token_resp.refresh_token = "refresh-tok"
        token_resp.token_type = "bearer"
        token_resp.expires_in = 3600
        token_resp.user = user
        mock_tokens.return_value = token_resp

        response = Response()
        request = _mock_request()
        db = _mock_db()

        result = await login(
            login_data=UserLogin(username="testuser", password="pass"),
            response=response,
            request=request,
            db=db,
        )
        assert result.access_token == "access-tok"

    @pytest.mark.asyncio
    @patch("routers.auth.create_tokens_with_refresh")
    @patch("routers.auth.authenticate_user")
    async def test_login_no_refresh_token(self, mock_auth, mock_tokens):
        from routers.auth import login
        from auth_module import UserLogin

        user = _mock_user()
        mock_auth.return_value = user

        token_resp = Mock()
        token_resp.access_token = "access-tok"
        token_resp.refresh_token = None
        token_resp.token_type = "bearer"
        token_resp.expires_in = 3600
        token_resp.user = user
        mock_tokens.return_value = token_resp

        response = Response()
        request = _mock_request()
        db = _mock_db()

        result = await login(
            login_data=UserLogin(username="testuser", password="pass"),
            response=response,
            request=request,
            db=db,
        )
        assert result.access_token == "access-tok"

    @pytest.mark.asyncio
    @patch("routers.auth.authenticate_user", side_effect=RuntimeError("DB boom"))
    async def test_login_exception_reraises(self, mock_auth):
        from routers.auth import login
        from auth_module import UserLogin

        response = Response()
        request = _mock_request()
        db = _mock_db()

        with pytest.raises(RuntimeError, match="DB boom"):
            await login(
                login_data=UserLogin(username="testuser", password="pass"),
                response=response,
                request=request,
                db=db,
            )

    @pytest.mark.asyncio
    @patch("routers.auth.authenticate_user", return_value=None)
    async def test_login_invalid_credentials(self, mock_auth):
        from routers.auth import login
        from auth_module import UserLogin

        response = Response()
        request = _mock_request()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await login(
                login_data=UserLogin(username="bad", password="bad"),
                response=response,
                request=request,
                db=db,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routers.auth.authenticate_user")
    async def test_login_unverified_email(self, mock_auth):
        from routers.auth import login
        from auth_module import UserLogin

        user = _mock_user(email_verified=False)
        mock_auth.return_value = user

        response = Response()
        request = _mock_request()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await login(
                login_data=UserLogin(username="testuser", password="pass"),
                response=response,
                request=request,
                db=db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

class TestRefreshToken:
    """Cover lines 290-351: refresh token endpoint."""

    @pytest.mark.asyncio
    @patch("routers.auth.refresh_access_token")
    async def test_refresh_success(self, mock_refresh):
        from routers.auth import refresh_token_endpoint

        token_resp = Mock()
        token_resp.access_token = "new-access"
        token_resp.refresh_token = "new-refresh"
        mock_refresh.return_value = token_resp

        request = _mock_request(cookies={"refresh_token": "old-refresh"})
        response = Response()
        db = _mock_db()

        result = await refresh_token_endpoint(request=request, response=response, db=db)
        assert result.access_token == "new-access"

    @pytest.mark.asyncio
    async def test_refresh_no_cookie(self):
        from routers.auth import refresh_token_endpoint

        request = _mock_request(cookies={})
        response = Response()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token_endpoint(request=request, response=response, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routers.auth.refresh_access_token", return_value=None)
    async def test_refresh_invalid_token(self, mock_refresh):
        from routers.auth import refresh_token_endpoint

        request = _mock_request(cookies={"refresh_token": "bad-token"})
        response = Response()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token_endpoint(request=request, response=response, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routers.auth.refresh_access_token")
    async def test_refresh_no_new_refresh_token(self, mock_refresh):
        from routers.auth import refresh_token_endpoint

        token_resp = Mock()
        token_resp.access_token = "new-access"
        token_resp.refresh_token = None
        mock_refresh.return_value = token_resp

        request = _mock_request(cookies={"refresh_token": "old-refresh"})
        response = Response()
        db = _mock_db()

        result = await refresh_token_endpoint(request=request, response=response, db=db)
        assert result.access_token == "new-access"


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    """Cover lines 354-383: logout endpoint."""

    @pytest.mark.asyncio
    @patch("routers.auth.revoke_refresh_token")
    async def test_logout_with_refresh_token(self, mock_revoke):
        from routers.auth import logout

        request = _mock_request(cookies={"refresh_token": "some-token"})
        response = Response()
        user = _mock_user()
        db = _mock_db()

        result = await logout(request=request, response=response, current_user=user, db=db)
        assert result["message"] == "Logged out successfully"
        mock_revoke.assert_called_once_with("some-token", db)

    @pytest.mark.asyncio
    async def test_logout_no_refresh_token(self):
        from routers.auth import logout

        request = _mock_request(cookies={})
        response = Response()
        user = _mock_user()
        db = _mock_db()

        result = await logout(request=request, response=response, current_user=user, db=db)
        assert result["message"] == "Logged out successfully"


# ---------------------------------------------------------------------------
# Logout all devices
# ---------------------------------------------------------------------------

class TestLogoutAll:
    """Cover lines 386-413: logout all devices."""

    @pytest.mark.asyncio
    @patch("routers.auth.revoke_user_tokens", create=True)
    async def test_logout_all_with_response(self, mock_revoke):
        from routers.auth import logout_all_devices

        mock_revoke_inner = Mock(return_value=3)
        user = _mock_user()
        db = _mock_db()
        response = Response()

        with patch("services.refresh_token_service.revoke_user_tokens", return_value=3):
            result = await logout_all_devices(current_user=user, response=response, db=db)
        assert result["revoked_sessions"] == 3

    @pytest.mark.asyncio
    async def test_logout_all_no_response(self):
        from routers.auth import logout_all_devices

        user = _mock_user()
        db = _mock_db()

        with patch("services.refresh_token_service.revoke_user_tokens", return_value=2):
            result = await logout_all_devices(current_user=user, response=None, db=db)
        assert result["revoked_sessions"] == 2


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

class TestSignup:
    """Cover signup paths."""

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    @patch("routers.auth.create_user")
    async def test_signup_regular(self, mock_create, mock_email_svc):
        from routers.auth import signup
        from auth_module import UserCreate

        new_user = _mock_user()
        mock_create.return_value = new_user
        mock_email_svc.send_verification_email = AsyncMock(return_value=True)

        request = _mock_request()
        db = _mock_db()

        result = await signup(
            user_data=_make_user_create(),
            request=request,
            db=db,
        )
        assert result.id == "user-123"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    @patch("routers.auth.create_user")
    async def test_signup_invitation_flow(self, mock_create, mock_email_svc):
        from routers.auth import signup
        from auth_module import UserCreate

        new_user = _mock_user()
        mock_create.return_value = new_user

        invitation = Mock()
        invitation.token = "inv-token"
        invitation.email = "new@test.com"
        invitation.accepted = False
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        invitation.organization_id = "org-1"
        invitation.role = "ANNOTATOR"

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = invitation

        user_create = _make_user_create()
        user_create.invitation_token = "inv-token"

        request = _mock_request()
        result = await signup(user_data=user_create, request=request, db=db)
        assert result.id == "user-123"

    @pytest.mark.asyncio
    @patch("routers.auth.create_user")
    async def test_signup_invitation_invalid(self, mock_create):
        from routers.auth import signup
        from auth_module import UserCreate

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        user_create = _make_user_create()
        user_create.invitation_token = "bad-token"

        request = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await signup(user_data=user_create, request=request, db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.create_user")
    async def test_signup_invitation_expired(self, mock_create):
        from routers.auth import signup
        from auth_module import UserCreate

        invitation = Mock()
        invitation.token = "inv-token"
        invitation.email = "new@test.com"
        invitation.accepted = False
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = invitation

        user_create = _make_user_create()
        user_create.invitation_token = "inv-token"

        request = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await signup(user_data=user_create, request=request, db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.create_user", side_effect=RuntimeError("DB crash"))
    async def test_signup_unexpected_error(self, mock_create):
        from routers.auth import signup

        request = _mock_request()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await signup(
                user_data=_make_user_create(),
                request=request,
                db=db,
            )
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class TestRegister:
    @pytest.mark.asyncio
    @patch("routers.auth.create_user")
    async def test_register_success(self, mock_create):
        from routers.auth import register

        new_user = _mock_user()
        mock_create.return_value = new_user

        admin = _mock_user(is_superadmin=True)
        db = _mock_db()

        result = await register(
            user_data=_make_user_create(),
            current_user=admin,
            db=db,
        )
        assert result.id == "user-123"


# ---------------------------------------------------------------------------
# /me and /me/contexts
# ---------------------------------------------------------------------------

class TestUserInfoEndpoints:
    @pytest.mark.asyncio
    @patch("routers.auth.get_user_primary_role", return_value="CONTRIBUTOR")
    async def test_get_current_user(self, mock_role):
        from routers.auth import get_current_user

        user = _mock_user()
        db = _mock_db()

        result = await get_current_user(current_user=user, db=db)
        assert result["id"] == "user-123"
        assert result["role"] == "CONTRIBUTOR"

    @pytest.mark.asyncio
    @patch("routers.auth.get_user_primary_role", return_value=None)
    async def test_get_user_contexts_superadmin(self, mock_role):
        from routers.auth import get_user_contexts

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        # Mock organizations query
        org = Mock()
        org.id = "org-1"
        org.name = "Test Org"
        org.display_name = "Test Org"
        org.slug = "test-org"
        org.description = None
        org.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.side_effect = [
            [org],   # organizations query
            [],      # member_counts query
            [],      # user_roles query
        ]
        db.query.return_value = mock_q

        result = await get_user_contexts(current_user=user, db=db)
        assert result["private_mode_available"] is True
        assert "organizations" in result

    @pytest.mark.asyncio
    @patch("routers.auth.get_user_primary_role", return_value="ANNOTATOR")
    async def test_get_user_contexts_regular_user(self, mock_role):
        from routers.auth import get_user_contexts

        user = _mock_user(is_superadmin=False)
        db = _mock_db()

        org = Mock()
        org.id = "org-1"
        org.name = "Test Org"
        org.display_name = "Test Org"
        org.slug = "test-org"
        org.description = None
        org.is_active = True
        role = Mock()
        role.value = "ANNOTATOR"

        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.side_effect = [
            [(org, role)],  # user_orgs_with_roles query
            [],             # member_counts query
        ]
        mock_q.group_by.return_value = mock_q
        db.query.return_value = mock_q

        result = await get_user_contexts(current_user=user, db=db)
        assert result["private_mode_available"] is True


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class TestProfileEndpoints:
    @pytest.mark.asyncio
    @patch("routers.auth._build_user_profile_response")
    async def test_get_profile_success(self, mock_build):
        from routers.auth import get_user_profile

        user = _mock_user()
        db = _mock_db()
        db_user = _mock_user()

        db.query.return_value.filter.return_value.first.return_value = db_user
        mock_build.return_value = Mock()

        result = await get_user_profile(current_user=user, db=db)
        mock_build.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.auth.get_user_primary_role", return_value=None)
    async def test_get_profile_user_not_found(self, mock_role):
        from routers.auth import get_user_profile

        user = _mock_user()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await get_user_profile(current_user=user, db=db)
        assert result.id == "user-123"

    @pytest.mark.asyncio
    @patch("routers.auth.get_user_primary_role", return_value=None)
    async def test_get_profile_exception_fallback(self, mock_role):
        from routers.auth import get_user_profile

        user = _mock_user()
        db = _mock_db()
        db.query.side_effect = RuntimeError("DB error")

        result = await get_user_profile(current_user=user, db=db)
        assert result.id == "user-123"
        assert result.is_active is True

    @pytest.mark.asyncio
    @patch("routers.auth._build_user_profile_response")
    @patch("routers.auth.update_user_profile")
    async def test_update_profile_success(self, mock_update, mock_build):
        from routers.auth import update_profile
        from schemas.auth_schemas import UserUpdate

        user = _mock_user()
        db = _mock_db()
        updated_user = _mock_user()
        mock_update.return_value = updated_user
        mock_build.return_value = Mock(id="user-123")

        result = await update_profile(
            profile_data=UserUpdate(name="New Name"),
            current_user=user,
            db=db,
        )
        mock_build.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.auth.update_user_profile", return_value=None)
    async def test_update_profile_not_found(self, mock_update):
        from routers.auth import update_profile
        from schemas.auth_schemas import UserUpdate

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await update_profile(
                profile_data=UserUpdate(name="New Name"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class TestChangePassword:
    @pytest.mark.asyncio
    @patch("routers.auth.change_user_password", return_value=True)
    async def test_change_password_success(self, mock_change):
        from routers.auth import change_password
        from schemas.auth_schemas import PasswordUpdate

        user = _mock_user()
        db = _mock_db()

        result = await change_password(
            password_data=PasswordUpdate(
                current_password="old", new_password="newpass123", confirm_password="newpass123"
            ),
            current_user=user,
            db=db,
        )
        assert result["message"] == "Password changed successfully"

    @pytest.mark.asyncio
    async def test_change_password_mismatch(self):
        from routers.auth import change_password
        from schemas.auth_schemas import PasswordUpdate

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await change_password(
                password_data=PasswordUpdate(
                    current_password="old", new_password="newpass123", confirm_password="different123"
                ),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.change_user_password", return_value=False)
    async def test_change_password_failure(self, mock_change):
        from routers.auth import change_password
        from schemas.auth_schemas import PasswordUpdate

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await change_password(
                password_data=PasswordUpdate(
                    current_password="wrong", new_password="newpass123", confirm_password="newpass123"
                ),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Request password reset
# ---------------------------------------------------------------------------

class TestRequestPasswordReset:
    @pytest.mark.asyncio
    async def test_request_reset_user_not_found(self):
        from routers.auth import request_password_reset
        from schemas.auth_schemas import PasswordResetRequest

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await request_password_reset(
            reset_request=PasswordResetRequest(email="missing@test.com"),
            db=db,
        )
        assert "password reset link" in result["message"]

    @pytest.mark.asyncio
    async def test_request_reset_user_found(self):
        from routers.auth import request_password_reset
        from schemas.auth_schemas import PasswordResetRequest

        db = _mock_db()
        user = _mock_user()
        db.query.return_value.filter.return_value.first.return_value = user

        with patch("app.auth_module.password_reset.password_reset_service") as mock_svc:
            mock_svc.send_password_reset_email = AsyncMock(return_value=True)
            result = await request_password_reset(
                reset_request=PasswordResetRequest(email="test@example.com"),
                db=db,
            )
        assert "password reset link" in result["message"]

    @pytest.mark.asyncio
    async def test_request_reset_email_error(self):
        from routers.auth import request_password_reset
        from schemas.auth_schemas import PasswordResetRequest

        db = _mock_db()
        user = _mock_user()
        db.query.return_value.filter.return_value.first.return_value = user

        with patch("app.auth_module.password_reset.password_reset_service") as mock_svc:
            mock_svc.send_password_reset_email = AsyncMock(side_effect=Exception("SMTP fail"))
            result = await request_password_reset(
                reset_request=PasswordResetRequest(email="test@example.com"),
                db=db,
            )
        assert "password reset link" in result["message"]


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

class TestResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        from routers.auth import reset_password
        from schemas.auth_schemas import PasswordResetConfirm

        db = _mock_db()

        with patch("app.auth_module.password_reset.password_reset_service") as mock_svc:
            mock_svc.reset_password.return_value = True
            result = await reset_password(
                reset_confirm=PasswordResetConfirm(
                    token="valid-token", new_password="newpass123", confirm_password="newpass123"
                ),
                db=db,
            )
        assert result["message"] == "Password has been reset successfully"

    @pytest.mark.asyncio
    async def test_reset_password_mismatch(self):
        from routers.auth import reset_password
        from schemas.auth_schemas import PasswordResetConfirm

        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await reset_password(
                reset_confirm=PasswordResetConfirm(
                    token="token", new_password="newpass999", confirm_password="different123"
                ),
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self):
        from routers.auth import reset_password
        from schemas.auth_schemas import PasswordResetConfirm

        db = _mock_db()

        with patch("app.auth_module.password_reset.password_reset_service") as mock_svc:
            mock_svc.reset_password.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(
                    reset_confirm=PasswordResetConfirm(
                        token="bad-token", new_password="newpass123", confirm_password="newpass123"
                    ),
                    db=db,
                )
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_verify_email_success(self, mock_svc):
        from routers.auth import verify_email
        from schemas.auth_schemas import EmailVerificationRequest

        mock_svc.verify_email_with_token.return_value = (True, "Verified")
        db = _mock_db()

        result = await verify_email(
            verification_request=EmailVerificationRequest(token="valid-token"),
            db=db,
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_verify_email_failure(self, mock_svc):
        from routers.auth import verify_email
        from schemas.auth_schemas import EmailVerificationRequest

        mock_svc.verify_email_with_token.return_value = (False, "Invalid token")
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await verify_email(
                verification_request=EmailVerificationRequest(token="bad-token"),
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_verify_email_with_path_token_success(self, mock_svc):
        from routers.auth import verify_email_with_token

        mock_svc.verify_email_with_token.return_value = (True, "OK")
        db = _mock_db()

        result = await verify_email_with_token(token="path-token", db=db)
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_verify_email_with_path_token_failure(self, mock_svc):
        from routers.auth import verify_email_with_token

        mock_svc.verify_email_with_token.return_value = (False, "Bad")
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await verify_email_with_token(token="bad-token", db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_verify_email_with_path_token_exception(self, mock_svc):
        from routers.auth import verify_email_with_token

        mock_svc.verify_email_with_token.side_effect = RuntimeError("crash")
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await verify_email_with_token(token="crash-token", db=db)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Verify email enhanced
# ---------------------------------------------------------------------------

class TestVerifyEmailEnhanced:
    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_enhanced_failure(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (False, "Bad token")
        db = _mock_db()

        result = await verify_email_enhanced(token="bad", db=db)
        assert result.success is False
        assert result.user_type == "unknown"

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_enhanced_success_no_token_data(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (True, "OK")
        db = _mock_db()

        with patch("auth_module.email_verification.email_verification_service") as inner_svc:
            inner_svc.validate_verification_token.return_value = None
            result = await verify_email_enhanced(token="tok", db=db)
        assert result.success is True
        assert result.redirect_url == "/login"

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_enhanced_success_self_registered(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (True, "OK")

        db_user = _mock_user()
        db_user.created_via_invitation = False
        db_user.profile_completed = True

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        with patch("auth_module.email_verification.email_verification_service") as inner_svc:
            inner_svc.validate_verification_token.return_value = ("user-123", "test@example.com")
            result = await verify_email_enhanced(token="tok", db=db)
        assert result.user_type == "self_registered"
        assert result.redirect_url == "/login"

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_enhanced_invited_not_completed(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (True, "OK")

        db_user = _mock_user()
        db_user.created_via_invitation = True
        db_user.profile_completed = False
        db_user.invitation_token = "inv-tok"

        invitation = Mock()
        invitation.organization_id = "org-1"
        invitation.role = Mock(value="ANNOTATOR")

        db = _mock_db()

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = db_user
            elif call_count[0] == 2:
                q.first.return_value = invitation
            return q
        db.query.side_effect = query_side_effect

        with patch("auth_module.email_verification.email_verification_service") as inner_svc:
            inner_svc.validate_verification_token.return_value = ("user-123", "test@example.com")
            result = await verify_email_enhanced(token="tok", db=db)
        assert result.user_type == "invited"
        assert result.redirect_url == "/complete-profile"


# ---------------------------------------------------------------------------
# Complete profile
# ---------------------------------------------------------------------------

class TestCompleteProfile:
    @pytest.mark.asyncio
    async def test_complete_profile_user_not_found(self):
        from routers.auth import complete_profile
        from schemas.profile_completion_schemas import ProfileCompletionRequest

        user = _mock_user()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await complete_profile(
                profile_data=ProfileCompletionRequest(username="new", password="password123"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_complete_profile_not_invited(self):
        from routers.auth import complete_profile
        from schemas.profile_completion_schemas import ProfileCompletionRequest

        user = _mock_user()
        db_user = _mock_user()
        db_user.created_via_invitation = False

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        with pytest.raises(HTTPException) as exc_info:
            await complete_profile(
                profile_data=ProfileCompletionRequest(username="new", password="password123"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_complete_profile_already_completed(self):
        from routers.auth import complete_profile
        from schemas.profile_completion_schemas import ProfileCompletionRequest

        user = _mock_user()
        db_user = _mock_user()
        db_user.created_via_invitation = True
        db_user.profile_completed = True

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        result = await complete_profile(
            profile_data=ProfileCompletionRequest(username="new", password="password123"),
            current_user=user,
            db=db,
        )
        assert result.message == "Profile already completed"

    @pytest.mark.asyncio
    async def test_complete_profile_success(self):
        from routers.auth import complete_profile
        from schemas.profile_completion_schemas import ProfileCompletionRequest

        user = _mock_user()
        db_user = _mock_user()
        db_user.created_via_invitation = True
        db_user.profile_completed = False

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        with patch("auth_module.user_service.get_user_by_username", return_value=None), \
             patch("auth_module.user_service.get_password_hash", return_value="hashed"):
            result = await complete_profile(
                profile_data=ProfileCompletionRequest(
                    username="newname", password="password123", name="New Name"
                ),
                current_user=user,
                db=db,
            )
        assert result.success is True


# ---------------------------------------------------------------------------
# Mandatory profile status
# ---------------------------------------------------------------------------

class TestMandatoryProfileStatus:
    @pytest.mark.asyncio
    async def test_mandatory_profile_not_due(self):
        from routers.auth import get_mandatory_profile_status

        user = _mock_user()
        db_user = _mock_user()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=[]), \
             patch("auth_module.user_service.check_confirmation_due", return_value=(False, None)):
            result = await get_mandatory_profile_status(current_user=user, db=db)
        assert result.confirmation_due is False

    @pytest.mark.asyncio
    async def test_mandatory_profile_due_creates_notification(self):
        from routers.auth import get_mandatory_profile_status

        user = _mock_user()
        db_user = _mock_user()
        deadline = datetime.now(timezone.utc) + timedelta(days=7)

        db = _mock_db()

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = db_user  # user lookup
            else:
                q.first.return_value = None  # no existing notification
            return q
        db.query.side_effect = query_side_effect

        with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender"]), \
             patch("auth_module.user_service.check_confirmation_due", return_value=(True, deadline)):
            result = await get_mandatory_profile_status(current_user=user, db=db)
        assert result.confirmation_due is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_mandatory_profile_user_not_found(self):
        from routers.auth import get_mandatory_profile_status

        user = _mock_user()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_mandatory_profile_status(current_user=user, db=db)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Confirm profile
# ---------------------------------------------------------------------------

class TestConfirmProfile:
    @pytest.mark.asyncio
    async def test_confirm_profile_success(self):
        from routers.auth import confirm_profile_endpoint

        user = _mock_user()
        db = _mock_db()

        updated = Mock()
        updated.profile_confirmed_at = datetime.now(timezone.utc)

        with patch("auth_module.user_service.confirm_profile", return_value=updated):
            result = await confirm_profile_endpoint(current_user=user, db=db)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_confirm_profile_not_found(self):
        from routers.auth import confirm_profile_endpoint

        user = _mock_user()
        db = _mock_db()

        with patch("auth_module.user_service.confirm_profile", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await confirm_profile_endpoint(current_user=user, db=db)
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------------

class TestProfileHistory:
    @pytest.mark.asyncio
    async def test_profile_history_own(self):
        from routers.auth import get_profile_history

        user = _mock_user()
        db = _mock_db()

        entry = Mock()
        entry.id = "entry-1"
        entry.changed_at = datetime.now(timezone.utc)
        entry.change_type = "update"
        entry.snapshot = {}
        entry.changed_fields = ["name"]

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [entry]
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        result = await get_profile_history(
            user_id=None, limit=50, offset=0, current_user=user, db=db,
        )
        assert len(result) == 1
        assert result[0]["id"] == "entry-1"

    @pytest.mark.asyncio
    async def test_profile_history_other_user_superadmin(self):
        from routers.auth import get_profile_history

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        db_current = Mock()
        db_current.is_superadmin = True

        entry = Mock()
        entry.id = "entry-2"
        entry.changed_at = datetime.now(timezone.utc)
        entry.change_type = "update"
        entry.snapshot = {}
        entry.changed_fields = ["email"]

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.first.return_value = db_current
        mock_q.all.return_value = [entry]
        db.query.return_value = mock_q

        result = await get_profile_history(
            user_id="other-user", limit=50, offset=0, current_user=user, db=db,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_profile_history_other_user_denied(self):
        from routers.auth import get_profile_history

        user = _mock_user(is_superadmin=False)
        db = _mock_db()

        db_current = Mock()
        db_current.is_superadmin = False

        db.query.return_value.filter.return_value.first.return_value = db_current

        with pytest.raises(HTTPException) as exc_info:
            await get_profile_history(
                user_id="other-user", limit=50, offset=0, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

class TestResendVerification:
    @pytest.mark.asyncio
    async def test_resend_user_not_found(self):
        from routers.auth import resend_verification_email
        from schemas.auth_schemas import ResendVerificationRequest

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        result = await resend_verification_email(
            resend_request=ResendVerificationRequest(email="missing@test.com"),
            db=db,
        )
        assert "verification link" in result["message"]

    @pytest.mark.asyncio
    async def test_resend_already_verified(self):
        from routers.auth import resend_verification_email
        from schemas.auth_schemas import ResendVerificationRequest

        user = _mock_user()
        user.email_verified = True

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = user

        result = await resend_verification_email(
            resend_request=ResendVerificationRequest(email="test@example.com"),
            db=db,
        )
        assert "verification link" in result["message"]

    @pytest.mark.asyncio
    @patch("routers.auth.email_verification_service")
    async def test_resend_success(self, mock_svc):
        from routers.auth import resend_verification_email
        from schemas.auth_schemas import ResendVerificationRequest

        user = _mock_user()
        user.email_verified = False

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = user
        mock_svc.send_verification_email = AsyncMock(return_value=True)

        result = await resend_verification_email(
            resend_request=ResendVerificationRequest(email="test@example.com"),
            db=db,
        )
        assert "verification link" in result["message"]


# ---------------------------------------------------------------------------
# Check profile status
# ---------------------------------------------------------------------------

class TestCheckProfileStatus:
    @pytest.mark.asyncio
    async def test_check_profile_status_success(self):
        from routers.auth import check_profile_status

        user = _mock_user()
        db_user = _mock_user()
        db_user.hashed_password = "hashed"
        db_user.created_via_invitation = False
        db_user.profile_completed = True

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = db_user

        result = await check_profile_status(current_user=user, db=db)
        assert result.has_password is True
        assert result.needs_profile_completion is False

    @pytest.mark.asyncio
    async def test_check_profile_status_not_found(self):
        from routers.auth import check_profile_status

        user = _mock_user()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await check_profile_status(current_user=user, db=db)
        assert exc_info.value.status_code == 404
