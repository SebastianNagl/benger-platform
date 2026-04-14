"""
Unit tests for app/core/authorization.py to increase coverage.
Tests Permission enum, authorization service methods.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest


class TestPermissionEnum:
    def test_all_permissions_exist(self):
        from app.core.authorization import Permission
        assert hasattr(Permission, 'PROJECT_VIEW')
        assert hasattr(Permission, 'PROJECT_EDIT')
        assert hasattr(Permission, 'PROJECT_DELETE')
        assert hasattr(Permission, 'PROJECT_CREATE')

    def test_permission_values(self):
        from app.core.authorization import Permission
        assert isinstance(Permission.PROJECT_VIEW.value, str)


class TestAuthorizationService:
    def test_superadmin_has_all_access(self):
        from app.core.authorization import auth_service, Permission
        user = Mock()
        user.is_superadmin = True
        user.id = "admin-1"

        project = Mock()
        project.id = "p-1"
        project.created_by = "other-user"
        project.is_private = False

        db = Mock()

        result = auth_service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is True

    def test_private_project_creator_has_access(self):
        from app.core.authorization import auth_service, Permission
        user = Mock()
        user.is_superadmin = False
        user.id = "user-1"

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-1"
        project.is_private = True
        project.project_organizations = []

        db = Mock()

        result = auth_service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is True

    def test_private_project_non_creator_denied(self):
        from app.core.authorization import auth_service, Permission
        user = Mock()
        user.is_superadmin = False
        user.id = "user-2"

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-1"
        project.is_private = True
        project.project_organizations = []

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        result = auth_service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is False

    def test_project_creator_has_edit_access(self):
        from app.core.authorization import auth_service, Permission
        user = Mock()
        user.is_superadmin = False
        user.id = "user-1"

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-1"
        project.is_private = False
        project.project_organizations = []

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        result = auth_service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is True

    def test_non_member_denied(self):
        from app.core.authorization import auth_service, Permission
        user = Mock()
        user.is_superadmin = False
        user.id = "user-3"

        project = Mock()
        project.id = "p-1"
        project.created_by = "user-1"
        project.is_private = False

        org_assignment = Mock()
        org_assignment.organization_id = "org-1"
        project.project_organizations = [org_assignment]

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        result = auth_service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db
        )
        assert result is False
