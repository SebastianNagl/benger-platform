"""
Unit tests for routers/auth.py to increase branch coverage.
Covers login, signup, refresh, logout, profile, password, email verification,
profile completion, mandatory profile, and profile history endpoints.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user, require_superadmin


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
            with patch("routers.auth.authenticate_user", return_value=None):
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
            with patch("routers.auth.authenticate_user", return_value=unverified_user):
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
            with patch("routers.auth.authenticate_user", return_value=user), \
                 patch("routers.auth.create_tokens_with_refresh", return_value=token_resp):
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
            with patch("routers.auth.refresh_access_token", return_value=None):
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
            with patch("routers.auth.refresh_access_token", return_value=token_resp):
                client.cookies.set("refresh_token", "valid-token")
                resp = client.post("/api/auth/refresh")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.revoke_refresh_token"):
                resp = client.post("/api/auth/logout")
                assert resp.status_code == 200
                assert resp.json()["message"] == "Logged out successfully"
        finally:
            app.dependency_overrides.clear()

    def test_logout_all_devices(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("services.refresh_token_service.revoke_user_tokens", return_value=3):
                resp = client.post("/api/auth/logout-all")
                assert resp.status_code == 200
                assert "revoked_sessions" in resp.json()
        finally:
            app.dependency_overrides.clear()


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
            with patch("routers.auth.create_user", return_value=new_user), \
                 patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.create_user", side_effect=Exception("DB error")):
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
            with patch("routers.auth.create_user", return_value=new_user):
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
    def test_get_me(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.get_user_primary_role", return_value="annotator"):
                resp = client.get("/api/auth/me")
                assert resp.status_code == 200
                assert resp.json()["username"] == "testuser"
        finally:
            app.dependency_overrides.clear()


    def test_get_me_contexts_regular_user(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.get_user_primary_role", return_value="annotator"):
                resp = client.get("/api/auth/me/contexts")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


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
            assert resp.json()["valid"] is True
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    def test_get_profile_user_in_db(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.username = "testuser"
        db_user.email = "test@example.com"
        db_user.name = "Test User"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.created_at = datetime.now(timezone.utc)
        db_user.updated_at = None
        db_user.legal_expertise_level = None
        db_user.german_proficiency = None
        db_user.age = None
        db_user.job = None
        db_user.years_of_experience = None
        db_user.use_pseudonym = False
        db_user.pseudonym = None
        db_user.degree_program_type = None
        db_user.current_semester = None
        db_user.legal_specializations = None
        db_user.german_state_exams_count = None
        db_user.german_state_exams_data = None
        db_user.gender = None
        db_user.subjective_competence_civil = None
        db_user.subjective_competence_public = None
        db_user.subjective_competence_criminal = None
        db_user.grade_zwischenpruefung = None
        db_user.grade_vorgeruecktenubung = None
        db_user.grade_first_staatsexamen = None
        db_user.grade_second_staatsexamen = None
        db_user.ati_s_scores = None
        db_user.ptt_a_scores = None
        db_user.ki_experience_scores = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.get_user_primary_role", return_value="annotator"):
                resp = client.get("/api/auth/profile")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_get_profile_user_not_in_db(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.get_user_primary_role", return_value="annotator"):
                resp = client.get("/api/auth/profile")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


    def test_update_profile_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.update_user_profile", return_value=None):
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
            with patch("routers.auth.change_user_password", return_value=True):
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
            with patch("routers.auth.change_user_password", return_value=False):
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
            with patch("routers.auth.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (True, "Verified")
                resp = client.post(
                    "/api/auth/verify-email",
                    json={"token": "valid-token"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_failure(self):
        client = TestClient(app)
        mock_db = _mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.email_verification_service") as mock_evs:
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
            with patch("routers.auth.email_verification_service") as mock_evs:
                mock_evs.verify_email_with_token.return_value = (False, "Invalid")
                resp = client.post("/api/auth/verify-email-enhanced/bad-token")
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is False
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
    def test_check_profile_status_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.email = "test@example.com"
        db_user.profile_completed = False
        db_user.created_via_invitation = True
        db_user.hashed_password = "hashed"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/check-profile-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["needs_profile_completion"] is True
        finally:
            app.dependency_overrides.clear()

    def test_check_profile_status_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/check-profile-status")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mandatory profile status
# ---------------------------------------------------------------------------


class TestMandatoryProfileStatus:
    def test_mandatory_profile_status_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.mandatory_profile_completed = False

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.get_mandatory_profile_fields", return_value=["gender", "age"]), \
                 patch("auth_module.user_service.check_confirmation_due", return_value=(False, None)):
                resp = client.get("/api/auth/mandatory-profile-status")
                assert resp.status_code == 200
                data = resp.json()
                assert data["mandatory_profile_completed"] is False
                assert "gender" in data["missing_fields"]
        finally:
            app.dependency_overrides.clear()

    def test_mandatory_profile_status_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/mandatory-profile-status")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Confirm profile
# ---------------------------------------------------------------------------


class TestConfirmProfile:
    def test_confirm_profile_success(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        updated_user = Mock()
        updated_user.profile_confirmed_at = datetime.now(timezone.utc)

        try:
            with patch("auth_module.user_service.confirm_profile", return_value=updated_user):
                resp = client.post("/api/auth/confirm-profile")
                assert resp.status_code == 200
                assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.clear()

    def test_confirm_profile_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.confirm_profile", return_value=None):
                resp = client.post("/api/auth/confirm-profile")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------------


class TestProfileHistory:
    def test_profile_history_own(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        entry = Mock()
        entry.id = "h-1"
        entry.changed_at = datetime.now(timezone.utc)
        entry.change_type = "update"
        entry.snapshot = {"name": "old"}
        entry.changed_fields = ["name"]

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [entry]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/profile-history")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_profile_history_other_user_as_superadmin(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        db_admin = Mock()
        db_admin.id = "admin-123"
        db_admin.is_superadmin = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_admin
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/profile-history?user_id=other-user")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_profile_history_other_user_as_non_admin(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.is_superadmin = False

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/auth/profile-history?user_id=other-user")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
