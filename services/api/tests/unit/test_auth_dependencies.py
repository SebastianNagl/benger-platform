"""
Unit tests for auth_module/dependencies.py covering require_user,
get_current_user, require_superadmin, require_org_admin, require_org_contributor.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from auth_module.dependencies import (
    get_current_user,
    require_superadmin,
    require_org_admin,
    require_org_contributor,
    optional_user,
)
from datetime import datetime, timezone

from auth_module.models import User

_NOW = datetime.now(timezone.utc)


class TestGetCurrentUser:
    """Tests for get_current_user (optional auth)."""

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    @patch("auth_module.dependencies.db_user_to_user")
    def test_valid_token_returns_user(self, mock_convert, mock_get_user, mock_verify):
        mock_verify.return_value = {"user_id": "user-1"}
        mock_db_user = Mock()
        mock_get_user.return_value = mock_db_user
        mock_convert.return_value = User(
            id="user-1", username="test", email="t@t.com", name="Test",
            is_superadmin=False, is_active=True, email_verified=True, use_pseudonym=False,
            organizations=[], created_at=_NOW,
        )

        request = Mock()
        db = Mock()
        result = get_current_user(request, db)
        assert result is not None
        assert result.id == "user-1"

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    def test_no_user_id_in_payload(self, mock_verify):
        mock_verify.return_value = {"sub": "something"}  # no user_id
        request = Mock()
        db = Mock()
        result = get_current_user(request, db)
        assert result is None

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    @patch("auth_module.dependencies.get_user_by_id")
    def test_user_not_found_in_db(self, mock_get_user, mock_verify):
        mock_verify.return_value = {"user_id": "nonexistent"}
        mock_get_user.return_value = None
        request = Mock()
        db = Mock()
        result = get_current_user(request, db)
        assert result is None

    @patch("auth_module.dependencies.verify_token_cookie_or_header")
    def test_invalid_token_returns_none(self, mock_verify):
        mock_verify.side_effect = HTTPException(status_code=401, detail="Invalid")
        request = Mock()
        db = Mock()
        result = get_current_user(request, db)
        assert result is None


class TestRequireSuperadmin:
    """Tests for require_superadmin dependency."""

    def test_superadmin_passes(self):
        user = User(
            id="admin", username="admin", email="a@t.com", name="Admin",
            is_superadmin=True, is_active=True, email_verified=True,
            use_pseudonym=False, organizations=[], created_at=_NOW,
        )
        result = require_superadmin(user)
        assert result.id == "admin"

    def test_non_superadmin_raises(self):
        user = User(
            id="user", username="user", email="u@t.com", name="User",
            is_superadmin=False, is_active=True, email_verified=True,
            use_pseudonym=False, organizations=[], created_at=_NOW,
        )
        with pytest.raises(HTTPException) as exc_info:
            require_superadmin(user)
        assert exc_info.value.status_code == 403


class TestOptionalUser:
    """Tests for optional_user (alias for get_current_user)."""

    @patch("auth_module.dependencies.get_current_user")
    def test_delegates_to_get_current_user(self, mock_get):
        mock_get.return_value = None
        request = Mock()
        db = Mock()
        result = optional_user(request, db)
        mock_get.assert_called_once_with(request, db)


class TestRequireOrgAdmin:
    """Tests for require_org_admin factory function."""

    def test_returns_callable(self):
        checker = require_org_admin("org-123")
        assert callable(checker)

    def test_returns_callable_without_org_id(self):
        checker = require_org_admin()
        assert callable(checker)


class TestRequireOrgContributor:
    """Tests for require_org_contributor factory function."""

    def test_returns_callable(self):
        checker = require_org_contributor("org-123")
        assert callable(checker)

    def test_returns_callable_without_org_id(self):
        checker = require_org_contributor()
        assert callable(checker)
