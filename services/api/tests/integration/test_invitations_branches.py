"""Behavioral branch-coverage integration tests for the invitations router.

Targets the permission / duplicate / expiry / accept / cancel branches in
``services/api/routers/invitations.py`` that the happy-path suite in
``test_remaining_router_endpoints.py`` does not exercise.

Endpoints covered here:

- ``create_invitation``        : org-admin success + persisted row, non-admin 403,
  already-member 400, active-pending-invitation 400.
- ``create_bulk_invitations``  : mixed per-email results (queued / invalid /
  duplicate / already_member / pending) + persisted rows, over-cap 400,
  org-not-found 404, non-admin 403.
- ``list_organization_invitations`` : non-admin 403, include_expired filter,
  pending-only filter (accepted excluded).
- ``validate_invitation_token`` : not-found 404, already-accepted 400.
- ``get_invitation_by_token``  : not-found 404, expired 400, already-accepted 400.
- ``accept_invitation``        : success + membership persisted + invitation
  marked accepted, expired 400, already-accepted 400, email-mismatch 400,
  already-member 400, profile-completion short-circuit (no membership written).
- ``cancel_invitation``        : not-found 404, inviter-can-cancel branch,
  non-admin-non-inviter 403, row deleted.

The Celery dispatch in ``create_invitation`` / ``create_bulk_invitations`` is
patched out (``routers.invitations.celery_app``) exactly as the existing passing
``test_create_invitation`` does, so no broker is contacted. Notification fan-out
writes local Notification rows and is wrapped in try/except in the router.

Permission map under ``test_org``:
  * test_users[0] / auth_headers["admin"]       -> superadmin + ORG_ADMIN member
  * test_users[1] / auth_headers["contributor"] -> CONTRIBUTOR member
  * test_users[2] / auth_headers["annotator"]   -> ANNOTATOR member
  * test_users[3] / auth_headers["org_admin"]   -> ORG_ADMIN member (non-superadmin)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import Invitation, OrganizationMembership, OrganizationRole, User


def _uid() -> str:
    return str(uuid.uuid4())


def _make_invitation(
    test_db,
    org_id,
    invited_by,
    *,
    email="invitee@example.com",
    role=OrganizationRole.ANNOTATOR,
    token=None,
    accepted=False,
    accepted_at=None,
    expires_in_days=7,
):
    inv = Invitation(
        id=_uid(),
        organization_id=org_id,
        email=email,
        role=role,
        token=token or _uid(),
        invited_by=invited_by,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        accepted=accepted,
        accepted_at=accepted_at,
    )
    test_db.add(inv)
    test_db.commit()
    return inv


def _make_user(test_db, email, name="Invitee User", email_verified=True):
    user = User(
        id=_uid(),
        username=email,
        email=email,
        name=name,
        hashed_password="hashed",
        is_active=True,
        email_verified=email_verified,
    )
    test_db.add(user)
    test_db.commit()
    return user


def _bearer(user) -> dict:
    from auth_module import create_access_token

    return {"Authorization": f"Bearer {create_access_token(data={'user_id': user.id})}"}


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


# ---------------------------------------------------------------------------
# create_invitation — success + permission + duplicate branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateInvitation:
    def test_org_admin_creates_invitation_persists(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": "brandnew@example.com", "role": "CONTRIBUTOR"},
                headers=auth_headers["org_admin"],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "brandnew@example.com"
        assert body["role"] == "CONTRIBUTOR"
        assert body["accepted"] is False
        assert body["organization_name"] == test_org.name
        assert body["token"]

        row = (
            test_db.query(Invitation)
            .filter(
                Invitation.organization_id == test_org.id,
                Invitation.email == "brandnew@example.com",
            )
            .first()
        )
        assert row is not None
        assert row.invited_by == test_users[3].id
        assert row.accepted is False
        assert row.role == OrganizationRole.CONTRIBUTOR

    def test_annotator_cannot_invite_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": "denied@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["annotator"],
            )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

        assert (
            test_db.query(Invitation)
            .filter(Invitation.email == "denied@example.com")
            .first()
            is None
        )

    def test_invite_existing_member_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        # contributor user is already an active member of test_org.
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": test_users[1].email, "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 400
        assert "already a member" in resp.json()["detail"]

        assert (
            test_db.query(Invitation)
            .filter(Invitation.email == test_users[1].email)
            .first()
            is None
        )

    def test_invite_with_active_pending_invitation_400(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        _make_invitation(
            test_db, test_org.id, test_users[0].id, email="pending@example.com"
        )

        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": "pending@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 400
        assert "active invitation already exists" in resp.json()["detail"]

        # Still exactly one invitation for that email (no second insert).
        cnt = (
            test_db.query(Invitation)
            .filter(Invitation.email == "pending@example.com")
            .count()
        )
        assert cnt == 1

    def test_invite_org_not_found_404(self, client, test_db, test_users, auth_headers):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                "/api/invitations/organizations/nonexistent-org/invitations",
                json={"email": "x@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 404
        assert "Organization not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# create_bulk_invitations — per-email status branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkInvitations:
    def test_bulk_mixed_statuses(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """One queued, one invalid, one in-request duplicate, one already_member,
        one pending — exercises every per-email branch + persisted rows."""
        # Pre-existing pending invitation.
        _make_invitation(
            test_db, test_org.id, test_users[0].id, email="haspending@example.com"
        )

        emails = [
            "fresh@example.com",         # queued
            "not-an-email",              # invalid
            "Fresh@example.com",         # duplicate (case-insensitive of fresh@)
            test_users[2].email,         # already_member (annotator)
            "haspending@example.com",    # pending
        ]

        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations/bulk",
                json={"emails": emails, "role": "ANNOTATOR"},
                headers=auth_headers["org_admin"],
            )
        assert resp.status_code == 200
        body = resp.json()
        statuses = {item["email"]: item["status"] for item in body["results"]}

        assert statuses["fresh@example.com"] == "queued"
        assert statuses["not-an-email"] == "invalid"
        assert statuses["Fresh@example.com"] == "duplicate"
        assert statuses[test_users[2].email] == "already_member"
        assert statuses["haspending@example.com"] == "pending"

        assert body["queued"] == 1
        assert body["total"] == 5
        assert body["skipped"] == 4

        # Only the queued address produced a new invitation row.
        assert (
            test_db.query(Invitation)
            .filter(
                Invitation.organization_id == test_org.id,
                Invitation.email == "fresh@example.com",
            )
            .count()
            == 1
        )

    def test_bulk_over_cap_400(self, client, test_db, test_users, test_org, auth_headers):
        emails = [f"user{i}@example.com" for i in range(101)]
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations/bulk",
                json={"emails": emails, "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 400
        assert "Too many invitations" in resp.json()["detail"]

        # Nothing persisted.
        assert (
            test_db.query(Invitation)
            .filter(Invitation.organization_id == test_org.id)
            .count()
            == 0
        )

    def test_bulk_org_not_found_404(self, client, test_db, test_users, auth_headers):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                "/api/invitations/organizations/nonexistent/invitations/bulk",
                json={"emails": ["a@example.com"], "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 404
        assert "Organization not found" in resp.json()["detail"]

    def test_bulk_non_admin_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations/bulk",
                json={"emails": ["a@example.com"], "role": "ANNOTATOR"},
                headers=auth_headers["annotator"],
            )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# list_organization_invitations — permission + filter branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListInvitations:
    def test_non_admin_cannot_list_403(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        resp = client.get(
            f"/api/invitations/organizations/{test_org.id}/invitations",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

    def test_pending_only_excludes_accepted(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        _make_invitation(
            test_db, test_org.id, test_users[0].id, email="pendinglist@example.com"
        )
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="acceptedlist@example.com",
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )

        resp = client.get(
            f"/api/invitations/organizations/{test_org.id}/invitations",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        emails = {inv["email"] for inv in resp.json()}
        assert "pendinglist@example.com" in emails
        assert "acceptedlist@example.com" not in emails

    def test_include_expired_toggle(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="expiredlist@example.com",
            expires_in_days=-1,
        )

        # Default: expired hidden.
        resp = client.get(
            f"/api/invitations/organizations/{test_org.id}/invitations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "expiredlist@example.com" not in {inv["email"] for inv in resp.json()}

        # With include_expired=true: shown.
        resp2 = client.get(
            f"/api/invitations/organizations/{test_org.id}/invitations?include_expired=true",
            headers=auth_headers["admin"],
        )
        assert resp2.status_code == 200
        assert "expiredlist@example.com" in {inv["email"] for inv in resp2.json()}


# ---------------------------------------------------------------------------
# validate_invitation_token / get_invitation_by_token — public-endpoint branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTokenLookup:
    def test_validate_not_found_404(self, client, test_db):
        resp = client.get(f"/api/invitations/validate/{_uid()}")
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    def test_validate_already_accepted_400(
        self, client, test_db, test_users, test_org
    ):
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="acc@example.com",
            token=token,
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]

    def test_get_by_token_not_found_404(self, client, test_db):
        resp = client.get(f"/api/invitations/token/{_uid()}")
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    def test_get_by_token_expired_400(self, client, test_db, test_users, test_org):
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="exp@example.com",
            token=token,
            expires_in_days=-2,
        )
        resp = client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_get_by_token_already_accepted_400(
        self, client, test_db, test_users, test_org
    ):
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="accbytoken@example.com",
            token=token,
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        resp = client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]

    def test_get_by_token_success_enriches(
        self, client, test_db, test_users, test_org
    ):
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="ok@example.com",
            token=token,
            role=OrganizationRole.CONTRIBUTOR,
        )
        resp = client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "ok@example.com"
        assert body["organization_name"] == test_org.name
        assert body["inviter_name"] == test_users[0].name
        assert body["role"] == "CONTRIBUTOR"


# ---------------------------------------------------------------------------
# accept_invitation — success + every guard branch
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAcceptInvitation:
    def test_accept_success_creates_membership(self, client, test_db, test_users, test_org):
        """A new user whose email matches the invitation accepts -> membership
        row created + invitation marked accepted."""
        invitee = _make_user(test_db, "newaccept@example.com", "New Accept")
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
            role=OrganizationRole.CONTRIBUTOR,
        )

        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(invitee),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["organization_id"] == test_org.id
        assert body["profile_completed"] is True

        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == invitee.id,
                OrganizationMembership.organization_id == test_org.id,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
            .first()
        )
        assert membership is not None
        assert membership.role == OrganizationRole.CONTRIBUTOR

        test_db.expire_all()
        inv = test_db.query(Invitation).filter(Invitation.token == token).first()
        assert inv.accepted is True
        assert inv.accepted_at is not None

    def test_accept_not_found_404(self, client, test_db, test_users):
        resp = client.post(
            f"/api/invitations/accept/{_uid()}",
            headers=_bearer(test_users[1]),
        )
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    def test_accept_expired_400(self, client, test_db, test_users, test_org):
        invitee = _make_user(test_db, "expaccept@example.com")
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
            expires_in_days=-1,
        )
        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(invitee),
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_accept_already_accepted_400(self, client, test_db, test_users, test_org):
        invitee = _make_user(test_db, "alreadyacc@example.com")
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(invitee),
        )
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]

    def test_accept_email_mismatch_400(self, client, test_db, test_users, test_org):
        """The authenticated user's email differs from the invitation email."""
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email="someoneelse@example.com",
            token=token,
        )
        # annotator's email is annotator@test.com, not the invitation email.
        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(test_users[2]),
        )
        assert resp.status_code == 400
        assert "not for your email" in resp.json()["detail"]

        # The mismatched accept was rejected — the invitation stays unaccepted.
        # (test_users[2] may already be an org member from the fixture, so
        # assert on the invitation state rather than a membership count.)
        inv = test_db.query(Invitation).filter(Invitation.token == token).first()
        assert inv is not None and inv.accepted_at is None

    def test_accept_already_member_400(self, client, test_db, test_users, test_org):
        """The invited email matches a user who is already an active member."""
        token = _uid()
        # contributor (test_users[1]) is already a member of test_org.
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=test_users[1].email,
            token=token,
        )
        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(test_users[1]),
        )
        assert resp.status_code == 400
        assert "already a member" in resp.json()["detail"]

        # Invitation NOT marked accepted (short-circuited before the write).
        test_db.expire_all()
        inv = test_db.query(Invitation).filter(Invitation.token == token).first()
        assert inv.accepted is False

    def test_accept_incomplete_profile_short_circuits(
        self, client, test_db, test_users, test_org
    ):
        """A user created via invitation with an incomplete profile is redirected
        to profile completion; no membership is created yet."""
        invitee = _make_user(test_db, "needsprofile@example.com")
        invitee.created_via_invitation = True
        invitee.profile_completed = False
        test_db.add(invitee)
        test_db.commit()

        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
        )

        resp = client.post(
            f"/api/invitations/accept/{token}",
            headers=_bearer(invitee),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile_completed"] is False
        assert body["redirect_url"] == "/complete-profile"

        # No membership created, invitation still pending.
        assert (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == invitee.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .count()
            == 0
        )
        test_db.expire_all()
        inv = test_db.query(Invitation).filter(Invitation.token == token).first()
        assert inv.accepted is False


# ---------------------------------------------------------------------------
# cancel_invitation — permission + deletion branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCancelInvitation:
    def test_cancel_not_found_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"/api/invitations/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    def test_org_admin_cancels_deletes_row(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        inv = _make_invitation(
            test_db, test_org.id, test_users[0].id, email="cancelme@example.com"
        )
        resp = client.delete(
            f"/api/invitations/{inv.id}",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert "cancelled successfully" in resp.json()["message"]

        test_db.expire_all()
        assert test_db.query(Invitation).filter(Invitation.id == inv.id).first() is None

    def test_inviter_can_cancel_own_invitation(self, client, test_db, test_users, test_org):
        """A non-admin user who created the invitation may cancel it (the
        ``invitation.invited_by == current_user.id`` branch)."""
        # Make the contributor (non-admin) the inviter.
        inviter = test_users[1]
        inv = _make_invitation(
            test_db, test_org.id, inviter.id, email="ownerinvite@example.com"
        )
        resp = client.delete(
            f"/api/invitations/{inv.id}",
            headers=_bearer(inviter),
        )
        assert resp.status_code == 200
        test_db.expire_all()
        assert test_db.query(Invitation).filter(Invitation.id == inv.id).first() is None

    def test_non_admin_non_inviter_cannot_cancel_403(
        self, client, test_db, test_users, test_org
    ):
        """A non-admin who did NOT create the invitation is forbidden."""
        inv = _make_invitation(
            test_db, test_org.id, test_users[0].id, email="protected@example.com"
        )
        # annotator is neither org-admin nor the inviter.
        resp = client.delete(
            f"/api/invitations/{inv.id}",
            headers=_bearer(test_users[2]),
        )
        assert resp.status_code == 403
        assert "Only organization admins or the inviter" in resp.json()["detail"]

        # Row still present.
        test_db.expire_all()
        assert test_db.query(Invitation).filter(Invitation.id == inv.id).first() is not None
