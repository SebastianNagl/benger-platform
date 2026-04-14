"""
Extended unit tests for AuthorizationService covering all role-permission
combinations and context-aware access checking.
"""

from unittest.mock import Mock, patch, MagicMock

import pytest

from app.core.authorization import (
    AuthorizationService,
    Permission,
    auth_service,
)


class TestCheckOrgRolePermission:
    """Tests for _check_org_role_permission covering all roles and permissions."""

    def setup_method(self):
        self.service = AuthorizationService()

    # org_admin role
    def test_org_admin_project_view(self):
        assert self.service._check_org_role_permission("org_admin", Permission.PROJECT_VIEW)

    def test_org_admin_project_edit(self):
        assert self.service._check_org_role_permission("org_admin", Permission.PROJECT_EDIT)

    def test_org_admin_project_delete(self):
        assert self.service._check_org_role_permission("org_admin", Permission.PROJECT_DELETE)

    def test_org_admin_project_create(self):
        assert self.service._check_org_role_permission("org_admin", Permission.PROJECT_CREATE)

    def test_org_admin_org_edit(self):
        assert self.service._check_org_role_permission("org_admin", Permission.ORG_EDIT)

    def test_org_admin_org_manage_members(self):
        assert self.service._check_org_role_permission("org_admin", Permission.ORG_MANAGE_MEMBERS)

    def test_org_admin_no_admin_view(self):
        assert not self.service._check_org_role_permission("org_admin", Permission.ADMIN_VIEW)

    def test_org_admin_no_feature_flag(self):
        assert not self.service._check_org_role_permission("org_admin", Permission.FEATURE_FLAG_MANAGE)

    def test_org_admin_no_org_delete(self):
        assert not self.service._check_org_role_permission("org_admin", Permission.ORG_DELETE)

    def test_org_admin_no_org_create(self):
        assert not self.service._check_org_role_permission("org_admin", Permission.ORG_CREATE)

    def test_org_admin_all_task_perms(self):
        for p in [Permission.TASK_VIEW, Permission.TASK_EDIT, Permission.TASK_DELETE, Permission.TASK_CREATE]:
            assert self.service._check_org_role_permission("org_admin", p)

    def test_org_admin_all_annotation_perms(self):
        for p in [Permission.ANNOTATION_VIEW, Permission.ANNOTATION_EDIT, Permission.ANNOTATION_DELETE, Permission.ANNOTATION_CREATE]:
            assert self.service._check_org_role_permission("org_admin", p)

    def test_org_admin_all_generation_perms(self):
        for p in [Permission.GENERATION_VIEW, Permission.GENERATION_EDIT, Permission.GENERATION_DELETE, Permission.GENERATION_CREATE]:
            assert self.service._check_org_role_permission("org_admin", p)

    # contributor role
    def test_contributor_project_view(self):
        assert self.service._check_org_role_permission("contributor", Permission.PROJECT_VIEW)

    def test_contributor_project_edit(self):
        assert self.service._check_org_role_permission("contributor", Permission.PROJECT_EDIT)

    def test_contributor_project_create(self):
        assert self.service._check_org_role_permission("contributor", Permission.PROJECT_CREATE)

    def test_contributor_no_project_delete(self):
        assert not self.service._check_org_role_permission("contributor", Permission.PROJECT_DELETE)

    def test_contributor_task_crud(self):
        assert self.service._check_org_role_permission("contributor", Permission.TASK_VIEW)
        assert self.service._check_org_role_permission("contributor", Permission.TASK_EDIT)
        assert self.service._check_org_role_permission("contributor", Permission.TASK_CREATE)
        assert self.service._check_org_role_permission("contributor", Permission.TASK_DELETE)

    def test_contributor_annotation_crud(self):
        assert self.service._check_org_role_permission("contributor", Permission.ANNOTATION_VIEW)
        assert self.service._check_org_role_permission("contributor", Permission.ANNOTATION_EDIT)
        assert self.service._check_org_role_permission("contributor", Permission.ANNOTATION_CREATE)
        assert self.service._check_org_role_permission("contributor", Permission.ANNOTATION_DELETE)

    def test_contributor_generation_crud(self):
        assert self.service._check_org_role_permission("contributor", Permission.GENERATION_VIEW)
        assert self.service._check_org_role_permission("contributor", Permission.GENERATION_EDIT)
        assert self.service._check_org_role_permission("contributor", Permission.GENERATION_CREATE)
        assert self.service._check_org_role_permission("contributor", Permission.GENERATION_DELETE)

    def test_contributor_org_view_only(self):
        assert self.service._check_org_role_permission("contributor", Permission.ORG_VIEW)
        assert not self.service._check_org_role_permission("contributor", Permission.ORG_EDIT)
        assert not self.service._check_org_role_permission("contributor", Permission.ORG_MANAGE_MEMBERS)

    # annotator role
    def test_annotator_project_view(self):
        assert self.service._check_org_role_permission("annotator", Permission.PROJECT_VIEW)

    def test_annotator_no_project_edit(self):
        assert not self.service._check_org_role_permission("annotator", Permission.PROJECT_EDIT)

    def test_annotator_no_project_create(self):
        assert not self.service._check_org_role_permission("annotator", Permission.PROJECT_CREATE)

    def test_annotator_task_view_only(self):
        assert self.service._check_org_role_permission("annotator", Permission.TASK_VIEW)
        assert not self.service._check_org_role_permission("annotator", Permission.TASK_EDIT)

    def test_annotator_annotation_view_edit_create(self):
        assert self.service._check_org_role_permission("annotator", Permission.ANNOTATION_VIEW)
        assert self.service._check_org_role_permission("annotator", Permission.ANNOTATION_EDIT)
        assert self.service._check_org_role_permission("annotator", Permission.ANNOTATION_CREATE)
        assert not self.service._check_org_role_permission("annotator", Permission.ANNOTATION_DELETE)

    def test_annotator_no_generation_perms(self):
        assert not self.service._check_org_role_permission("annotator", Permission.GENERATION_VIEW)
        assert not self.service._check_org_role_permission("annotator", Permission.GENERATION_EDIT)

    def test_annotator_org_view_only(self):
        assert self.service._check_org_role_permission("annotator", Permission.ORG_VIEW)
        assert not self.service._check_org_role_permission("annotator", Permission.ORG_EDIT)

    # user role
    def test_user_view_only_perms(self):
        assert self.service._check_org_role_permission("user", Permission.PROJECT_VIEW)
        assert self.service._check_org_role_permission("user", Permission.TASK_VIEW)
        assert self.service._check_org_role_permission("user", Permission.ANNOTATION_VIEW)
        assert self.service._check_org_role_permission("user", Permission.GENERATION_VIEW)
        assert self.service._check_org_role_permission("user", Permission.ORG_VIEW)

    def test_user_no_edit_perms(self):
        assert not self.service._check_org_role_permission("user", Permission.PROJECT_EDIT)
        assert not self.service._check_org_role_permission("user", Permission.TASK_EDIT)
        assert not self.service._check_org_role_permission("user", Permission.ANNOTATION_EDIT)
        assert not self.service._check_org_role_permission("user", Permission.GENERATION_EDIT)

    # unknown role
    def test_unknown_role_no_perms(self):
        assert not self.service._check_org_role_permission("unknown", Permission.PROJECT_VIEW)

    # enum role value
    def test_enum_role_value(self):
        role_mock = Mock()
        role_mock.value = "org_admin"
        assert self.service._check_org_role_permission(role_mock, Permission.PROJECT_VIEW)

    def test_enum_role_uppercase(self):
        role_mock = Mock()
        role_mock.value = "ORG_ADMIN"
        assert self.service._check_org_role_permission(role_mock, Permission.PROJECT_VIEW)


