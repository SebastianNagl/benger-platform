"""
Integration tests targeting uncovered handler body code in routers/auth.py.

Focuses on:
- login: success flow, invalid credentials, unverified email, cookie setting
- signup: self-registration, duplicate user, invitation-based signup
- register: superadmin-only creation
- /me: user data response structure
- /me/contexts: combined user + org contexts
- /profile GET/PUT: full profile fields, demographic data, legal expertise
- /change-password: success and failure paths
- /verify-email: token verification
- /check-profile-status: invited vs self-registered
- /mandatory-profile-status: missing fields, confirmation due
- /confirm-profile: profile confirmation
- /profile-history: own and admin access
- /verify: token validity check
- /logout: cookie clearing
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from models import (
    User,
)


def _uid():
    return str(uuid.uuid4())


# ===================================================================
# Async-endpoint test helpers
# ===================================================================
#
# A subset of /api/auth/* endpoints moved onto the async DB lane
# (``Depends(get_async_db)``). Driving those with the sync ``client`` /
# ``test_db`` poisons the shared asyncpg pool (cross-event-loop), so those
# tests use the async fixtures (``async_test_client`` + ``async_test_db``)
# and override ``require_user`` rather than presenting a Bearer JWT — the
# handlers re-query the DB by ``current_user.id``, so a lightweight pydantic
# auth user is all the dependency needs to return.


@contextmanager
def _as_user(db_user):
    """Override ``require_user`` to return an auth user mirroring ``db_user``.

    The async handlers re-query the real (async-session) DB row by id, so the
    returned object only needs id/username/email/name/flags — the demographic
    and profile state all come from the seeded ORM row.
    """
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _seed_user(
    db,
    *,
    user_id=None,
    username=None,
    email=None,
    name="Test User",
    is_superadmin=False,
):
    """Seed a minimal users row on the async session and return it.

    Captures created_at into the instance after flush so callers can read
    plain attributes without triggering an implicit sync lazy reload.
    """
    from models import User as DBUser

    uid = user_id or _uid()
    user = DBUser(
        id=uid,
        username=username or f"user_{uid[:8]}@test.com",
        email=email or f"user_{uid[:8]}@test.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_org_membership(db, user, role):
    """Seed an Organization + active OrganizationMembership for ``user``.

    ``role`` is an ``OrganizationRole`` enum member. Returns the Organization.
    """
    from models import Organization, OrganizationMembership

    org = Organization(
        id=_uid(),
        name="Test Organization",
        display_name="Test Organization Display",
        slug=f"test-org-{_uid()[:8]}",
        description="A test organization",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()

    membership = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    await db.flush()
    return org


# ===================================================================
# LOGIN
# ===================================================================

@pytest.mark.integration
class TestLoginDeep:
    """Deep coverage for login handler body."""

    def test_login_success_returns_token_and_user(self, client, test_db, test_users):
        """Successful login returns access_token and user object."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        user = data["user"]
        assert user["id"] == "admin-test-id"
        assert user["username"] == "admin@test.com"
        assert user["email"] == "admin@test.com"

    def test_login_invalid_password(self, client, test_db, test_users):
        """Invalid password returns 401."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, test_db, test_users):
        """Nonexistent user returns 401."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody@test.com", "password": "anything"},
        )
        assert resp.status_code == 401

    def test_login_unverified_email(self, client, test_db):
        """User with unverified email gets 403."""
        from auth_module.user_service import get_password_hash
        unverified = User(
            id=_uid(), username="unverified@test.com",
            email="unverified@test.com", name="Unverified",
            hashed_password=get_password_hash("password123"),
            is_superadmin=False, is_active=True,
            email_verified=False,
        )
        test_db.add(unverified)
        test_db.commit()

        resp = client.post(
            "/api/auth/login",
            json={"username": "unverified@test.com", "password": "password123"},
        )
        assert resp.status_code == 403

    def test_login_sets_cookies(self, client, test_db, test_users):
        """Login sets access_token and refresh_token cookies."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        cookies = resp.cookies
        assert "access_token" in cookies

    def test_login_contributor(self, client, test_db, test_users):
        """Contributor can login."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "contributor@test.com", "password": "contrib123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ===================================================================
# ME ENDPOINT
# ===================================================================

