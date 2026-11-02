"""Platform side of solutions uploaded for people not on BenGER yet (core 2.49).

- ``invite_or_reuse``: ANNOTATOR invitation, 90-day validity, group scope,
  reuse of a pending invitation, the invite gate.
- ``add_existing_user``: member / added_to_group / added_to_org /
  needs_invitation, by the actor's rights.
- ``after_invitation_accepted``: called once per consumption on the accept
  endpoint (both branches) and the automatic acceptance; isolated failures.

Permission map under ``test_org`` (see test_invitations_branches.py):
  test_users[0] superadmin + ORG_ADMIN, test_users[2] ANNOTATOR,
  test_users[3] ORG_ADMIN (no superadmin).
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from models import (
    Invitation,
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _user(test_db, email=None, name="Course Student"):
    email = email or f"student-{_uid()[:8]}@example.com"
    user = User(
        id=_uid(),
        username=email,
        email=email,
        name=name,
        hashed_password="hashed",
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


def _group(test_db, org, admin=None):
    group = OrganizationGroup(
        id=_uid(), organization_id=org.id, name=f"Kurs {_uid()[:6]}", is_active=True
    )
    test_db.add(group)
    test_db.flush()
    if admin is not None:
        test_db.add(
            OrganizationGroupMembership(
                id=_uid(), group_id=group.id, user_id=admin.id, role=OrganizationRole.ORG_ADMIN
            )
        )
    test_db.commit()
    return group


def _member(test_db, user, org, active=True):
    test_db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=OrganizationRole.ANNOTATOR,
            is_active=active,
        )
    )
    test_db.commit()


def _in_group(test_db, user, group) -> bool:
    return (
        test_db.query(OrganizationGroupMembership)
        .filter_by(group_id=group.id, user_id=user.id)
        .first()
        is not None
    )


def _active_member(test_db, user, org) -> bool:
    return (
        test_db.query(OrganizationMembership)
        .filter_by(user_id=user.id, organization_id=org.id, is_active=True)
        .first()
        is not None
    )


@pytest.mark.integration
class TestInviteOrReuse:
    def test_creates_annotator_invitation_valid_for_90_days(
        self, test_db, test_users, test_org
    ):
        from routers.invitations import INVITATION_VALIDITY_DAYS, invite_or_reuse

        assert INVITATION_VALIDITY_DAYS == 90
        with patch("routers.invitations.celery_app") as celery:
            invitation, created = invite_or_reuse(
                test_db,
                inviter=test_users[3],
                organization=test_org,
                email="  New.Student@Example.com ",
                host="what-a-benger.net",
            )
        assert created is True
        assert invitation.email == "New.Student@Example.com"
        assert invitation.role == OrganizationRole.ANNOTATOR
        assert invitation.group_id is None
        remaining = invitation.expires_at - datetime.now(timezone.utc)
        assert timedelta(days=89) < remaining <= timedelta(days=90)
        celery.send_task.assert_called_once()
        assert celery.send_task.call_args.args[0] == "emails.send_invitation"
        assert invitation.token in celery.send_task.call_args.kwargs["args"][4]
        assert invitation.email_last_attempt_at is not None

    def test_reuses_pending_invitation_without_new_mail(self, test_db, test_users, test_org):
        from routers.invitations import invite_or_reuse

        with patch("routers.invitations.celery_app") as celery:
            first, _ = invite_or_reuse(
                test_db, inviter=test_users[3], organization=test_org, email="twice@example.com"
            )
            second, created = invite_or_reuse(
                test_db, inviter=test_users[3], organization=test_org, email="TWICE@example.com"
            )
        assert created is False
        assert second.id == first.id
        assert celery.send_task.call_count == 1

    def test_group_admin_invites_into_own_group(self, test_db, test_users, test_org):
        from routers.invitations import invite_or_reuse

        group = _group(test_db, test_org, admin=test_users[2])
        with patch("routers.invitations.celery_app"):
            invitation, created = invite_or_reuse(
                test_db,
                inviter=test_users[2],
                organization=test_org,
                email="grp@example.com",
                group_id=group.id,
            )
        assert created is True
        assert invitation.group_id == group.id
        assert invitation.group_role == OrganizationRole.ANNOTATOR

    def test_plain_member_may_not_invite(self, test_db, test_users, test_org):
        from routers.invitations import invite_or_reuse

        with patch("routers.invitations.celery_app"), pytest.raises(HTTPException) as exc:
            invite_or_reuse(
                test_db, inviter=test_users[2], organization=test_org, email="x@example.com"
            )
        assert exc.value.status_code == 403
        assert test_db.query(Invitation).filter_by(email="x@example.com").first() is None


@pytest.mark.integration
class TestAddExistingUser:
    def test_active_member_without_group_is_member(self, test_db, test_users, test_org):
        from routers.invitations import add_existing_user

        student = _user(test_db)
        _member(test_db, student, test_org)
        assert (
            add_existing_user(
                test_db, actor=test_users[3], organization=test_org, user_id=student.id
            )
            == "member"
        )

    def test_group_admin_puts_org_member_into_group(self, test_db, test_users, test_org):
        from routers.invitations import add_existing_user

        group = _group(test_db, test_org, admin=test_users[2])
        student = _user(test_db)
        _member(test_db, student, test_org)
        outcome = add_existing_user(
            test_db,
            actor=test_users[2],
            organization=test_org,
            user_id=student.id,
            group_id=group.id,
        )
        assert outcome == "added_to_group"
        assert _in_group(test_db, student, group)
        # A second call changes nothing.
        assert (
            add_existing_user(
                test_db,
                actor=test_users[2],
                organization=test_org,
                user_id=student.id,
                group_id=group.id,
            )
            == "member"
        )

    def test_org_admin_adds_outsider_to_org_and_group(self, test_db, test_users, test_org):
        from routers.invitations import add_existing_user

        group = _group(test_db, test_org)
        student = _user(test_db)
        outcome = add_existing_user(
            test_db,
            actor=test_users[3],
            organization=test_org,
            user_id=student.id,
            group_id=group.id,
        )
        assert outcome == "added_to_org"
        assert _active_member(test_db, student, test_org)
        assert _in_group(test_db, student, group)

    def test_org_admin_restores_removed_member(self, test_db, test_users, test_org):
        from routers.invitations import add_existing_user

        student = _user(test_db)
        _member(test_db, student, test_org, active=False)
        outcome = add_existing_user(
            test_db, actor=test_users[3], organization=test_org, user_id=student.id
        )
        assert outcome == "added_to_org"
        assert _active_member(test_db, student, test_org)

    def test_group_admin_needs_invitation_for_outsider(self, test_db, test_users, test_org):
        from routers.invitations import add_existing_user

        group = _group(test_db, test_org, admin=test_users[2])
        student = _user(test_db)
        outcome = add_existing_user(
            test_db,
            actor=test_users[2],
            organization=test_org,
            user_id=student.id,
            group_id=group.id,
        )
        assert outcome == "needs_invitation"
        assert not _active_member(test_db, student, test_org)
        assert not _in_group(test_db, student, group)


def _invitation(test_db, org, inviter, email, group_id=None):
    inv = Invitation(
        id=_uid(),
        organization_id=org.id,
        email=email,
        role=OrganizationRole.ANNOTATOR,
        group_id=group_id,
        group_role=OrganizationRole.ANNOTATOR if group_id else None,
        token=_uid(),
        invited_by=inviter.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        accepted=False,
    )
    test_db.add(inv)
    test_db.commit()
    return inv


def _bearer(user) -> dict:
    from auth_module import create_access_token

    return {"Authorization": f"Bearer {create_access_token(data={'user_id': user.id})}"}


@pytest.mark.integration
class TestAcceptanceHook:
    def test_accept_endpoint_calls_hook_once(self, client, test_db, test_users, test_org):
        student = _user(test_db)
        inv = _invitation(test_db, test_org, test_users[3], student.email)
        with patch("extensions.after_invitation_accepted") as hook:
            resp = client.post(f"/api/invitations/accept/{inv.token}", headers=_bearer(student))
        assert resp.status_code == 200
        hook.assert_called_once()
        assert hook.call_args.args[1].id == inv.id
        assert hook.call_args.args[2] == student.id

    def test_accept_endpoint_member_joining_group_calls_hook(
        self, client, test_db, test_users, test_org
    ):
        group = _group(test_db, test_org)
        student = _user(test_db)
        _member(test_db, student, test_org)
        inv = _invitation(test_db, test_org, test_users[3], student.email, group_id=group.id)
        with patch("extensions.after_invitation_accepted") as hook:
            resp = client.post(f"/api/invitations/accept/{inv.token}", headers=_bearer(student))
        assert resp.status_code == 200
        hook.assert_called_once()
        assert hook.call_args.args[2] == student.id

    def test_auto_accept_calls_hook_per_invitation(self, test_db, test_users, test_org):
        from auth_module.email_verification import email_verification_service

        other_org = Organization(
            id=_uid(),
            name="Other Org",
            display_name="Other Org",
            slug=f"other-{_uid()[:8]}",
        )
        test_db.add(other_org)
        test_db.commit()
        student = _user(test_db)
        first = _invitation(test_db, test_org, test_users[3], student.email)
        second = _invitation(test_db, other_org, test_users[0], student.email.upper())
        with patch("extensions.after_invitation_accepted") as hook:
            email_verification_service.accept_pending_invitations(test_db, student)
        assert sorted(c.args[1].id for c in hook.call_args_list) == sorted(
            [first.id, second.id]
        )
        assert {c.args[2] for c in hook.call_args_list} == {student.id}

    def test_no_acceptance_no_hook(self, test_db, test_users, test_org):
        from auth_module.email_verification import email_verification_service

        student = _user(test_db)
        with patch("extensions.after_invitation_accepted") as hook:
            email_verification_service.accept_pending_invitations(test_db, student)
        hook.assert_not_called()


class TestHookWrapperIsolation:
    def test_failing_implementation_is_logged_and_rolled_back(self, monkeypatch):
        import extensions

        calls = []

        def boom(db, invitation, user_id):
            raise RuntimeError("attach failed")

        def ok(db, invitation, user_id):
            calls.append(user_id)

        monkeypatch.setattr(
            extensions, "_hook_impls", lambda key: [("a", boom), ("b", ok)]
        )
        db = MagicMock()
        extensions.after_invitation_accepted(db, MagicMock(id="inv"), "u1")
        db.rollback.assert_called_once()
        assert calls == ["u1"]

    def test_runs_for_each_invitation(self, monkeypatch):
        import extensions

        seen = []
        monkeypatch.setattr(
            extensions,
            "_hook_impls",
            lambda key: [("a", lambda db, inv, uid: seen.append((inv, uid)))],
        )
        extensions.run_after_invitations_accepted(None, ["i1", "i2"], "u1")
        assert seen == [("i1", "u1"), ("i2", "u1")]
