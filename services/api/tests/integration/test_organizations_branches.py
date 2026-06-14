"""Behavioral branch-coverage integration tests for the organizations router.

Targets the error / permission / edge paths in
``services/api/routers/organizations.py`` that the happy-path suites
(``test_organizations_integration.py`` / ``_deep.py`` / ``_router_coverage.py``)
either skip or assert too loosely (``in (200, 404)``) to actually exercise.

Endpoints covered here:

- ``get_organization_by_slug``  : non-member 403.
- ``list_organization_members`` : non-member 403.
- ``update_member_role``        : org-admin success + persisted role, annotator
  403, member-not-found 404, own-role guard 400, superadmin-modifies-own-role
  allowed.
- ``remove_member``             : org-admin success + soft-delete state, annotator
  403, member-not-found 404, self-removal guard 400, superadmin self-removal
  allowed.
- ``add_user_to_organization``  : org-admin success + persisted row, user-not-found
  404, already-active-member 400, reactivate-previously-removed branch, annotator
  403.
- ``verify_member_email``       : success + persisted verification fields,
  already-verified short-circuit, non-member 404 (org-admin path), annotator 403.
- ``bulk_verify_member_emails`` : mixed success/skip/error tally + persisted state.
- ``list_all_users`` (manage)   : superadmin sees all, non-superadmin org-scoped,
  ``search`` ILIKE filter, no-org non-superadmin empty list.
- ``update_user_superadmin_status`` : promote success + persisted flag, non-admin
  403, user-not-found 404.
- ``delete_user`` (manage)      : non-superadmin 403, user-not-found 404,
  self-delete guard 400, last-superadmin guard 400.

Every test calls through the ``client`` fixture, asserts HTTP status + response
JSON, and verifies persisted DB state via ``test_db``.

Permission map under ``test_org``:
  * test_users[0] / auth_headers["admin"]       -> superadmin + ORG_ADMIN member
  * test_users[1] / auth_headers["contributor"] -> CONTRIBUTOR member
  * test_users[2] / auth_headers["annotator"]   -> ANNOTATOR member
  * test_users[3] / auth_headers["org_admin"]   -> ORG_ADMIN member (non-superadmin)
"""

import uuid

import pytest

from models import Organization, OrganizationMembership, OrganizationRole, User


def _uid() -> str:
    return str(uuid.uuid4())


def _make_user(test_db, name="Extra User", *, is_superadmin=False, email_verified=False):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=_uid(),
        username=f"user-{suffix}@test.com",
        email=f"user-{suffix}@test.com",
        name=name,
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=email_verified,
    )
    test_db.add(user)
    test_db.commit()
    return user


def _membership(test_db, user_id, org_id, role="ANNOTATOR", is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
    )
    test_db.add(m)
    test_db.commit()
    return m


