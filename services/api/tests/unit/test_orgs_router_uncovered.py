"""
Unit tests for routers/organizations.py targeting uncovered lines.

Covers: get_organization_by_slug success path, update_organization success,
list_organization_members success, update_member_role success,
remove_member success, list_all_users with org filtering,
update_user_superadmin_status success, delete_user success,
add_user_to_organization success, verify_member_email success paths,
bulk_verify_member_emails success paths.

Rewritten to call handler functions directly (no TestClient) so that pytest-cov
tracks the router code.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from models import OrganizationMembership, OrganizationRole, User


# ---------------------------------------------------------------------------
# get_organization_by_slug: success paths (lines 334-358)
# ---------------------------------------------------------------------------


def _make_org_obj():
    """Create a plain object with org attributes (avoids Mock.__dict__ issues)."""
    class FakeOrg:
        pass

    org = FakeOrg()
    org.id = "org-1"
    org.name = "Test Org"
    org.display_name = "Test Org"
    org.slug = "test-org"
    org.description = None
    org.settings = {}
    org.is_active = True
    org.created_at = datetime(2025, 1, 1)
    org.updated_at = None
    return org


class TestGetOrganizationBySlugSuccess:
    @pytest.mark.asyncio
    async def test_superadmin_access(self):
        """Cover lines 334-358: superadmin gets org by slug with member count."""
        from routers.organizations import get_organization_by_slug

        db = MagicMock()
        user = Mock(is_superadmin=True, id="admin-1")

        org = _make_org_obj()
        membership = Mock()
        membership.role = OrganizationRole.ORG_ADMIN

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org  # org lookup
            elif call_count[0] == 2:
                q.scalar.return_value = 5  # member count
            else:
                q.first.return_value = membership  # user membership
            return q

        db.query.side_effect = query_side_effect

        result = await get_organization_by_slug(
            slug="test-org", current_user=user, db=db,
        )
        assert result.id == "org-1"
        assert result.member_count == 5

    @pytest.mark.asyncio
    async def test_member_access(self):
        """Cover lines 320-332: non-superadmin member gets org."""
        from routers.organizations import get_organization_by_slug

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1")

        org = _make_org_obj()
        membership = Mock()
        membership.role = OrganizationRole.ANNOTATOR

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org  # org found
            else:
                q.first.return_value = membership  # membership checks
                q.scalar.return_value = 3
            return q

        db.query.side_effect = query_side_effect

        result = await get_organization_by_slug(
            slug="test-org", current_user=user, db=db,
        )
        assert result.id == "org-1"

    @pytest.mark.asyncio
    async def test_slug_not_found(self):
        """Cover: org not found by slug."""
        from routers.organizations import get_organization_by_slug

        db = MagicMock()
        user = Mock(is_superadmin=True, id="admin-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(slug="missing", current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_denied(self):
        """Cover: non-superadmin, non-member denied."""
        from routers.organizations import get_organization_by_slug

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1")

        org = _make_org_obj()
        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org
            else:
                q.first.return_value = None  # no membership
            return q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(slug="test-org", current_user=user, db=db)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# update_organization: success path (lines 430-456)
# ---------------------------------------------------------------------------


class TestUpdateOrganizationSuccess:
    @pytest.mark.asyncio
    @patch("routers.organizations.can_manage_organization", return_value=True)
    async def test_update_org_success(self, mock_can_manage):
        """Cover lines 430-456: successful org update."""
        from routers.organizations import update_organization, OrganizationUpdate

        db = MagicMock()
        user = Mock(is_superadmin=True, id="admin-1")

        org = _make_org_obj()
        org.name = "Old Name"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = org
        mock_q.scalar.return_value = 3
        db.query.return_value = mock_q

        with patch("redis_cache.OrgSlugCache"):
            result = await update_organization(
                organization_id="org-1",
                update_data=OrganizationUpdate(name="New Name", description="Updated"),
                current_user=user,
                db=db,
            )
        assert result.id == "org-1"


# ---------------------------------------------------------------------------
# list_organization_members: success path (lines 520-539)
# ---------------------------------------------------------------------------


class TestListMembersSuccess:
    @pytest.mark.asyncio
    async def test_superadmin_lists_members(self):
        """Cover lines 519-539: successful member listing."""
        from routers.organizations import list_organization_members

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        member_mock = Mock()
        member_mock.id = "mem-1"
        member_mock.user_id = "user-1"
        member_mock.organization_id = "org-1"
        member_mock.role = OrganizationRole.ANNOTATOR
        member_mock.is_active = True
        member_mock.joined_at = datetime(2025, 1, 1)
        member_mock.__dict__ = {
            "id": "mem-1", "user_id": "user-1", "organization_id": "org-1",
            "role": OrganizationRole.ANNOTATOR, "is_active": True,
            "joined_at": datetime(2025, 1, 1),
        }

        user_mock = Mock()
        user_mock.name = "Test User"
        user_mock.email = "test@test.com"
        user_mock.email_verified = True
        user_mock.email_verification_method = "link"

        members_query = MagicMock()
        members_query.join.return_value = members_query
        members_query.filter.return_value = members_query
        members_query.all.return_value = [(member_mock, user_mock)]

        db.query.return_value = members_query

        result = await list_organization_members(
            organization_id="org-1", current_user=user, db=db,
        )
        assert len(result) == 1
        assert result[0].user_name == "Test User"


# ---------------------------------------------------------------------------
# update_member_role: success path (lines 595-600)
# ---------------------------------------------------------------------------


class TestUpdateMemberRoleSuccess:
    @pytest.mark.asyncio
    async def test_superadmin_updates_role(self):
        """Cover lines 594-600: successful role update."""
        from routers.organizations import update_member_role, UpdateMemberRole

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        target_membership = Mock()
        target_membership.role = OrganizationRole.ANNOTATOR

        db.query.return_value.filter.return_value.first.return_value = target_membership

        result = await update_member_role(
            organization_id="org-1",
            user_id="user-2",
            role_update=UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR),
            current_user=user,
            db=db,
        )
        assert result["message"] == "Member role updated successfully"
        assert target_membership.role == OrganizationRole.CONTRIBUTOR


# ---------------------------------------------------------------------------
# remove_member: success path (lines 655-660)
# ---------------------------------------------------------------------------


class TestRemoveMemberSuccess:
    @pytest.mark.asyncio
    async def test_superadmin_removes_member(self):
        """Cover lines 654-660: successful member removal."""
        from routers.organizations import remove_member

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        target_membership = Mock()
        target_membership.is_active = True

        db.query.return_value.filter.return_value.first.return_value = target_membership

        result = await remove_member(
            organization_id="org-1",
            user_id="user-2",
            current_user=user,
            db=db,
        )
        assert result["message"] == "Member removed from organization successfully"
        assert target_membership.is_active is False


# ---------------------------------------------------------------------------
# list_all_users: with org filtering (lines 715-724)
# ---------------------------------------------------------------------------


class TestListAllUsersOrgFiltering:
    @pytest.mark.asyncio
    async def test_non_superadmin_with_orgs(self):
        """Cover lines 708-724: non-superadmin sees org users."""
        from routers.organizations import list_all_users

        db = MagicMock()
        user = Mock(is_superadmin=False, id="user-1", organizations=[{"id": "org-1"}])

        u1 = Mock()
        u1.__dict__ = {
            "id": "u1", "username": "user1", "email": "u1@test.com",
            "email_verified": True, "email_verification_method": "link",
            "name": "User 1", "is_superadmin": False, "is_active": True,
            "created_at": datetime(2025, 1, 1), "updated_at": None,
        }

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.subquery.return_value = MagicMock()
        mock_q.all.return_value = [u1]
        db.query.return_value = mock_q

        result = await list_all_users(current_user=user, db=db)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_superadmin_sees_all(self):
        """Cover: superadmin lists all users."""
        from routers.organizations import list_all_users

        db = MagicMock()
        user = Mock(is_superadmin=True, id="admin-1")

        u1 = Mock()
        u1.__dict__ = {
            "id": "u1", "username": "user1", "email": "u1@test.com",
            "email_verified": True, "email_verification_method": "link",
            "name": "User 1", "is_superadmin": False, "is_active": True,
            "created_at": datetime(2025, 1, 1), "updated_at": None,
        }

        db.query.return_value.filter.return_value.all.return_value = [u1]

        result = await list_all_users(current_user=user, db=db)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# update_user_superadmin_status: success (lines 750-757)
# ---------------------------------------------------------------------------


class TestUpdateSuperadminStatusSuccess:
    @pytest.mark.asyncio
    async def test_promote_user(self):
        """Cover lines 749-768: successful superadmin promotion."""
        from routers.organizations import update_user_superadmin_status, UserSuperadminUpdate

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1")

        target_user = Mock()
        target_user.id = "user-1"
        target_user.username = "user1"
        target_user.email = "user1@test.com"
        target_user.email_verified = True
        target_user.email_verification_method = "link"
        target_user.name = "User 1"
        target_user.is_superadmin = False
        target_user.is_active = True
        target_user.created_at = datetime(2025, 1, 1)
        target_user.updated_at = None

        db.query.return_value.filter.return_value.first.return_value = target_user

        result = await update_user_superadmin_status(
            user_id="user-1",
            superadmin_update=UserSuperadminUpdate(is_superadmin=True),
            current_user=admin,
            db=db,
        )
        assert target_user.is_superadmin is True
        assert result.is_superadmin is True


# ---------------------------------------------------------------------------
# delete_user: full success (lines 819-915)
# ---------------------------------------------------------------------------


class TestDeleteUserSuccess:
    @pytest.mark.asyncio
    async def test_delete_regular_user(self):
        """Cover lines 819-909: successful user deletion."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")

        user_result = Mock(email="target@test.com", is_superadmin=False)

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                # First call: user lookup
                mock_result.first.return_value = user_result
            else:
                mock_result.rowcount = 0
                arg_str = str(args[0]) if args else ""
                if "SELECT id FROM users" in arg_str:
                    mock_result.fetchone.return_value = None  # User is gone
                else:
                    mock_result.fetchone.return_value = ("user-2",)
            return mock_result

        db.execute.side_effect = execute_side_effect

        result = await delete_user(user_id="user-2", current_user=admin, db=db)
        assert result["message"] == "User deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_user_critical_failure(self):
        """Cover lines 911-918: critical failure during user deletion."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")

        user_result = Mock(email="target@test.com", is_superadmin=False)

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.first.return_value = user_result
            else:
                mock_result.rowcount = 0
                mock_result.fetchone.return_value = None
            return mock_result

        db.execute.side_effect = execute_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-2", current_user=admin, db=db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_user_outer_exception(self):
        """Cover lines 923-929: unexpected outer exception."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")

        db.execute.side_effect = RuntimeError("Unexpected DB crash")

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-2", current_user=admin, db=db)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# add_user_to_organization: success (lines 990-1001)
# ---------------------------------------------------------------------------


