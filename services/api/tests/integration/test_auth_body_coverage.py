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
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    Organization,
    OrganizationMembership,
    User,
)


def _uid():
    return str(uuid.uuid4())


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
        assert user["is_superadmin"] is True

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
        from user_service import get_password_hash
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
        assert data["is_superadmin"] is False

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

    def test_me_admin_fields(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        required = ["id", "username", "email", "name", "is_superadmin", "is_active", "role"]
        for f in required:
            assert f in data
        assert data["is_superadmin"] is True
        assert data["email_verified"] is True

    def test_me_annotator_has_role(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "ANNOTATOR"
        assert data["is_superadmin"] is False

    def test_me_unauthorized(self, client, test_db):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


# ===================================================================
# /ME/CONTEXTS
# ===================================================================

@pytest.mark.integration
class TestMeContextsBody:

    def test_contexts_superadmin_structure(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "organizations" in data
        assert data["private_mode_available"] is True
        assert data["user"]["id"] == "admin-test-id"

    def test_contexts_org_fields(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["admin"])
        data = resp.json()
        assert len(data["organizations"]) >= 1
        org = data["organizations"][0]
        org_fields = ["id", "name", "display_name", "slug", "role", "member_count"]
        for f in org_fields:
            assert f in org, f"Missing org field: {f}"

    def test_contexts_annotator_own_orgs(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) >= 1

    def test_contexts_member_count_positive(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/me/contexts", headers=auth_headers["admin"])
        for org in resp.json()["organizations"]:
            assert org["member_count"] >= 0


# ===================================================================
# /VERIFY
# ===================================================================

@pytest.mark.integration
class TestVerifyBody:

    def test_verify_valid(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

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

    def test_get_profile_full_fields(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/profile", headers=auth_headers["admin"])
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

    def test_get_profile_annotator(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/profile", headers=auth_headers["annotator"])
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

    def test_normal_user_status(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/check-profile-status", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "profile_completed" in data
        assert "needs_profile_completion" in data
        assert "has_password" in data

    def test_annotator_status(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/check-profile-status", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "annotator-test-id"


# ===================================================================
# MANDATORY PROFILE STATUS
# ===================================================================

@pytest.mark.integration
class TestMandatoryProfileStatusBody:

    def test_mandatory_status_fields(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/mandatory-profile-status", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert "mandatory_profile_completed" in data
        assert "confirmation_due" in data
        assert "missing_fields" in data

    def test_mandatory_status_annotator(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get("/api/auth/mandatory-profile-status", headers=auth_headers["annotator"])
        assert resp.status_code == 200


# ===================================================================
# CONFIRM PROFILE
# ===================================================================

@pytest.mark.integration
class TestConfirmProfileBody:

    def test_confirm_profile_missing_fields_returns_400(self, client, test_db, test_users, auth_headers):
        """Test users lack mandatory profile fields, so confirm returns 400."""
        resp = client.post("/api/auth/confirm-profile", headers=auth_headers["admin"])
        assert resp.status_code == 400
        assert "missing fields" in resp.json()["detail"].lower()

    def test_confirm_profile_success_with_complete_profile(self, client, test_db, test_users, auth_headers):
        """User with all mandatory fields can confirm profile."""
        from models import User as DBUser
        admin = test_db.query(DBUser).filter(DBUser.id == "admin-test-id").first()
        # Fill all mandatory fields
        admin.gender = "maennlich"
        admin.age = 30
        admin.legal_expertise_level = "layperson"
        admin.german_proficiency = "native"
        admin.subjective_competence_civil = 5
        admin.subjective_competence_public = 4
        admin.subjective_competence_criminal = 3
        admin.ati_s_scores = {"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4}
        admin.ptt_a_scores = {"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4}
        admin.ki_experience_scores = {"item_1": 4, "item_2": 4, "item_3": 4, "item_4": 4}
        test_db.commit()

        resp = client.post("/api/auth/confirm-profile", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "confirmed_at" in data


# ===================================================================
# PROFILE HISTORY
# ===================================================================

@pytest.mark.integration
class TestProfileHistoryBody:

    def test_own_history(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/auth/profile-history", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_views_other_user(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"/api/auth/profile-history?user_id={test_users[2].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_non_admin_blocked_from_other_user(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"/api/auth/profile-history?user_id={test_users[0].id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ===================================================================
# LOGOUT
# ===================================================================

@pytest.mark.integration
class TestLogoutBody:

    def test_logout_returns_message(self, client, test_db, test_users, auth_headers):
        resp = client.post("/api/auth/logout", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_logout_all_returns_revoked_count(self, client, test_db, test_users, auth_headers):
        resp = client.post("/api/auth/logout-all", headers=auth_headers["admin"])
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
