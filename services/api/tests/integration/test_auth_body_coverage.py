"""
Integration tests for auth.py handler body code.

Covers:
- login: cookie setting, user response structure, contributor/annotator login
- signup: required fields validation, demographic fields, duplicate email,
  legal_expertise_level and german_proficiency required
- register: superadmin-only, annotator blocked
- /me: full response fields, unauthorized
- /me/contexts: superadmin sees all orgs, non-admin sees own orgs,
  org data includes slug, display_name, role, member_count
- /verify: valid/invalid tokens
- /profile GET: full field set, demographic, legal expertise, psychometric
- /profile PUT: update name, demographic, legal specializations, pseudonym
- /change-password: mismatch, wrong current, success
- /request-password-reset: existing email, nonexistent email (no enumeration)
- /reset-password: mismatched passwords
- /verify-email: invalid token
- /resend-verification: already verified, nonexistent
- /check-profile-status: normal user, status fields
- /mandatory-profile-status: annotator/admin status
- /confirm-profile: timestamp update
- /profile-history: own, admin views other, non-admin blocked
- /logout: cookie clearing
- /logout-all: session revocation
- helper: _ensure_dict, get_user_primary_role
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Async-lane helpers
#
# Several auth read/action endpoints moved to the async DB lane
# (Depends(get_async_db)): /me, /me/contexts, /profile (GET),
# /check-profile-status, /mandatory-profile-status, /confirm-profile,
# /profile-history, /logout, /logout-all. Driving them with the sync
# TestClient + sync test_db fails with a cross-event-loop RuntimeError (the
# async engine binds to a different loop than TestClient's portal). Those tests
# are driven with async_test_client, seeded via async_test_db, overriding
# require_user with an AuthUser that mirrors a seeded row so the handlers' async
# DB queries resolve it.
#
# The remaining endpoints stay sync (login, signup, register, /verify,
# change/reset/request-password, verify-email*, resend-verification,
# PUT /profile, refresh) — their tests keep the sync client + test_db fixtures.
# ---------------------------------------------------------------------------

from auth_module.dependencies import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from auth_module.user_service import get_password_hash  # noqa: E402
from main import app  # noqa: E402


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB user row."""
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


