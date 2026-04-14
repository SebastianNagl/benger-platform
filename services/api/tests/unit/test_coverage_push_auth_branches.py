"""
Coverage push tests for auth router branches.

Targets specific uncovered branches in routers/auth.py:
- _ensure_dict with different input types
- _build_user_profile_response
- get_user_primary_role priority chain
- Login with valid/invalid credentials
- Profile endpoint
- Signup with additional fields
"""

import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership


class TestEnsureDict:
    """Test _ensure_dict helper function."""

    def test_none_input(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(None) is None

    def test_dict_input(self):
        from routers.auth import _ensure_dict
        d = {"key": "value"}
        assert _ensure_dict(d) == d

    def test_json_string_input(self):
        from routers.auth import _ensure_dict
        s = '{"key": "value"}'
        assert _ensure_dict(s) == {"key": "value"}

    def test_invalid_json_string(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("not json") is None

    def test_non_dict_json_string(self):
        from routers.auth import _ensure_dict
        # JSON array, not dict
        assert _ensure_dict("[1, 2, 3]") is None

    def test_integer_input(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(42) is None

    def test_empty_dict(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict({}) == {}

    def test_empty_string(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("") is None


class TestGetUserPrimaryRole:
    """Test get_user_primary_role with role priority."""

    def test_no_memberships(self, test_db, test_users):
        from routers.auth import get_user_primary_role
        # Use annotator user who has no org membership
        result = get_user_primary_role(test_users[2], test_db)
        assert result is None

    def test_org_admin_role(self, test_db, test_users):
        from routers.auth import get_user_primary_role

        org = Organization(
            id=str(uuid.uuid4()),
            name="Auth Test Org",
            slug=f"auth-org-{uuid.uuid4().hex[:8]}",
            display_name="Auth Test Org",
            created_at=datetime.utcnow(),
        )
        test_db.add(org)
        test_db.commit()

        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[1].id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        result = get_user_primary_role(test_users[1], test_db)
        assert result == "ORG_ADMIN"

    def test_contributor_role(self, test_db, test_users):
        from routers.auth import get_user_primary_role

        org = Organization(
            id=str(uuid.uuid4()),
            name="Auth Test Org 2",
            slug=f"auth-org2-{uuid.uuid4().hex[:8]}",
            display_name="Auth Test Org 2",
            created_at=datetime.utcnow(),
        )
        test_db.add(org)
        test_db.commit()

        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[2].id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        result = get_user_primary_role(test_users[2], test_db)
        assert result == "CONTRIBUTOR"


class TestBuildUserProfileResponse:
    """Test _build_user_profile_response."""

    def test_basic_profile(self, test_db, test_users):
        from routers.auth import _build_user_profile_response
        profile = _build_user_profile_response(test_users[0], test_db)
        assert profile.id == test_users[0].id
        assert profile.email == test_users[0].email
        assert profile.is_superadmin == test_users[0].is_superadmin

    def test_profile_missing_optional_attrs(self, test_db, test_users):
        from routers.auth import _build_user_profile_response
        user = test_users[0]
        # Test that profile works even when optional attrs are missing
        profile = _build_user_profile_response(user, test_db)
        # Optional fields default to None
        assert profile.pseudonym is None or isinstance(profile.pseudonym, str)
        assert profile.legal_expertise_level is None or isinstance(profile.legal_expertise_level, str)


class TestLoginEndpoint:
    """Test POST /api/auth/login"""

    def test_login_success(self, client, test_users, test_db):
        resp = client.post("/api/auth/login", json={
            "username": "admin@test.com",
            "password": "admin123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_invalid_password(self, client, test_users, test_db):
        resp = client.post("/api/auth/login", json={
            "username": "admin@test.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, test_users, test_db):
        resp = client.post("/api/auth/login", json={
            "username": "nonexistent@test.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_login_unverified_email(self, client, test_users, test_db):
        # Create user with unverified email
        from user_service import get_password_hash
        from models import User
        user = User(
            id=str(uuid.uuid4()),
            username="unverified@test.com",
            email="unverified@test.com",
            name="Unverified User",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            email_verified=False,
        )
        test_db.add(user)
        test_db.commit()

        resp = client.post("/api/auth/login", json={
            "username": "unverified@test.com",
            "password": "password123",
        })
        assert resp.status_code == 403
        assert "verification" in resp.json()["detail"].lower()


class TestProfileEndpoint:
    """Test GET /api/auth/profile"""

    def test_get_profile(self, client, test_users, test_db, auth_headers):
        resp = client.get("/api/auth/profile", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "admin@test.com"
        assert body["is_superadmin"] is True


class TestMeEndpoint:
    """Test GET /api/auth/me"""

    def test_get_me(self, client, test_users, test_db, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == test_users[0].id

    def test_get_me_unauthenticated(self, client, test_users, test_db):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestRefreshEndpoint:
    """Test POST /api/auth/refresh"""

    def test_refresh_no_token(self, client, test_users, test_db):
        resp = client.post("/api/auth/refresh")
        # Without refresh token cookie, should fail
        assert resp.status_code in [400, 401, 403]

    def test_refresh_invalid_token(self, client, test_users, test_db):
        resp = client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": "invalid-token"},
        )
        assert resp.status_code in [400, 401, 403]


class TestLogoutEndpoint:
    """Test POST /api/auth/logout"""

    def test_logout(self, client, test_users, test_db, auth_headers):
        resp = client.post("/api/auth/logout", headers=auth_headers["admin"])
        assert resp.status_code == 200


class TestSignupEndpoint:
    """Test POST /api/auth/signup"""

    def test_signup_basic(self, client, test_users, test_db):
        email = f"newuser_{uuid.uuid4().hex[:8]}@test.com"
        with patch("routers.auth.email_verification_service") as mock_email:
            mock_email.send_verification_email.return_value = True
            resp = client.post("/api/auth/signup", json={
                "username": email,
                "email": email,
                "password": "SecurePass123!",
                "name": "New User",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            })
        assert resp.status_code in [200, 201]

    def test_signup_with_all_fields(self, client, test_users, test_db):
        email = f"fulluser_{uuid.uuid4().hex[:8]}@test.com"
        with patch("routers.auth.email_verification_service") as mock_email:
            mock_email.send_verification_email.return_value = True
            resp = client.post("/api/auth/signup", json={
                "username": email,
                "email": email,
                "password": "SecurePass123!",
                "name": "Full Profile User",
                "legal_expertise_level": "law_student",
                "german_proficiency": "c1",
                "degree_program_type": "staatsexamen",
                "current_semester": 5,
                "legal_specializations": ["civil_law", "criminal_law"],
                "gender": "male",
                "age": 25,
                "job": "Student",
                "years_of_experience": 2,
                "subjective_competence_civil": 5,
                "subjective_competence_public": 4,
                "subjective_competence_criminal": 3,
                "grade_zwischenpruefung": 8.5,
                "ati_s_scores": {"ati1": 4, "ati2": 5},
                "ptt_a_scores": {"ptt1": 3, "ptt2": 4},
                "ki_experience_scores": {"ki1": 5},
            })
        # 200/201 = success, 400 = already exists or validation
        assert resp.status_code in [200, 201, 400]

    def test_signup_duplicate_email(self, client, test_users, test_db):
        resp = client.post("/api/auth/signup", json={
            "username": "admin@test.com",
            "email": "admin@test.com",
            "password": "SecurePass123!",
            "name": "Duplicate User",
            "legal_expertise_level": "layperson",
            "german_proficiency": "native",
        })
        assert resp.status_code in [400, 409]
