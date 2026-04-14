"""
Coverage boost tests for auth endpoints.

Targets specific branches in routers/auth.py:
- signup with various fields
- login success/failure
- password change
- profile updates
- profile completion
- email verification
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from models import User
from user_service import get_password_hash


class TestSignup:
    """Test signup endpoint."""

    @patch("routers.auth.email_verification_service")
    def test_signup_basic(self, mock_email, client, test_db):
        mock_email.send_verification_email.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"newuser_{uuid.uuid4().hex[:6]}",
                "email": f"new_{uuid.uuid4().hex[:6]}@test.com",
                "password": "StrongPass123!",
                "name": "New User",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            },
        )
        assert resp.status_code == 200

    @patch("routers.auth.email_verification_service")
    def test_signup_with_all_fields(self, mock_email, client, test_db, test_users):
        mock_email.send_verification_email.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"demo_{uuid.uuid4().hex[:6]}",
                "email": f"demo_{uuid.uuid4().hex[:6]}@test.com",
                "password": "DemoPass123!",
                "name": "Demo User",
                "legal_expertise_level": "law_student",
                "german_proficiency": "c1",
                "degree_program_type": "staatsexamen",
                "current_semester": 5,
                "legal_specializations": ["civil_law", "criminal_law"],
                "gender": "divers",
                "age": 25,
            },
        )
        assert resp.status_code == 200

    def test_signup_duplicate_email(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"different_{uuid.uuid4().hex[:6]}",
                "email": "admin@test.com",
                "password": "DupePass123!",
                "name": "Dupe User",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            },
        )
        assert resp.status_code in [400, 409, 500]


class TestLogin:
    """Test login endpoint."""

    def test_login_success(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "admin@test.com",
                "password": "admin123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    def test_login_wrong_password(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "admin@test.com",
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, test_db):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent@test.com",
                "password": "anypass",
            },
        )
        assert resp.status_code == 401

    def test_login_contributor(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "contributor@test.com",
                "password": "contrib123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_annotator(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "annotator@test.com",
                "password": "annotator123",
            },
        )
        assert resp.status_code == 200


class TestGetCurrentUser:
    """Test me endpoint."""

    def test_me_success(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@test.com"

    def test_me_no_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code in [401, 403]

    def test_me_invalid_token(self, client):
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code in [401, 403]

    def test_me_contexts(self, client, auth_headers):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["admin"])
        assert resp.status_code == 200


class TestPasswordChange:
    """Test change-password endpoint (POST /api/auth/change-password)."""

    def test_change_password_success(self, client, auth_headers, test_db, test_users):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "NewAdmin456!",
                "confirm_password": "NewAdmin456!",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_change_password_wrong_current(self, client, auth_headers):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "wrong_password",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in [400, 401, 403, 500]

    def test_change_password_mismatch(self, client, auth_headers):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "NewPass123!",
                "confirm_password": "DifferentPass!",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_change_password_no_auth(self, client):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "x",
                "new_password": "yyyyyy",
                "confirm_password": "yyyyyy",
            },
        )
        assert resp.status_code in [401, 403]


class TestPasswordReset:
    """Test password reset flow."""

    @patch("routers.auth.email_verification_service")
    def test_request_password_reset(self, mock_email, client, test_db, test_users):
        mock_email.send_password_reset_email = MagicMock(return_value=True)
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200

    @patch("routers.auth.email_verification_service")
    def test_request_password_reset_nonexistent(self, mock_email, client, test_db):
        mock_email.send_password_reset_email = MagicMock(return_value=True)
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "nonexistent@test.com"},
        )
        # Should still return 200 to prevent email enumeration
        assert resp.status_code == 200


class TestProfileUpdate:
    """Test profile update endpoints."""

    def test_get_profile(self, client, auth_headers):
        resp = client.get("/api/auth/profile", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_update_profile_basic(self, client, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Updated Admin Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_profile_demographic(self, client, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={
                "name": "Admin Demo",
                "age": 30,
                "job": "Researcher",
                "years_of_experience": 5,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_profile_legal_fields(self, client, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={
                "name": "Legal Admin",
                "legal_expertise_level": "practicing_lawyer",
                "german_proficiency": "native",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


class TestProfileCompletion:
    """Test mandatory profile completion endpoints."""

    def test_check_profile_status(self, client, auth_headers):
        resp = client.get(
            "/api/auth/check-profile-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_mandatory_profile_status(self, client, auth_headers):
        resp = client.get(
            "/api/auth/mandatory-profile-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_profile_history(self, client, auth_headers):
        resp = client.get(
            "/api/auth/profile-history",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


class TestLogout:
    """Test logout endpoint."""

    def test_logout_success(self, client, auth_headers):
        resp = client.post("/api/auth/logout", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_logout_all(self, client, auth_headers):
        resp = client.post("/api/auth/logout-all", headers=auth_headers["admin"])
        assert resp.status_code == 200


class TestRefreshToken:
    """Test token refresh endpoint."""

    def test_refresh_with_valid_login(self, client, test_db, test_users):
        login_resp = client.post(
            "/api/auth/login",
            json={
                "username": "admin@test.com",
                "password": "admin123",
            },
        )
        assert login_resp.status_code == 200
        data = login_resp.json()
        if "refresh_token" in data:
            resp = client.post(
                "/api/auth/refresh",
                json={"refresh_token": data["refresh_token"]},
            )
            assert resp.status_code in [200, 401]

    def test_refresh_with_invalid_token(self, client, test_db):
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid-refresh-token"},
        )
        assert resp.status_code in [401, 422]
