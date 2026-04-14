"""
Unit tests for routers/organizations.py — covers endpoint logic with mocked DB.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from routers.organizations import (
    can_manage_organization,
    can_create_organization,
)


# ============= can_manage_organization =============


class TestCanManageOrganization:
    """Tests for can_manage_organization."""

    def test_none_user(self):
        db = Mock()
        assert can_manage_organization(None, "org-1", db) is False

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True)
        assert can_manage_organization(user, "org-1", db) is True

    def test_org_admin_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_manage_organization(user, "org-1", db) is True

    def test_non_admin_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) is False


# ============= can_create_organization =============


class TestCanCreateOrganization:
    """Tests for can_create_organization."""

    def test_none_user(self):
        db = Mock()
        assert can_create_organization(None, db) is False

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True)
        assert can_create_organization(user, db) is True

    def test_org_admin_of_any_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_create_organization(user, db) is True

    def test_no_admin_membership(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_create_organization(user, db) is False


# ============= Endpoint tests =============


class TestListOrganizations:
    """Tests for list_organizations endpoint."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all(self):
        from routers.organizations import list_organizations

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        org = Mock()
        org.__dict__ = {
            "id": "org-1",
            "name": "Org 1",
            "display_name": "Org 1",
            "slug": "org-1",
            "description": None,
            "settings": {},
            "is_active": True,
            "created_at": datetime(2025, 1, 1),
            "updated_at": None,
        }

        orgs_query = MagicMock()
        orgs_query.filter.return_value = orgs_query
        orgs_query.all.return_value = [org]

        member_count_query = MagicMock()
        member_count_query.filter.return_value = member_count_query
        member_count_query.group_by.return_value = member_count_query
        member_count_query.all.return_value = [("org-1", 5)]

        roles_query = MagicMock()
        roles_query.filter.return_value = roles_query
        roles_query.all.return_value = []

        db.query.side_effect = [orgs_query, member_count_query, roles_query]

        result = await list_organizations(current_user=user, db=db)
        assert len(result) == 1
        assert result[0].member_count == 5

    @pytest.mark.asyncio
    async def test_regular_user_sees_own_orgs(self):
        from routers.organizations import list_organizations

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        # Use a simple namespace object instead of Mock to avoid __dict__ issues
        class FakeOrg:
            pass

        org = FakeOrg()
        org.id = "org-1"
        org.name = "Org 1"
        org.display_name = "Org 1"
        org.slug = "org-1"
        org.description = None
        org.settings = {}
        org.is_active = True
        org.created_at = datetime(2025, 1, 1)
        org.updated_at = None

        user_orgs_query = MagicMock()
        user_orgs_query.join.return_value = user_orgs_query
        user_orgs_query.filter.return_value = user_orgs_query
        user_orgs_query.all.return_value = [(org, "ANNOTATOR")]

        member_count_query = MagicMock()
        member_count_query.filter.return_value = member_count_query
        member_count_query.group_by.return_value = member_count_query
        member_count_query.all.return_value = [("org-1", 3)]

        db.query.side_effect = [user_orgs_query, member_count_query]

        result = await list_organizations(current_user=user, db=db)
        assert len(result) == 1
        assert result[0].role == "ANNOTATOR"

    @pytest.mark.asyncio
    async def test_regular_user_no_orgs(self):
        from routers.organizations import list_organizations

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        user_orgs_query = MagicMock()
        user_orgs_query.join.return_value = user_orgs_query
        user_orgs_query.filter.return_value = user_orgs_query
        user_orgs_query.all.return_value = []

        db.query.return_value = user_orgs_query

        result = await list_organizations(current_user=user, db=db)
        assert result == []


