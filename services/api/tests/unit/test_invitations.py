"""
Unit tests for the invitation system
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser

# send_invitation_email function no longer exported from invitations router
from main import app
from models import (
    Invitation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from routers.invitations import (
    accept_invitation,
    create_invitation,
    generate_invitation_token,
)


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _mk_user(db_session, *, is_superadmin=False, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        id=f"user-{suffix}",
        username=f"user-{suffix}",
        email=f"user-{suffix}@example.com",
        name=f"User {suffix}",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    return user


def _mk_org(db_session, *, suffix=None, name="Test Org"):
    suffix = suffix or uuid.uuid4().hex[:8]
    org = Organization(
        id=f"org-{suffix}",
        name=name,
        display_name=name,
        slug=f"org-{suffix}",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(org)
    return org


def _mk_membership(db_session, *, user, org, role=OrganizationRole.ORG_ADMIN):
    membership = OrganizationMembership(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db_session.add(membership)
    return membership


def _mk_invitation(db_session, *, org, inviter, email, role=OrganizationRole.CONTRIBUTOR):
    suffix = uuid.uuid4().hex[:8]
    inv = Invitation(
        id=f"inv-{suffix}",
        organization_id=org.id,
        email=email,
        role=role,
        token=f"token-{suffix}",
        invited_by=inviter.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        accepted=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(inv)
    return inv


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
    async def test_create_invitation_vertretbar_host_branding(
        self, mock_db, mock_user, mock_organization
    ):
        """A vertretbar.net invite links to vertretbar + passes the host to the email task."""
        from routers.invitations import InvitationCreate

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_organization,  # Organization exists
            None,  # No existing user with email
            None,  # No existing invitation
            Mock(role=OrganizationRole.ORG_ADMIN),  # requester is org admin
        ]

        def mock_refresh(obj):
            obj.created_at = datetime.now(timezone.utc)
            obj.accepted_at = None

        mock_db.refresh = mock_refresh

        req = Mock()
        req.headers.get.side_effect = (
            lambda k, *a: "vertretbar.net" if k == "x-forwarded-host" else None
        )
        invitation_data = InvitationCreate(
            email="stud@example.com", role=OrganizationRole.CONTRIBUTOR
        )

        with patch("routers.invitations.can_manage_organization", return_value=True):
            with patch("routers.invitations.notify_organization_invitation_sent"):
                with patch("routers.invitations.celery_app") as mock_celery:
                    await create_invitation(
                        organization_id="org-123",
                        invitation_data=invitation_data,
                        request=req,
                        current_user=mock_user,
                        db=mock_db,
                    )

        # The accept link points at vertretbar, and the host is forwarded to the
        # Celery email task so it renders the Vertretbar sender/branding.
        mock_celery.send_task.assert_called_once()
        task_kwargs = mock_celery.send_task.call_args.kwargs
        assert task_kwargs["args"][4].startswith("https://vertretbar.net/accept-invitation/")
        assert task_kwargs["kwargs"]["host"] == "vertretbar.net"

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
        with patch("services.feature_flag_service.FeatureFlagService") as mock_flag_service:
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
    """Test listing organization invitations.

    The list endpoint was migrated to the async DB lane (`Depends(get_async_db)`
    + `await db.execute(select(...))` joins). These tests run against the real
    `async_test_client` / `async_test_db` fixtures with seeded rows so the
    permission check, the join, and the InvitationResponse serialization are all
    exercised end-to-end.
    """

    @pytest.mark.asyncio
    async def test_list_invitations_success(self, async_test_client, async_test_db):
        """Test listing invitations as org admin returns the pending rows."""
        org = _mk_org(async_test_db, name="Test Org")
        inviter = _mk_user(async_test_db, suffix="inviter")
        admin = _mk_user(async_test_db, suffix="admin")
        _mk_membership(async_test_db, user=admin, org=org, role=OrganizationRole.ORG_ADMIN)
        _mk_invitation(
            async_test_db, org=org, inviter=inviter, email="test1@example.com",
            role=OrganizationRole.CONTRIBUTOR,
        )
        _mk_invitation(
            async_test_db, org=org, inviter=inviter, email="test2@example.com",
            role=OrganizationRole.ORG_ADMIN,
        )
        await async_test_db.flush()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert len(data) == 2
        emails = {item["email"] for item in data}
        assert emails == {"test1@example.com", "test2@example.com"}
        # join-populated fields surface on the response
        assert all(item["organization_name"] == "Test Org" for item in data)
        assert all(item["inviter_name"] == inviter.name for item in data)

    @pytest.mark.asyncio
    async def test_list_invitations_unauthorized(self, async_test_client, async_test_db):
        """Test listing invitations without permission yields 403."""
        org = _mk_org(async_test_db)
        # Requesting user has no org-admin membership.
        non_admin = _mk_user(async_test_db, suffix="nonadmin")
        await async_test_db.flush()

        with _as_user(non_admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "Only organization admins" in resp.json()["detail"]
