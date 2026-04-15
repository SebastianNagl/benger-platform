"""
Unit tests for uncovered lines in auth_module/dependencies.py and auth_module/service.py.

dependencies.py targets: require_user branches (lines 52-53, 79-84),
  require_org_admin inner function (lines 124-165),
  require_org_contributor inner function (lines 184-227).

service.py targets: db_user_to_user with organizations (lines 26-36),
  authenticate_user without db (lines 55-62),
  refresh_access_token (lines 139-175), revoke_refresh_token (line 186),
  logout_user (lines 189-194).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, Request

from auth_module.models import User


_NOW = datetime.now(timezone.utc)


def _make_user(
    user_id="user-1",
    username="testuser",
    email="test@test.com",
    is_superadmin=False,
    is_active=True,
):
    return User(
        id=user_id,
        username=username,
        email=email,
        name="Test User",
        is_superadmin=is_superadmin,
        is_active=is_active,
        email_verified=True,
        organizations=[],
        created_at=_NOW,
    )


# ---------------------------------------------------------------------------
# dependencies.py - require_user branch coverage (lines 52-53, 79-84)
# ---------------------------------------------------------------------------

class TestRequireUserBranches:
    """Test require_user for branches not covered by existing tests."""

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    def test_no_user_id_in_payload_raises_401(self, mock_verify):
        """Line 52-53: payload has no user_id key."""
        from auth_module.dependencies import require_user

        mock_verify.return_value = {"sub": "someone"}  # no user_id
        request = Mock()
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            require_user(request, db)
        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in exc_info.value.detail

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    def test_user_not_found_raises_401(self, mock_get_user, mock_verify):
        """Line 60-66: user not in DB."""
        from auth_module.dependencies import require_user

        mock_verify.return_value = {"user_id": "nonexistent"}
        mock_get_user.return_value = None
        request = Mock()
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            require_user(request, db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    def test_inactive_user_raises_401(self, mock_get_user, mock_verify):
        """Line 68-74: user found but inactive."""
        from auth_module.dependencies import require_user

        mock_verify.return_value = {"user_id": "user-1"}
        mock_db_user = Mock(is_active=False)
        mock_get_user.return_value = mock_db_user
        request = Mock()
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            require_user(request, db)
        assert exc_info.value.status_code == 401
        assert "Inactive user" in exc_info.value.detail

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    def test_unexpected_exception_raises_401(self, mock_verify):
        """Lines 79-84: generic Exception during auth."""
        from auth_module.dependencies import require_user

        mock_verify.side_effect = ValueError("Unexpected error")
        request = Mock()
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            require_user(request, db)
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail


# ---------------------------------------------------------------------------
# dependencies.py - require_org_admin inner function (lines 124-165)
# ---------------------------------------------------------------------------

class TestRequireOrgAdminInner:
    """Test the inner _check_org_admin function returned by require_org_admin."""

    def test_superadmin_always_passes(self):
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin("org-123")
        superadmin = _make_user(is_superadmin=True)
        request = Mock()
        db = Mock()

        result = checker(request, superadmin, db)
        assert result.id == superadmin.id

    def test_org_id_from_parameter(self):
        """When organization_id is provided to factory, use it directly."""
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin("org-123")
        user = _make_user(is_superadmin=False)
        request = Mock()
        db = MagicMock()

        # Simulate no membership found
        db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            checker(request, user, db)
        assert exc_info.value.status_code == 403
        assert "Organization admin access required" in exc_info.value.detail

    def test_org_id_from_request_state(self):
        """When no org_id parameter, get from request.state."""
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin()  # no org_id param
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state.organization_context = "org-from-state"
        db = MagicMock()

        # Mock membership found
        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id

    def test_org_id_from_header_fallback(self):
        """When no org_id from param or state, fallback to header."""
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin()
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state = Mock(spec=[])  # no organization_context attribute
        request.headers = {"X-Organization-Context": "org-from-header"}
        db = MagicMock()

        # Mock membership found
        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id

    def test_no_org_context_raises_400(self):
        """When no org context from any source, raise 400."""
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin()
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state = Mock(spec=[])  # no organization_context
        request.headers = {}  # no X-Organization-Context header
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            checker(request, user, db)
        assert exc_info.value.status_code == 400
        assert "Organization context required" in exc_info.value.detail

    def test_user_is_admin_passes(self):
        from auth_module.dependencies import require_org_admin

        checker = require_org_admin("org-123")
        user = _make_user(is_superadmin=False)
        request = Mock()
        db = MagicMock()

        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id


# ---------------------------------------------------------------------------
# dependencies.py - require_org_contributor inner function (lines 184-227)
# ---------------------------------------------------------------------------

class TestRequireOrgContributorInner:
    """Test the inner _check_org_contributor function returned by require_org_contributor."""

    def test_superadmin_always_passes(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor("org-123")
        superadmin = _make_user(is_superadmin=True)
        request = Mock()
        db = Mock()

        result = checker(request, superadmin, db)
        assert result.id == superadmin.id

    def test_no_membership_raises_403(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor("org-123")
        user = _make_user(is_superadmin=False)
        request = Mock()
        db = MagicMock()

        db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            checker(request, user, db)
        assert exc_info.value.status_code == 403
        assert "Organization contributor access required" in exc_info.value.detail

    def test_org_id_from_request_state(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor()
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state.organization_context = "org-from-state"
        db = MagicMock()

        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id

    def test_org_id_from_header(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor()
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state = Mock(spec=[])  # no organization_context
        request.headers = {"X-Organization-Context": "org-from-header"}
        db = MagicMock()

        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id

    def test_no_org_context_raises_400(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor()
        user = _make_user(is_superadmin=False)
        request = Mock()
        request.state = Mock(spec=[])
        request.headers = {}
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            checker(request, user, db)
        assert exc_info.value.status_code == 400
        assert "Organization context required" in exc_info.value.detail

    def test_contributor_has_access(self):
        from auth_module.dependencies import require_org_contributor

        checker = require_org_contributor("org-123")
        user = _make_user(is_superadmin=False)
        request = Mock()
        db = MagicMock()

        membership = Mock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = membership

        result = checker(request, user, db)
        assert result.id == user.id


# ---------------------------------------------------------------------------
# service.py - db_user_to_user with organizations (lines 26-36)
# ---------------------------------------------------------------------------

class TestDbUserToUser:
    """Test db_user_to_user conversion including organization memberships."""

    def test_with_organization_memberships(self):
        from auth_module.service import db_user_to_user

        mock_org = Mock()
        mock_org.name = "Test Org"

        mock_membership = Mock()
        mock_membership.organization_id = "org-1"
        mock_membership.organization = mock_org
        mock_membership.role = Mock(value="ORG_ADMIN")

        db_user = Mock()
        db_user.id = "user-1"
        db_user.username = "testuser"
        db_user.email = "test@test.com"
        db_user.name = "Test User"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = _NOW
        db_user.organization_memberships = [mock_membership]

        user = db_user_to_user(db_user)

        assert isinstance(user, User)
        assert user.organizations is not None
        assert len(user.organizations) == 1
        assert user.organizations[0]["id"] == "org-1"
        assert user.organizations[0]["name"] == "Test Org"
        assert user.organizations[0]["role"] == "ORG_ADMIN"

    def test_without_organization_memberships(self):
        from auth_module.service import db_user_to_user

        db_user = Mock()
        db_user.id = "user-2"
        db_user.username = "testuser2"
        db_user.email = "test2@test.com"
        db_user.name = "Test User 2"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = _NOW
        db_user.organization_memberships = []

        user = db_user_to_user(db_user)
        assert user.organizations is None  # empty list becomes None

    def test_without_memberships_attribute(self):
        from auth_module.service import db_user_to_user

        db_user = Mock(spec=["id", "username", "email", "name", "is_superadmin", "is_active", "email_verified", "created_at"])
        db_user.id = "user-3"
        db_user.username = "testuser3"
        db_user.email = "test3@test.com"
        db_user.name = "Test User 3"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = _NOW

        user = db_user_to_user(db_user)
        assert user.organizations is None

    def test_membership_with_no_organization(self):
        from auth_module.service import db_user_to_user

        mock_membership = Mock()
        mock_membership.organization_id = "org-2"
        mock_membership.organization = None
        mock_membership.role = Mock(value="ANNOTATOR")

        db_user = Mock()
        db_user.id = "user-4"
        db_user.username = "testuser4"
        db_user.email = "test4@test.com"
        db_user.name = "Test User 4"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = _NOW
        db_user.organization_memberships = [mock_membership]

        user = db_user_to_user(db_user)
        assert user.organizations[0]["name"] is None

    def test_membership_with_no_role(self):
        from auth_module.service import db_user_to_user

        mock_membership = Mock()
        mock_membership.organization_id = "org-3"
        mock_membership.organization = Mock(name="Org3")
        mock_membership.role = None

        db_user = Mock()
        db_user.id = "user-5"
        db_user.username = "testuser5"
        db_user.email = "test5@test.com"
        db_user.name = "Test User 5"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = _NOW
        db_user.organization_memberships = [mock_membership]

        user = db_user_to_user(db_user)
        assert user.organizations[0]["role"] is None


# ---------------------------------------------------------------------------
# service.py - authenticate_user without db (lines 55-62)
# ---------------------------------------------------------------------------

class TestAuthenticateUserNoDb:
    """Test authenticate_user when db is None (backward compat path)."""

    @patch("auth_module.service.db_authenticate_user")
    @patch("database.SessionLocal")
    def test_no_db_creates_session(self, mock_session_class, mock_db_auth):
        from auth_module.service import authenticate_user

        mock_db_user = Mock()
        mock_db_user.id = "user-1"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@test.com"
        mock_db_user.name = "Test User"
        mock_db_user.is_superadmin = False
        mock_db_user.is_active = True
        mock_db_user.email_verified = True
        mock_db_user.created_at = _NOW
        mock_db_user.organization_memberships = []

        mock_db_auth.return_value = mock_db_user
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # db=None triggers the backward compat path
        result = authenticate_user("testuser", "password", db=None)

        assert result is not None
        assert result.username == "testuser"
        mock_session.close.assert_called_once()

    @patch("auth_module.service.db_authenticate_user")
    @patch("database.SessionLocal")
    def test_no_db_user_not_found(self, mock_session_class, mock_db_auth):
        from auth_module.service import authenticate_user

        mock_db_auth.return_value = None
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        result = authenticate_user("testuser", "wrongpw", db=None)

        assert result is None
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# service.py - refresh_access_token (lines 139-175)
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    """Test refresh_access_token function."""

    @patch("auth_module.service.refresh_token_service")
    def test_invalid_refresh_token(self, mock_rts):
        from auth_module.service import refresh_access_token

        mock_rts.validate_refresh_token.return_value = None
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            refresh_access_token("bad-token", db)
        assert exc_info.value.status_code == 401
        assert "Invalid refresh token" in exc_info.value.detail

    @patch("auth_module.service.refresh_token_service")
    @patch("auth_module.user_service.get_user_by_id")
    def test_user_not_found(self, mock_get_user, mock_rts):
        from auth_module.service import refresh_access_token

        mock_rt = Mock(user_id="user-1")
        mock_rts.validate_refresh_token.return_value = mock_rt
        mock_get_user.return_value = None
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            refresh_access_token("valid-token", db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    @patch("auth_module.service.refresh_token_service")
    @patch("auth_module.user_service.get_user_by_id")
    @patch("auth_module.service.create_tokens_with_refresh")
    def test_success(self, mock_create_tokens, mock_get_user, mock_rts):
        from auth_module.service import refresh_access_token

        mock_rt = Mock(user_id="user-1")
        mock_rts.validate_refresh_token.return_value = mock_rt

        mock_db_user = Mock()
        mock_db_user.id = "user-1"
        mock_db_user.username = "testuser"
        mock_db_user.email = "test@test.com"
        mock_db_user.name = "Test"
        mock_db_user.is_superadmin = False
        mock_db_user.is_active = True
        mock_db_user.email_verified = True
        mock_db_user.created_at = _NOW
        mock_db_user.organization_memberships = []
        mock_get_user.return_value = mock_db_user

        expected_token = Mock()
        mock_create_tokens.return_value = expected_token

        db = Mock()
        result = refresh_access_token("valid-token", db, user_agent="agent", ip_address="1.2.3.4")

        assert result == expected_token
        mock_create_tokens.assert_called_once()


# ---------------------------------------------------------------------------
# service.py - revoke_refresh_token (line 186)
# ---------------------------------------------------------------------------

class TestRevokeRefreshToken:
    """Test revoke_refresh_token function."""

    @patch("auth_module.service.refresh_token_service")
    def test_revoke_success(self, mock_rts):
        from auth_module.service import revoke_refresh_token

        mock_rts.revoke_refresh_token.return_value = True
        db = Mock()

        result = revoke_refresh_token("some-token", db)
        assert result is True
        mock_rts.revoke_refresh_token.assert_called_once_with(db, "some-token")

    @patch("auth_module.service.refresh_token_service")
    def test_revoke_failure(self, mock_rts):
        from auth_module.service import revoke_refresh_token

        mock_rts.revoke_refresh_token.return_value = False
        db = Mock()

        result = revoke_refresh_token("invalid-token", db)
        assert result is False


# ---------------------------------------------------------------------------
# service.py - logout_user (lines 189-194)
# ---------------------------------------------------------------------------

class TestLogoutUser:
    """Test logout_user function."""

    @patch("auth_module.service.revoke_refresh_token")
    def test_logout_with_refresh_token(self, mock_revoke):
        from auth_module.service import logout_user

        mock_revoke.return_value = True
        request = Mock()
        request.cookies = {"refresh_token": "some-refresh-token"}
        db = Mock()

        result = logout_user(request, db)
        assert result is True
        mock_revoke.assert_called_once_with("some-refresh-token", db)

    def test_logout_without_refresh_token(self):
        from auth_module.service import logout_user

        request = Mock()
        request.cookies = {}
        db = Mock()

        result = logout_user(request, db)
        assert result is True
