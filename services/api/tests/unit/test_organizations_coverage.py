"""
Unit tests for routers/organizations.py to increase branch coverage.
Covers permission check helper functions.
"""

from unittest.mock import Mock

from sqlalchemy.orm import Session

from models import OrganizationMembership, User
from routers.organizations import can_manage_organization, can_create_organization


class TestCanManageOrganization:
    def test_none_user(self):
        assert can_manage_organization(None, "org-1", Mock()) == False  # noqa: E712

    def test_superadmin(self):
        user = Mock(spec=User)
        user.is_superadmin = True
        assert can_manage_organization(user, "org-1", Mock()) == True  # noqa: E712

    def test_org_admin_found(self):
        user = Mock(spec=User)
        user.id = "u1"
        user.is_superadmin = False
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = Mock(spec=OrganizationMembership)
        mock_db.query.return_value = mock_q
        assert can_manage_organization(user, "org-1", mock_db) == True  # noqa: E712

    def test_no_membership(self):
        user = Mock(spec=User)
        user.id = "u1"
        user.is_superadmin = False
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q
        assert can_manage_organization(user, "org-1", mock_db) == False  # noqa: E712


class TestCanCreateOrganization:
    def test_none_user(self):
        assert can_create_organization(None, Mock()) == False  # noqa: E712

    def test_superadmin(self):
        user = Mock(spec=User)
        user.is_superadmin = True
        assert can_create_organization(user, Mock()) == True  # noqa: E712

    def test_admin_of_any_org(self):
        user = Mock(spec=User)
        user.id = "u1"
        user.is_superadmin = False
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = Mock(spec=OrganizationMembership)
        mock_db.query.return_value = mock_q
        assert can_create_organization(user, mock_db) == True  # noqa: E712

    def test_not_admin(self):
        user = Mock(spec=User)
        user.id = "u1"
        user.is_superadmin = False
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q
        assert can_create_organization(user, mock_db) == False  # noqa: E712
