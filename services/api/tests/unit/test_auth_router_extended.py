"""
Extended tests for auth router - covering uncovered branches.

Targets: routers/auth.py lines 96-108, 117-119, 219-287, 296-351,
363-383, 393-410, 424-536, 549-557, 571-585, 599-695, 705,
718-759, 779-812, 827-843, 855-877, 886-902, 919-928, 937-948,
960-991, 1000-1065, 1087-1139, 1150-1159, 1179-1214, 1228-1234, 1250-1273
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, MagicMock, patch, PropertyMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestEnsureDict:
    """Test the _ensure_dict helper function."""

    def test_none_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(None) is None

    def test_dict_returns_same_dict(self):
        from routers.auth import _ensure_dict
        d = {"key": "value"}
        assert _ensure_dict(d) == d

    def test_valid_json_string_returns_dict(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict('{"key": "value"}') == {"key": "value"}

    def test_invalid_json_string_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("not json") is None

    def test_json_array_string_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict('[1, 2, 3]') is None

    def test_non_string_non_dict_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(42) is None
        assert _ensure_dict([1, 2]) is None

    def test_empty_json_object_string(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict('{}') == {}


class TestGetUserPrimaryRole:
    """Test get_user_primary_role helper."""

    def test_no_memberships_returns_none(self):
        from routers.auth import get_user_primary_role
        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.id = "user-1"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        result = get_user_primary_role(mock_user, mock_db)
        assert result is None

    def test_org_admin_role_prioritized(self):
        from routers.auth import get_user_primary_role
        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.id = "user-1"

        membership1 = Mock()
        membership1.role = Mock()
        membership1.role.value = "CONTRIBUTOR"
        membership1.is_active = True

        membership2 = Mock()
        membership2.role = Mock()
        membership2.role.value = "ORG_ADMIN"
        membership2.is_active = True

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = [membership1, membership2]
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        result = get_user_primary_role(mock_user, mock_db)
        assert result == "ORG_ADMIN"

    def test_annotator_role_returned(self):
        from routers.auth import get_user_primary_role
        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.id = "user-1"

        membership = Mock()
        membership.role = Mock()
        membership.role.value = "ANNOTATOR"
        membership.is_active = True

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = [membership]
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        result = get_user_primary_role(mock_user, mock_db)
        assert result == "ANNOTATOR"


class TestBuildUserProfileResponse:
    """Test _build_user_profile_response helper."""

    def test_builds_complete_profile(self):
        from routers.auth import _build_user_profile_response
        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.username = "testuser"
        mock_user.email = "test@test.com"
        mock_user.name = "Test User"
        mock_user.is_superadmin = False
        mock_user.is_active = True
        mock_user.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_user.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_user.pseudonym = "anon_1234"
        mock_user.use_pseudonym = True
        mock_user.age = 30
        mock_user.job = "Lawyer"
        mock_user.years_of_experience = 5
        mock_user.legal_expertise_level = "practicing_lawyer"
        mock_user.german_proficiency = "native"
        mock_user.degree_program_type = "jura"
        mock_user.current_semester = 8
        mock_user.legal_specializations = ["civil_law"]
        mock_user.german_state_exams_count = 1
        mock_user.german_state_exams_data = None
        mock_user.gender = "male"
        mock_user.subjective_competence_civil = 4
        mock_user.subjective_competence_public = 3
        mock_user.subjective_competence_criminal = 2
        mock_user.grade_zwischenpruefung = "10.0"
        mock_user.grade_vorgeruecktenubung = "9.5"
        mock_user.grade_first_staatsexamen = "11.0"
        mock_user.grade_second_staatsexamen = None
        mock_user.ati_s_scores = {"item1": 5}
        mock_user.ptt_a_scores = {"item1": 3}
        mock_user.ki_experience_scores = {"item1": 4}
        mock_user.mandatory_profile_completed = True
        mock_user.profile_confirmed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

        with patch("routers.auth.get_user_primary_role") as mock_role:
            mock_role.return_value = "CONTRIBUTOR"
            result = _build_user_profile_response(mock_user, mock_db)

        assert result.id == "user-1"
        assert result.username == "testuser"
        assert result.role == "CONTRIBUTOR"
        assert result.pseudonym == "anon_1234"
        assert result.ati_s_scores == {"item1": 5}

    def test_builds_profile_with_none_dates(self):
        from routers.auth import _build_user_profile_response
        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.id = "user-2"
        mock_user.username = "user2"
        mock_user.email = "user2@test.com"
        mock_user.name = "User 2"
        mock_user.is_superadmin = False
        mock_user.is_active = True
        mock_user.created_at = None
        mock_user.updated_at = None
        mock_user.profile_confirmed_at = None
        # Set all optional fields to None to avoid Mock object validation errors
        mock_user.pseudonym = None
        mock_user.use_pseudonym = True
        mock_user.age = None
        mock_user.job = None
        mock_user.years_of_experience = None
        mock_user.legal_expertise_level = None
        mock_user.german_proficiency = None
        mock_user.degree_program_type = None
        mock_user.current_semester = None
        mock_user.legal_specializations = None
        mock_user.german_state_exams_count = None
        mock_user.german_state_exams_data = None
        mock_user.gender = None
        mock_user.subjective_competence_civil = None
        mock_user.subjective_competence_public = None
        mock_user.subjective_competence_criminal = None
        mock_user.grade_zwischenpruefung = None
        mock_user.grade_vorgeruecktenubung = None
        mock_user.grade_first_staatsexamen = None
        mock_user.grade_second_staatsexamen = None
        mock_user.ati_s_scores = None
        mock_user.ptt_a_scores = None
        mock_user.ki_experience_scores = None
        mock_user.mandatory_profile_completed = None

        with patch("routers.auth.get_user_primary_role") as mock_role:
            mock_role.return_value = None
            result = _build_user_profile_response(mock_user, mock_db)

        assert result.created_at is None
        assert result.updated_at is None
        assert result.role is None


class TestAuthRouterExtended:
    """Extended auth router endpoint tests."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="test-user-ext",
            username="testuser_ext",
            email="testext@example.com",
            name="Test Extended",
            hashed_password="hashed_pw",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="superadmin-ext",
            username="superadmin_ext",
            email="superadmin@example.com",
            name="Super Admin",
            hashed_password="hashed_pw",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def _signup_payload(self, **overrides):
        """Build a valid signup payload with required fields."""
        base = {
            "username": "newuser",
            "email": "new@example.com",
            "name": "New User",
            "password": "securepassword123",
            "legal_expertise_level": "law_student",
            "german_proficiency": "native",
        }
        base.update(overrides)
        return base

    def test_signup_success(self, client):
        """Test successful public signup."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None  # No existing invitation
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        mock_created_user = User(
            id="new-user-id",
            username="newuser",
            email="new@example.com",
            name="New User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=False,
            created_at=datetime.now(timezone.utc),
        )

        def override_get_db():
            return mock_db

        with patch("routers.auth.create_user") as mock_create, \
             patch("routers.auth.email_verification_service") as mock_evs:
            mock_create.return_value = mock_created_user
            mock_evs.send_verification_email = AsyncMock(return_value=True)

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/signup", json=self._signup_payload())
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["username"] == "newuser"
            finally:
                app.dependency_overrides.clear()

    def test_signup_duplicate_username(self, client):
        """Test signup with duplicate username."""
        from database import get_db

        mock_db = Mock(spec=Session)

        def override_get_db():
            return mock_db

        with patch("routers.auth.create_user") as mock_create:
            from fastapi import HTTPException
            mock_create.side_effect = HTTPException(
                status_code=400, detail="Username already exists"
            )

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/signup", json=self._signup_payload(
                    username="existing", email="existing@example.com", name="Existing"
                ))
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_signup_unexpected_error(self, client):
        """Test signup with unexpected error."""
        from database import get_db

        mock_db = Mock(spec=Session)

        def override_get_db():
            return mock_db

        with patch("routers.auth.create_user") as mock_create:
            mock_create.side_effect = RuntimeError("Database connection lost")

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/signup", json=self._signup_payload())
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_register_superadmin_only(self, client, mock_superadmin):
        """Test register endpoint for superadmin."""
        from database import get_db
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        def override_get_db():
            return Mock(spec=Session)

        mock_created_user = User(
            id="registered-user",
            username="registered",
            email="registered@example.com",
            name="Registered",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=False,
            created_at=datetime.now(timezone.utc),
        )

        with patch("routers.auth.create_user") as mock_create:
            mock_create.return_value = mock_created_user
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/register", json={
                    "username": "registered",
                    "email": "registered@example.com",
                    "name": "Registered",
                    "password": "password123",
                    "legal_expertise_level": "law_student",
                    "german_proficiency": "native",
                })
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_refresh_token_invalid(self, client):
        """Test refresh with invalid token returns 401."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.refresh_access_token") as mock_refresh:
            mock_refresh.return_value = None

            app.dependency_overrides[get_db] = override_get_db
            try:
                client.cookies["refresh_token"] = "invalid-token"
                response = client.post("/api/auth/refresh")
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            finally:
                app.dependency_overrides.clear()

    def test_logout_without_refresh_token(self, client, mock_user):
        """Test logout when no refresh token cookie exists."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Don't set any cookies
            response = client.post("/api/auth/logout")
            assert response.status_code == status.HTTP_200_OK
            assert "successfully" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_logout_all_devices(self, client, mock_user):
        """Test logout from all devices."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.revoke_user_tokens", create=True) as mock_revoke:
            mock_revoke.return_value = 3

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                with patch("services.refresh_token_service.revoke_user_tokens") as mock_svc:
                    mock_svc.return_value = 3
                    response = client.post("/api/auth/logout-all")
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "all devices" in data["message"].lower()
                    assert data["revoked_sessions"] == 3
            finally:
                app.dependency_overrides.clear()

    def test_get_me_contexts_superadmin(self, client, mock_superadmin):
        """Test /me/contexts for superadmin returns user and organizations."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_superadmin

        mock_db = MagicMock(spec=Session)
        # MagicMock allows any chained call pattern, return empty lists
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []

        def override_get_db():
            return mock_db

        with patch("routers.auth.get_user_primary_role") as mock_role:
            mock_role.return_value = "ORG_ADMIN"
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/auth/me/contexts")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "user" in data
                assert "organizations" in data
                assert data["user"]["is_superadmin"] is True
            finally:
                app.dependency_overrides.clear()

    def test_verify_token(self, client, mock_user):
        """Test /auth/verify endpoint."""
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user
        try:
            response = client.get("/api/auth/verify")
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["valid"] is True
        finally:
            app.dependency_overrides.clear()

    def test_get_profile_exception_fallback(self, client, mock_user):
        """Test profile endpoint falls back gracefully on DB exception."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_db.query.side_effect = Exception("DB error")

        def override_get_db():
            return mock_db

        with patch("routers.auth.get_user_primary_role") as mock_role:
            mock_role.return_value = "ANNOTATOR"
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/auth/profile")
                assert response.status_code == status.HTTP_200_OK
                # Falls back to current_user-based profile
                data = response.json()
                assert data["id"] == mock_user.id
            finally:
                app.dependency_overrides.clear()

    def test_update_profile_user_not_found(self, client, mock_user):
        """Test profile update when user not found."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.update_user_profile") as mock_update:
            mock_update.return_value = None
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.put("/api/auth/profile", json={
                    "name": "Updated",
                    "email": "test@example.com",
                })
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_change_password_failure(self, client, mock_user):
        """Test change password returns 500 on failure."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.change_user_password") as mock_change:
            mock_change.return_value = False
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/change-password", json={
                    "current_password": "oldpassword123",
                    "new_password": "newpassword123",
                    "confirm_password": "newpassword123",
                })
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_request_password_reset_nonexistent_email(self, client):
        """Test password reset for non-existent email (anti-enumeration)."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.post("/api/auth/request-password-reset", json={
                "email": "nonexistent@example.com",
            })
            assert response.status_code == status.HTTP_200_OK
            assert "if the email exists" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_request_password_reset_with_user(self, client):
        """Test password reset for existing user."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_user = Mock()
        mock_user.email = "user@example.com"
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
            mock_prs.send_password_reset_email = AsyncMock(return_value=True)

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/request-password-reset", json={
                    "email": "user@example.com",
                })
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_reset_password_success(self, client):
        """Test successful password reset."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
            mock_prs.reset_password.return_value = True

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/reset-password", json={
                    "token": "valid-token",
                    "new_password": "newpass123",
                    "confirm_password": "newpass123",
                })
                assert response.status_code == status.HTTP_200_OK
                assert "successfully" in response.json()["message"].lower()
            finally:
                app.dependency_overrides.clear()

    def test_reset_password_mismatch(self, client):
        """Test password reset with mismatched passwords."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.post("/api/auth/reset-password", json={
                "token": "valid-token",
                "new_password": "newpass123",
                "confirm_password": "differentpass",
            })
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_reset_password_invalid_token(self, client):
        """Test password reset with invalid token."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("app.auth_module.password_reset.password_reset_service") as mock_prs:
            mock_prs.reset_password.return_value = False

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/reset-password", json={
                    "token": "invalid-token",
                    "new_password": "newpass123",
                    "confirm_password": "newpass123",
                })
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_verify_email_post_body_success(self, client):
        """Test POST /verify-email with body."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.email_verification_service") as mock_evs:
            mock_evs.verify_email_with_token.return_value = (True, "Email verified")

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/verify-email", json={
                    "token": "valid-token",
                })
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["success"] is True
            finally:
                app.dependency_overrides.clear()

    def test_verify_email_post_body_failure(self, client):
        """Test POST /verify-email with invalid token."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.email_verification_service") as mock_evs:
            mock_evs.verify_email_with_token.return_value = (False, "Invalid token")

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/verify-email", json={
                    "token": "invalid-token",
                })
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_verify_email_enhanced_failure(self, client):
        """Test enhanced email verification failure."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.email_verification_service") as mock_evs:
            mock_evs.verify_email_with_token.return_value = (False, "Token expired")

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/verify-email-enhanced/expired-token")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["success"] is False
                assert data["user_type"] == "unknown"
            finally:
                app.dependency_overrides.clear()

    def test_verify_email_path_exception(self, client):
        """Test verify-email/{token} with unexpected exception."""
        from database import get_db

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.email_verification_service") as mock_evs:
            mock_evs.verify_email_with_token.side_effect = RuntimeError("Unexpected")

            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/verify-email/some-token")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_resend_verification_nonexistent_user(self, client):
        """Test resend verification for non-existent user."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.post("/api/auth/resend-verification", json={
                "email": "nobody@example.com",
            })
            assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()

    def test_check_profile_status(self, client, mock_user):
        """Test check-profile-status endpoint."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_db_user = Mock()
        mock_db_user.id = mock_user.id
        mock_db_user.email = mock_user.email
        mock_db_user.profile_completed = True
        mock_db_user.created_via_invitation = False
        mock_db_user.hashed_password = "hashed"
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_db_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/auth/check-profile-status")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["profile_completed"] is True
            assert data["needs_profile_completion"] is False
        finally:
            app.dependency_overrides.clear()

    def test_check_profile_status_not_found(self, client, mock_user):
        """Test check-profile-status for missing user."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/auth/check-profile-status")
            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_confirm_profile_success(self, client, mock_user):
        """Test confirm-profile endpoint."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("auth_module.user_service.confirm_profile") as mock_confirm:
            confirmed_user = Mock()
            confirmed_user.profile_confirmed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
            mock_confirm.return_value = confirmed_user

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/confirm-profile")
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["success"] is True
            finally:
                app.dependency_overrides.clear()

    def test_confirm_profile_not_found(self, client, mock_user):
        """Test confirm-profile when user not found."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("auth_module.user_service.confirm_profile") as mock_confirm:
            mock_confirm.return_value = None
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.post("/api/auth/confirm-profile")
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_profile_history_own(self, client, mock_user):
        """Test profile-history for own user."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_order = Mock()
        mock_offset = Mock()
        mock_limit = Mock()
        mock_limit.all.return_value = []
        mock_offset.limit.return_value = mock_limit
        mock_order.offset.return_value = mock_offset
        mock_filter.order_by.return_value = mock_order
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/auth/profile-history")
            assert response.status_code == status.HTTP_200_OK
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_profile_history_other_user_non_superadmin(self, client, mock_user):
        """Test profile-history for another user as non-superadmin returns 403."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_db_user = Mock()
        mock_db_user.is_superadmin = False
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_db_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/auth/profile-history?user_id=other-user-id")
            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    def test_mandatory_profile_status(self, client, mock_user):
        """Test mandatory-profile-status endpoint."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_db_user = Mock()
        mock_db_user.id = mock_user.id
        mock_db_user.mandatory_profile_completed = True
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_db_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        with patch("auth_module.user_service.get_mandatory_profile_fields") as mock_fields, \
             patch("auth_module.user_service.check_confirmation_due") as mock_due:
            mock_fields.return_value = []
            mock_due.return_value = (False, None)

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/auth/mandatory-profile-status")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["mandatory_profile_completed"] is True
                assert data["confirmation_due"] is False
            finally:
                app.dependency_overrides.clear()

    def test_mandatory_profile_status_not_found(self, client, mock_user):
        """Test mandatory-profile-status for missing user."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/auth/mandatory-profile-status")
            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()