class TestCreateOrganization:
    """Tests for create_organization endpoint."""

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        from routers.organizations import create_organization, OrganizationCreate

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        org = OrganizationCreate(
            name="New Org", display_name="New Org", slug="new-org"
        )

        with patch("routers.organizations.can_create_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await create_organization(organization=org, current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_slug(self):
        from routers.organizations import create_organization, OrganizationCreate

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        db.query.return_value.filter.return_value.first.return_value = Mock()  # Existing org

        org = OrganizationCreate(
            name="New Org", display_name="New Org", slug="existing-slug"
        )

        with patch("routers.organizations.can_create_organization", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await create_organization(organization=org, current_user=user, db=db)
            assert exc_info.value.status_code == 400


class TestGetOrganizationBySlug:
    """Tests for get_organization_by_slug endpoint."""

    @pytest.mark.asyncio
    async def test_invalid_slug_format(self):
        from routers.organizations import get_organization_by_slug

        db = Mock()
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug="INVALID_SLUG!", current_user=user, db=db
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_org_not_found(self):
        from routers.organizations import get_organization_by_slug

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug="unknown-slug", current_user=user, db=db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_access_denied(self):
        from routers.organizations import get_organization_by_slug

        db = Mock()
        org = Mock(id="org-1")
        user = Mock(is_superadmin=False, id="user-1")

        # First query returns org, second returns None (no membership)
        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org
            else:
                q.first.return_value = None
            return q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug="my-org", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403


class TestGetOrganization:
    """Tests for get_organization endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.organizations import get_organization

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await get_organization(
                organization_id="org-1", current_user=user, db=db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.organizations import get_organization

        db = Mock()
        org = Mock()
        user = Mock(is_superadmin=False, id="user-1")

        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org
            else:
                q.first.return_value = None
            return q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await get_organization(
                organization_id="org-1", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403


class TestUpdateOrganization:
    """Tests for update_organization endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.organizations import update_organization, OrganizationUpdate

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        update = OrganizationUpdate(name="New Name")

        with pytest.raises(HTTPException) as exc_info:
            await update_organization(
                organization_id="org-1", update_data=update, current_user=user, db=db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        from routers.organizations import update_organization, OrganizationUpdate

        db = Mock()
        org = Mock()
        db.query.return_value.filter.return_value.first.return_value = org
        user = Mock(is_superadmin=False, id="user-1")
        update = OrganizationUpdate(name="New Name")

        with patch("routers.organizations.can_manage_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await update_organization(
                    organization_id="org-1",
                    update_data=update,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestDeleteOrganization:
    """Tests for delete_organization endpoint."""

    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self):
        from routers.organizations import delete_organization

        db = Mock()
        user = Mock(is_superadmin=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_organization(
                organization_id="org-1", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.organizations import delete_organization

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await delete_organization(
                organization_id="org-1", current_user=user, db=db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_delete(self):
        from routers.organizations import delete_organization

        db = Mock()
        org = Mock(is_active=True, slug="org-slug")
        db.query.return_value.filter.return_value.first.return_value = org
        db.query.return_value.filter.return_value.update.return_value = 3
        user = Mock(is_superadmin=True)

        with patch("redis_cache.OrgSlugCache") as mock_cache:
            result = await delete_organization(
                organization_id="org-1", current_user=user, db=db
            )
            assert result["message"] == "Organization deleted successfully"
            assert org.is_active is False


class TestListOrganizationMembers:
    """Tests for list_organization_members endpoint."""

    @pytest.mark.asyncio
    async def test_non_member_denied(self):
        from routers.organizations import list_organization_members

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await list_organization_members(
                organization_id="org-1", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403


class TestUpdateMemberRole:
    """Tests for update_member_role endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        from routers.organizations import update_member_role, UpdateMemberRole
        from models import OrganizationRole

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id="org-1",
                user_id="user-2",
                role_update=UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_not_found(self):
        from routers.organizations import update_member_role, UpdateMemberRole
        from models import OrganizationRole

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id="org-1",
                user_id="user-2",
                role_update=UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_modify_own_role(self):
        from routers.organizations import update_member_role, UpdateMemberRole
        from models import OrganizationRole

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        admin_mem = Mock()  # Has admin membership
        target_mem = Mock()  # Target membership found

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = admin_mem
            else:
                q.first.return_value = target_mem
            return q
        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id="org-1",
                user_id="user-1",  # Same as current user
                role_update=UpdateMemberRole(role=OrganizationRole.ANNOTATOR),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestRemoveMember:
    """Tests for remove_member endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        from routers.organizations import remove_member

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id="org-1", user_id="user-2", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_not_found(self):
        from routers.organizations import remove_member

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id="org-1", user_id="user-2", current_user=user, db=db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_remove_self(self):
        from routers.organizations import remove_member

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        admin_mem = Mock()
        target_mem = Mock()

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = admin_mem
            else:
                q.first.return_value = target_mem
            return q
        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id="org-1",
                user_id="user-1",
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestListAllUsers:
    """Tests for list_all_users endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated(self):
        from routers.organizations import list_all_users

        db = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await list_all_users(current_user=None, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_superadmin_all_users(self):
        from routers.organizations import list_all_users

        db = Mock()
        user = Mock(is_superadmin=True)

        u1 = Mock()
        u1.__dict__ = {
            "id": "u1", "username": "user1", "email": "u1@test.com",
            "email_verified": True, "email_verification_method": "link",
            "name": "User 1", "is_superadmin": False, "is_active": True,
            "created_at": datetime(2025, 1, 1), "updated_at": None,
        }
        db.query.return_value.filter.return_value.all.return_value = [u1]

        result = await list_all_users(current_user=user, db=db)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_regular_user_no_orgs(self):
        from routers.organizations import list_all_users

        db = Mock()
        user = Mock(is_superadmin=False, organizations=[])

        result = await list_all_users(current_user=user, db=db)
        assert result == []


class TestUpdateUserSuperadminStatus:
    """Tests for update_user_superadmin_status endpoint."""

    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self):
        from routers.organizations import update_user_superadmin_status, UserSuperadminUpdate

        db = Mock()
        user = Mock(is_superadmin=False)

        with pytest.raises(HTTPException) as exc_info:
            await update_user_superadmin_status(
                user_id="user-1",
                superadmin_update=UserSuperadminUpdate(is_superadmin=True),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        from routers.organizations import update_user_superadmin_status, UserSuperadminUpdate

        db = Mock()
        user = Mock(is_superadmin=True)
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_user_superadmin_status(
                user_id="user-1",
                superadmin_update=UserSuperadminUpdate(is_superadmin=True),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404


class TestDeleteUser:
    """Tests for delete_user endpoint."""

    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self):
        from routers.organizations import delete_user

        db = Mock()
        user = Mock(is_superadmin=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-1", current_user=user, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        from routers.organizations import delete_user

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        db.execute.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_self(self):
        from routers.organizations import delete_user

        db = Mock()
        user = Mock(is_superadmin=True, id="user-1")
        result = Mock(email="test@test.com", is_superadmin=False)
        db.execute.return_value.first.return_value = result

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-1", current_user=user, db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_delete_last_superadmin(self):
        from routers.organizations import delete_user

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        result = Mock(email="test@test.com", is_superadmin=True)

        # First execute returns user, second returns superadmin count
        call_count = [0]
        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = Mock()
            if call_count[0] == 1:
                mock_result.first.return_value = result
            else:
                mock_result.scalar.return_value = 1
            return mock_result
        db.execute.side_effect = execute_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(user_id="user-2", current_user=user, db=db)
        assert exc_info.value.status_code == 400


class TestAddUserToOrganization:
    """Tests for add_user_to_organization endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id="org-1",
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_org_not_found(self):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = None  # org not found
            return q
        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id="org-1",
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        org = Mock()

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org  # org found
            elif call_count[0] == 2:
                q.first.return_value = None  # user not found
            return q
        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id="org-1",
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_member(self):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        db = Mock()
        user = Mock(is_superadmin=True, id="admin-1")
        org = Mock()
        target_user = Mock()
        existing_mem = Mock()

        call_count = [0]
        def query_side_effect(*args):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count[0] == 1:
                q.first.return_value = org
            elif call_count[0] == 2:
                q.first.return_value = target_user
            elif call_count[0] == 3:
                q.first.return_value = existing_mem
            return q
        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id="org-1",
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestVerifyMemberEmail:
    """Tests for verify_member_email endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        from routers.organizations import verify_member_email, VerifyEmailRequest

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await verify_member_email(
                organization_id="org-1",
                user_id="user-2",
                request=VerifyEmailRequest(),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403


class TestBulkVerifyMemberEmails:
    """Tests for bulk_verify_member_emails endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_denied(self):
        from routers.organizations import bulk_verify_member_emails, BulkVerifyEmailRequest

        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await bulk_verify_member_emails(
                organization_id="org-1",
                request=BulkVerifyEmailRequest(user_ids=["u1", "u2"]),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403