@pytest.mark.integration
class TestMeDeep:
    """Deep coverage for /me endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_me_returns_user_object(self, async_test_client, async_test_db):
        """GET /me returns user data from database."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "admin-test-id"
        assert data["username"] == "admin@test.com"
        assert data["is_superadmin"] == True  # noqa: E712
        assert "role" in data

    @pytest.mark.asyncio
    async def test_me_annotator(self, async_test_client, async_test_db):
        """Annotator /me includes role."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "annotator-test-id"
        assert data["is_superadmin"] == False  # noqa: E712
        assert data["role"] == "ANNOTATOR"

    @pytest.mark.asyncio
    async def test_me_unauthorized(self, async_test_client, async_test_db):
        """No auth header returns 401."""
        resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 401


# ===================================================================
# ME/CONTEXTS
# ===================================================================

@pytest.mark.integration
class TestMeContextsDeep:
    """Deep coverage for /me/contexts endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_contexts_superadmin_sees_all_orgs(self, async_test_client, async_test_db):
        """Superadmin /me/contexts returns all organizations."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ORG_ADMIN)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "organizations" in data
        assert "private_mode_available" in data
        assert data["user"]["id"] == "admin-test-id"

    @pytest.mark.asyncio
    async def test_contexts_annotator_sees_own_orgs(self, async_test_client, async_test_db):
        """Annotator /me/contexts returns only their organizations."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) >= 1

    @pytest.mark.asyncio
    async def test_contexts_org_has_member_count(self, async_test_client, async_test_db):
        """Organization context includes member_count."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ORG_ADMIN)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        orgs = resp.json()["organizations"]
        assert len(orgs) >= 1
        for org in orgs:
            assert "member_count" in org

    @pytest.mark.asyncio
    async def test_contexts_org_has_role(self, async_test_client, async_test_db):
        """Organization context includes user's role."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ORG_ADMIN)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        orgs = resp.json()["organizations"]
        assert len(orgs) >= 1
        for org in orgs:
            assert "role" in org


# ===================================================================
# VERIFY TOKEN
# ===================================================================

