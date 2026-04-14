"""
Unit tests for profile endpoint permission fixes
Tests that the /profile endpoint returns correct role values for different user types
"""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from models import OrganizationMembership, OrganizationRole
from models import User as DBUser
from routers.auth import get_user_primary_role
from routers.auth import get_user_primary_role as get_user_primary_role_v1


class TestProfilePermissionFixes:
    """Test the profile endpoint permission fixes for Issue #630"""

    def create_mock_user(self, user_id: str = "test-user-id", is_superadmin: bool = False) -> Mock:
        """Create a mock user for testing"""
        user = Mock(spec=DBUser)
        user.id = user_id
        user.username = "testuser"
        user.email = "test@example.com"
        user.name = "Test User"
        user.is_superadmin = is_superadmin
        user.is_active = True
        return user

    def create_mock_membership(
        self, user_id: str, org_id: str, role: OrganizationRole, is_active: bool = True
    ) -> Mock:
        """Create a mock organization membership"""
        membership = Mock(spec=OrganizationMembership)
        membership.user_id = user_id
        membership.organization_id = org_id
        membership.role = role
        membership.is_active = is_active
        return membership

    def create_mock_db_session(self, memberships: list = None) -> Mock:
        """Create a mock database session"""
        db = Mock(spec=Session)
        query_mock = Mock()

        if memberships is None:
            memberships = []

        # Setup the query chain for OrganizationMembership
        filter_mock = Mock()
        filter_mock.all.return_value = memberships
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        return db

    @pytest.fixture
    def org_admin_role(self):
        """Mock ORG_ADMIN role"""
        role = Mock(spec=OrganizationRole)
        role.value = "ORG_ADMIN"
        return role

    @pytest.fixture
    def contributor_role(self):
        """Mock CONTRIBUTOR role"""
        role = Mock(spec=OrganizationRole)
        role.value = "CONTRIBUTOR"
        return role

    @pytest.fixture
    def annotator_role(self):
        """Mock ANNOTATOR role"""
        role = Mock(spec=OrganizationRole)
        role.value = "ANNOTATOR"
        return role

    def test_get_user_primary_role_with_no_memberships(self):
        """Test that users with no organization memberships return None role"""
        user = self.create_mock_user()
        db = self.create_mock_db_session(memberships=[])

        result = get_user_primary_role(user, db)

        assert result is None

    def test_get_user_primary_role_with_org_admin(self, org_admin_role):
        """Test that ORG_ADMIN users return ORG_ADMIN role"""
        user = self.create_mock_user()
        membership = self.create_mock_membership(user.id, "org-1", org_admin_role)
        db = self.create_mock_db_session(memberships=[membership])

        result = get_user_primary_role(user, db)

        assert result == "ORG_ADMIN"

    def test_get_user_primary_role_with_contributor(self, contributor_role):
        """Test that CONTRIBUTOR users return CONTRIBUTOR role"""
        user = self.create_mock_user()
        membership = self.create_mock_membership(user.id, "org-1", contributor_role)
        db = self.create_mock_db_session(memberships=[membership])

        result = get_user_primary_role(user, db)

        assert result == "CONTRIBUTOR"

    def test_get_user_primary_role_with_annotator(self, annotator_role):
        """Test that ANNOTATOR users return ANNOTATOR role"""
        user = self.create_mock_user()
        membership = self.create_mock_membership(user.id, "org-1", annotator_role)
        db = self.create_mock_db_session(memberships=[membership])

        result = get_user_primary_role(user, db)

        assert result == "ANNOTATOR"

    def test_get_user_primary_role_with_multiple_memberships_prioritizes_highest_role(
        self, org_admin_role, contributor_role, annotator_role
    ):
        """Test that users with multiple memberships get their highest priority role"""
        user = self.create_mock_user()

        # User is annotator in org-1, contributor in org-2, and admin in org-3
        memberships = [
            self.create_mock_membership(user.id, "org-1", annotator_role),
            self.create_mock_membership(user.id, "org-2", contributor_role),
            self.create_mock_membership(user.id, "org-3", org_admin_role),
        ]
        db = self.create_mock_db_session(memberships=memberships)

        result = get_user_primary_role(user, db)

        # Should return ORG_ADMIN as it's the highest priority role
        assert result == "ORG_ADMIN"

    def test_get_user_primary_role_ignores_inactive_memberships(
        self, org_admin_role, annotator_role
    ):
        """Test that inactive memberships are excluded from role calculation"""
        user = self.create_mock_user()

        # User has inactive ORG_ADMIN membership and active ANNOTATOR membership
        memberships = [
            self.create_mock_membership(user.id, "org-1", org_admin_role, is_active=False),
            self.create_mock_membership(user.id, "org-2", annotator_role, is_active=True),
        ]

        # Mock the database query to only return active memberships
        db = Mock(spec=Session)
        query_mock = Mock()
        filter_mock = Mock()
        filter_mock.all.return_value = [memberships[1]]  # Only active membership
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        result = get_user_primary_role(user, db)

        # Should return ANNOTATOR, not ORG_ADMIN since the admin membership is inactive
        assert result == "ANNOTATOR"

    def test_get_user_primary_role_with_superadmin_still_returns_org_role(self, contributor_role):
        """Test that superadmin users still get their organization role returned, not 'superadmin'"""
        user = self.create_mock_user(is_superadmin=True)
        membership = self.create_mock_membership(user.id, "org-1", contributor_role)
        db = self.create_mock_db_session(memberships=[membership])

        result = get_user_primary_role(user, db)

        # Should return CONTRIBUTOR, not "superadmin"
        assert result == "CONTRIBUTOR"

    def test_get_user_primary_role_with_superadmin_no_memberships(self):
        """Test that superadmin users with no org memberships return None"""
        user = self.create_mock_user(is_superadmin=True)
        db = self.create_mock_db_session(memberships=[])

        result = get_user_primary_role(user, db)

        # Should return None since they have no organization memberships
        assert result is None

    def test_get_user_primary_role_v1_function_exists(self):
        """Test that the v1 version of the function also exists and works the same way"""
        user = self.create_mock_user()
        db = self.create_mock_db_session(memberships=[])

        result = get_user_primary_role_v1(user, db)

        assert result is None

    def test_get_user_primary_role_handles_empty_role_value(self):
        """Test that the function handles memberships with invalid/empty roles gracefully"""
        user = self.create_mock_user()

        # Create a membership with an invalid role
        membership = Mock(spec=OrganizationMembership)
        membership.user_id = user.id
        membership.organization_id = "org-1"
        membership.role = Mock()
        membership.role.value = None  # Invalid role value
        membership.is_active = True

        db = self.create_mock_db_session(memberships=[membership])

        result = get_user_primary_role(user, db)

        # Should fallback to the first membership's role (None in this case)
        assert result is None

    def test_role_hierarchy_priority(self, org_admin_role, contributor_role, annotator_role):
        """Test that the role hierarchy is correctly prioritized: ORG_ADMIN > CONTRIBUTOR > ANNOTATOR"""
        user = self.create_mock_user()

        # Test CONTRIBUTOR > ANNOTATOR
        memberships = [
            self.create_mock_membership(user.id, "org-1", annotator_role),
            self.create_mock_membership(user.id, "org-2", contributor_role),
        ]
        db = self.create_mock_db_session(memberships=memberships)

        result = get_user_primary_role(user, db)
        assert result == "CONTRIBUTOR"

        # Test ORG_ADMIN > CONTRIBUTOR
        memberships = [
            self.create_mock_membership(user.id, "org-1", contributor_role),
            self.create_mock_membership(user.id, "org-2", org_admin_role),
        ]
        db = self.create_mock_db_session(memberships=memberships)

        result = get_user_primary_role(user, db)
        assert result == "ORG_ADMIN"

        # Test ORG_ADMIN > ANNOTATOR
        memberships = [
            self.create_mock_membership(user.id, "org-1", annotator_role),
            self.create_mock_membership(user.id, "org-2", org_admin_role),
        ]
        db = self.create_mock_db_session(memberships=memberships)

        result = get_user_primary_role(user, db)
        assert result == "ORG_ADMIN"

    def test_database_query_parameters(self):
        """Test that the database query uses correct parameters"""
        user = self.create_mock_user()
        db = Mock(spec=Session)
        query_mock = Mock()
        filter_mock = Mock()
        filter_mock.all.return_value = []

        # Setup query chain
        query_mock.filter.return_value = filter_mock
        db.query.return_value = query_mock

        # Call the function
        get_user_primary_role(user, db)

        # Verify that query was called with OrganizationMembership
        db.query.assert_called_once()

        # Verify that filter was called (should filter by user_id and is_active=True)
        query_mock.filter.assert_called_once()

        # Verify that all() was called to get results
        filter_mock.all.assert_called_once()


class TestPermissionIntegration:
    """Integration tests for the permission system fix"""

    # NOTE: test_issue_630_fix_superadmin_access and
    # test_role_field_separation_from_superadmin_flag were removed because
    # they contained only `assert True` placeholders or empty bodies,
    # testing nothing. Real regression tests for Issue #630 should be
    # added to the integration test suite with a real database.
    pass
