"""
Unit tests for the authorization service.

Targets: app/core/authorization.py — 38.46% coverage (71 uncovered lines)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestCanManageOrganization:
    """Tests for can_manage_organization helper in organizations router."""

    def test_none_user_returns_false(self):
        from routers.organizations import can_manage_organization
        db = MagicMock()
        assert can_manage_organization(None, "org-1", db) is False

    def test_superadmin_returns_true(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=True)
        db = MagicMock()
        assert can_manage_organization(user, "org-1", db) is True

    def test_org_admin_returns_true(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        # Mock the query chain to return a membership
        mock_membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = mock_membership
        assert can_manage_organization(user, "org-1", db) is True

    def test_non_admin_returns_false(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) is False


class TestCanCreateOrganization:
    """Tests for can_create_organization helper."""

    def test_none_user_returns_false(self):
        from routers.organizations import can_create_organization
        db = MagicMock()
        assert can_create_organization(None, db) is False

    def test_superadmin_returns_true(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=True)
        db = MagicMock()
        assert can_create_organization(user, db) is True

    def test_regular_user_with_admin_membership(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        # User is admin of an organization
        db.query.return_value.filter.return_value.first.return_value = Mock()
        assert can_create_organization(user, db) is True

    def test_regular_user_without_admin_membership(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_create_organization(user, db) is False


class TestReviewPermission:
    """Tests for _check_review_permission in reviews router."""

    def test_superadmin_allowed(self):
        from routers.projects.reviews import _check_review_permission
        user = Mock(is_superadmin=True)
        project = Mock()
        db = MagicMock()
        # Should not raise
        _check_review_permission(user, project, db)

    def test_non_member_denied(self):
        from routers.projects.reviews import _check_review_permission
        user = Mock(is_superadmin=False, id="user-1")
        # No role attribute
        delattr(user, 'role') if hasattr(user, 'role') else None
        project = Mock(id="proj-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception):  # HTTPException
            _check_review_permission(user, project, db)
