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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from models import (
    Invitation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Async-lane helpers
#
# Several invitation endpoints moved to the async DB lane
# (``Depends(get_async_db)``): list, validate-by-token, get-by-token, cancel.
# Driving them with the sync TestClient + sync test_db fails because the async
# engine is bound to a different event loop than TestClient's portal. Those
# tests are driven with ``async_test_client`` and seed rows via
# ``async_test_db`` instead. The create / bulk / accept endpoints stay sync, so
# their tests keep using the sync ``client`` + ``test_db`` helpers above.
# ---------------------------------------------------------------------------

from auth_module.dependencies import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from main import app  # noqa: E402


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB user row."""
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


async def _aseed_user(
    db, email, name="Inviter User", *, is_superadmin=False, email_verified=True
):
    """Seed a User row on the async session and return it."""
    user = User(
        id=_uid(),
        username=email,
        email=email,
        name=name,
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=email_verified,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _aseed_org(db, *, name="Async Test Org", slug=None):
    org = Organization(
        id=_uid(),
        name=name,
        display_name=f"{name} Display",
        slug=slug or f"async-org-{uuid.uuid4().hex[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _aseed_membership(db, user_id, org_id, role=OrganizationRole.ANNOTATOR, is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
    )
    db.add(m)
    await db.flush()
    return m


async def _aseed_invitation(
    db,
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
    db.add(inv)
    await db.flush()
    return inv


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
    group_id=None,
    invited_as_group_admin=False,
):
    inv = Invitation(
        id=_uid(),
        organization_id=org_id,
        email=email,
        role=role,
        group_id=group_id,
        invited_as_group_admin=invited_as_group_admin,
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
    """list_organization_invitations is async — driven via async_test_client."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_403(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        annotator = await _aseed_user(async_test_db, "list-annotator@example.com")
        await _aseed_membership(
            async_test_db, annotator.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )
        assert resp.status_code == 403
        assert "Only organization admins" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_pending_only_excludes_accepted(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, "list-admin1@example.com", is_superadmin=True
        )
        inviter = await _aseed_user(async_test_db, "list-inviter1@example.com")
        await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="pendinglist@example.com"
        )
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="acceptedlist@example.com",
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )
        assert resp.status_code == 200
        emails = {inv["email"] for inv in resp.json()}
        assert "pendinglist@example.com" in emails
        assert "acceptedlist@example.com" not in emails

    @pytest.mark.asyncio
    async def test_include_expired_toggle(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, "list-admin2@example.com", is_superadmin=True
        )
        inviter = await _aseed_user(async_test_db, "list-inviter2@example.com")
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="expiredlist@example.com",
            expires_in_days=-1,
        )
        await async_test_db.commit()

        # Default: expired hidden.
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )
        assert resp.status_code == 200
        assert "expiredlist@example.com" not in {inv["email"] for inv in resp.json()}

        # With include_expired=true: shown.
        with _as_user(admin):
            resp2 = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations?include_expired=true"
            )
        assert resp2.status_code == 200
        assert "expiredlist@example.com" in {inv["email"] for inv in resp2.json()}


