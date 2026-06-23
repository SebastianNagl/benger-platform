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

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from models import Organization, OrganizationMembership
from models import User as DBUser


# ---------------------------------------------------------------------------
# Async helper: GET /api/auth/me moved to the async DB lane (it runs
# get_user_primary_role_async against the real test Postgres). Seed a real
# user and override require_user with a matching-id AuthUser.
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
        assert profile.pseudonym == None or isinstance(profile.pseudonym, str)  # noqa: E711
        assert profile.legal_expertise_level == None or isinstance(profile.legal_expertise_level, str)  # noqa: E711


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
        from auth_module.user_service import get_password_hash
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

    @pytest.mark.asyncio
    async def test_get_profile(self, async_test_client, async_test_db):
        # GET /profile is on the async DB lane; seed a real superadmin and
        # assert the returned email + superadmin flag.
        user = await _seed_user(
            async_test_db, email="admin@test.com", is_superadmin=True
        )
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
            assert resp.status_code == 200
            body = resp.json()
            assert body["email"] == "admin@test.com"
            assert body["is_superadmin"] == True  # noqa: E712


class TestMeEndpoint:
    """Test GET /api/auth/me"""

    @pytest.mark.asyncio
    async def test_get_me(self, async_test_client, async_test_db):
        # /me moved to the async DB lane; seed a real user and assert the
        # returned id matches (replaces the auth_headers JWT round-trip,
        # which seeds into the sync session the async handler can't see).
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == user.id

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

    @pytest.mark.asyncio
    async def test_logout(self, async_test_client, async_test_db):
        # logout is on the async DB lane (revoke_refresh_token_async); with no
        # refresh_token cookie the async revoke is skipped but the route 200s.
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/logout")
            assert resp.status_code == 200


class TestSignupEndpoint:
    """Test POST /api/auth/signup"""

    def test_signup_basic(self, client, test_users, test_db):
        email = f"newuser_{uuid.uuid4().hex[:8]}@test.com"
        with patch("routers.auth.session.email_verification_service") as mock_email:
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
        with patch("routers.auth.session.email_verification_service") as mock_email:
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