class TestAddUserToOrgSuccess:
    @pytest.mark.asyncio
    async def test_add_user_success(self):
        """Cover lines 989-1001: successful user addition."""
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1")
        org = Mock()
        target_user = Mock()

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org  # org found
            elif call_count[0] == 2:
                q.first.return_value = target_user  # user found
            elif call_count[0] == 3:
                q.first.return_value = None  # not already member
            return q

        db.query.side_effect = query_side_effect

        result = await add_user_to_organization(
            organization_id="org-1",
            add_user=AddUserToOrganization(user_id="user-2"),
            current_user=admin,
            db=db,
        )
        assert result["message"] == "User added to organization successfully"
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# verify_member_email: success paths (lines 1058-1114)
# ---------------------------------------------------------------------------


class TestVerifyMemberEmailSuccess:
    @pytest.mark.asyncio
    async def test_already_verified(self):
        """Cover lines 1084-1090: user email already verified."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = True
        user_to_verify.email_verified_by_id = "prev-admin"
        user_to_verify.email_verification_method = "link"

        db.query.return_value.filter.return_value.first.return_value = user_to_verify

        result = await verify_member_email(
            organization_id="org-1",
            user_id="user-1",
            request=VerifyEmailRequest(),
            current_user=admin,
            db=db,
        )
        assert result["message"] == "Email already verified"

    @pytest.mark.asyncio
    async def test_verify_unverified_email(self):
        """Cover lines 1093-1119: successfully verify an unverified email."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = False

        db.query.return_value.filter.return_value.first.return_value = user_to_verify

        result = await verify_member_email(
            organization_id="org-1",
            user_id="user-1",
            request=VerifyEmailRequest(reason="Manual verification"),
            current_user=admin,
            db=db,
        )
        assert result["message"] == "Email verified successfully"
        assert user_to_verify.email_verified is True
        assert user_to_verify.email_verification_method == "admin"

    @pytest.mark.asyncio
    async def test_verify_non_member_non_superadmin(self):
        """Cover lines 1058-1073: non-superadmin checks membership."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        user = Mock(is_superadmin=False, id="admin-1", email="admin@test.com")

        admin_membership = Mock()
        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = False

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = admin_membership  # admin check
            elif call_count[0] == 2:
                q.first.return_value = Mock()  # target is member
            elif call_count[0] == 3:
                q.first.return_value = user_to_verify  # user found
            return q

        db.query.side_effect = query_side_effect

        result = await verify_member_email(
            organization_id="org-1",
            user_id="user-1",
            request=VerifyEmailRequest(),
            current_user=user,
            db=db,
        )
        assert result["message"] == "Email verified successfully"

    @pytest.mark.asyncio
    async def test_verify_user_not_found(self):
        """Cover lines 1077-1081: user not found."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await verify_member_email(
                organization_id="org-1",
                user_id="nonexistent",
                request=VerifyEmailRequest(),
                current_user=admin,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_target_denied(self):
        """Cover lines 1059-1073: non-superadmin, target not member of org."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        user = Mock(is_superadmin=False, id="admin-1", email="admin@test.com")

        admin_membership = Mock()

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = admin_membership  # admin check passed
            elif call_count[0] == 2:
                q.first.return_value = None  # target NOT a member
            return q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await verify_member_email(
                organization_id="org-1",
                user_id="user-1",
                request=VerifyEmailRequest(),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# bulk_verify_member_emails: success paths (lines 1157-1247)
# ---------------------------------------------------------------------------


class TestBulkVerifySuccess:
    @pytest.mark.asyncio
    async def test_bulk_verify_mixed_results(self):
        """Cover lines 1157-1255: mix of success, skip, error."""
        from routers.organizations import bulk_verify_member_emails, BulkVerifyEmailRequest

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        # user1: already verified (skip)
        user1 = Mock()
        user1.email = "u1@test.com"
        user1.email_verified = True

        # user2: unverified (success)
        user2 = Mock()
        user2.email = "u2@test.com"
        user2.email_verified = False

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = user1  # user1 found
            elif call_count[0] == 2:
                q.first.return_value = user2  # user2 found
            elif call_count[0] == 3:
                q.first.return_value = None  # user3 not found
            return q

        db.query.side_effect = query_side_effect

        result = await bulk_verify_member_emails(
            organization_id="org-1",
            request=BulkVerifyEmailRequest(
                user_ids=["user-1", "user-2", "user-3"],
                reason="Bulk test",
            ),
            current_user=admin,
            db=db,
        )

        assert result["summary"]["total"] == 3
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["success"] == 1
        assert result["summary"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_bulk_verify_non_superadmin_non_member(self):
        """Cover lines 1165-1185: non-superadmin, target not org member."""
        from routers.organizations import bulk_verify_member_emails, BulkVerifyEmailRequest

        db = Mock()
        user = Mock(is_superadmin=False, id="org-admin-1", email="oadmin@test.com")

        admin_membership = Mock()

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = admin_membership  # admin check
            elif call_count[0] == 2:
                q.first.return_value = None  # user not member
            return q

        db.query.side_effect = query_side_effect

        result = await bulk_verify_member_emails(
            organization_id="org-1",
            request=BulkVerifyEmailRequest(user_ids=["user-1"]),
            current_user=user,
            db=db,
        )
        assert result["summary"]["errors"] == 1
        assert result["results"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_bulk_verify_all_success(self):
        """Cover the fully successful path."""
        from routers.organizations import bulk_verify_member_emails, BulkVerifyEmailRequest

        db = Mock()
        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user1 = Mock()
        user1.email = "u1@test.com"
        user1.email_verified = False

        db.query.return_value.filter.return_value.first.return_value = user1

        result = await bulk_verify_member_emails(
            organization_id="org-1",
            request=BulkVerifyEmailRequest(user_ids=["user-1"], reason="Test"),
            current_user=admin,
            db=db,
        )
        assert result["summary"]["success"] == 1
        assert user1.email_verified is True
        assert user1.email_verification_method == "admin"
