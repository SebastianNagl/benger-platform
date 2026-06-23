"""
Unit tests for routers/auth.py to increase branch coverage.
Covers login, signup, refresh, logout, profile, password, email verification,
profile completion, mandatory profile, and profile history endpoints.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from auth_module.models import User as AuthUser
from database import get_db
from auth_module.dependencies import require_user, require_superadmin

from models import (
    User as DBUser,
    OrganizationMembership,
    Organization,
    OrganizationRole,
    UserProfileHistory,
)


# ---------------------------------------------------------------------------
# Async helpers (handlers below were migrated to the async DB lane, so they
# query the REAL test Postgres by current_user.id — we seed real rows and
# override `require_user` with an AuthUser whose id matches the seeded row).
# ---------------------------------------------------------------------------


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
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


async def _seed_user(db, is_superadmin=False, **over):
    over.setdefault("id", _uid())
    over.setdefault("username", f"u-{_uid()[:8]}")
    over.setdefault("email", f"{_uid()[:8]}@e.com")
    over.setdefault("name", "U")
    over.setdefault("hashed_password", "x")
    over.setdefault("is_active", True)
    over.setdefault("email_verified", True)
    over.setdefault("created_at", datetime.now(timezone.utc))
    u = DBUser(is_superadmin=is_superadmin, **over)
    db.add(u)
    await db.flush()
    return u


async def _seed_membership(db, user, role, org=None):
    if org is None:
        org = Organization(
            id=_uid(),
            name=f"Org {_uid()[:8]}",
            display_name="Org",
            slug=f"org-{_uid()[:8]}",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        await db.flush()
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return org


def _make_user(is_superadmin=False, user_id="user-123", email_verified=True):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=email_verified,
        created_at=datetime.now(timezone.utc),
    )


def _make_admin():
    return _make_user(is_superadmin=True, user_id="admin-123")


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_invalid_credentials(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.auth.session.authenticate_user", return_value=None):
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "baduser", "password": "badpass"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_login_unverified_email(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        unverified_user = _make_user(email_verified=False)

        try:
            with patch("routers.auth.session.authenticate_user", return_value=unverified_user):
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "testuser", "password": "pass"},
                )
                assert resp.status_code == 403
                assert "verification" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_login_success(self):
        from auth_module.models import Token, User as UserModel

        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        user = _make_user()

        user_for_token = UserModel(
            id="user-123", username="testuser", email="test@example.com",
            name="Test User", is_superadmin=False, is_active=True,
            email_verified=True, created_at=datetime.now(timezone.utc),
        )
        token_resp = Token(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            token_type="bearer",
            expires_in=3600,
            user=user_for_token,
        )

        try:
            with patch("routers.auth.session.authenticate_user", return_value=user), \
                 patch("routers.auth.session.create_tokens_with_refresh", return_value=token_resp):
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "testuser", "password": "pass"},
                )
                assert resp.status_code == 200
                assert "access_token" in resp.json()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


class TestRefreshToken:
    def test_refresh_no_cookie(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post("/api/auth/refresh")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_refresh_invalid_token(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.tokens.refresh_access_token", return_value=None):
                client.cookies.set("refresh_token", "invalid-token")
                resp = client.post("/api/auth/refresh")
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_refresh_success(self):
        from auth_module.models import Token, User as UserModel

        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db

        user_for_token = UserModel(
            id="user-123", username="testuser", email="test@example.com",
            name="Test User", is_superadmin=False, is_active=True,
            email_verified=True, created_at=datetime.now(timezone.utc),
        )
        token_resp = Token(
            access_token="new-access", refresh_token="new-refresh",
            token_type="bearer", expires_in=3600, user=user_for_token,
        )

        try:
            with patch("routers.auth.tokens.refresh_access_token", return_value=token_resp):
                client.cookies.set("refresh_token", "valid-token")
                resp = client.post("/api/auth/refresh")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self, async_test_client, async_test_db):
        # logout is async; with no refresh_token cookie the async revoke is
        # skipped and the route returns the success message.
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/logout")
            assert resp.status_code == 200
            assert resp.json()["message"] == "Logged out successfully"

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, async_test_client, async_test_db):
        # logout-all awaits revoke_user_tokens_async — patch the async twin
        # (the old sync revoke_user_tokens is no longer called by this handler).
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch(
                 "services.refresh_token_service.revoke_user_tokens_async",
                 new=AsyncMock(return_value=3),
             ):
            resp = await async_test_client.post("/api/auth/logout-all")
            assert resp.status_code == 200
            assert "revoked_sessions" in resp.json()
            assert resp.json()["revoked_sessions"] == 3


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


class TestSignup:
    def test_signup_basic(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db

        new_user = _make_user()
        try:
            with patch("routers.auth.session.create_user", return_value=new_user), \
                 patch("routers.auth.session.email_verification_service") as mock_evs:
                mock_evs.send_verification_email = AsyncMock(return_value=True)
                resp = client.post(
                    "/api/auth/signup",
                    json={
                        "username": "newuser",
                        "email": "new@test.com",
                        "password": "StrongPass123!",
                        "legal_expertise_level": "law_student",
                        "german_proficiency": "native",
                        "name": "New User",
                    },
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_signup_exception(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.session.create_user", side_effect=Exception("DB error")):
                resp = client.post(
                    "/api/auth/signup",
                    json={
                        "username": "newuser",
                        "email": "new@test.com",
                        "password": "Password123!",
                        "legal_expertise_level": "law_student",
                        "german_proficiency": "native",
                        "name": "New",
                    },
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Register (admin-only)
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_as_admin(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db

        new_user = _make_user()
        try:
            with patch("routers.auth.session.create_user", return_value=new_user):
                resp = client.post(
                    "/api/auth/register",
                    json={
                        "username": "registered",
                        "email": "reg@test.com",
                        "password": "Password123!",
                        "legal_expertise_level": "law_student",
                        "german_proficiency": "native",
                        "name": "Registered",
                    },
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Current user / contexts
# ---------------------------------------------------------------------------


class TestCurrentUser:
    @pytest.mark.asyncio
    async def test_get_me(self, async_test_client, async_test_db):
        # Seed an ANNOTATOR-role user so the async primary-role lookup
        # resolves to "annotator" off real rows (replaces the old
        # get_user_primary_role patch on the now-async handler).
        user = await _seed_user(async_test_db, username="testuser")
        await _seed_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "testuser"
            assert data["role"] == "ANNOTATOR"

    @pytest.mark.asyncio
    async def test_get_me_contexts_regular_user(self, async_test_client, async_test_db):
        # Regular (non-superadmin) user with one ANNOTATOR membership.
        user = await _seed_user(async_test_db)
        org = await _seed_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["user"]["id"] == user.id
            org_ids = [o["id"] for o in data["organizations"]]
            assert org.id in org_ids


# ---------------------------------------------------------------------------
# Verify token
# ---------------------------------------------------------------------------


class TestVerifyToken:
    def test_verify_valid_token(self):
        client = TestClient(app)
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = client.get("/api/auth/verify")
            assert resp.status_code == 200
            assert resp.json()["valid"] == True  # noqa: E712
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    @pytest.mark.asyncio
    async def test_get_profile_user_in_db(self, async_test_client, async_test_db):
        # User row present → handler builds the full profile response off the
        # async DB read (_build_user_profile_response_async).
        user = await _seed_user(async_test_db, email="test@example.com")
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
            assert resp.status_code == 200
            assert resp.json()["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_profile_user_not_in_db(self, async_test_client, async_test_db):
        # AuthUser whose id is not seeded → handler takes the "not found"
        # branch and returns a 200 fallback profile from current_user.
        au = AuthUser(
            id=_uid(),
            username="ghost",
            email="ghost@e.com",
            name="Ghost",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[require_user] = lambda: au
        try:
            resp = await async_test_client.get("/api/auth/profile")
            assert resp.status_code == 200
            assert resp.json()["email"] == "ghost@e.com"
        finally:
            app.dependency_overrides.pop(require_user, None)

    def test_update_profile_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.user.update_user_profile", return_value=None):
                resp = client.put(
                    "/api/auth/profile",
                    json={"name": "Updated"},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------


class TestPassword:
    def test_change_password_mismatch(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/auth/change-password",
                json={
                    "current_password": "old",
                    "new_password": "NewPassword123!",
                    "confirm_password": "DifferentPass456!",
                },
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_change_password_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.password.change_user_password", return_value=True):
                resp = client.post(
                    "/api/auth/change-password",
                    json={
                        "current_password": "old",
                        "new_password": "NewPassword123!",
                        "confirm_password": "NewPassword123!",
                    },
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_change_password_failure(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.password.change_user_password", return_value=False):
                resp = client.post(
                    "/api/auth/change-password",
                    json={
                        "current_password": "old",
                        "new_password": "NewPassword123!",
                        "confirm_password": "NewPassword123!",
                    },
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_request_password_reset_user_not_found(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/auth/request-password-reset",
                json={"email": "nonexistent@test.com"},
            )
            assert resp.status_code == 200
            assert "If the email exists" in resp.json()["message"]
        finally:
            app.dependency_overrides.clear()

    def test_request_password_reset_success(self):
        client = TestClient(app)
        mock_db = _mock_db()
        db_user = Mock()
        db_user.email = "found@test.com"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
                mock_prs.send_password_reset_email = AsyncMock(return_value=True)
                resp = client.post(
                    "/api/auth/request-password-reset",
                    json={"email": "found@test.com"},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_reset_password_mismatch(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/auth/reset-password",
                json={
                    "token": "token123",
                    "new_password": "NewPassword123!",
                    "confirm_password": "DifferentPass456!",
                },
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_reset_password_success(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
                mock_prs.reset_password.return_value = True
                resp = client.post(
                    "/api/auth/reset-password",
                    json={
                        "token": "token123",
                        "new_password": "NewPass123!",
                        "confirm_password": "NewPass123!",
                    },
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_reset_password_invalid_token(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
                mock_prs.reset_password.return_value = False
                resp = client.post(
                    "/api/auth/reset-password",
                    json={
                        "token": "bad-token",
                        "new_password": "NewPass123!",
                        "confirm_password": "NewPass123!",
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


class TestEmailVerification:
    def test_verify_email_success(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (True, "Verified")
                resp = client.post(
                    "/api/auth/verify-email",
                    json={"token": "valid-token"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] == True  # noqa: E712
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_failure(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (False, "Invalid token")
                resp = client.post(
                    "/api/auth/verify-email",
                    json={"token": "bad-token"},
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_with_path_token_success(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (True, "OK")
                resp = client.post("/api/auth/verify-email/token123")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_with_path_token_failure(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (False, "Bad token")
                resp = client.post("/api/auth/verify-email/badtoken")
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_with_path_token_exception(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.side_effect = Exception("DB crash")
                resp = client.post("/api/auth/verify-email/crashtoken")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_resend_verification_user_not_found(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/auth/resend-verification",
                json={"email": "nonexistent@test.com"},
            )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_resend_verification_already_verified(self):
        client = TestClient(app)
        mock_db = _mock_db()
        db_user = Mock()
        db_user.email = "verified@test.com"
        db_user.email_verified = True
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/auth/resend-verification",
                json={"email": "verified@test.com"},
            )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_resend_verification_sends_email(self):
        client = TestClient(app)
        mock_db = _mock_db()
        db_user = Mock()
        db_user.email = "unverified@test.com"
        db_user.email_verified = False
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.send_verification_email = AsyncMock(return_value=True)
                resp = client.post(
                    "/api/auth/resend-verification",
                    json={"email": "unverified@test.com"},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Enhanced email verification
# ---------------------------------------------------------------------------


class TestEnhancedEmailVerification:
    def test_verify_email_enhanced_failure(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.verification.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (False, "Invalid")
                resp = client.post("/api/auth/verify-email-enhanced/bad-token")
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] == False  # noqa: E712
                assert data["user_type"] == "unknown"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile completion
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Check profile status
# ---------------------------------------------------------------------------


class TestCheckProfileStatus:
    @pytest.mark.asyncio
    async def test_check_profile_status_found(self, async_test_client, async_test_db):
        # Invited user who hasn't completed their profile → needs completion.
        user = await _seed_user(
            async_test_db,
            created_via_invitation=True,
            profile_completed=False,
            hashed_password="hashed",
        )
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/check-profile-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["needs_profile_completion"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_check_profile_status_not_found(self, async_test_client, async_test_db):
        # AuthUser whose id was never seeded → handler's DB lookup misses → 404.
        au = AuthUser(
            id=_uid(),
            username="ghost",
            email="ghost@e.com",
            name="Ghost",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[require_user] = lambda: au
        try:
            resp = await async_test_client.get("/api/auth/check-profile-status")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# Mandatory profile status
# ---------------------------------------------------------------------------


class TestMandatoryProfileStatus:
    @pytest.mark.asyncio
    async def test_mandatory_profile_status_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db, mandatory_profile_completed=False)
        await async_test_db.flush()
        # Patch the field-helpers (the handler imports them from
        # auth_module.user_service) for deterministic missing-fields / not-due.
        with _as_user(user), \
             patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender", "age"]), \
             patch("auth_module.user_service.check_confirmation_due", return_value=(False, None)):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["mandatory_profile_completed"] == False  # noqa: E712
            assert "gender" in data["missing_fields"]

    @pytest.mark.asyncio
    async def test_mandatory_profile_status_not_found(self, async_test_client, async_test_db):
        au = AuthUser(
            id=_uid(),
            username="ghost",
            email="ghost@e.com",
            name="Ghost",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[require_user] = lambda: au
        try:
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# Confirm profile
# ---------------------------------------------------------------------------


class TestConfirmProfile:
    @pytest.mark.asyncio
    async def test_confirm_profile_success(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.flush()

        updated_user = Mock()
        updated_user.profile_confirmed_at = datetime.now(timezone.utc)

        # Handler awaits confirm_profile_async — patch the async twin.
        with _as_user(user), \
             patch(
                 "auth_module.user_service.confirm_profile_async",
                 new=AsyncMock(return_value=updated_user),
             ):
            resp = await async_test_client.post("/api/auth/confirm-profile")
            assert resp.status_code == 200
            assert resp.json()["success"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_confirm_profile_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch(
                 "auth_module.user_service.confirm_profile_async",
                 new=AsyncMock(return_value=None),
             ):
            resp = await async_test_client.post("/api/auth/confirm-profile")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------------


class TestProfileHistory:
    @pytest.mark.asyncio
    async def test_profile_history_own(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        async_test_db.add(
            UserProfileHistory(
                id=_uid(),
                user_id=user.id,
                changed_at=datetime.now(timezone.utc),
                change_type="update",
                snapshot={"name": "old"},
                changed_fields=["name"],
            )
        )
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile-history")
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_profile_history_other_user_as_superadmin(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        other = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={other.id}"
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_profile_history_other_user_as_non_admin(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db, is_superadmin=False)
        other = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={other.id}"
            )
            assert resp.status_code == 403
