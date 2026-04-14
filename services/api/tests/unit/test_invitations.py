"""
Unit tests for the invitation system
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

# send_invitation_email function no longer exported from invitations router
from models import Invitation, Organization, OrganizationRole, User
from routers.invitations import (
    accept_invitation,
    create_invitation,
    generate_invitation_token,
    list_organization_invitations,
)


class TestInvitationHelpers:
    """Test helper functions"""

    def test_generate_invitation_token(self):
        """Test token generation"""
        token1 = generate_invitation_token()
        token2 = generate_invitation_token()

        assert token1 != token2
        assert len(token1) > 20
        assert isinstance(token1, str)


# TestInvitationEmail class removed - send_invitation_email is internal to invitations router
# and should be tested through the create_invitation endpoint instead


class TestCreateInvitation:
    """Test invitation creation endpoint"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = Mock(spec=Session)
        db.query = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.refresh = Mock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Mock current user"""
        user = Mock(spec=User)
        user.id = "user-123"
        user.name = "Admin User"
        user.role = is_superadmin = False
        return user

    @pytest.fixture
    def mock_organization(self):
        """Mock organization"""
        org = Mock(spec=Organization)
        org.id = "org-123"
        org.name = "Test Org"
        return org

    @pytest.mark.asyncio
    async def test_create_invitation_success(self, mock_db, mock_user, mock_organization):
        """Test successful invitation creation"""
        from routers.invitations import InvitationCreate

        # Mock organization query
        mock_db.query.return_value.filter.return_value.first.return_value = mock_organization

        # Mock membership check (user is org admin)
        mock_membership = Mock()
        mock_membership.role = OrganizationRole.ORG_ADMIN
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_organization,  # Organization exists
            None,  # No existing user with email
            None,  # No existing invitation
            mock_membership,  # User is org admin
        ]

        # Mock background tasks
        Mock()

        invitation_data = InvitationCreate(
            email="newuser@example.com", role=OrganizationRole.CONTRIBUTOR
        )

        # Patch the permission check and notification
        with patch("routers.invitations.can_manage_organization", return_value=True):
            with patch("routers.invitations.notify_organization_invitation_sent"):
                # Mock the refresh method to set required fields
                def mock_refresh(obj):
                    obj.created_at = datetime.now(timezone.utc)
                    obj.accepted_at = None

                mock_db.refresh = mock_refresh

                result = await create_invitation(
                    organization_id="org-123",
                    invitation_data=invitation_data,
                    current_user=mock_user,
                    db=mock_db,
                )

        assert result.email == "newuser@example.com"
        assert result.role == OrganizationRole.CONTRIBUTOR
        assert result.organization_name == "Test Org"
        assert result.inviter_name == "Admin User"

        # Check invitation was added to DB
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_invitation_organization_not_found(self, mock_db, mock_user):
        """Test invitation creation with non-existent organization"""
        from routers.invitations import InvitationCreate

        mock_db.query.return_value.filter.return_value.first.return_value = None

        invitation_data = InvitationCreate(
            email="test@example.com", role=OrganizationRole.CONTRIBUTOR
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_invitation(
                organization_id="non-existent",
                invitation_data=invitation_data,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "Organization not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_invitation_user_already_member(
        self, mock_db, mock_user, mock_organization
    ):
        """Test invitation creation for existing member"""
        from routers.invitations import InvitationCreate

        # Mock existing user
        mock_existing_user = Mock(spec=User)
        mock_existing_user.id = "existing-user"
        mock_existing_user.email = "existing@example.com"

        # Mock existing membership
        mock_membership = Mock()

        mock_db.query.return_value.filter.side_effect = [
            Mock(first=Mock(return_value=mock_organization)),  # Organization exists
            Mock(first=Mock(return_value=mock_existing_user)),  # User exists
            Mock(first=Mock(return_value=mock_membership)),  # User is member
        ]

        invitation_data = InvitationCreate(
            email="existing@example.com", role=OrganizationRole.CONTRIBUTOR
        )

        with patch("routers.invitations.can_manage_organization", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await create_invitation(
                    organization_id="org-123",
                    invitation_data=invitation_data,
                    current_user=mock_user,
                    db=mock_db,
                )

        assert exc_info.value.status_code == 400
        assert "already a member" in str(exc_info.value.detail)


class TestAcceptInvitation:
    """Test invitation acceptance"""

    @pytest.fixture
    def mock_invitation(self):
        """Mock invitation"""
        invitation = Mock(spec=Invitation)
        invitation.id = "inv-123"
        invitation.organization_id = "org-123"
        invitation.email = "test@example.com"
        invitation.role = OrganizationRole.CONTRIBUTOR
        invitation.token = "test-token-123"
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        invitation.accepted = False
        return invitation

    @pytest.mark.asyncio
    async def test_accept_invitation_success(self, mock_invitation):
        """Test successful invitation acceptance"""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=User)
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"
        # default_organization_id field removed from User model

        # Mock queries
        mock_db_user = Mock()
        mock_db_user.hashed_password = "hashed_password"  # User has password
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_invitation,  # Invitation exists
            None,  # No existing membership
            mock_db_user,  # DBUser for feature flag check
            Mock(name="Test Org"),  # Organization for notification
        ]

        # Mock feature flag service
        with patch("feature_flag_service.FeatureFlagService") as mock_flag_service:
            mock_flag_service.return_value.is_enabled.return_value = True

            # Mock notification service
            with patch("routers.invitations.notify_organization_invitation_accepted"):
                result = await accept_invitation(
                    token="test-token-123", current_user=mock_user, db=mock_db
                )

        assert result["message"] == "Invitation accepted successfully"
        assert result["organization_id"] == "org-123"
        assert result["role"] == OrganizationRole.CONTRIBUTOR

        # Check invitation marked as accepted
        assert mock_invitation.accepted == True
        assert mock_invitation.accepted_at is not None

        # Check membership created
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Check default organization set
        # default_organization_id field removed - organization membership handled separately

    @pytest.mark.asyncio
    async def test_accept_invitation_expired(self, mock_invitation):
        """Test accepting expired invitation"""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=User)

        # Set invitation as expired
        mock_invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_invitation

        with pytest.raises(HTTPException) as exc_info:
            await accept_invitation(token="test-token-123", current_user=mock_user, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "expired" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_accept_invitation_email_mismatch(self, mock_invitation):
        """Test accepting invitation with wrong email"""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=User)
        mock_user.email = "different@example.com"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_invitation

        with pytest.raises(HTTPException) as exc_info:
            await accept_invitation(token="test-token-123", current_user=mock_user, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "not for your email" in str(exc_info.value.detail)


class TestListInvitations:
    """Test listing organization invitations"""

    @pytest.mark.asyncio
    async def test_list_invitations_success(self):
        """Test listing invitations as org admin"""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=User)
        mock_user.id = "user-123"
        mock_user.role = is_superadmin = False

        # Mock membership check
        mock_membership = Mock()
        mock_membership.role = OrganizationRole.ORG_ADMIN
        mock_db.query.return_value.filter.return_value.first.return_value = mock_membership

        # Mock invitations query with proper attributes
        mock_invitation1_obj = Mock()
        mock_invitation1_obj.id = "inv-1"
        mock_invitation1_obj.email = "test1@example.com"
        mock_invitation1_obj.organization_id = "org-123"
        mock_invitation1_obj.role = OrganizationRole.CONTRIBUTOR
        mock_invitation1_obj.token = "token-1"
        mock_invitation1_obj.invited_by = "user-123"
        mock_invitation1_obj.expires_at = datetime.now(timezone.utc)
        mock_invitation1_obj.accepted_at = None
        mock_invitation1_obj.accepted = False
        mock_invitation1_obj.created_at = datetime.now(timezone.utc)
        mock_invitation1_obj.__dict__ = {
            "id": "inv-1",
            "email": "test1@example.com",
            "organization_id": "org-123",
            "role": OrganizationRole.CONTRIBUTOR,
            "token": "token-1",
            "invited_by": "user-123",
            "expires_at": datetime.now(timezone.utc),
            "accepted_at": None,
            "accepted": False,
            "created_at": datetime.now(timezone.utc),
        }

        mock_invitation2_obj = Mock()
        mock_invitation2_obj.id = "inv-2"
        mock_invitation2_obj.email = "test2@example.com"
        mock_invitation2_obj.organization_id = "org-123"
        mock_invitation2_obj.role = OrganizationRole.ORG_ADMIN
        mock_invitation2_obj.token = "token-2"
        mock_invitation2_obj.invited_by = "user-123"
        mock_invitation2_obj.expires_at = datetime.now(timezone.utc)
        mock_invitation2_obj.accepted_at = None
        mock_invitation2_obj.accepted = False
        mock_invitation2_obj.created_at = datetime.now(timezone.utc)
        mock_invitation2_obj.__dict__ = {
            "id": "inv-2",
            "email": "test2@example.com",
            "organization_id": "org-123",
            "role": OrganizationRole.ORG_ADMIN,
            "token": "token-2",
            "invited_by": "user-123",
            "expires_at": datetime.now(timezone.utc),
            "accepted_at": None,
            "accepted": False,
            "created_at": datetime.now(timezone.utc),
        }

        mock_org = Mock()
        mock_org.name = "Test Org"

        mock_inviter = Mock()
        mock_inviter.name = "John Doe"

        mock_invitation1 = (mock_invitation1_obj, mock_org, mock_inviter)
        mock_invitation2 = (mock_invitation2_obj, mock_org, mock_inviter)

        # Mock the query chain to return proper result
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_invitation1, mock_invitation2]

        result = await list_organization_invitations(
            organization_id="org-123",
            include_expired=False,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 2
        assert result[0].email == "test1@example.com"
        assert result[1].email == "test2@example.com"

    @pytest.mark.asyncio
    async def test_list_invitations_unauthorized(self):
        """Test listing invitations without permission"""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=User)
        mock_user.is_superadmin = False

        # No membership - user is not an org admin
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await list_organization_invitations(
                organization_id="org-123",
                include_expired=False,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 403
        assert "Only organization admins" in str(exc_info.value.detail)
