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
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from models import (
    User as DBUser,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    UserProfileHistory,
)


# ---------------------------------------------------------------------------
# Async helpers: several /auth endpoints moved to the async DB lane and now
# query the real test Postgres by current_user.id. We seed real rows and
# override require_user with a matching-id AuthUser (the old `auth_headers`
# JWT seeded into the SYNC session is invisible to the async transaction).
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


async def _seed_membership(db, user, role):
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


class TestSignup:
    """Test signup endpoint."""

    @patch("routers.auth.session.email_verification_service")
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

    @patch("routers.auth.session.email_verification_service")
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

    @pytest.mark.asyncio
    async def test_me_success(self, async_test_client, async_test_db):
        # /me moved to the async DB lane. Seed a real user (the async handler
        # runs get_user_primary_role_async against Postgres) and assert the
        # returned email. Using async_test_client keeps the async engine pool
        # from being poisoned by a sync-client call into an async handler.
        user = await _seed_user(async_test_db, email="admin@test.com")
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
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

    @pytest.mark.asyncio
    async def test_me_contexts(self, async_test_client, async_test_db):
        # /me/contexts moved to the async DB lane — seed a superadmin (mirrors
        # the original admin auth_headers intent) and assert org contexts come back.
        admin = await _seed_user(async_test_db, is_superadmin=True)
        await _seed_membership(async_test_db, admin, OrganizationRole.ORG_ADMIN)
        await async_test_db.flush()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me/contexts")
            assert resp.status_code == 200
            data = resp.json()
            assert "organizations" in data
            assert data["user"]["id"] == admin.id


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

    @patch("routers.auth.verification.email_verification_service")
    def test_request_password_reset(self, mock_email, client, test_db, test_users):
        mock_email.send_password_reset_email = MagicMock(return_value=True)
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200

    @patch("routers.auth.verification.email_verification_service")
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

    @pytest.mark.asyncio
    async def test_get_profile(self, async_test_client, async_test_db):
        # GET /profile is on the async lane (PUT /profile below stays sync).
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
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

    @pytest.mark.asyncio
    async def test_check_profile_status(self, async_test_client, async_test_db):
        # Async lane: seed a real user so the handler's DB lookup hits.
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/check-profile-status")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_mandatory_profile_status(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_profile_history(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile-history")
            assert resp.status_code == 200


class TestLogout:
    """Test logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, async_test_client, async_test_db):
        # logout moved to the async lane; with no refresh_token cookie the
        # async revoke is skipped, but route + cookie clearing still 200s.
        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/logout")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_all(self, async_test_client, async_test_db):
        # logout-all awaits revoke_user_tokens_async — patch the async twin.
        from unittest.mock import AsyncMock

        user = await _seed_user(async_test_db)
        await async_test_db.flush()
        with _as_user(user), \
             patch(
                 "services.refresh_token_service.revoke_user_tokens_async",
                 new=AsyncMock(return_value=3),
             ):
            resp = await async_test_client.post("/api/auth/logout-all")
            assert resp.status_code == 200
            assert resp.json()["revoked_sessions"] == 3


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