# ---------------------------------------------------------------------------
# validate_invitation_token / get_invitation_by_token — public-endpoint branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTokenLookup:
    """validate_invitation_token / get_invitation_by_token are async + public
    (no auth) — driven via async_test_client, no _as_user needed."""

    @pytest.mark.asyncio
    async def test_validate_not_found_404(self, async_test_client, async_test_db):
        resp = await async_test_client.get(f"/api/invitations/validate/{_uid()}")
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_validate_already_accepted_400(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(async_test_db, "validate-inviter1@example.com")
        token = _uid()
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="acc@example.com",
            token=token,
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_by_token_not_found_404(self, async_test_client, async_test_db):
        resp = await async_test_client.get(f"/api/invitations/token/{_uid()}")
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_by_token_expired_400(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(async_test_db, "token-inviter-exp@example.com")
        token = _uid()
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="exp@example.com",
            token=token,
            expires_in_days=-2,
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_by_token_already_accepted_400(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(async_test_db, "token-inviter-acc@example.com")
        token = _uid()
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="accbytoken@example.com",
            token=token,
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_by_token_success_enriches(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(
            async_test_db, "token-inviter-ok@example.com", name="Token Inviter"
        )
        token = _uid()
        await _aseed_invitation(
            async_test_db,
            org.id,
            inviter.id,
            email="ok@example.com",
            token=token,
            role=OrganizationRole.CONTRIBUTOR,
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "ok@example.com"
        assert body["organization_name"] == org.name
        assert body["inviter_name"] == inviter.name
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

    def test_accept_restores_a_removed_membership(
        self, client, test_db, test_users, test_org
    ):
        """A removed member who is invited again gets the old row back with
        the invited role (the (user, org) pair is unique; a second insert
        used to fail with a 500)."""
        invitee = _make_user(test_db, f"removed-{_uid()[:8]}@example.com", "Removed")
        removed = _membership(
            test_db, invitee.id, test_org.id, role="ANNOTATOR", is_active=False
        )
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
        assert resp.status_code == 200, resp.text

        test_db.expire_all()
        rows = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == invitee.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .all()
        )
        assert [r.id for r in rows] == [removed.id]
        assert rows[0].is_active is True
        assert rows[0].role == OrganizationRole.CONTRIBUTOR
        inv = test_db.query(Invitation).filter(Invitation.token == token).first()
        assert inv.accepted is True

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
    """cancel_invitation is async — driven via async_test_client."""

    @pytest.mark.asyncio
    async def test_cancel_not_found_404(self, async_test_client, async_test_db):
        admin = await _aseed_user(
            async_test_db, "cancel-admin0@example.com", is_superadmin=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete(f"/api/invitations/{_uid()}")
        assert resp.status_code == 404
        assert "Invitation not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_org_admin_cancels_deletes_row(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        # Non-superadmin who holds an ORG_ADMIN membership for this org.
        org_admin = await _aseed_user(async_test_db, "cancel-orgadmin@example.com")
        await _aseed_membership(
            async_test_db, org_admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        inviter = await _aseed_user(async_test_db, "cancel-inviter1@example.com")
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="cancelme@example.com"
        )
        await async_test_db.commit()

        with _as_user(org_admin):
            resp = await async_test_client.delete(f"/api/invitations/{inv.id}")
        assert resp.status_code == 200
        assert "cancelled successfully" in resp.json()["message"]

        row = (
            await async_test_db.execute(
                select(Invitation).where(Invitation.id == inv.id)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_inviter_can_cancel_own_invitation(self, async_test_client, async_test_db):
        """A non-admin user who created the invitation may cancel it (the
        ``invitation.invited_by == current_user.id`` branch)."""
        org = await _aseed_org(async_test_db)
        # A non-admin contributor who is the inviter — no ORG_ADMIN membership.
        inviter = await _aseed_user(async_test_db, "cancel-owner@example.com")
        await _aseed_membership(
            async_test_db, inviter.id, org.id, role=OrganizationRole.CONTRIBUTOR
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="ownerinvite@example.com"
        )
        await async_test_db.commit()

        with _as_user(inviter):
            resp = await async_test_client.delete(f"/api/invitations/{inv.id}")
        assert resp.status_code == 200

        row = (
            await async_test_db.execute(
                select(Invitation).where(Invitation.id == inv.id)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_non_admin_non_inviter_cannot_cancel_403(
        self, async_test_client, async_test_db
    ):
        """A non-admin who did NOT create the invitation is forbidden."""
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(async_test_db, "cancel-realinviter@example.com")
        # The actor: a non-admin annotator who is neither org-admin nor inviter.
        actor = await _aseed_user(async_test_db, "cancel-annotator@example.com")
        await _aseed_membership(
            async_test_db, actor.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="protected@example.com"
        )
        await async_test_db.commit()

        with _as_user(actor):
            resp = await async_test_client.delete(f"/api/invitations/{inv.id}")
        assert resp.status_code == 403
        assert "Only organization admins or the inviter" in resp.json()["detail"]

        # Row still present.
        row = (
            await async_test_db.execute(
                select(Invitation).where(Invitation.id == inv.id)
            )
        ).scalar_one_or_none()
        assert row is not None


class TestAcceptGroupScopedInvitation:
    """Group-scoped invitations (org → group → user layer): accepting also
    joins the group; a deactivated group degrades to a plain org invite."""

    def _group(self, test_db, org_id, *, active=True):
        from models import OrganizationGroup

        group = OrganizationGroup(
            id=_uid(), organization_id=org_id, name=f"G-{_uid()[:6]}", is_active=active
        )
        test_db.add(group)
        test_db.commit()
        return group

    def test_accept_creates_group_membership_with_admin_flag(
        self, client, test_db, test_users, test_org
    ):
        from models import OrganizationGroupMembership

        group = self._group(test_db, test_org.id)
        invitee = _make_user(test_db, "groupaccept@example.com", "Group Accept")
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
            role=OrganizationRole.CONTRIBUTOR,
            group_id=group.id,
            invited_as_group_admin=True,
        )

        resp = client.post(
            f"/api/invitations/accept/{token}", headers=_bearer(invitee)
        )
        assert resp.status_code == 200

        gm = (
            test_db.query(OrganizationGroupMembership)
            .filter(
                OrganizationGroupMembership.group_id == group.id,
                OrganizationGroupMembership.user_id == invitee.id,
            )
            .first()
        )
        assert gm is not None
        assert gm.is_group_admin is True
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == invitee.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .first()
        )
        assert membership is not None and membership.role == OrganizationRole.CONTRIBUTOR

    def test_accept_with_inactive_group_degrades_to_org_invite(
        self, client, test_db, test_users, test_org
    ):
        from models import OrganizationGroupMembership

        group = self._group(test_db, test_org.id, active=False)
        invitee = _make_user(test_db, "inactivegroup@example.com", "Degraded")
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            token=token,
            group_id=group.id,
        )

        resp = client.post(
            f"/api/invitations/accept/{token}", headers=_bearer(invitee)
        )
        assert resp.status_code == 200

        gm = (
            test_db.query(OrganizationGroupMembership)
            .filter(OrganizationGroupMembership.user_id == invitee.id)
            .first()
        )
        assert gm is None  # no group join — but the org membership stands
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == invitee.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .first()
        )
        assert membership is not None

    def test_signup_with_token_creates_group_membership(
        self, client, test_db, test_users, test_org
    ):
        """The NEW-user path: registering via the invite email's token must
        join the group too (regression — signup used to create only the org
        membership, silently dropping the group scope + admin flag, and the
        accept endpoint can't recover it later: 400 already-a-member)."""
        import uuid as _uuid

        from models import OrganizationGroupMembership, User

        group = self._group(test_db, test_org.id)
        email = f"signup_{_uuid.uuid4().hex[:8]}@test.com"
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=email,
            token=token,
            role=OrganizationRole.CONTRIBUTOR,
            group_id=group.id,
            invited_as_group_admin=True,
        )

        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"user_{_uuid.uuid4().hex[:8]}",
                "email": email,
                "name": "Signup Via Group Invite",
                "password": "secure123password",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
                "invitation_token": token,
            },
        )
        assert resp.status_code == 200

        user = test_db.query(User).filter(User.email == email).first()
        assert user is not None
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .first()
        )
        assert membership is not None and membership.role == OrganizationRole.CONTRIBUTOR
        gm = (
            test_db.query(OrganizationGroupMembership)
            .filter(
                OrganizationGroupMembership.group_id == group.id,
                OrganizationGroupMembership.user_id == user.id,
            )
            .first()
        )
        assert gm is not None
        assert gm.is_group_admin is True

    def test_signup_with_token_inactive_group_degrades(
        self, client, test_db, test_users, test_org
    ):
        import uuid as _uuid

        from models import OrganizationGroupMembership, User

        group = self._group(test_db, test_org.id, active=False)
        email = f"signup_{_uuid.uuid4().hex[:8]}@test.com"
        token = _uid()
        _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=email,
            token=token,
            group_id=group.id,
        )

        resp = client.post(
            "/api/auth/signup",
            json={
                "username": f"user_{_uuid.uuid4().hex[:8]}",
                "email": email,
                "name": "Signup Degraded Invite",
                "password": "secure123password",
                "legal_expertise_level": "layperson",
                "german_proficiency": "native",
                "invitation_token": token,
            },
        )
        assert resp.status_code == 200

        user = test_db.query(User).filter(User.email == email).first()
        assert user is not None
        gm = (
            test_db.query(OrganizationGroupMembership)
            .filter(OrganizationGroupMembership.user_id == user.id)
            .first()
        )
        assert gm is None  # no group join — but the org membership stands
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .first()
        )
        assert membership is not None


