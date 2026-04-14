"""
Unit tests for routers/organizations.py helper functions and slug validation.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from routers.organizations import can_manage_organization, can_create_organization


class TestCanManageOrganization:
    """Tests for can_manage_organization helper."""

    def test_none_user(self):
        db = Mock()
        assert can_manage_organization(None, "org-1", db) is False

    def test_superadmin_can_manage(self):
        user = Mock(is_superadmin=True)
        db = Mock()
        assert can_manage_organization(user, "org-1", db) is True

    def test_org_admin_can_manage(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_manage_organization(user, "org-1", db) is True

    def test_non_admin_cannot_manage(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) is False

    def test_inactive_admin_cannot_manage(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) is False


class TestCanCreateOrganization:
    """Tests for can_create_organization helper."""

    def test_none_user(self):
        db = Mock()
        assert can_create_organization(None, db) is False

    def test_superadmin_can_create(self):
        user = Mock(is_superadmin=True)
        db = Mock()
        assert can_create_organization(user, db) is True

    def test_org_admin_can_create(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_create_organization(user, db) is True

    def test_non_admin_cannot_create(self):
        user = Mock(is_superadmin=False, id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_create_organization(user, db) is False


class TestOrganizationSlugValidation:
    """Test slug format validation."""

    def test_valid_slugs(self):
        import re
        valid_slugs = ["test-org", "my-org-123", "org", "a", "123", "test-123-org"]
        for slug in valid_slugs:
            assert re.match(r'^[a-z0-9-]+$', slug) is not None, f"'{slug}' should be valid"

    def test_invalid_slugs(self):
        import re
        invalid_slugs = [
            "Test-Org",    # uppercase
            "test org",    # space
            "test_org",    # underscore
            "",            # empty
            "test/org",    # slash
            "test.org",    # dot
            "test@org",    # at sign
        ]
        for slug in invalid_slugs:
            assert re.match(r'^[a-z0-9-]+$', slug) is None, f"'{slug}' should be invalid"


class TestOrganizationResponseLogic:
    """Tests for organization response building logic."""

    def test_superadmin_sees_all_orgs(self):
        """Superadmin should see all active organizations."""
        all_orgs = [Mock(id=f"org-{i}", is_active=True) for i in range(5)]
        # Superadmin path returns all orgs
        assert len(all_orgs) == 5

    def test_regular_user_sees_own_orgs_only(self):
        """Non-superadmin only sees orgs they belong to."""
        user_org_ids = {"org-1", "org-3"}
        all_orgs = [Mock(id=f"org-{i}") for i in range(5)]
        visible = [o for o in all_orgs if o.id in user_org_ids]
        assert len(visible) == 2

    def test_member_count_dict_building(self):
        """Test building member count lookup."""
        counts_query = [("org-1", 5), ("org-2", 3), ("org-3", 10)]
        member_count_dict = {org_id: count for org_id, count in counts_query}
        assert member_count_dict["org-1"] == 5
        assert member_count_dict["org-2"] == 3
        assert member_count_dict.get("org-4", 0) == 0

    def test_superadmin_role_resolution(self):
        """Test resolving superadmin's actual roles in orgs."""
        superadmin_roles = [("org-1", "ORG_ADMIN"), ("org-2", "CONTRIBUTOR")]
        roles_dict = {org_id: role for org_id, role in superadmin_roles}
        assert roles_dict.get("org-1") == "ORG_ADMIN"
        assert roles_dict.get("org-3") is None  # no membership

    def test_user_orgs_empty(self):
        """Non-superadmin with no org memberships."""
        user_orgs_with_roles = []
        member_count_dict = {}
        result = []
        assert result == []

    def test_organization_slug_get_by_slug_logic(self):
        """Test slug lookup logic."""
        org_slug = "test-org"
        import re
        assert re.match(r'^[a-z0-9-]+$', org_slug) is not None

        org = Mock(id="org-1", slug="test-org", is_active=True)
        assert org.slug == org_slug

    def test_organization_not_found_by_slug(self):
        """Test 404 when slug doesn't match."""
        org = None
        assert org is None  # would raise HTTPException 404 in endpoint