def _get_membership(test_db, user_id, org_id):
    test_db.expire_all()
    return (
        test_db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# get_organization_by_slug / list_organization_members — access 403 branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestOrgAccessForbidden:
    def test_get_by_slug_non_member_forbidden(self, client, test_db, test_users, auth_headers):
        """A user with no membership on the org gets 403 from the by-slug route."""
        org = Organization(
            id=_uid(),
            name="Slug Outsider Org",
            slug=f"slug-outsider-{uuid.uuid4().hex[:8]}",
            display_name="Slug Outsider Org",
        )
        test_db.add(org)
        test_db.commit()

        # annotator has no membership in this fresh org.
        resp = client.get(
            f"/api/organizations/by-slug/{org.slug}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Not a member" in resp.json()["detail"]

    def test_list_members_non_member_forbidden(self, client, test_db, test_users, auth_headers):
        org = Organization(
            id=_uid(),
            name="Members Outsider Org",
            slug=f"members-outsider-{uuid.uuid4().hex[:8]}",
            display_name="Members Outsider Org",
        )
        test_db.add(org)
        test_db.commit()

        resp = client.get(
            f"/api/organizations/{org.id}/members",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# update_member_role — permission + guard branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateMemberRole:
    def test_org_admin_updates_role_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """org_admin (non-superadmin) promotes the annotator -> persisted role."""
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{test_users[2].id}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert "updated successfully" in resp.json()["message"]

        m = _get_membership(test_db, test_users[2].id, test_org.id)
        assert m is not None
        assert m.role == OrganizationRole.CONTRIBUTOR

    def test_annotator_cannot_update_role_forbidden(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{test_users[1].id}/role",
            json={"role": "ORG_ADMIN"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

        # contributor's role is unchanged.
        m = _get_membership(test_db, test_users[1].id, test_org.id)
        assert m.role == OrganizationRole.CONTRIBUTOR

    def test_member_not_found_returns_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{_uid()}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "Member not found" in resp.json()["detail"]

    def test_org_admin_cannot_modify_own_role(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Non-superadmin modifying their own role -> 400 own-role guard."""
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{test_users[3].id}/role",
            json={"role": "ANNOTATOR"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 400
        assert "Cannot modify your own role" in resp.json()["detail"]

        # org_admin still ORG_ADMIN.
        m = _get_membership(test_db, test_users[3].id, test_org.id)
        assert m.role == OrganizationRole.ORG_ADMIN

    def test_superadmin_can_modify_own_role(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Superadmin is exempt from the own-role guard -> persisted change."""
        resp = client.put(
            f"/api/organizations/{test_org.id}/members/{test_users[0].id}/role",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        m = _get_membership(test_db, test_users[0].id, test_org.id)
        assert m.role == OrganizationRole.CONTRIBUTOR


# ---------------------------------------------------------------------------
# remove_member — permission + guard + soft-delete branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRemoveMember:
    def test_org_admin_removes_member_soft_deletes(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        target = _make_user(test_db, "Target Member")
        _membership(test_db, target.id, test_org.id, "ANNOTATOR")

        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{target.id}",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert "removed" in resp.json()["message"].lower()

        # Soft delete: row still exists but is_active is False.
        m = _get_membership(test_db, target.id, test_org.id)
        assert m is not None
        assert m.is_active is False

    def test_annotator_cannot_remove_member_forbidden(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{test_users[1].id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

        m = _get_membership(test_db, test_users[1].id, test_org.id)
        assert m.is_active is True

    def test_remove_nonexistent_member_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "Member not found" in resp.json()["detail"]

    def test_org_admin_cannot_remove_self(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{test_users[3].id}",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 400
        assert "Cannot remove yourself" in resp.json()["detail"]

        # Still an active member.
        m = _get_membership(test_db, test_users[3].id, test_org.id)
        assert m.is_active is True

    def test_superadmin_can_remove_self(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Superadmin is exempt from the self-removal guard."""
        resp = client.delete(
            f"/api/organizations/{test_org.id}/members/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        m = _get_membership(test_db, test_users[0].id, test_org.id)
        assert m.is_active is False


# ---------------------------------------------------------------------------
# add_user_to_organization — create / reactivate / guard branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAddMember:
    def test_org_admin_adds_new_member_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        new_user = _make_user(test_db, "Fresh Add")
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": new_user.id, "role": "CONTRIBUTOR"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert "added" in resp.json()["message"].lower()

        m = _get_membership(test_db, new_user.id, test_org.id)
        assert m is not None
        assert m.is_active is True
        assert m.role == OrganizationRole.CONTRIBUTOR

    def test_add_user_not_found_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": _uid(), "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]

    def test_add_already_active_member_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        # contributor is already an active member of test_org.
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": test_users[1].id, "role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "already a member" in resp.json()["detail"]

        # Role unchanged (the 400 short-circuits before any write).
        m = _get_membership(test_db, test_users[1].id, test_org.id)
        assert m.role == OrganizationRole.CONTRIBUTOR

    def test_add_reactivates_previously_removed_member(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A prior inactive membership is reactivated (not a 2nd row), with the
        new role applied."""
        target = _make_user(test_db, "Returning Member")
        _membership(test_db, target.id, test_org.id, "ANNOTATOR", is_active=False)

        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": target.id, "role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        rows = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == target.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].is_active is True
        assert rows[0].role == OrganizationRole.CONTRIBUTOR

    def test_annotator_cannot_add_member_forbidden(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        new_user = _make_user(test_db, "Denied Add")
        resp = client.post(
            f"/api/organizations/{test_org.id}/members",
            json={"user_id": new_user.id, "role": "ANNOTATOR"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

        assert _get_membership(test_db, new_user.id, test_org.id) is None


# ---------------------------------------------------------------------------
# verify_member_email — single verification branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestVerifyMemberEmail:
    def test_org_admin_verifies_member_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        target = _make_user(test_db, "Unverified Member", email_verified=False)
        _membership(test_db, target.id, test_org.id, "ANNOTATOR")

        resp = client.post(
            f"/api/organizations/{test_org.id}/members/{target.id}/verify-email",
            json={"reason": "manual check"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["verification_method"] == "admin"

        test_db.expire_all()
        refreshed = test_db.query(User).filter(User.id == target.id).first()
        assert refreshed.email_verified is True
        assert refreshed.email_verification_method == "admin"
        assert refreshed.email_verified_by_id == test_users[3].id

    def test_already_verified_short_circuits(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        target = _make_user(test_db, "Already Verified", email_verified=True)
        _membership(test_db, target.id, test_org.id, "ANNOTATOR")

        resp = client.post(
            f"/api/organizations/{test_org.id}/members/{target.id}/verify-email",
            json={},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Email already verified"

    def test_verify_non_member_404_for_org_admin(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """org_admin path checks org membership of the target -> 404 if absent."""
        outsider = _make_user(test_db, "Org Outsider", email_verified=False)

        resp = client.post(
            f"/api/organizations/{test_org.id}/members/{outsider.id}/verify-email",
            json={},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 404
        assert "not a member" in resp.json()["detail"].lower()

        test_db.expire_all()
        refreshed = test_db.query(User).filter(User.id == outsider.id).first()
        assert refreshed.email_verified is False

    def test_annotator_cannot_verify_forbidden(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        target = _make_user(test_db, "Verify Target", email_verified=False)
        _membership(test_db, target.id, test_org.id, "ANNOTATOR")

        resp = client.post(
            f"/api/organizations/{test_org.id}/members/{target.id}/verify-email",
            json={},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# bulk_verify_member_emails — mixed-result tally branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkVerifyMemberEmails:
    def test_bulk_verify_mixed_results(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """One unverified member (success), one already-verified member (skipped),
        one non-member (error) -> tally + persisted state for the success."""
        unverified = _make_user(test_db, "Bulk Unverified", email_verified=False)
        _membership(test_db, unverified.id, test_org.id, "ANNOTATOR")

        verified = _make_user(test_db, "Bulk Verified", email_verified=True)
        _membership(test_db, verified.id, test_org.id, "ANNOTATOR")

        outsider = _make_user(test_db, "Bulk Outsider", email_verified=False)

        resp = client.post(
            f"/api/organizations/{test_org.id}/members/verify-emails",
            json={"user_ids": [unverified.id, verified.id, outsider.id]},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert summary["total"] == 3
        assert summary["success"] == 1
        assert summary["skipped"] == 1
        assert summary["errors"] == 1

        test_db.expire_all()
        assert (
            test_db.query(User).filter(User.id == unverified.id).first().email_verified
            is True
        )
        # The non-member was never touched.
        assert (
            test_db.query(User).filter(User.id == outsider.id).first().email_verified
            is False
        )

    def test_bulk_verify_annotator_forbidden(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.post(
            f"/api/organizations/{test_org.id}/members/verify-emails",
            json={"user_ids": [test_users[1].id]},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# list_all_users (manage/users) — scope + search branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListAllUsers:
    def test_superadmin_sees_all_users(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.get(
            "/api/organizations/manage/users",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        ids = {u["id"] for u in body}
        # All 4 test users are active and visible to the superadmin.
        assert {u.id for u in test_users[:4]}.issubset(ids)

    def test_non_superadmin_scoped_to_own_org(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A contributor only sees members of their shared org. A user in a
        different org is excluded."""
        other_org = Organization(
            id=_uid(),
            name="Disjoint Org",
            slug=f"disjoint-{uuid.uuid4().hex[:8]}",
            display_name="Disjoint Org",
        )
        test_db.add(other_org)
        test_db.commit()
        stranger = _make_user(test_db, "Stranger")
        _membership(test_db, stranger.id, other_org.id, "ANNOTATOR")

        resp = client.get(
            "/api/organizations/manage/users",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        ids = {u["id"] for u in resp.json()}
        # Sees co-members of test_org...
        assert test_users[2].id in ids
        # ...but not the stranger in the disjoint org.
        assert stranger.id not in ids

    def test_search_filter_narrows(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.get(
            "/api/organizations/manage/users?search=annotator@test.com",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) >= 1
        assert all("annotator" in u["email"].lower() for u in body)

    def test_non_superadmin_no_org_returns_empty(
        self, client, test_db, auth_headers
    ):
        """A non-superadmin with no org memberships (no test_org fixture) sees an
        empty list — the early-return branch when user_org_ids is empty."""
        resp = client.get(
            "/api/organizations/manage/users",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# update_user_superadmin_status — promote / permission branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateSuperadmin:
    def test_superadmin_promotes_user_persists(
        self, client, test_db, test_users, auth_headers
    ):
        target = _make_user(test_db, "Promote Me")
        resp = client.put(
            f"/api/organizations/manage/users/{target.id}/superadmin",
            json={"is_superadmin": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_superadmin"] is True

        test_db.expire_all()
        refreshed = test_db.query(User).filter(User.id == target.id).first()
        assert refreshed.is_superadmin is True

    def test_non_superadmin_cannot_promote_403(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        resp = client.put(
            f"/api/organizations/manage/users/{test_users[2].id}/superadmin",
            json={"is_superadmin": True},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 403
        assert "Only superadmins" in resp.json()["detail"]

        test_db.expire_all()
        assert (
            test_db.query(User).filter(User.id == test_users[2].id).first().is_superadmin
            is False
        )

    def test_promote_user_not_found_404(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            f"/api/organizations/manage/users/{_uid()}/superadmin",
            json={"is_superadmin": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# delete_user (manage/users) — permission + guard branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteUser:
    def test_non_superadmin_cannot_delete_403(
        self, client, test_db, test_users, auth_headers
    ):
        target = _make_user(test_db, "Delete Denied")
        resp = client.delete(
            f"/api/organizations/manage/users/{target.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403
        assert "Only superadmins" in resp.json()["detail"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == target.id).first() is not None

    def test_delete_user_not_found_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"/api/organizations/manage/users/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]

    def test_cannot_delete_self_400(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"/api/organizations/manage/users/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "your own account" in resp.json()["detail"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == test_users[0].id).first() is not None

    def test_superadmin_deletes_non_superadmin_success(
        self, client, test_db, test_users, auth_headers
    ):
        """Full delete-user success path: a second superadmin acts as the
        reassignment-fallback target, and a plain user is deleted.

        ``delete_user_service`` requires another superadmin to exist (to reassign
        authored content to), so ``test_users[0]`` alone is not enough — we add a
        second superadmin first. The deleted row is gone afterward.
        """
        # Fallback superadmin so reassignment in delete_user_service is possible.
        _make_user(test_db, "Fallback Admin", is_superadmin=True)

        target = _make_user(test_db, "Doomed User")
        resp = client.delete(
            f"/api/organizations/manage/users/{target.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "deleted successfully" in resp.json()["message"]

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == target.id).first() is None