class TestEmailVerificationAutoAccept:
    """Verifying an email accepts the address's pending invitations
    (``EmailVerificationService._auto_accept_invitations``)."""

    def _service(self):
        from auth_module.email_verification import EmailVerificationService

        with patch("auth_module.email_verification.EmailService"):
            return EmailVerificationService()

    def _memberships(self, test_db, user_id, org_id):
        test_db.expire_all()
        return (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == org_id,
            )
            .all()
        )

    def test_restores_a_removed_membership(self, test_db, test_users, test_org):
        """A removed member gets the old row back with the invited role.
        The (user, org) pair is unique, so a second insert used to fail and
        the invitation silently stayed pending."""
        invitee = _make_user(
            test_db, f"verify-removed-{_uid()[:8]}@example.com", email_verified=False
        )
        removed = _membership(
            test_db, invitee.id, test_org.id, role="ANNOTATOR", is_active=False
        )
        inv = _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            role=OrganizationRole.CONTRIBUTOR,
        )

        messages = self._service()._auto_accept_invitations(
            test_db, invitee.id, invitee.email
        )

        assert len(messages) == 1
        rows = self._memberships(test_db, invitee.id, test_org.id)
        assert [r.id for r in rows] == [removed.id]
        assert rows[0].is_active is True
        assert rows[0].role == OrganizationRole.CONTRIBUTOR
        stored = test_db.query(Invitation).filter(Invitation.id == inv.id).one()
        assert stored.accepted is True
        assert stored.accepted_at is not None
        assert stored.pending_user_id == invitee.id

    def test_new_member_gets_one_row_and_the_group(
        self, test_db, test_users, test_org
    ):
        from models import OrganizationGroup, OrganizationGroupMembership

        group = OrganizationGroup(
            id=_uid(), organization_id=test_org.id, name=f"G-{_uid()[:6]}"
        )
        test_db.add(group)
        test_db.commit()
        invitee = _make_user(
            test_db, f"verify-new-{_uid()[:8]}@example.com", email_verified=False
        )
        inv = _make_invitation(
            test_db,
            test_org.id,
            test_users[0].id,
            email=invitee.email,
            group_id=group.id,
        )

        self._service()._auto_accept_invitations(test_db, invitee.id, invitee.email)

        rows = self._memberships(test_db, invitee.id, test_org.id)
        assert len(rows) == 1 and rows[0].is_active is True
        assert rows[0].role == OrganizationRole.ANNOTATOR
        assert (
            test_db.query(OrganizationGroupMembership)
            .filter(
                OrganizationGroupMembership.group_id == group.id,
                OrganizationGroupMembership.user_id == invitee.id,
            )
            .count()
            == 1
        )
        assert test_db.query(Invitation).filter(Invitation.id == inv.id).one().accepted

    def test_active_member_only_marks_the_invitation(
        self, test_db, test_users, test_org
    ):
        invitee = _make_user(
            test_db, f"verify-active-{_uid()[:8]}@example.com", email_verified=False
        )
        existing = _membership(test_db, invitee.id, test_org.id, role="CONTRIBUTOR")
        inv = _make_invitation(
            test_db, test_org.id, test_users[0].id, email=invitee.email
        )

        messages = self._service()._auto_accept_invitations(
            test_db, invitee.id, invitee.email
        )

        assert messages == []
        rows = self._memberships(test_db, invitee.id, test_org.id)
        assert [r.id for r in rows] == [existing.id]
        assert rows[0].role == OrganizationRole.CONTRIBUTOR
        stored = test_db.query(Invitation).filter(Invitation.id == inv.id).one()
        assert stored.accepted is True


