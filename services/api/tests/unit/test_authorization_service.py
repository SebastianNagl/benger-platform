"""
Unit tests for the authorization service.

Targets: app/core/authorization.py — 38.46% coverage (71 uncovered lines)
"""

from unittest.mock import MagicMock, Mock


class TestCanManageOrganization:
    """Tests for can_manage_organization helper in organizations router."""

    def test_none_user_returns_false(self):
        from routers.organizations import can_manage_organization
        db = MagicMock()
        assert can_manage_organization(None, "org-1", db) == False  # noqa: E712

    def test_superadmin_returns_true(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=True)
        db = MagicMock()
        assert can_manage_organization(user, "org-1", db) == True  # noqa: E712

    def test_org_admin_returns_true(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        # Mock the query chain to return a membership
        mock_membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = mock_membership
        assert can_manage_organization(user, "org-1", db) == True  # noqa: E712

    def test_non_admin_returns_false(self):
        from routers.organizations import can_manage_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) == False  # noqa: E712


class TestCanCreateOrganization:
    """Tests for can_create_organization helper."""

    def test_none_user_returns_false(self):
        from routers.organizations import can_create_organization
        db = MagicMock()
        assert can_create_organization(None, db) == False  # noqa: E712

    def test_superadmin_returns_true(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=True)
        db = MagicMock()
        assert can_create_organization(user, db) == True  # noqa: E712

    def test_regular_user_with_admin_membership(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        # User is admin of an organization
        db.query.return_value.filter.return_value.first.return_value = Mock()
        assert can_create_organization(user, db) == True  # noqa: E712

    def test_regular_user_without_admin_membership(self):
        from routers.organizations import can_create_organization
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_create_organization(user, db) == False  # noqa: E712


class TestDecideProjectAccessUnattachedProjectUnderOrgContext:
    """A project attached to NO organization is private whatever
    ``X-Organization-Context`` says.

    Before this rule the context-aware branch fell through to
    ``org_context not in project_org_ids`` and 403ed the creator of an
    unattached project as soon as the client sent any org context — the
    extended task-rubric read endpoints re-implemented creator-first access
    to work around it. Exercises the pure decision shared by the sync and
    async lanes.
    """

    def setup_method(self):
        from app.core.authorization import AuthorizationService

        self.service = AuthorizationService()

    @staticmethod
    def _project(created_by: str):
        return Mock(deleted_at=None, is_public=False, is_private=False, created_by=created_by)

    def _decide(self, user, project, *, org_context, project_org_ids, memberships=()):
        from app.core.authorization import Permission

        return self.service._decide_project_access(
            user, project, Permission.PROJECT_VIEW, org_context, list(project_org_ids), list(memberships),
        )

    def test_creator_keeps_access_under_a_foreign_org_context(self):
        user = Mock(is_superadmin=False, id="user-1")
        project = self._project("user-1")
        assert self._decide(user, project, org_context="org-foreign", project_org_ids=[]) is True

    def test_creator_keeps_edit_and_delete_too(self):
        from app.core.authorization import Permission

        user = Mock(is_superadmin=False, id="user-1")
        project = self._project("user-1")
        for perm in (Permission.PROJECT_EDIT, Permission.PROJECT_DELETE):
            assert self.service._decide_project_access(
                user, project, perm, "org-foreign", [], []
            ) is True

    def test_stranger_denied_even_as_member_of_the_context_org(self):
        user = Mock(is_superadmin=False, id="user-2")
        project = self._project("user-1")
        membership = Mock(organization_id="org-foreign", is_active=True, role="ORG_ADMIN")
        assert self._decide(
            user, project, org_context="org-foreign", project_org_ids=[], memberships=[membership],
        ) is False

    def test_org_attached_project_unchanged_foreign_context_still_denied(self):
        # The new rule fires only for unattached projects: an org-attached
        # project keeps rejecting a context that is not one of its orgs,
        # creator or not.
        user = Mock(is_superadmin=False, id="user-1")
        project = self._project("user-1")
        assert self._decide(
            user, project, org_context="org-foreign", project_org_ids=["org-a"],
        ) is False

    def test_org_attached_project_unchanged_member_in_matching_context_allowed(self):
        user = Mock(is_superadmin=False, id="user-2")
        project = self._project("user-1")
        membership = Mock(organization_id="org-a", is_active=True, role="contributor")
        assert self._decide(
            user, project, org_context="org-a", project_org_ids=["org-a"], memberships=[membership],
        ) is True

    def test_private_context_still_creator_only(self):
        # The explicit "private" case above the new rule is untouched.
        user = Mock(is_superadmin=False, id="user-2")
        project = self._project("user-1")
        assert self._decide(user, project, org_context="private", project_org_ids=[]) is False