class TestCheckProjectAccessSimple:
    """Tests for check_project_access that don't require complex DB mocking."""

    def setup_method(self):
        self.service = AuthorizationService()

    def test_superadmin_always_has_access(self):
        user = Mock(is_superadmin=True)
        project = Mock()
        db = Mock()
        assert self.service.check_project_access(user, project, Permission.PROJECT_VIEW, db)

    def test_private_context_creator_has_access(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-1")
        db = Mock()
        assert self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context="private"
        )

    def test_private_context_non_creator_denied(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-2")
        db = Mock()
        assert not self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context="private"
        )

    def test_private_context_non_private_project_denied(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, created_by="user-1")
        db = Mock()
        assert not self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context="private"
        )

    def test_legacy_mode_private_project_creator(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-1")
        db = Mock()
        assert self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context=None
        )

    def test_legacy_mode_private_project_non_creator(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=True, created_by="user-2")
        db = Mock()
        assert not self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context=None
        )

    def test_legacy_mode_creator_view(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, id="proj-1", created_by="user-1")
        db = Mock()
        assert self.service.check_project_access(
            user, project, Permission.PROJECT_VIEW, db, org_context=None
        )

    def test_legacy_mode_creator_edit(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, id="proj-1", created_by="user-1")
        db = Mock()
        assert self.service.check_project_access(
            user, project, Permission.PROJECT_EDIT, db, org_context=None
        )

    def test_legacy_mode_creator_delete(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = Mock(is_private=False, id="proj-1", created_by="user-1")
        db = Mock()
        assert self.service.check_project_access(
            user, project, Permission.PROJECT_DELETE, db, org_context=None
        )


class TestCheckOrganizationAccess:
    """Tests for check_organization_access."""

    def setup_method(self):
        self.service = AuthorizationService()

    def test_superadmin_always_has_access(self):
        user = Mock(is_superadmin=True)
        db = Mock()
        assert self.service.check_organization_access(
            user, "org-1", Permission.ORG_VIEW, db
        )

    @patch("app.core.authorization.AuthorizationService._get_user_org_memberships")
    def test_member_with_permission(self, mock_get_memberships):
        user = Mock(is_superadmin=False)
        db = Mock()
        membership = Mock(organization_id="org-1", role="org_admin")
        mock_get_memberships.return_value = [membership]

        assert self.service.check_organization_access(
            user, "org-1", Permission.ORG_EDIT, db
        )

    @patch("app.core.authorization.AuthorizationService._get_user_org_memberships")
    def test_non_member_denied(self, mock_get_memberships):
        user = Mock(is_superadmin=False)
        db = Mock()
        mock_get_memberships.return_value = []

        assert not self.service.check_organization_access(
            user, "org-1", Permission.ORG_VIEW, db
        )

    @patch("app.core.authorization.AuthorizationService._get_user_org_memberships")
    def test_member_without_permission(self, mock_get_memberships):
        user = Mock(is_superadmin=False)
        db = Mock()
        membership = Mock(organization_id="org-1", role="annotator")
        mock_get_memberships.return_value = [membership]

        assert not self.service.check_organization_access(
            user, "org-1", Permission.ORG_EDIT, db
        )

    @patch("app.core.authorization.AuthorizationService._get_user_org_memberships")
    def test_member_different_org(self, mock_get_memberships):
        user = Mock(is_superadmin=False)
        db = Mock()
        membership = Mock(organization_id="org-2", role="org_admin")
        mock_get_memberships.return_value = [membership]

        assert not self.service.check_organization_access(
            user, "org-1", Permission.ORG_VIEW, db
        )


class TestConvenienceMethods:
    """Tests for can_edit_project, can_delete_project, filter_accessible_projects."""

    def setup_method(self):
        self.service = AuthorizationService()

    def test_can_edit_project_superadmin(self):
        user = Mock(is_superadmin=True)
        project = Mock()
        db = Mock()
        assert self.service.can_edit_project(user, project, db)

    def test_can_delete_project_superadmin(self):
        user = Mock(is_superadmin=True)
        project = Mock()
        db = Mock()
        assert self.service.can_delete_project(user, project, db)

    def test_filter_accessible_projects_superadmin(self):
        user = Mock(is_superadmin=True)
        projects = [Mock(), Mock()]
        db = Mock()
        result = self.service.filter_accessible_projects(
            user, projects, Permission.PROJECT_VIEW, db
        )
        assert len(result) == 2

    @patch.object(AuthorizationService, "check_project_access")
    def test_filter_accessible_projects_filters_correctly(self, mock_check):
        user = Mock(is_superadmin=False)
        p1 = Mock(id="1")
        p2 = Mock(id="2")
        p3 = Mock(id="3")
        db = Mock()
        mock_check.side_effect = [True, False, True]

        result = self.service.filter_accessible_projects(
            user, [p1, p2, p3], Permission.PROJECT_VIEW, db
        )
        assert result == [p1, p3]

    @patch.object(AuthorizationService, "check_project_access")
    def test_filter_empty_list(self, mock_check):
        user = Mock(is_superadmin=False)
        db = Mock()
        result = self.service.filter_accessible_projects(
            user, [], Permission.PROJECT_VIEW, db
        )
        assert result == []


class TestGetUserOrgMemberships:
    """Tests for _get_user_org_memberships."""

    def setup_method(self):
        self.service = AuthorizationService()

    def test_db_user_with_memberships(self):
        user = Mock()
        user.organization_memberships = [Mock(organization_id="org-1")]
        db = Mock()
        result = self.service._get_user_org_memberships(user, db)
        assert len(result) == 1

    def test_db_user_with_none_memberships_queries_db(self):
        user = Mock(spec=["id"])
        user.organization_memberships = None
        db = Mock()

        with patch("routers.projects.helpers.get_user_with_memberships") as mock_get:
            mock_db_user = Mock()
            mock_db_user.organization_memberships = [Mock(organization_id="org-1")]
            mock_get.return_value = mock_db_user

            result = self.service._get_user_org_memberships(user, db)
            assert len(result) == 1

    def test_db_user_with_none_memberships_and_no_db_user(self):
        user = Mock(spec=["id"])
        user.organization_memberships = None
        db = Mock()

        with patch("routers.projects.helpers.get_user_with_memberships") as mock_get:
            mock_get.return_value = None

            result = self.service._get_user_org_memberships(user, db)
            assert result == []

    def test_db_user_with_empty_memberships_list(self):
        user = Mock()
        user.organization_memberships = []
        db = Mock()
        result = self.service._get_user_org_memberships(user, db)
        assert result == []


class TestPermissionEnum:
    """Tests for the Permission enum."""

    def test_all_permissions_exist(self):
        assert Permission.PROJECT_VIEW.value == "project:view"
        assert Permission.PROJECT_EDIT.value == "project:edit"
        assert Permission.PROJECT_DELETE.value == "project:delete"
        assert Permission.PROJECT_CREATE.value == "project:create"
        assert Permission.TASK_VIEW.value == "task:view"
        assert Permission.ANNOTATION_VIEW.value == "annotation:view"
        assert Permission.GENERATION_VIEW.value == "generation:view"
        assert Permission.ORG_VIEW.value == "organization:view"
        assert Permission.ORG_EDIT.value == "organization:edit"
        assert Permission.ORG_DELETE.value == "organization:delete"
        assert Permission.ORG_CREATE.value == "organization:create"
        assert Permission.ORG_MANAGE_MEMBERS.value == "organization:manage_members"
        assert Permission.ADMIN_VIEW.value == "admin:view"
        assert Permission.ADMIN_EDIT.value == "admin:edit"
        assert Permission.FEATURE_FLAG_MANAGE.value == "feature_flag:manage"

    def test_permission_count(self):
        """Ensure all expected permissions are defined."""
        assert len(Permission) == 24
