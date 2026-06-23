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

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Notification,
    NotificationType,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    UserProfileHistory,
)
from models import User as DBUser


# ---------------------------------------------------------------------------
# Async fixtures helpers (auth handlers migrated to the async DB lane)
# ---------------------------------------------------------------------------

def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB row.

    Handlers query the real DB by current_user.id, so the seeded row's id
    must equal this AuthUser id.
    """
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


@contextmanager
def _as_unseeded_user(user_id=None, is_superadmin=False):
    """Override require_user with an AuthUser whose id is NOT in the DB.

    Used to exercise the 'user not found' branches of handlers that read the
    DB row by current_user.id.
    """
    uid = user_id or _uid()
    au = AuthUser(
        id=uid,
        username=f"ghost-{uid[:8]}",
        email=f"{uid[:8]}@ghost.com",
        name="Ghost",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, **over):
    fields = dict(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(over)
    u = DBUser(**fields)
    db.add(u)
    await db.flush()
    return u


async def _seed_membership(db, user, org, role):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
    )
    db.add(m)
    await db.flush()
    return m


async def _seed_org(db, **over):
    suffix = _uid()[:8]
    org = Organization(
        id=over.get("id", _uid()),
        name=over.get("name", f"Org {suffix}"),
        display_name=over.get("display_name", f"Org {suffix}"),
        slug=over.get("slug", f"org-{suffix}"),
        description=over.get("description"),
        is_active=over.get("is_active", True),
    )
    db.add(org)
    await db.flush()
    return org


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
    @patch("routers.auth.session.create_tokens_with_refresh")
    @patch("routers.auth.session.authenticate_user")
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
    @patch("routers.auth.session.create_tokens_with_refresh")
    @patch("routers.auth.session.authenticate_user")
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
    @patch("routers.auth.session.authenticate_user", side_effect=RuntimeError("DB boom"))
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
    @patch("routers.auth.session.authenticate_user", return_value=None)
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
    @patch("routers.auth.session.authenticate_user")
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
    @patch("routers.auth.tokens.refresh_access_token")
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
    @patch("routers.auth.tokens.refresh_access_token", return_value=None)
    async def test_refresh_invalid_token(self, mock_refresh):
        from routers.auth import refresh_token_endpoint

        request = _mock_request(cookies={"refresh_token": "bad-token"})
        response = Response()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token_endpoint(request=request, response=response, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routers.auth.tokens.refresh_access_token")
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
    """Cover the logout endpoint (now async DB lane)."""

    @pytest.mark.asyncio
    async def test_logout_with_refresh_token(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            with patch(
                "services.refresh_token_service.revoke_refresh_token_async",
                new=AsyncMock(return_value=True),
            ) as mock_revoke:
                async_test_client.cookies.set("refresh_token", "some-token")
                resp = await async_test_client.post("/api/auth/logout")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"
        mock_revoke.assert_awaited_once()
        # token is passed as the 2nd positional arg (db, token)
        assert mock_revoke.await_args.args[1] == "some-token"
        # access/refresh cookies cleared
        assert "access_token" in resp.headers.get("set-cookie", "")

    @pytest.mark.asyncio
    async def test_logout_no_refresh_token(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            async_test_client.cookies.clear()
            resp = await async_test_client.post("/api/auth/logout")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"


# ---------------------------------------------------------------------------
# Logout all devices
# ---------------------------------------------------------------------------

class TestLogoutAll:
    """Cover logout-all-devices (now async DB lane)."""

    @pytest.mark.asyncio
    async def test_logout_all_with_response(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            with patch(
                "services.refresh_token_service.revoke_user_tokens_async",
                new=AsyncMock(return_value=3),
            ):
                resp = await async_test_client.post("/api/auth/logout-all")

        assert resp.status_code == 200
        assert resp.json()["revoked_sessions"] == 3

    @pytest.mark.asyncio
    async def test_logout_all_no_response(self, async_test_client, async_test_db):
        # The HTTP endpoint always supplies a Response, so the no-cookie-clear
        # branch is exercised by directly invoking the handler with response=None
        # while still patching the async revoke twin.
        from routers.auth import logout_all_devices

        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user) as au:
            with patch(
                "services.refresh_token_service.revoke_user_tokens_async",
                new=AsyncMock(return_value=2),
            ):
                result = await logout_all_devices(
                    current_user=au, response=None, db=async_test_db
                )
        assert result["revoked_sessions"] == 2


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

class TestSignup:
    """Cover signup paths."""

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
    @patch("routers.auth.session.create_user")
    async def test_signup_regular(self, mock_create, mock_email_svc):
        from routers.auth import signup

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
    @patch("routers.auth.verification.email_verification_service")
    @patch("routers.auth.session.create_user")
    async def test_signup_invitation_flow(self, mock_create, mock_email_svc):
        from routers.auth import signup

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
    @patch("routers.auth.session.create_user")
    async def test_signup_invitation_invalid(self, mock_create):
        from routers.auth import signup

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        user_create = _make_user_create()
        user_create.invitation_token = "bad-token"

        request = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await signup(user_data=user_create, request=request, db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.session.create_user")
    async def test_signup_invitation_expired(self, mock_create):
        from routers.auth import signup

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
    @patch("routers.auth.session.create_user", side_effect=RuntimeError("DB crash"))
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
    @patch("routers.auth.session.create_user")
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
    async def test_get_current_user(self, async_test_client, async_test_db):
        # Seed a CONTRIBUTOR membership so the role resolves from the DB.
        user = await _seed_user(async_test_db)
        org = await _seed_org(async_test_db)
        await _seed_membership(async_test_db, user, org, OrganizationRole.CONTRIBUTOR)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user.id
        assert data["role"] == "CONTRIBUTOR"

    @pytest.mark.asyncio
    async def test_get_current_user_no_role(self, async_test_client, async_test_db):
        # No membership -> role is None.
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")

        assert resp.status_code == 200
        assert resp.json()["role"] is None

    @pytest.mark.asyncio
    async def test_get_user_contexts_superadmin(self, async_test_client, async_test_db):
        # Superadmin sees all active orgs.
        user = await _seed_user(async_test_db, is_superadmin=True)
        org = await _seed_org(async_test_db, name="Test Org", display_name="Test Org")
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["private_mode_available"] == True  # noqa: E712
        assert "organizations" in data
        assert data["user"]["is_superadmin"] is True
        org_ids = {o["id"] for o in data["organizations"]}
        assert org.id in org_ids

    @pytest.mark.asyncio
    async def test_get_user_contexts_regular_user(self, async_test_client, async_test_db):
        # Regular user sees only orgs they belong to, with their role.
        user = await _seed_user(async_test_db, is_superadmin=False)
        org = await _seed_org(async_test_db, name="Test Org", display_name="Test Org")
        await _seed_membership(async_test_db, user, org, OrganizationRole.ANNOTATOR)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["private_mode_available"] == True  # noqa: E712
        ctx = {o["id"]: o for o in data["organizations"]}
        assert org.id in ctx
        assert ctx[org.id]["role"] == "ANNOTATOR"


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class TestProfileEndpoints:
    @pytest.mark.asyncio
    async def test_get_profile_success(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db, name="Profile User")
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user.id
        assert data["username"] == user.username
        assert data["name"] == "Profile User"

    @pytest.mark.asyncio
    async def test_get_profile_user_not_found(self, async_test_client, async_test_db):
        # current_user.id is not in the DB -> handler returns the fallback
        # UserProfile built from current_user (200).
        with _as_unseeded_user() as au:
            resp = await async_test_client.get("/api/auth/profile")

        assert resp.status_code == 200
        assert resp.json()["id"] == au.id

    @pytest.mark.asyncio
    async def test_get_profile_exception_fallback(self, async_test_client, async_test_db):
        # Force the async profile builder to raise so the except branch fires;
        # the handler falls back to a current_user-derived UserProfile (200).
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user) as au:
            with patch(
                "routers.auth.user._build_user_profile_response_async",
                new=AsyncMock(side_effect=RuntimeError("DB error")),
            ):
                resp = await async_test_client.get("/api/auth/profile")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == au.id
        assert data["is_active"] == True  # noqa: E712

    @pytest.mark.asyncio
    @patch("routers.auth.user._build_user_profile_response")
    @patch("routers.auth.user.update_user_profile")
    async def test_update_profile_success(self, mock_update, mock_build):
        from routers.auth import update_profile
        from schemas.auth_schemas import UserUpdate

        user = _mock_user()
        db = _mock_db()
        updated_user = _mock_user()
        mock_update.return_value = updated_user
        mock_build.return_value = Mock(id="user-123")

        result = await update_profile(  # noqa: F841
            profile_data=UserUpdate(name="New Name"),
            current_user=user,
            db=db,
        )
        mock_build.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.auth.user.update_user_profile", return_value=None)
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
    @patch("routers.auth.password.change_user_password", return_value=True)
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
    @patch("routers.auth.password.change_user_password", return_value=False)
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
    @patch("routers.auth.verification.email_verification_service")
    async def test_verify_email_success(self, mock_svc):
        from routers.auth import verify_email
        from schemas.auth_schemas import EmailVerificationRequest

        mock_svc.verify_email_with_token.return_value = (True, "Verified")
        db = _mock_db()

        result = await verify_email(
            verification_request=EmailVerificationRequest(token="valid-token"),
            db=db,
        )
        assert result["success"] == True  # noqa: E712

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
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
    @patch("routers.auth.verification.email_verification_service")
    async def test_verify_email_with_path_token_success(self, mock_svc):
        from routers.auth import verify_email_with_token

        mock_svc.verify_email_with_token.return_value = (True, "OK")
        db = _mock_db()

        result = await verify_email_with_token(token="path-token", db=db)
        assert result["success"] == True  # noqa: E712

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
    async def test_verify_email_with_path_token_failure(self, mock_svc):
        from routers.auth import verify_email_with_token

        mock_svc.verify_email_with_token.return_value = (False, "Bad")
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await verify_email_with_token(token="bad-token", db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
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
    @patch("routers.auth.verification.email_verification_service")
    async def test_enhanced_failure(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (False, "Bad token")
        db = _mock_db()

        result = await verify_email_enhanced(token="bad", db=db)
        assert result.success == False  # noqa: E712
        assert result.user_type == "unknown"

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
    async def test_enhanced_success_no_token_data(self, mock_svc):
        from routers.auth import verify_email_enhanced

        mock_svc.verify_email_with_token.return_value = (True, "OK")
        db = _mock_db()

        with patch("auth_module.email_verification.email_verification_service") as inner_svc:
            inner_svc.validate_verification_token.return_value = None
            result = await verify_email_enhanced(token="tok", db=db)
        assert result.success == True  # noqa: E712
        assert result.redirect_url == "/login"

    @pytest.mark.asyncio
    @patch("routers.auth.verification.email_verification_service")
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
    @patch("routers.auth.verification.email_verification_service")
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
    async def test_complete_profile_user_not_found(self, async_test_client, async_test_db):
        # current_user.id not in DB -> 404.
        with _as_unseeded_user():
            resp = await async_test_client.post(
                "/api/auth/complete-profile",
                json={"username": "newname1", "password": "password123"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_complete_profile_not_invited(self, async_test_client, async_test_db):
        user = await _seed_user(
            async_test_db, created_via_invitation=False, profile_completed=False
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/auth/complete-profile",
                json={"username": "newname2", "password": "password123"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_complete_profile_already_completed(self, async_test_client, async_test_db):
        user = await _seed_user(
            async_test_db, created_via_invitation=True, profile_completed=True
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/auth/complete-profile",
                json={"username": "newname3", "password": "password123"},
            )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Profile already completed"

    @pytest.mark.asyncio
    async def test_complete_profile_success(self, async_test_client, async_test_db):
        user = await _seed_user(
            async_test_db, created_via_invitation=True, profile_completed=False
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/auth/complete-profile",
                json={
                    "username": f"newname-{_uid()[:6]}",
                    "password": "password123",
                    "name": "New Name",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] == True  # noqa: E712


# ---------------------------------------------------------------------------
# Mandatory profile status
# ---------------------------------------------------------------------------

class TestMandatoryProfileStatus:
    @pytest.mark.asyncio
    async def test_mandatory_profile_not_due(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        # check_confirmation_due / get_mandatory_profile_fields are imported
        # inside the handler from auth_module.user_service -> patch there.
        with _as_user(user):
            with patch(
                "auth_module.user_service.get_mandatory_profile_fields", return_value=[]
            ), patch(
                "auth_module.user_service.check_confirmation_due", return_value=(False, None)
            ):
                resp = await async_test_client.get("/api/auth/mandatory-profile-status")

        assert resp.status_code == 200
        assert resp.json()["confirmation_due"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_mandatory_profile_due_creates_notification(
        self, async_test_client, async_test_db
    ):
        from sqlalchemy import select

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        deadline = datetime.now(timezone.utc) + timedelta(days=7)

        with _as_user(user):
            with patch(
                "auth_module.user_service.get_mandatory_profile_fields", return_value=[]
            ), patch(
                "auth_module.user_service.check_confirmation_due",
                return_value=(True, deadline),
            ):
                resp = await async_test_client.get("/api/auth/mandatory-profile-status")

        assert resp.status_code == 200
        assert resp.json()["confirmation_due"] == True  # noqa: E712

        # A PROFILE_CONFIRMATION_DUE notification row was created for the user.
        rows = (
            await async_test_db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.type == NotificationType.PROFILE_CONFIRMATION_DUE,
                )
            )
        ).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_mandatory_profile_user_not_found(self, async_test_client, async_test_db):
        with _as_unseeded_user():
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Confirm profile
# ---------------------------------------------------------------------------

class TestConfirmProfile:
    @pytest.mark.asyncio
    async def test_confirm_profile_success(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        confirmed = Mock()
        confirmed.profile_confirmed_at = datetime.now(timezone.utc)

        # confirm_profile_async is imported inside the handler from
        # auth_module.user_service -> patch there with an async twin.
        with _as_user(user):
            with patch(
                "auth_module.user_service.confirm_profile_async",
                new=AsyncMock(return_value=confirmed),
            ):
                resp = await async_test_client.post("/api/auth/confirm-profile")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] == True  # noqa: E712
        assert body["confirmed_at"] is not None

    @pytest.mark.asyncio
    async def test_confirm_profile_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            with patch(
                "auth_module.user_service.confirm_profile_async",
                new=AsyncMock(return_value=None),
            ):
                resp = await async_test_client.post("/api/auth/confirm-profile")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------------

class TestProfileHistory:
    async def _seed_history(self, db, user, change_type="update", changed_fields=None):
        entry = UserProfileHistory(
            id=_uid(),
            user_id=user.id,
            changed_at=datetime.now(timezone.utc),
            change_type=change_type,
            snapshot={},
            changed_fields=changed_fields or ["name"],
        )
        db.add(entry)
        await db.flush()
        return entry

    @pytest.mark.asyncio
    async def test_profile_history_own(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        entry = await self._seed_history(async_test_db, user)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile-history")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == entry.id

    @pytest.mark.asyncio
    async def test_profile_history_other_user_superadmin(
        self, async_test_client, async_test_db
    ):
        # Superadmin requester can view another user's history.
        requester = await _seed_user(async_test_db, is_superadmin=True)
        target = await _seed_user(async_test_db)
        await self._seed_history(async_test_db, target, changed_fields=["email"])
        await async_test_db.commit()

        with _as_user(requester):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={target.id}"
            )

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_profile_history_other_user_denied(self, async_test_client, async_test_db):
        # Non-superadmin requester asking for another user's history -> 403.
        requester = await _seed_user(async_test_db, is_superadmin=False)
        target = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(requester):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={target.id}"
            )
        assert resp.status_code == 403


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
    @patch("routers.auth.verification.email_verification_service")
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
    async def test_check_profile_status_success(self, async_test_client, async_test_db):
        user = await _seed_user(
            async_test_db,
            hashed_password="hashed",
            created_via_invitation=False,
            profile_completed=True,
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/check-profile-status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_password"] == True  # noqa: E712
        assert data["needs_profile_completion"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_check_profile_status_not_found(self, async_test_client, async_test_db):
        with _as_unseeded_user():
            resp = await async_test_client.get("/api/auth/check-profile-status")
        assert resp.status_code == 404