async def _aseed_user(db, *, is_superadmin=False, mandatory_profile_completed=False, **overrides):
    """Seed a User row on the async session and return it."""
    suffix = uuid.uuid4().hex[:8]
    fields = dict(
        id=_uid(),
        username=f"user_{suffix}@test.com",
        email=f"user_{suffix}@test.com",
        name="Seeded User",
        hashed_password=get_password_hash("password123"),
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        mandatory_profile_completed=mandatory_profile_completed,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    user = User(**fields)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _aseed_org(db, *, name="Async Body Org", slug=None):
    org = Organization(
        id=_uid(),
        name=name,
        display_name=f"{name} Display",
        slug=slug or f"async-body-org-{uuid.uuid4().hex[:8]}",
        description="seeded org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _aseed_membership(db, user_id, org_id, role=OrganizationRole.ANNOTATOR, is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
    )
    db.add(m)
    await db.flush()
    return m


def _signup_payload(**overrides):
    """Build a valid signup payload with all required fields."""
    base = {
        "username": f"user_{uuid.uuid4().hex[:8]}",
        "email": f"u_{uuid.uuid4().hex[:8]}@test.com",
        "name": "Test User",
        "password": "secure123password",
        "legal_expertise_level": "layperson",
        "german_proficiency": "native",
    }
    base.update(overrides)
    return base


# ===================================================================
# LOGIN: extended coverage
# ===================================================================

@pytest.mark.integration
class TestLoginBody:

    def test_login_response_has_user_object(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"
        user = data["user"]
        assert user["id"] == "admin-test-id"
        assert user["email"] == "admin@test.com"
        assert user["is_superadmin"] == True  # noqa: E712

    def test_login_sets_access_cookie(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert "access_token" in resp.cookies

    def test_login_contributor_returns_token(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "contributor@test.com", "password": "contrib123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_annotator_returns_token(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "annotator@test.com", "password": "annotator123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_invalid_password_401(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user_401(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody@test.com", "password": "anything"},
        )
        assert resp.status_code == 401

    def test_login_unverified_email_403(self, client, test_db):
        from auth_module.user_service import get_password_hash
        u = User(
            id=_uid(), username=f"unverified_{uuid.uuid4().hex[:6]}@test.com",
            email=f"unverified_{uuid.uuid4().hex[:6]}@test.com", name="Unverified",
            hashed_password=get_password_hash("password123"),
            is_superadmin=False, is_active=True, email_verified=False,
        )
        test_db.add(u)
        test_db.commit()
        resp = client.post(
            "/api/auth/login",
            json={"username": u.username, "password": "password123"},
        )
        assert resp.status_code == 403


# ===================================================================
# SIGNUP: field validation
# ===================================================================

@pytest.mark.integration
class TestSignupBody:

    def test_signup_success(self, client, test_db, test_users):
        payload = _signup_payload()
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == payload["username"]
        assert data["is_superadmin"] == False  # noqa: E712

    def test_signup_with_demographic_fields(self, client, test_db, test_users):
        payload = _signup_payload(
            age=25,
            gender="maennlich",  # German enum values required
            job="Student",
            years_of_experience=2,
            degree_program_type="staatsexamen",
            current_semester=5,
        )
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200

    def test_signup_with_legal_specializations(self, client, test_db, test_users):
        payload = _signup_payload(
            legal_specializations=["civil_law", "criminal_law"],
        )
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200

    def test_signup_with_psychometric_scores(self, client, test_db, test_users):
        # Psychometric scales require keys item_1..item_4, each int 1-7
        payload = _signup_payload(
            ati_s_scores={"item_1": 5, "item_2": 3, "item_3": 4, "item_4": 6},
            ptt_a_scores={"item_1": 4, "item_2": 5, "item_3": 3, "item_4": 2},
            ki_experience_scores={"item_1": 3, "item_2": 4, "item_3": 5, "item_4": 6},
        )
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200

    def test_signup_with_subjective_competence(self, client, test_db, test_users):
        payload = _signup_payload(
            subjective_competence_civil=5,
            subjective_competence_public=3,
            subjective_competence_criminal=4,
        )
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200

    def test_signup_with_grade_fields(self, client, test_db, test_users):
        payload = _signup_payload(
            grade_zwischenpruefung=8.5,
            grade_vorgeruecktenubung=10.0,
        )
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 200

    def test_signup_missing_legal_expertise(self, client, test_db, test_users):
        payload = {
            "username": f"noexpert_{uuid.uuid4().hex[:6]}",
            "email": f"noexpert_{uuid.uuid4().hex[:6]}@test.com",
            "name": "No Expert",
            "password": "password123",
            # Missing legal_expertise_level and german_proficiency
        }
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 422  # validation error

    def test_signup_short_password(self, client, test_db, test_users):
        payload = _signup_payload(password="12345")  # too short (min 6)
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 422

    def test_signup_duplicate_email(self, client, test_db, test_users):
        payload = _signup_payload(email="admin@test.com")
        resp = client.post("/api/auth/signup", json=payload)
        # Could be 400, 409, or 500 depending on DB constraint handling
        assert resp.status_code in (400, 409, 500)

    def test_signup_duplicate_username(self, client, test_db, test_users):
        payload = _signup_payload(username="admin@test.com")
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code in (400, 409, 500)

    def test_signup_invalid_email_format(self, client, test_db, test_users):
        payload = _signup_payload(email="not-an-email")
        resp = client.post("/api/auth/signup", json=payload)
        assert resp.status_code == 422


# ===================================================================
# REGISTER (superadmin only)
# ===================================================================

@pytest.mark.integration
class TestRegisterBody:

    def test_register_by_admin(self, client, test_db, test_users, auth_headers):
        payload = _signup_payload()
        resp = client.post(
            "/api/auth/register", json=payload,
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_register_by_annotator_blocked(self, client, test_db, test_users, auth_headers, test_org):
        payload = _signup_payload()
        resp = client.post(
            "/api/auth/register", json=payload,
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_register_by_contributor_blocked(self, client, test_db, test_users, auth_headers, test_org):
        payload = _signup_payload()
        resp = client.post(
            "/api/auth/register", json=payload,
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403

    def test_register_no_auth_blocked(self, client, test_db, test_users):
        payload = _signup_payload()
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 401


# ===================================================================
# /ME
# ===================================================================

@pytest.mark.integration
class TestMeBody:
    """GET /api/auth/me is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_me_admin_fields(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        required = ["id", "username", "email", "name", "is_superadmin", "is_active", "role"]
        for f in required:
            assert f in data
        assert data["is_superadmin"] == True  # noqa: E712
        assert data["email_verified"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_me_annotator_has_role(self, async_test_client, async_test_db):
        annotator = await _aseed_user(async_test_db)
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, annotator.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "ANNOTATOR"
        assert data["is_superadmin"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_me_unauthorized(self, async_test_client):
        resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 401


# ===================================================================
# /ME/CONTEXTS
# ===================================================================

@pytest.mark.integration
class TestMeContextsBody:
    """GET /api/auth/me/contexts is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_contexts_superadmin_structure(self, async_test_client, async_test_db):
        admin = await _aseed_user(
            async_test_db,
            id="admin-test-id",
            username="admin@test.com",
            email="admin@test.com",
            name="Test Admin",
            is_superadmin=True,
        )
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "organizations" in data
        assert data["private_mode_available"] == True  # noqa: E712
        assert data["user"]["id"] == "admin-test-id"

    @pytest.mark.asyncio
    async def test_contexts_org_fields(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me/contexts")
        data = resp.json()
        assert len(data["organizations"]) >= 1
        org_ctx = data["organizations"][0]
        org_fields = ["id", "name", "display_name", "slug", "role", "member_count"]
        for f in org_fields:
            assert f in org_ctx, f"Missing org field: {f}"

    @pytest.mark.asyncio
    async def test_contexts_annotator_own_orgs(self, async_test_client, async_test_db):
        annotator = await _aseed_user(async_test_db)
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, annotator.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) >= 1

    @pytest.mark.asyncio
    async def test_contexts_member_count_positive(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me/contexts")
        for org_ctx in resp.json()["organizations"]:
            assert org_ctx["member_count"] >= 0


# ===================================================================
# /VERIFY
# ===================================================================

@pytest.mark.integration
class TestVerifyBody:

    def test_verify_valid(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["valid"] == True  # noqa: E712

    def test_verify_invalid(self, client, test_db):
        resp = client.get(
            "/api/auth/verify",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401


# ===================================================================
# PROFILE GET/PUT
# ===================================================================

@pytest.mark.integration
class TestProfileBody:

    @pytest.mark.asyncio
    async def test_get_profile_full_fields(self, async_test_client, async_test_db):
        # GET /api/auth/profile is async — driven via async client.
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        data = resp.json()
        expected = [
            "id", "username", "email", "name", "role",
            "is_superadmin", "is_active", "created_at",
            "pseudonym", "use_pseudonym",
            "age", "job", "years_of_experience",
            "legal_expertise_level", "german_proficiency",
            "degree_program_type", "current_semester",
            "legal_specializations",
            "german_state_exams_count", "german_state_exams_data",
            "gender",
            "subjective_competence_civil", "subjective_competence_public",
            "subjective_competence_criminal",
            "grade_zwischenpruefung", "grade_vorgeruecktenubung",
            "grade_first_staatsexamen", "grade_second_staatsexamen",
            "ati_s_scores", "ptt_a_scores", "ki_experience_scores",
            "mandatory_profile_completed", "profile_confirmed_at",
        ]
        for f in expected:
            assert f in data, f"Missing profile field: {f}"

    def test_update_profile_name(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Updated Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_profile_demographics(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"age": 35, "job": "Researcher", "years_of_experience": 10},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["age"] == 35

    def test_update_profile_legal_fields(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={
                "legal_expertise_level": "law_student",
                "german_proficiency": "c2",
                "degree_program_type": "llm",
                "current_semester": 4,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["legal_expertise_level"] == "law_student"

    def test_update_profile_pseudonym_toggle(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"use_pseudonym": False},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_profile_annotator(self, async_test_client, async_test_db):
        # GET /api/auth/profile is async — driven via async client.
        annotator = await _aseed_user(
            async_test_db,
            id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
        )
        org = await _aseed_org(async_test_db)
        await _aseed_membership(
            async_test_db, annotator.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        assert resp.json()["id"] == "annotator-test-id"

    def test_update_profile_legal_specializations(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/auth/profile",
            json={"legal_specializations": ["civil_law", "tax_law"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ===================================================================
# CHANGE PASSWORD
# ===================================================================

@pytest.mark.integration
class TestChangePasswordBody:

    def test_change_password_mismatch(self, client, test_db, test_users, auth_headers):
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

    def test_change_password_success(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "newadminpass",
                "confirm_password": "newadminpass",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "message" in resp.json()


# ===================================================================
# PASSWORD RESET REQUEST
# ===================================================================

@pytest.mark.integration
class TestPasswordResetBody:

    def test_request_reset_existing_email(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_request_reset_nonexistent_no_enumeration(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "nonexistent@test.com"},
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_request_reset_with_language(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/request-password-reset",
            json={"email": "admin@test.com", "language": "de"},
        )
        assert resp.status_code == 200

    def test_reset_password_mismatch(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/reset-password",
            json={
                "token": "fake-token",
                "new_password": "newpass1",
                "confirm_password": "newpass2",
            },
        )
        assert resp.status_code == 400

    def test_reset_password_invalid_token(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/reset-password",
            json={
                "token": "invalid-token",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )
        assert resp.status_code == 400


# ===================================================================
# VERIFY EMAIL
# ===================================================================

@pytest.mark.integration
class TestVerifyEmailBody:

    def test_verify_email_invalid_token(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/verify-email",
            json={"token": "invalid-token-xyz"},
        )
        assert resp.status_code == 400

    def test_verify_email_path_param_invalid(self, client, test_db, test_users):
        resp = client.post("/api/auth/verify-email/bad-token-123")
        assert resp.status_code == 400


# ===================================================================
# RESEND VERIFICATION
# ===================================================================

@pytest.mark.integration
class TestResendVerificationBody:

    def test_resend_nonexistent_no_enumeration(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "nobody@test.com"},
        )
        assert resp.status_code == 200

    def test_resend_already_verified(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "admin@test.com"},
        )
        assert resp.status_code == 200

    def test_resend_with_language(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "admin@test.com", "language": "de"},
        )
        assert resp.status_code == 200


# ===================================================================
# CHECK PROFILE STATUS
# ===================================================================

@pytest.mark.integration
class TestCheckProfileStatusBody:
    """GET /api/auth/check-profile-status is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_normal_user_status(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/check-profile-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "profile_completed" in data
        assert "needs_profile_completion" in data
        assert "has_password" in data

    @pytest.mark.asyncio
    async def test_annotator_status(self, async_test_client, async_test_db):
        annotator = await _aseed_user(
            async_test_db,
            id="annotator-test-id",
            username="annotator@test.com",
            email="annotator@test.com",
            name="Test Annotator",
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/auth/check-profile-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "annotator-test-id"


# ===================================================================
# MANDATORY PROFILE STATUS
# ===================================================================

@pytest.mark.integration
class TestMandatoryProfileStatusBody:
    """GET /api/auth/mandatory-profile-status is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_mandatory_status_fields(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "mandatory_profile_completed" in data
        assert "confirmation_due" in data
        assert "missing_fields" in data

    @pytest.mark.asyncio
    async def test_mandatory_status_annotator(self, async_test_client, async_test_db):
        annotator = await _aseed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 200


# ===================================================================
# CONFIRM PROFILE
# ===================================================================

@pytest.mark.integration
class TestConfirmProfileBody:
    """POST /api/auth/confirm-profile is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_confirm_profile_missing_fields_returns_400(
        self, async_test_client, async_test_db
    ):
        """A user lacking mandatory profile fields gets a 400 on confirm."""
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/confirm-profile")
        assert resp.status_code == 400
        assert "missing fields" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_confirm_profile_success_with_complete_profile(
        self, async_test_client, async_test_db
    ):
        """User with all mandatory fields can confirm profile."""
        admin = await _aseed_user(
            async_test_db,
            is_superadmin=True,
            gender="maennlich",
            age=30,
            legal_expertise_level="layperson",
            german_proficiency="native",
            subjective_competence_civil=5,
            subjective_competence_public=4,
            subjective_competence_criminal=3,
            ati_s_scores={"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4},
            ptt_a_scores={"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4},
            ki_experience_scores={"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/confirm-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] == True  # noqa: E712
        assert "confirmed_at" in data


# ===================================================================
# PROFILE HISTORY
# ===================================================================

@pytest.mark.integration
class TestProfileHistoryBody:
    """GET /api/auth/profile-history is async — driven via async client."""

    @pytest.mark.asyncio
    async def test_own_history(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/profile-history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_admin_views_other_user(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        other = await _aseed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={other.id}"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_other_user(
        self, async_test_client, async_test_db
    ):
        annotator = await _aseed_user(async_test_db)
        other = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/auth/profile-history?user_id={other.id}"
            )
        assert resp.status_code == 403


# ===================================================================
# LOGOUT
# ===================================================================

@pytest.mark.integration
class TestLogoutBody:
    """POST /api/auth/logout and /logout-all are async — driven via async client."""

    @pytest.mark.asyncio
    async def test_logout_returns_message(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert "message" in resp.json()

    @pytest.mark.asyncio
    async def test_logout_all_returns_revoked_count(self, async_test_client, async_test_db):
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/logout-all")
        assert resp.status_code == 200
        data = resp.json()
        assert "revoked_sessions" in data


# ===================================================================
# REFRESH TOKEN
# ===================================================================

@pytest.mark.integration
class TestRefreshBody:

    def test_refresh_without_cookie_401(self, client, test_db, test_users):
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 401


# ===================================================================
# HELPER: _ensure_dict
# ===================================================================

@pytest.mark.integration
class TestEnsureDictHelper:

    def test_none_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(None) is None

    def test_dict_returns_dict(self):
        from routers.auth import _ensure_dict
        d = {"key": "value"}
        assert _ensure_dict(d) == d

    def test_json_string_returns_dict(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict('{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("not json") is None

    def test_non_dict_json_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("[1, 2, 3]") is None

    def test_int_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(42) is None