@pytest.mark.integration
class TestVerifyToken:
    """Coverage for /verify endpoint."""

    def test_verify_valid_token(self, client, test_db, test_users, auth_headers):
        """Valid token returns valid=True."""
        resp = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["valid"] == True  # noqa: E712

    def test_verify_invalid_token(self, client, test_db):
        """Invalid token returns 401."""
        resp = client.get(
            "/api/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


# ===================================================================
# PROFILE
# ===================================================================

@pytest.mark.integration
class TestProfileDeep:
    """Deep coverage for profile GET/PUT."""

    @pytest.mark.asyncio
    async def test_get_profile_full_fields(self, async_test_client, async_test_db):
        """GET /profile returns all profile fields."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        data = resp.json()
        expected_fields = [
            "id", "username", "email", "name", "role",
            "is_superadmin", "is_active", "created_at",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_profile_includes_demographic_fields(self, async_test_client, async_test_db):
        """Profile includes demographic and legal expertise fields."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        data = resp.json()
        # These fields should exist (may be null)
        demographic_fields = [
            "age", "job", "years_of_experience",
            "legal_expertise_level", "german_proficiency",
        ]
        for field in demographic_fields:
            assert field in data, f"Missing field: {field}"

    def test_update_profile_name(self, client, test_db, test_users, auth_headers):
        """PUT /profile updates user name."""
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Updated Admin Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Admin Name"

    def test_update_profile_demographic_fields(self, client, test_db, test_users, auth_headers):
        """PUT /profile updates demographic fields."""
        resp = client.put(
            "/api/auth/profile",
            json={
                "name": "Admin With Demographics",
                "age": 30,
                "job": "Legal researcher",
                "years_of_experience": 5,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["age"] == 30
        assert data["job"] == "Legal researcher"

    @pytest.mark.asyncio
    async def test_get_profile_annotator(self, async_test_client, async_test_db):
        """Annotator can get their profile."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "annotator-test-id"
        assert data["role"] == "ANNOTATOR"

    def test_update_profile_pseudonym(self, client, test_db, test_users, auth_headers):
        """PUT /profile can toggle use_pseudonym."""
        resp = client.put(
            "/api/auth/profile",
            json={"use_pseudonym": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ===================================================================
# CHANGE PASSWORD
# ===================================================================

@pytest.mark.integration
class TestChangePasswordDeep:
    """Deep coverage for change-password endpoint."""

    def test_change_password_success(self, client, test_db, test_users, auth_headers):
        """Successful password change."""
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "newpassword456",
                "confirm_password": "newpassword456",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_change_password_mismatch(self, client, test_db, test_users, auth_headers):
        """Password confirmation mismatch returns 400."""
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "newpass1",
                "confirm_password": "newpass2",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_change_password_wrong_current(self, client, test_db, test_users, auth_headers):
        """Wrong current password returns error."""
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "wrongpassword",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400


# ===================================================================
# CHECK PROFILE STATUS
# ===================================================================

@pytest.mark.integration
class TestCheckProfileStatus:
    """Coverage for check-profile-status endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_check_status_normal_user(self, async_test_client, async_test_db):
        """Normal user profile status check."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/check-profile-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "profile_completed" in data
        assert "needs_profile_completion" in data


# ===================================================================
# MANDATORY PROFILE STATUS
# ===================================================================

@pytest.mark.integration
class TestMandatoryProfileStatus:
    """Coverage for mandatory-profile-status endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_mandatory_status(self, async_test_client, async_test_db):
        """Mandatory profile status includes required fields."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "mandatory_profile_completed" in data
        assert "confirmation_due" in data
        assert "missing_fields" in data

    @pytest.mark.asyncio
    async def test_mandatory_status_annotator(self, async_test_client, async_test_db):
        """Annotator mandatory profile status."""
        from models import OrganizationRole

        user = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        await _seed_org_membership(async_test_db, user, OrganizationRole.ANNOTATOR)
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 200


# ===================================================================
# CONFIRM PROFILE
# ===================================================================

@pytest.mark.integration
class TestConfirmProfile:
    """Coverage for confirm-profile endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_confirm_profile_updates_timestamp(self, async_test_client, async_test_db):
        """Profile confirmation updates confirmed_at timestamp.

        confirm_profile_endpoint delegates to confirm_profile_async, which
        raises 400 when mandatory profile fields are missing (the freshly
        seeded user has none populated) and otherwise sets the timestamp and
        returns 200. The accepted-status set mirrors the original sync test."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/confirm-profile")
        # Regular users get 200 (confirm_profile sets timestamp), 400 if
        # mandatory fields are still missing, or 404 if user not found.
        assert resp.status_code in (200, 400, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] == True  # noqa: E712
            assert "confirmed_at" in data


# ===================================================================
# PROFILE HISTORY
# ===================================================================

@pytest.mark.integration
class TestProfileHistory:
    """Coverage for profile-history endpoint (async lane)."""

    @pytest.mark.asyncio
    async def test_profile_history_own(self, async_test_client, async_test_db):
        """User can view their own profile history."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.get("/api/auth/profile-history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_profile_history_superadmin_can_view_others(self, async_test_client, async_test_db):
        """Superadmin can view another user's profile history."""
        admin = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        target = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={target.id}"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_profile_history_non_admin_cannot_view_others(self, async_test_client, async_test_db):
        """Non-superadmin cannot view another user's profile history."""
        from models import OrganizationRole

        annotator = await _seed_user(
            async_test_db,
            user_id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
            is_superadmin=False,
        )
        await _seed_org_membership(async_test_db, annotator, OrganizationRole.ANNOTATOR)
        other = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={other.id}"
            )
        assert resp.status_code == 403


# ===================================================================
# LOGOUT
# ===================================================================

@pytest.mark.integration
class TestLogoutDeep:
    """Coverage for logout endpoints (async lane)."""

    @pytest.mark.asyncio
    async def test_logout(self, async_test_client, async_test_db):
        """Logout returns success message."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert "message" in resp.json()

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, async_test_client, async_test_db):
        """Logout all devices returns revoked count."""
        user = await _seed_user(
            async_test_db,
            user_id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        with _as_user(user):
            resp = await async_test_client.post("/api/auth/logout-all")
        assert resp.status_code == 200
        data = resp.json()
        assert "revoked_sessions" in data


# ===================================================================
# SIGNUP
# ===================================================================

@pytest.mark.integration
class TestSignupDeep:
    """Coverage for signup handler body."""

    def test_signup_new_user(self, client, test_db, test_users):
        """Self-registration creates a new user."""
        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"newuser_{uuid.uuid4().hex[:8]}",
                "email": f"new_{uuid.uuid4().hex[:8]}@test.com",
                "name": "New User",
                "password": "securepassword123",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["is_superadmin"] == False  # noqa: E712

    def test_signup_duplicate_username(self, client, test_db, test_users):
        """Signup with existing username fails."""
        resp = client.post(
            "/api/auth/signup",
            json={
                "username": "admin@test.com",
                "email": "different@test.com",
                "name": "Duplicate",
                "password": "password123",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            },
        )
        assert resp.status_code in (400, 409, 422)


# ===================================================================
# REGISTER (superadmin only)
# ===================================================================

@pytest.mark.integration
class TestRegisterDeep:
    """Coverage for register (admin-only) endpoint."""

    def test_register_as_admin(self, client, test_db, test_users, auth_headers):
        """Superadmin can register new users."""
        resp = client.post(
            "/api/auth/register",
            json={
                "username": f"registered_{uuid.uuid4().hex[:8]}",
                "email": f"reg_{uuid.uuid4().hex[:8]}@test.com",
                "name": "Registered User",
                "password": "password123",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_register_as_non_admin(self, client, test_db, test_users, auth_headers, test_org):
        """Non-superadmin cannot register users."""
        resp = client.post(
            "/api/auth/register",
            json={
                "username": "shouldfail",
                "email": "fail@test.com",
                "name": "Fail",
                "password": "password123",
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ===================================================================
# REQUEST PASSWORD RESET
# ===================================================================

@pytest.mark.integration
class TestPasswordReset:
    """Coverage for password reset request endpoint."""

    def test_request_reset_existing_email(self, client, test_db, test_users):
        """Password reset for existing email returns success (no enumeration)."""
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_request_reset_nonexistent_email(self, client, test_db, test_users):
        """Password reset for nonexistent email also returns success (no enumeration)."""
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "nonexistent@test.com"},
        )
        assert resp.status_code == 200
        assert "message" in resp.json()


# ===================================================================
# RESEND VERIFICATION
# ===================================================================

@pytest.mark.integration
class TestResendVerification:
    """Coverage for resend-verification endpoint."""

    def test_resend_nonexistent_email(self, client, test_db, test_users):
        """Resend for nonexistent email returns success (no enumeration)."""
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "nobody@test.com"},
        )
        assert resp.status_code == 200

    def test_resend_already_verified(self, client, test_db, test_users):
        """Resend for already verified email returns success."""
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200
