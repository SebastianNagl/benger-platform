"""
Unit/branch tests for routers/organizations/*.

The CRUD + member + manage handlers were migrated to the async DB lane, so the
old ``Mock().query(...).filter(...).first()`` doubles no longer match the
handler call shape (handlers now do ``await db.execute(select(...))`` and bridge
sync helpers via ``await db.run_sync(...)``). Those tests are rewritten to drive
the real handler coroutines against a real ``async_test_db`` AsyncSession, with
rows seeded in-test (SAVEPOINT isolation). This still exercises the same
error/permission branches without the HTTP layer.

Two things stay on plain ``Mock``:
  * the sync permission helpers ``can_manage_organization`` /
    ``can_create_organization`` (still synchronous, unchanged);
  * ``delete_user`` — kept SYNC (dominated by the self-committing sync-only
    ``user_service.delete_user``); its early-guard branches still take a plain
    sync ``Mock`` db whose ``db.execute(text(...)).first()/.scalar()`` shape
    matches the unchanged handler.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from models import Organization, OrganizationMembership, OrganizationRole, User
from routers.organizations import (
    can_manage_organization,
    can_create_organization,
)


# ============= helpers (real async seeding) =============

def _uid() -> str:
    return str(uuid.uuid4())


async def _make_user(db, *, is_superadmin=False, email_verified=True) -> User:
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}@test.com",
        email=f"u-{_uid()[:8]}@test.com",
        name="Unit User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=email_verified,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Unit Org", slug=None) -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"unit-{uuid.uuid4().hex[:8]}",
        display_name=name,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _membership(db, user_id, org_id, role="ANNOTATOR", is_active=True):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            is_active=is_active,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


def _pyd_user(db_user: User):
    """Build the auth Pydantic User the handlers receive as current_user."""
    from auth_module.models import User as AuthUser

    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


# ============= can_manage_organization (sync helper, unchanged) =============


class TestCanManageOrganization:
    """Tests for can_manage_organization."""

    def test_none_user(self):
        db = Mock()
        assert can_manage_organization(None, "org-1", db) == False  # noqa: E712

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True)
        assert can_manage_organization(user, "org-1", db) == True  # noqa: E712

    def test_org_admin_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_manage_organization(user, "org-1", db) == True  # noqa: E712

    def test_non_admin_member(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_manage_organization(user, "org-1", db) == False  # noqa: E712


# ============= can_create_organization (sync helper, unchanged) =============


class TestCanCreateOrganization:
    """Tests for can_create_organization."""

    def test_none_user(self):
        db = Mock()
        assert can_create_organization(None, db) == False  # noqa: E712

    def test_superadmin(self):
        db = Mock()
        user = Mock(is_superadmin=True)
        assert can_create_organization(user, db) == True  # noqa: E712

    def test_org_admin_of_any_org(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        membership = Mock()
        db.query.return_value.filter.return_value.first.return_value = membership
        assert can_create_organization(user, db) == True  # noqa: E712

    def test_no_admin_membership(self):
        db = Mock()
        user = Mock(is_superadmin=False, id="user-1")
        db.query.return_value.filter.return_value.first.return_value = None
        assert can_create_organization(user, db) == False  # noqa: E712


# ============= list_organizations (async) =============


class TestListOrganizations:
    @pytest.mark.asyncio
    async def test_superadmin_sees_all(self, async_test_db):
        from routers.organizations import list_organizations

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, name="Org 1")
        member = await _make_user(async_test_db)
        await _membership(async_test_db, member.id, org.id, "ANNOTATOR")
        await async_test_db.commit()

        result = await list_organizations(current_user=_pyd_user(admin), db=async_test_db)
        ids = {r.id for r in result}
        assert org.id in ids
        target = next(r for r in result if r.id == org.id)
        assert target.member_count == 1

    @pytest.mark.asyncio
    async def test_regular_user_sees_own_orgs(self, async_test_db):
        from routers.organizations import list_organizations

        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db, name="Org 1")
        await _membership(async_test_db, user.id, org.id, "ANNOTATOR")
        await async_test_db.commit()

        result = await list_organizations(current_user=_pyd_user(user), db=async_test_db)
        assert len(result) == 1
        assert result[0].role == OrganizationRole.ANNOTATOR

    @pytest.mark.asyncio
    async def test_regular_user_no_orgs(self, async_test_db):
        from routers.organizations import list_organizations

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        result = await list_organizations(current_user=_pyd_user(user), db=async_test_db)
        assert result == []


# ============= create_organization (async) =============


class TestCreateOrganization:
    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_db):
        from routers.organizations import create_organization, OrganizationCreate

        user = await _make_user(async_test_db)  # non-superadmin, no admin membership
        await async_test_db.commit()
        org = OrganizationCreate(name="New Org", display_name="New Org", slug="new-org")

        with pytest.raises(HTTPException) as exc_info:
            await create_organization(
                organization=org, current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_slug(self, async_test_db):
        from routers.organizations import create_organization, OrganizationCreate

        admin = await _make_user(async_test_db, is_superadmin=True)
        existing = await _make_org(async_test_db, slug="existing-slug")
        await async_test_db.commit()

        org = OrganizationCreate(
            name="New Org", display_name="New Org", slug=existing.slug
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_organization(
                organization=org, current_user=_pyd_user(admin), db=async_test_db
            )
        assert exc_info.value.status_code == 400


# ============= get_organization_by_slug (async) =============


class TestGetOrganizationBySlug:
    @pytest.mark.asyncio
    async def test_invalid_slug_format(self, async_test_db):
        from routers.organizations import get_organization_by_slug

        user = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug="INVALID_SLUG!", current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_org_not_found(self, async_test_db):
        from routers.organizations import get_organization_by_slug

        user = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug="unknown-slug", current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_access_denied(self, async_test_db):
        from routers.organizations import get_organization_by_slug

        user = await _make_user(async_test_db)  # non-superadmin, no membership
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(
                slug=org.slug, current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 403


# ============= get_organization (async) =============


class TestGetOrganization:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.organizations import get_organization

        user = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_organization(
                organization_id="org-1", current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.organizations import get_organization

        user = await _make_user(async_test_db)  # non-superadmin, no membership
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_organization(
                organization_id=org.id, current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 403


# ============= update_organization (async) =============


class TestUpdateOrganization:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.organizations import update_organization, OrganizationUpdate

        user = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        update = OrganizationUpdate(name="New Name")
        with pytest.raises(HTTPException) as exc_info:
            await update_organization(
                organization_id="org-1",
                update_data=update,
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_db):
        from routers.organizations import update_organization, OrganizationUpdate

        user = await _make_user(async_test_db)  # non-superadmin, not org admin
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        update = OrganizationUpdate(name="New Name")
        with pytest.raises(HTTPException) as exc_info:
            await update_organization(
                organization_id=org.id,
                update_data=update,
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403


# ============= delete_organization (async) =============


class TestDeleteOrganization:
    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self, async_test_db):
        from routers.organizations import delete_organization

        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await delete_organization(
                organization_id="org-1", current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.organizations import delete_organization

        user = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await delete_organization(
                organization_id="org-1", current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_delete(self, async_test_db):
        from routers.organizations import delete_organization

        user = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with patch("redis_cache.OrgSlugCache"):
            result = await delete_organization(
                organization_id=org.id, current_user=_pyd_user(user), db=async_test_db
            )
        assert result["message"] == "Organization deleted successfully"
        # Reload to confirm the soft-delete persisted.
        from sqlalchemy import select

        refreshed = (
            await async_test_db.execute(select(Organization).where(Organization.id == org.id))
        ).scalar_one()
        assert refreshed.is_active is False


# ============= list_organization_members (async) =============


class TestListOrganizationMembers:
    @pytest.mark.asyncio
    async def test_non_member_denied(self, async_test_db):
        from routers.organizations import list_organization_members

        user = await _make_user(async_test_db)  # non-superadmin, no membership
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await list_organization_members(
                organization_id=org.id, current_user=_pyd_user(user), db=async_test_db
            )
        assert exc_info.value.status_code == 403


# ============= update_member_role (async) =============


class TestUpdateMemberRole:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, async_test_db):
        from routers.organizations import update_member_role, UpdateMemberRole

        user = await _make_user(async_test_db)  # non-superadmin, not org admin
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id=org.id,
                user_id="user-2",
                role_update=UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR),
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_not_found(self, async_test_db):
        from routers.organizations import update_member_role, UpdateMemberRole

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id=org.id,
                user_id="user-2",
                role_update=UpdateMemberRole(role=OrganizationRole.CONTRIBUTOR),
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_modify_own_role(self, async_test_db):
        from routers.organizations import update_member_role, UpdateMemberRole

        # org_admin (non-superadmin) targeting their own membership.
        org_admin = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await _membership(async_test_db, org_admin.id, org.id, "ORG_ADMIN")
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await update_member_role(
                organization_id=org.id,
                user_id=org_admin.id,  # same as current user
                role_update=UpdateMemberRole(role=OrganizationRole.ANNOTATOR),
                current_user=_pyd_user(org_admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 400


# ============= remove_member (async) =============


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, async_test_db):
        from routers.organizations import remove_member

        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id=org.id,
                user_id="user-2",
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_not_found(self, async_test_db):
        from routers.organizations import remove_member

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id=org.id,
                user_id="user-2",
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_remove_self(self, async_test_db):
        from routers.organizations import remove_member

        org_admin = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await _membership(async_test_db, org_admin.id, org.id, "ORG_ADMIN")
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await remove_member(
                organization_id=org.id,
                user_id=org_admin.id,
                current_user=_pyd_user(org_admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 400


# ============= list_all_users (async) =============


class TestListAllUsers:
    @pytest.mark.asyncio
    async def test_unauthenticated(self, async_test_db):
        from routers.organizations import list_all_users

        with pytest.raises(HTTPException) as exc_info:
            await list_all_users(current_user=None, db=async_test_db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_superadmin_all_users(self, async_test_db):
        from routers.organizations import list_all_users

        admin = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db)
        await async_test_db.commit()

        result = await list_all_users(
            current_user=_pyd_user(admin), db=async_test_db, search=None, limit=500
        )
        ids = {u.id for u in result}
        assert admin.id in ids
        assert other.id in ids

    @pytest.mark.asyncio
    async def test_regular_user_no_orgs(self, async_test_db):
        from auth_module.models import User as AuthUser
        from routers.organizations import list_all_users

        user = await _make_user(async_test_db)
        await async_test_db.commit()
        # Non-superadmin auth User with no organizations -> early empty return.
        auth_user = AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            name=user.name,
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=user.created_at or datetime.now(timezone.utc),
            organizations=[],
        )
        result = await list_all_users(current_user=auth_user, db=async_test_db)
        assert result == []


# ============= update_user_superadmin_status (async) =============


class TestUpdateUserSuperadminStatus:
    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self, async_test_db):
        from routers.organizations import (
            update_user_superadmin_status,
            UserSuperadminUpdate,
        )

        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await update_user_superadmin_status(
                user_id="user-1",
                superadmin_update=UserSuperadminUpdate(is_superadmin=True),
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_db):
        from routers.organizations import (
            update_user_superadmin_status,
            UserSuperadminUpdate,
        )

        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await update_user_superadmin_status(
                user_id="user-1",
                superadmin_update=UserSuperadminUpdate(is_superadmin=True),
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404


# ============= delete_user (SYNC handler — plain Mock db, unchanged) =============


class TestDeleteUser:
    """delete_user stays SYNC; its early-guard branches still take a plain sync
    Mock db whose ``db.execute(text(...)).first()/.scalar()`` shape matches the
    unchanged handler."""

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


# ============= add_user_to_organization (async) =============


class TestAddUserToOrganization:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, async_test_db):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id=org.id,
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_org_not_found(self, async_test_db):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id="org-1",
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_db):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id=org.id,
                add_user=AddUserToOrganization(user_id="user-2"),
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_member(self, async_test_db):
        from routers.organizations import add_user_to_organization, AddUserToOrganization

        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        target = await _make_user(async_test_db)
        await _membership(async_test_db, target.id, org.id, "ANNOTATOR", is_active=True)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await add_user_to_organization(
                organization_id=org.id,
                add_user=AddUserToOrganization(user_id=target.id),
                current_user=_pyd_user(admin),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 400


# ============= verify_member_email (async) =============


class TestVerifyMemberEmail:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, async_test_db):
        from routers.organizations import verify_member_email, VerifyEmailRequest

        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await verify_member_email(
                organization_id=org.id,
                user_id="user-2",
                request=VerifyEmailRequest(),
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403


# ============= bulk_verify_member_emails (async) =============


class TestBulkVerifyMemberEmails:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, async_test_db):
        from routers.organizations import (
            bulk_verify_member_emails,
            BulkVerifyEmailRequest,
        )

        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await bulk_verify_member_emails(
                organization_id=org.id,
                request=BulkVerifyEmailRequest(user_ids=["u1", "u2"]),
                current_user=_pyd_user(user),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 403
