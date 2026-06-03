"""
Unit tests for the invitation system
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# send_invitation_email function no longer exported from invitations router
from main import app
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
        user.role = is_superadmin = False  # noqa: F841
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


class TestCreateBulkInvitations:
    """Test the bulk invitation creation endpoint"""

    @pytest.fixture
    def mock_db(self):
        db = Mock(spec=Session)
        db.query = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.refresh = Mock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = Mock(spec=User)
        user.id = "user-123"
        user.name = "Admin User"
        user.is_superadmin = False
        return user

    @pytest.fixture
    def mock_organization(self):
        org = Mock(spec=Organization)
        org.id = "org-123"
        org.name = "Göttingen"
        return org

    @pytest.mark.asyncio
    async def test_bulk_invite_requires_admin(self, mock_db, mock_user, mock_organization):
        """Non-admins cannot bulk invite (mirrors single-invite 403)."""
        from routers.invitations import BulkInvitationCreate, create_bulk_invitations

        mock_db.query.return_value.filter.return_value.first.return_value = mock_organization

        bulk_data = BulkInvitationCreate(
            emails=["a@example.com"], role=OrganizationRole.ANNOTATOR
        )

        with patch("routers.invitations.can_manage_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await create_bulk_invitations(
                    organization_id="org-123",
                    bulk_data=bulk_data,
                    current_user=mock_user,
                    db=mock_db,
                )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_invite_mixed_batch(self, mock_db, mock_user, mock_organization):
        """A mixed batch returns the right per-email status, creates only the
        valid new rows, and dispatches emails.send_bulk_invitations with a
        payload of exactly those rows."""
        from routers.invitations import BulkInvitationCreate, create_bulk_invitations

        existing_user = Mock(spec=User)
        existing_user.id = "member-1"
        existing_user.email = "member@example.com"
        active_membership = Mock()
        pending_invitation = Mock(spec=Invitation)

        # Query order: org check, then per valid+new-or-existing email in input order:
        #   new@      -> User None, Invitation None  (queued)
        #   member@   -> User existing_user, Membership active  (already_member)
        #   pending@  -> User None, Invitation pending  (pending)
        #   not-an-email -> rejected before any query (invalid)
        #   NEW@      -> intra-batch duplicate, no query  (duplicate)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_organization,   # organization exists
            None,                # new@ user
            None,                # new@ pending invitation
            existing_user,       # member@ user
            active_membership,   # member@ membership
            None,                # pending@ user
            pending_invitation,  # pending@ pending invitation
        ]

        bulk_data = BulkInvitationCreate(
            emails=[
                "new@example.com",
                "member@example.com",
                "pending@example.com",
                "not-an-email",
                "NEW@example.com",
            ],
            role=OrganizationRole.ANNOTATOR,
        )

        with patch("routers.invitations.can_manage_organization", return_value=True), \
             patch("routers.invitations.notify_organization_invitation_sent"), \
             patch("routers.invitations.celery_app") as mock_celery:
            result = await create_bulk_invitations(
                organization_id="org-123",
                bulk_data=bulk_data,
                current_user=mock_user,
                db=mock_db,
            )

        # Results preserve input order, so assert position by position. (Can't key
        # a dict on the email — the queued "new@" and duplicate "NEW@" share a key.)
        statuses = [item.status for item in result.results]
        assert statuses == [
            "queued",         # new@example.com
            "already_member",  # member@example.com
            "pending",        # pending@example.com
            "invalid",        # not-an-email
            "duplicate",      # NEW@example.com (collides with new@)
        ]

        assert result.queued == 1
        assert result.total == 5
        assert result.skipped == 4

        # Only the one valid new row is persisted.
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_called_once()

        # Dispatched once to the bulk worker task with a 1-item payload.
        mock_celery.send_task.assert_called_once()
        args, kwargs = mock_celery.send_task.call_args
        assert args[0] == "emails.send_bulk_invitations"
        payload = kwargs["args"][0]
        assert len(payload) == 1
        entry = payload[0]
        assert entry["to_email"] == "new@example.com"
        assert entry["organization_name"] == "Göttingen"
        assert entry["inviter_name"] == "Admin User"
        assert entry["role"] == "ANNOTATOR"
        assert "/accept-invitation/" in entry["invitation_url"]
        assert kwargs["queue"] == "emails"

    @pytest.mark.asyncio
    async def test_bulk_invite_no_valid_emails_skips_dispatch(
        self, mock_db, mock_user, mock_organization
    ):
        """All-blank/invalid input creates nothing and queues no task."""
        from routers.invitations import BulkInvitationCreate, create_bulk_invitations

        mock_db.query.return_value.filter.return_value.first.return_value = mock_organization

        bulk_data = BulkInvitationCreate(
            emails=["   ", "still-not-an-email"], role=OrganizationRole.ANNOTATOR
        )

        with patch("routers.invitations.can_manage_organization", return_value=True), \
             patch("routers.invitations.celery_app") as mock_celery:
            result = await create_bulk_invitations(
                organization_id="org-123",
                bulk_data=bulk_data,
                current_user=mock_user,
                db=mock_db,
            )

        assert result.queued == 0
        assert result.total == 1  # blank dropped silently, only the bad email reported
        assert result.results[0].status == "invalid"
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()
        mock_celery.send_task.assert_not_called()


class TestBulkInvitationsHttp:
    """Exercise the bulk endpoint through the real HTTP stack: route
    registration, BulkInvitationCreate body parsing (List[str] + role enum),
    and BulkInvitationResponse serialization — none of which the direct
    function-call tests above cover."""

    URL = "/api/invitations/organizations/org-123/invitations/bulk"

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="user-123",
            username="admin",
            email="admin@test.com",
            name="Admin User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def _override(self, mock_user, mock_db):
        from auth_module.dependencies import require_user
        from database import get_db

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

    def test_bulk_endpoint_happy_path(self, client, mock_user):
        """A valid body hits the route, parses, queues one row, returns 200."""
        org = Mock(spec=Organization)
        org.id = "org-123"
        org.name = "Göttingen"

        mock_db = Mock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            org,   # organization exists
            None,  # new@ user lookup
            None,  # new@ pending invitation lookup
        ]
        self._override(mock_user, mock_db)
        try:
            with patch("routers.invitations.can_manage_organization", return_value=True), \
                 patch("routers.invitations.notify_organization_invitation_sent"), \
                 patch("routers.invitations.celery_app") as mock_celery:
                response = client.post(
                    self.URL,
                    json={"emails": ["new@example.com"], "role": "ANNOTATOR"},
                )

            assert response.status_code == status.HTTP_200_OK
            body = response.json()
            assert body["queued"] == 1
            assert body["total"] == 1
            assert body["results"][0]["status"] == "queued"
            mock_celery.send_task.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    def test_bulk_endpoint_rejects_unknown_role(self, client, mock_user):
        """An invalid role is a 422 from Pydantic before the handler runs."""
        self._override(mock_user, Mock(spec=Session))
        try:
            with patch("routers.invitations.can_manage_organization", return_value=True):
                response = client.post(
                    self.URL,
                    json={"emails": ["a@example.com"], "role": "SUPER_DUPER_ADMIN"},
                )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    def test_bulk_endpoint_rejects_non_list_emails(self, client, mock_user):
        """emails must be a list; a bare string is a 422."""
        self._override(mock_user, Mock(spec=Session))
        try:
            with patch("routers.invitations.can_manage_organization", return_value=True):
                response = client.post(
                    self.URL,
                    json={"emails": "a@example.com", "role": "ANNOTATOR"},
                )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()


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
        assert mock_invitation.accepted == True  # noqa: E712
        assert mock_invitation.accepted_at != None  # noqa: E711

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
        mock_user.role = is_superadmin = False  # noqa: F841

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
