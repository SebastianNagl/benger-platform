"""
Coverage boost tests for organization endpoints.

Targets branches in routers/organizations/* (migrated to the async DB lane):
- list_organizations for superadmin vs regular user
- create_organization with various inputs
- get_organization
- update_organization
- delete_organization
- list/add/update/remove members

The handlers use ``Depends(get_async_db)``, so rows are seeded via
``async_test_db`` and the HTTP surface is driven through ``async_test_client``,
with both auth dependencies overridden per-test via ``_as_user`` (the sync auth
deps can't see the async test transaction).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, *, is_superadmin=False, prefix="boost") -> User:
    u = User(
        id=_uid(),
        username=f"{prefix}-{_uid()[:8]}@test.com",
        email=f"{prefix}-{_uid()[:8]}@test.com",
        name="Boost User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name="Test Org", slug=None) -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        slug=slug or f"test-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        description="test org",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user_id, org_id, role="ORG_ADMIN"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


class TestListOrganizations:
    """Test list_organizations endpoint."""

    @pytest.mark.asyncio
    async def test_list_orgs_superadmin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_org(async_test_db, "Org A")
        await _make_org(async_test_db, "Org B")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    @pytest.mark.asyncio
    async def test_list_orgs_regular_user(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "My Org")
        await _add_membership(async_test_db, user.id, org.id, "CONTRIBUTOR")
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        names = [o["name"] for o in data]
        assert "My Org" in names

    @pytest.mark.asyncio
    async def test_list_orgs_no_memberships(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/organizations/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orgs_superadmin_with_role(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Admin Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        admin_orgs = [o for o in data if o["name"] == "Admin Org"]
        assert len(admin_orgs) >= 1

    @pytest.mark.asyncio
    async def test_list_orgs_member_counts(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        u1 = await _make_user(async_test_db)
        u2 = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Count Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await _add_membership(async_test_db, u1.id, org.id, "CONTRIBUTOR")
        await _add_membership(async_test_db, u2.id, org.id, "ANNOTATOR")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        count_orgs = [o for o in data if o["name"] == "Count Org"]
        assert len(count_orgs) >= 1
        assert count_orgs[0]["member_count"] == 3


class TestCreateOrganization:
    """Test create_organization endpoint."""

    @pytest.mark.asyncio
    async def test_create_org_superadmin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        slug = f"new-org-{uuid.uuid4().hex[:8]}"
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "New Organization",
                    "display_name": "New Organization Display",
                    "slug": slug,
                    "description": "A brand new org",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Organization"
        assert data["slug"] == slug

    @pytest.mark.asyncio
    async def test_create_org_with_settings(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        slug = f"settings-org-{uuid.uuid4().hex[:8]}"
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "Settings Org",
                    "display_name": "Settings Org Display",
                    "slug": slug,
                    "settings": {"theme": "dark", "language": "de"},
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_org_duplicate_slug(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        slug = f"dup-slug-{uuid.uuid4().hex[:8]}"
        await _make_org(async_test_db, "First", slug)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "Second",
                    "display_name": "Second Display",
                    "slug": slug,
                },
            )
        assert resp.status_code in [400, 409, 500]

    @pytest.mark.asyncio
    async def test_create_org_invalid_slug(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "Invalid Slug",
                    "display_name": "Invalid Slug Display",
                    "slug": "INVALID SLUG WITH SPACES",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_org_annotator_forbidden(self, async_test_client, async_test_db):
        # Non-superadmin with no ORG_ADMIN membership anywhere -> 403.
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "Forbidden",
                    "display_name": "Forbidden Display",
                    "slug": f"forbidden-{uuid.uuid4().hex[:8]}",
                },
            )
        assert resp.status_code == 403


class TestGetOrganization:
    """Test get_organization endpoint."""

    @pytest.mark.asyncio
    async def test_get_org_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Get Org")
        await _add_membership(async_test_db, admin.id, org.id)
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/organizations/{oid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Org"

    @pytest.mark.asyncio
    async def test_get_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_org_by_slug(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        slug = f"slug-get-{uuid.uuid4().hex[:8]}"
        org = await _make_org(async_test_db, "Slug Org", slug)
        await _add_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/organizations/by-slug/{slug}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == slug

    @pytest.mark.asyncio
    async def test_get_org_by_slug_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/by-slug/nonexistent")
        assert resp.status_code == 404


class TestUpdateOrganization:
    """Test update_organization endpoint."""

    @pytest.mark.asyncio
    async def test_update_org_name(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Update Org")
        await _add_membership(async_test_db, admin.id, org.id)
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}",
                json={"name": "Updated Org"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Org"

    @pytest.mark.asyncio
    async def test_update_org_description(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Desc Org")
        await _add_membership(async_test_db, admin.id, org.id)
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}",
                json={"description": "New description"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_org_settings(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Settings Update")
        await _add_membership(async_test_db, admin.id, org.id)
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}",
                json={"settings": {"key": "value"}},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                "/api/organizations/nonexistent",
                json={"name": "X"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_org_no_permission(self, async_test_client, async_test_db):
        annotator = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "No Perm Org")
        await _add_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        oid = org.id
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}",
                json={"name": "Hacked"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_deactivate_org(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Deactivate Org")
        await _add_membership(async_test_db, admin.id, org.id)
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}",
                json={"is_active": False},
            )
        assert resp.status_code == 200
        assert resp.json()["is_active"] == False  # noqa: E712


class TestDeleteOrganization:
    """Test delete_organization endpoint."""

    @pytest.mark.asyncio
    async def test_delete_org_superadmin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "Delete Org")
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(f"/api/organizations/{oid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete("/api/organizations/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_org_not_superadmin(self, async_test_client, async_test_db):
        contributor = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "No Delete")
        await _add_membership(async_test_db, contributor.id, org.id, "CONTRIBUTOR")
        oid = org.id
        await async_test_db.commit()
        with _as_user(contributor):
            resp = await async_test_client.delete(f"/api/organizations/{oid}")
        assert resp.status_code == 403


class TestListOrgMembers:
    """Test list_organization_members endpoint."""

    @pytest.mark.asyncio
    async def test_list_members(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        u1 = await _make_user(async_test_db)
        u2 = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Members Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await _add_membership(async_test_db, u1.id, org.id, "CONTRIBUTOR")
        await _add_membership(async_test_db, u2.id, org.id, "ANNOTATOR")
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/organizations/{oid}/members")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

    @pytest.mark.asyncio
    async def test_list_members_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/organizations/nonexistent/members")
        # Superadmin may get empty list or 404 depending on implementation
        assert resp.status_code in [200, 404]


class TestAddOrgMember:
    """Test add_organization_member endpoint."""

    @pytest.mark.asyncio
    async def test_add_member_as_admin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Add Member Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        oid, tid = org.id, target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/organizations/{oid}/members",
                json={"user_id": tid, "role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_add_member_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        tid = target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/organizations/nonexistent/members",
                json={"user_id": tid, "role": "ANNOTATOR"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_member_user_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "No User Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/organizations/{oid}/members",
                json={"user_id": "nonexistent-user-id", "role": "ANNOTATOR"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_duplicate_member(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Dup Member Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await _add_membership(async_test_db, target.id, org.id, "ANNOTATOR")
        oid, tid = org.id, target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/organizations/{oid}/members",
                json={"user_id": tid, "role": "CONTRIBUTOR"},
            )
        assert resp.status_code in [400, 409]


class TestUpdateMemberRole:
    """Test update_member_role endpoint."""

    @pytest.mark.asyncio
    async def test_update_role(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Update Role Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await _add_membership(async_test_db, target.id, org.id, "ANNOTATOR")
        oid, tid = org.id, target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/{oid}/members/{tid}/role",
                json={"role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_role_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        tid = target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/nonexistent/members/{tid}/role",
                json={"role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 404


class TestRemoveOrgMember:
    """Test remove_organization_member endpoint."""

    @pytest.mark.asyncio
    async def test_remove_member(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        org = await _make_org(async_test_db, "Remove Member Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await _add_membership(async_test_db, target.id, org.id, "ANNOTATOR")
        oid, tid = org.id, target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/organizations/{oid}/members/{tid}"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_member_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, "No Remove Org")
        await _add_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        oid = org.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/organizations/{oid}/members/nonexistent-user"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_member_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        target = await _make_user(async_test_db)
        tid = target.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/organizations/nonexistent/members/{tid}"
            )
        assert resp.status_code == 404
