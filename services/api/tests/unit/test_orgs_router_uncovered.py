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

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from models import OrganizationRole


# ---------------------------------------------------------------------------
# Async-db mock helpers
#
# The handlers under test were migrated to the async lane: each does
# ``result = await db.execute(stmt)`` then unpacks via
# ``result.scalar_one_or_none()`` / ``result.scalars().all()`` /
# ``result.scalar()`` / ``result.all()``. These helpers build result-mocks
# shaped to match that access, and wire ``db.execute`` as an AsyncMock whose
# side_effect yields them in call order.
# ---------------------------------------------------------------------------


def _result(
    scalar_one_or_none=None,
    scalars_all=None,
    scalar=None,
    all_=None,
):
    """Build a mock mirroring the object returned by ``await db.execute(stmt)``."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar_one_or_none
    res.scalars.return_value.all.return_value = scalars_all or []
    res.scalar.return_value = scalar
    res.all.return_value = all_ or []
    return res


def _async_db(execute_results):
    """Create a MagicMock db whose async surface is wired for the handlers.

    ``execute_results`` is a list of result-mocks (from ``_result``) returned
    by successive ``await db.execute(...)`` calls, in call order.
    """
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    # The org-management permission check runs ``can_manage_organization`` on a
    # sync session bridged via ``await db.run_sync(lambda s: ...)``. Default to
    # invoking the lambda with a stub sync session (superadmin -> True without a
    # query; a non-superadmin's MagicMock membership query is truthy -> True).
    # Authz-DENY tests override this with ``AsyncMock(return_value=False)``.
    db.run_sync = AsyncMock(side_effect=lambda fn, *a, **k: fn(MagicMock()))
    return db


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

        user = Mock(is_superadmin=True, id="admin-1")

        org = _make_org_obj()
        membership = Mock()
        membership.role = OrganizationRole.ORG_ADMIN

        # Superadmin path: org lookup, member count, user_membership lookup.
        db = _async_db([
            _result(scalar_one_or_none=org),
            _result(scalar=5),
            _result(scalar_one_or_none=membership),
        ])

        result = await get_organization_by_slug(
            slug="test-org", current_user=user, db=db,
        )
        assert result.id == "org-1"
        assert result.member_count == 5

    @pytest.mark.asyncio
    async def test_member_access(self):
        """Cover lines 320-332: non-superadmin member gets org."""
        from routers.organizations import get_organization_by_slug

        user = Mock(is_superadmin=False, id="user-1")

        org = _make_org_obj()
        membership = Mock()
        membership.role = OrganizationRole.ANNOTATOR

        # Non-superadmin path: org lookup, access-membership check, member
        # count, user_membership lookup.
        db = _async_db([
            _result(scalar_one_or_none=org),
            _result(scalar_one_or_none=membership),
            _result(scalar=3),
            _result(scalar_one_or_none=membership),
        ])

        result = await get_organization_by_slug(
            slug="test-org", current_user=user, db=db,
        )
        assert result.id == "org-1"

    @pytest.mark.asyncio
    async def test_slug_not_found(self):
        """Cover: org not found by slug."""
        from routers.organizations import get_organization_by_slug

        user = Mock(is_superadmin=True, id="admin-1")
        db = _async_db([_result(scalar_one_or_none=None)])

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(slug="missing", current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_denied(self):
        """Cover: non-superadmin, non-member denied."""
        from routers.organizations import get_organization_by_slug

        user = Mock(is_superadmin=False, id="user-1")

        org = _make_org_obj()
        # org lookup succeeds, access-membership check returns None -> 403.
        db = _async_db([
            _result(scalar_one_or_none=org),
            _result(scalar_one_or_none=None),
        ])

        with pytest.raises(HTTPException) as exc_info:
            await get_organization_by_slug(slug="test-org", current_user=user, db=db)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# update_organization: success path (lines 430-456)
# ---------------------------------------------------------------------------


class TestUpdateOrganizationSuccess:
    @pytest.mark.asyncio
    @patch("routers.organizations.crud.can_manage_organization", return_value=True)
    async def test_update_org_success(self, mock_can_manage):
        """Cover lines 430-456: successful org update."""
        from routers.organizations import update_organization, OrganizationUpdate

        user = Mock(is_superadmin=True, id="admin-1")

        org = _make_org_obj()
        org.name = "Old Name"

        # Handler order: org lookup (scalar_one_or_none), then member count
        # (scalar). The permission check is bridged through ``db.run_sync``.
        db = _async_db([
            _result(scalar_one_or_none=org),
            _result(scalar=3),
        ])

        # ``can_manage_organization`` runs on a sync session via db.run_sync;
        # invoke the passed lambda with a stub sync session so the patched
        # helper (return_value=True) is exercised.
        async def _run_sync(fn, *args, **kwargs):
            return fn(MagicMock())

        db.run_sync = AsyncMock(side_effect=_run_sync)

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

        # Superadmin path: single ``await db.execute(...).all()`` yielding
        # (membership, user) row tuples.
        db = _async_db([_result(all_=[(member_mock, user_mock)])])

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

        user = Mock(is_superadmin=True, id="admin-1")

        target_membership = Mock()
        target_membership.role = OrganizationRole.ANNOTATOR

        # Superadmin path: target_membership lookup then commit.
        db = _async_db([_result(scalar_one_or_none=target_membership)])

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

        user = Mock(is_superadmin=True, id="admin-1")

        target_membership = Mock()
        target_membership.is_active = True

        # Superadmin path: target_membership lookup then commit.
        db = _async_db([_result(scalar_one_or_none=target_membership)])

        result = await remove_member(
            organization_id="org-1",
            user_id="user-2",
            current_user=user,
            db=db,
        )
        assert result["message"] == "Member removed from organization successfully"
        assert target_membership.is_active == False  # noqa: E712


# ---------------------------------------------------------------------------
# list_all_users: with org filtering (lines 715-724)
# ---------------------------------------------------------------------------


class TestListAllUsersOrgFiltering:
    @pytest.mark.asyncio
    async def test_non_superadmin_with_orgs(self):
        """Cover lines 708-724: non-superadmin sees org users."""
        from routers.organizations import list_all_users

        user = Mock(is_superadmin=False, id="user-1", organizations=[{"id": "org-1"}])

        u1 = Mock()
        u1.__dict__ = {
            "id": "u1", "username": "user1", "email": "u1@test.com",
            "email_verified": True, "email_verification_method": "link",
            "name": "User 1", "is_superadmin": False, "is_active": True,
            "created_at": datetime(2025, 1, 1), "updated_at": None,
        }

        # Non-superadmin path: subqueries are built into the statement (pure
        # SQLAlchemy, no execute), then a single ``await db.execute(stmt)``
        # whose ``.scalars().all()`` yields the User rows. ``search`` defaults
        # to None so the ilike branch is skipped.
        db = _async_db([_result(scalars_all=[u1])])

        # `limit` is a FastAPI Query(...) default; when calling the handler
        # directly (no FastAPI param resolution) it must be passed an int,
        # else the Query sentinel leaks into `.limit()` and SQLAlchemy raises.
        result = await list_all_users(current_user=user, db=db, search=None, limit=500)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_superadmin_sees_all(self):
        """Cover: superadmin lists all users."""
        from routers.organizations import list_all_users

        user = Mock(is_superadmin=True, id="admin-1")

        u1 = Mock()
        u1.__dict__ = {
            "id": "u1", "username": "user1", "email": "u1@test.com",
            "email_verified": True, "email_verification_method": "link",
            "name": "User 1", "is_superadmin": False, "is_active": True,
            "created_at": datetime(2025, 1, 1), "updated_at": None,
        }

        # Superadmin path: single ``await db.execute(stmt).scalars().all()``.
        db = _async_db([_result(scalars_all=[u1])])

        # `limit` is a FastAPI Query(...) default; when calling the handler
        # directly (no FastAPI param resolution) it must be passed an int,
        # else the Query sentinel leaks into `.limit()` and SQLAlchemy raises.
        result = await list_all_users(current_user=user, db=db, search=None, limit=500)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# update_user_superadmin_status: success (lines 750-757)
# ---------------------------------------------------------------------------


class TestUpdateSuperadminStatusSuccess:
    @pytest.mark.asyncio
    async def test_promote_user(self):
        """Cover lines 749-768: successful superadmin promotion."""
        from routers.organizations import update_user_superadmin_status, UserSuperadminUpdate

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

        # Single user lookup (scalar_one_or_none) then commit/refresh.
        db = _async_db([_result(scalar_one_or_none=target_user)])

        result = await update_user_superadmin_status(
            user_id="user-1",
            superadmin_update=UserSuperadminUpdate(is_superadmin=True),
            current_user=admin,
            db=db,
        )
        assert target_user.is_superadmin == True  # noqa: E712
        assert result.is_superadmin == True  # noqa: E712


# ---------------------------------------------------------------------------
# delete_user: full success (lines 819-915)
# ---------------------------------------------------------------------------


class TestDeleteUserSuccess:
    @pytest.mark.asyncio
    async def test_delete_regular_user(self):
        """The endpoint delegates to the canonical user_service.delete_user."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")

        user_result = Mock(email="target@test.com", is_superadmin=False)
        db.execute.return_value.first.return_value = user_result

        with patch(
            "routers.organizations.manage.delete_user_service", return_value=True
        ) as svc:
            result = await delete_user(user_id="user-2", current_user=admin, db=db)

        svc.assert_called_once_with(db, "user-2")
        assert result["message"] == "User deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_user_service_reports_not_found(self):
        """A False return from the canonical service surfaces as a 404."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")
        db.execute.return_value.first.return_value = Mock(
            email="target@test.com", is_superadmin=False
        )

        with patch("routers.organizations.manage.delete_user_service", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await delete_user(user_id="user-2", current_user=admin, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_critical_failure(self):
        """An unexpected error inside the service bubbles up as a 500."""
        from routers.organizations import delete_user

        db = MagicMock()
        admin = Mock(is_superadmin=True, id="admin-1")
        db.execute.return_value.first.return_value = Mock(
            email="target@test.com", is_superadmin=False
        )

        with patch(
            "routers.organizations.manage.delete_user_service",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_user(user_id="user-2", current_user=admin, db=db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_user_outer_exception(self):
        """An error during the pre-delegation user lookup surfaces as a 500."""
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

        admin = Mock(is_superadmin=True, id="admin-1")
        org = Mock()
        target_user = Mock()

        # Superadmin path: org lookup, user lookup, existing-membership lookup
        # (None -> new membership created), then db.add + commit.
        db = _async_db([
            _result(scalar_one_or_none=org),
            _result(scalar_one_or_none=target_user),
            _result(scalar_one_or_none=None),
        ])

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

        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = True
        user_to_verify.email_verified_by_id = "prev-admin"
        user_to_verify.email_verification_method = "link"

        # Superadmin path: single user_to_verify lookup; already verified
        # returns early before any commit.
        db = _async_db([_result(scalar_one_or_none=user_to_verify)])

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

        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = False

        # Superadmin path: single user_to_verify lookup, then commit.
        db = _async_db([_result(scalar_one_or_none=user_to_verify)])

        result = await verify_member_email(
            organization_id="org-1",
            user_id="user-1",
            request=VerifyEmailRequest(reason="Manual verification"),
            current_user=admin,
            db=db,
        )
        assert result["message"] == "Email verified successfully"
        assert user_to_verify.email_verified == True  # noqa: E712
        assert user_to_verify.email_verification_method == "admin"

    @pytest.mark.asyncio
    async def test_verify_non_member_non_superadmin(self):
        """Cover lines 1058-1073: non-superadmin checks membership."""
        from routers.organizations import verify_member_email, VerifyEmailRequest

        user = Mock(is_superadmin=False, id="admin-1", email="admin@test.com")

        user_to_verify = Mock()
        user_to_verify.email = "user@test.com"
        user_to_verify.email_verified = False

        # Non-superadmin path: the admin-role authz check now runs via
        # ``db.run_sync`` (default-wired to pass for this admin user), NOT via
        # ``db.execute``. The remaining execute calls are the target-is-member
        # check, then the user_to_verify lookup, then commit.
        db = _async_db([
            _result(scalar_one_or_none=Mock()),
            _result(scalar_one_or_none=user_to_verify),
        ])

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

        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        # Superadmin path: single user lookup returns None -> 404.
        db = _async_db([_result(scalar_one_or_none=None)])

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

        user = Mock(is_superadmin=False, id="admin-1", email="admin@test.com")

        admin_membership = Mock()

        # Non-superadmin path: admin-role check passes, target-member check
        # returns None -> 404.
        db = _async_db([
            _result(scalar_one_or_none=admin_membership),
            _result(scalar_one_or_none=None),
        ])

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

        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        # user1: already verified (skip)
        user1 = Mock()
        user1.email = "u1@test.com"
        user1.email_verified = True

        # user2: unverified (success)
        user2 = Mock()
        user2.email = "u2@test.com"
        user2.email_verified = False

        # Superadmin path: per-user the member check is skipped, so one
        # user-lookup execute per id: user1 (skip), user2 (success), None
        # (error). Then a single commit.
        db = _async_db([
            _result(scalar_one_or_none=user1),
            _result(scalar_one_or_none=user2),
            _result(scalar_one_or_none=None),
        ])

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

        user = Mock(is_superadmin=False, id="org-admin-1", email="oadmin@test.com")

        admin_membership = Mock()

        # Non-superadmin path: admin-role check, then per-user member check
        # (None -> error). One user id -> 2 executes, then commit.
        db = _async_db([
            _result(scalar_one_or_none=admin_membership),
            _result(scalar_one_or_none=None),
        ])

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

        admin = Mock(is_superadmin=True, id="admin-1", email="admin@test.com")

        user1 = Mock()
        user1.email = "u1@test.com"
        user1.email_verified = False

        # Superadmin path: single user lookup (unverified -> success), commit.
        db = _async_db([_result(scalar_one_or_none=user1)])

        result = await bulk_verify_member_emails(
            organization_id="org-1",
            request=BulkVerifyEmailRequest(user_ids=["user-1"], reason="Test"),
            current_user=admin,
            db=db,
        )
        assert result["summary"]["success"] == 1
        assert user1.email_verified == True  # noqa: E712
        assert user1.email_verification_method == "admin"