# ---------------------------------------------------------------------------
# Invitation-mail delivery state + resend (migration 107)
#
# Before this, the invitations table held no record of whether its mail went
# out: the only traces were a worker log line and a Celery result that expires
# after a day, and the admin UI reported "invite sent" as soon as the task was
# queued. Repairing a lost mail meant cancelling and re-creating the
# invitation, which mints a new token and kills any link already in flight.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestInvitationEmailStateInList:
    """list_organization_invitations exposes the delivery state read-only."""

    @pytest.mark.asyncio
    async def test_queue_time_is_stamped_on_create(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A successful enqueue is not a delivery, but it IS an attempt. The
        row has to say so, otherwise a broker outage leaves no trace."""
        email = f"stamp-{_uid()[:8]}@example.com"
        with _as_user(test_users[0]), patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": email, "role": "ANNOTATOR"},
            )
        assert resp.status_code == 200

        stored = (
            test_db.query(Invitation).filter(Invitation.email == email).one()
        )
        assert stored.email_last_attempt_at is not None
        assert stored.email_sent_at is None
        assert stored.email_last_error is None
        assert stored.email_attempts == 0

    @pytest.mark.asyncio
    async def test_queue_failure_is_recorded_and_does_not_fail_the_create(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """The invitation still gets created, but it must not look delivered."""
        email = f"queuefail-{_uid()[:8]}@example.com"
        broker = patch("routers.invitations.celery_app")
        with _as_user(test_users[0]), broker as mock_celery:
            mock_celery.send_task.side_effect = RuntimeError("broker down")
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": email, "role": "ANNOTATOR"},
            )
        assert resp.status_code == 200

        stored = (
            test_db.query(Invitation).filter(Invitation.email == email).one()
        )
        assert stored.email_sent_at is None
        assert "broker down" in stored.email_last_error

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sent_at_days_ago,last_attempt,last_error,expected",
        [
            (1, True, None, "sent"),
            (None, True, "SendGrid 400: bad address", "failed"),
            (None, True, None, "queued"),
            (None, False, None, "unknown"),
        ],
    )
    async def test_email_status_is_derived_per_row(
        self,
        async_test_client,
        async_test_db,
        sent_at_days_ago,
        last_attempt,
        last_error,
        expected,
    ):
        """unknown and failed stay distinct: pre-migration rows carry no
        timestamps and must not be reported as failures."""
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"state-admin-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, admin.id, email=f"state-{_uid()[:8]}@example.com"
        )
        now = datetime.now(timezone.utc)
        if sent_at_days_ago is not None:
            inv.email_sent_at = now - timedelta(days=sent_at_days_ago)
        if last_attempt:
            inv.email_last_attempt_at = now - timedelta(minutes=5)
        inv.email_last_error = last_error
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations"
            )
        assert resp.status_code == 200
        row = next(r for r in resp.json() if r["id"] == inv.id)
        assert row["email_status"] == expected
        assert "email_attempts" in row
        assert "email_last_attempt_at" in row

    @pytest.mark.asyncio
    async def test_public_by_token_endpoint_does_not_leak_the_error(
        self, async_test_client, async_test_db
    ):
        """Whoever holds a link must not learn our provider's failure text."""
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"leak-admin-{_uid()[:8]}@example.com", is_superadmin=True
        )
        token = _uid()
        inv = await _aseed_invitation(
            async_test_db, org.id, admin.id, token=token, email="leak@example.com"
        )
        inv.email_last_error = "SendGrid 401: api key revoked"
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert "email_last_error" not in body
        assert "email_status" not in body


@pytest.mark.integration
class TestResendInvitation:
    """POST /api/invitations/{id}/resend — async lane, same gate as cancel."""

    @pytest.mark.asyncio
    async def test_not_found_404(self, async_test_client, async_test_db):
        admin = await _aseed_user(
            async_test_db, f"resend-404-{_uid()[:8]}@example.com", is_superadmin=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(f"/api/invitations/{_uid()}/resend")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_admin_resends_and_keeps_the_token(
        self, async_test_client, async_test_db
    ):
        """Reusing the token is the point: a link the recipient already has
        must keep working, unlike the cancel-and-recreate workaround."""
        org = await _aseed_org(async_test_db)
        org_admin = await _aseed_user(
            async_test_db, f"resend-oa-{_uid()[:8]}@example.com"
        )
        await _aseed_membership(
            async_test_db, org_admin.id, org.id, role=OrganizationRole.ORG_ADMIN
        )
        inviter = await _aseed_user(
            async_test_db, f"resend-inv-{_uid()[:8]}@example.com"
        )
        token = _uid()
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, token=token, email="resend@example.com"
        )
        inv.email_last_error = "SendGrid 503: upstream down"
        await async_test_db.commit()

        with _as_user(org_admin), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")

        assert resp.status_code == 200
        body = resp.json()
        assert body["invitation_id"] == inv.id
        assert body["email"] == "resend@example.com"
        assert body["email_status"] == "queued"
        # Never hand the admin the token.
        assert "token" not in body

        celery.send_task.assert_called_once()
        args = celery.send_task.call_args
        assert args[0][0] == "emails.send_invitation"
        assert token in args.kwargs["args"][4]

        await async_test_db.refresh(inv)
        assert inv.token == token
        assert inv.email_last_attempt_at is not None
        # A successful re-queue clears the stale failure.
        assert inv.email_last_error is None

    @pytest.mark.asyncio
    async def test_resend_keeps_the_original_inviter_name(
        self, async_test_client, async_test_db
    ):
        """The recipient already saw one name; a resend is not a new invite."""
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(
            async_test_db, f"resend-orig-{_uid()[:8]}@example.com", name="Original Inviter"
        )
        actor = await _aseed_user(
            async_test_db, f"resend-actor-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="keepname@example.com"
        )
        await async_test_db.commit()

        with _as_user(actor), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")

        assert resp.status_code == 200
        assert celery.send_task.call_args.kwargs["args"][2] == "Original Inviter"

    @pytest.mark.asyncio
    async def test_inviter_may_resend_own_invitation(
        self, async_test_client, async_test_db
    ):
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(
            async_test_db, f"resend-own-{_uid()[:8]}@example.com"
        )
        await _aseed_membership(
            async_test_db, inviter.id, org.id, role=OrganizationRole.CONTRIBUTOR
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="own@example.com"
        )
        await async_test_db.commit()

        with _as_user(inviter), patch("routers.invitations.celery_app"):
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_admin_non_inviter_403(self, async_test_client, async_test_db):
        """The gate must not reach further than cancel's: resending mails a
        third party on the organization's behalf."""
        org = await _aseed_org(async_test_db)
        inviter = await _aseed_user(
            async_test_db, f"resend-real-{_uid()[:8]}@example.com"
        )
        actor = await _aseed_user(
            async_test_db, f"resend-nobody-{_uid()[:8]}@example.com"
        )
        await _aseed_membership(
            async_test_db, actor.id, org.id, role=OrganizationRole.ANNOTATOR
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, inviter.id, email="protected@example.com"
        )
        await async_test_db.commit()

        with _as_user(actor), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 403
        assert "resend invitations" in resp.json()["detail"]
        celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepted_invitation_400(self, async_test_client, async_test_db):
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"resend-acc-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db,
            org.id,
            admin.id,
            email="accepted@example.com",
            accepted=True,
            accepted_at=datetime.now(timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 400
        assert "already been accepted" in resp.json()["detail"]
        celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_expired_invitation_400(self, async_test_client, async_test_db):
        """An expired invitation's link is dead, so mailing it again is worse
        than useless. Cancel and create a fresh one instead."""
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"resend-exp-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db,
            org.id,
            admin.id,
            email="expired@example.com",
            expires_in_days=-1,
        )
        await async_test_db.commit()

        with _as_user(admin), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]
        celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_refuses_a_second_resend_within_the_window(
        self, async_test_client, async_test_db
    ):
        from routers.invitations import RESEND_MIN_INTERVAL_SECONDS

        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"resend-guard-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, admin.id, email="guard@example.com"
        )
        inv.email_last_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        await async_test_db.commit()

        with _as_user(admin), patch("routers.invitations.celery_app") as celery:
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 429
        assert "wait" in resp.json()["detail"]
        celery.send_task.assert_not_called()

        # Past the window the same call goes through.
        inv.email_last_attempt_at = datetime.now(timezone.utc) - timedelta(
            seconds=RESEND_MIN_INTERVAL_SECONDS + 5
        )
        await async_test_db.commit()
        with _as_user(admin), patch("routers.invitations.celery_app"):
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_guard_holds_when_the_worker_never_ran(
        self, async_test_client, async_test_db
    ):
        """The OOM case: nothing ever bumped email_attempts, so the guard has
        to lean on the queue-time stamp instead of the worker's."""
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"resend-oom-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, admin.id, email="oom@example.com"
        )
        await async_test_db.commit()

        with _as_user(admin), patch("routers.invitations.celery_app"):
            first = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert first.status_code == 200

        with _as_user(admin), patch("routers.invitations.celery_app"):
            second = await async_test_client.post(f"/api/invitations/{inv.id}/resend")
        assert second.status_code == 429

        await async_test_db.refresh(inv)
        # The worker is the only writer of the attempt counter.
        assert inv.email_attempts == 0

    @pytest.mark.asyncio
    async def test_queue_failure_is_reported_not_raised(
        self, async_test_client, async_test_db
    ):
        org = await _aseed_org(async_test_db)
        admin = await _aseed_user(
            async_test_db, f"resend-broker-{_uid()[:8]}@example.com", is_superadmin=True
        )
        inv = await _aseed_invitation(
            async_test_db, org.id, admin.id, email="brokerdown@example.com"
        )
        await async_test_db.commit()

        with _as_user(admin), patch("routers.invitations.celery_app") as celery:
            celery.send_task.side_effect = RuntimeError("broker down")
            resp = await async_test_client.post(f"/api/invitations/{inv.id}/resend")

        assert resp.status_code == 200
        assert resp.json()["email_status"] == "failed"
        await async_test_db.refresh(inv)
        assert "broker down" in inv.email_last_error
