"""Integration tests for the annotator exam carve-out and the org-membership
participant source (LTI cohort feature, 2026-07-24).

Three interlocking rules over org-shared exams (``kind='exam'`` projects
attached to an org via ``ProjectOrganization``):

1. ANNOTATOR org members never get the FULL project tier on exams
   (``check_project_accessible`` + its pure deciders) — full tier would expose
   raw ``task.data`` (the Musterlösung), exports, and other students'
   attempts. CONTRIBUTOR/ORG_ADMIN keep full tier.
2. Instead, ANY active org member reaches a NON-private, non-archived org
   exam through the narrow participant tier (``get_student_read_access``) —
   the university ongoing-training catalog. Private exams stay
   entitlement/share/creator-only.
3. The generic project browser hides org exams from annotators
   (``get_accessible_project_ids``) — the Klausuren list is their surface.

Plus the member-enumeration gate: annotators can no longer list org members.
Real Postgres via the sync ``test_db`` / async fixtures.
"""

import uuid
from datetime import datetime, timezone

import pytest

from models import Organization, OrganizationMembership, OrganizationRole, User
from project_models import MarketplaceEntitlement, Project, ProjectOrganization
from routers.projects.helpers import (
    _decide_project_accessible_context_mode,
    _decide_project_accessible_legacy_mode,
    _org_grants_full_tier,
    check_project_accessible,
    get_accessible_project_ids,
    get_student_read_access,
)


def _user(test_db, tag, superadmin=False):
    u = User(
        id=f"oxa-{tag}-{uuid.uuid4().hex[:8]}",
        username=f"oxa-{uuid.uuid4().hex[:8]}",
        email=f"oxa-{uuid.uuid4().hex[:8]}@test.com",
        name=f"OXA {tag}",
        hashed_password="x",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(u)
    test_db.flush()
    return u


def _org(test_db):
    suffix = uuid.uuid4().hex[:8]
    o = Organization(
        id=f"oxa-org-{suffix}",
        name=f"OXA Uni {suffix}",
        display_name=f"OXA Uni {suffix}",
        slug=f"oxa-uni-{suffix}",
        is_active=True,
    )
    test_db.add(o)
    test_db.flush()
    return o


def _member(test_db, user, org, role, active=True):
    m = OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=active,
    )
    test_db.add(m)
    test_db.flush()
    return m


def _project(test_db, owner_id, org=None, *, kind="exam", is_private=False,
             is_archived=False, title="OXA org exam", window_start_at=None,
             window_end_at=None):
    p = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner_id,
        kind=kind,
        is_private=is_private,
        is_public=False,
        is_archived=is_archived,
        window_start_at=window_start_at,
        window_end_at=window_end_at,
    )
    test_db.add(p)
    test_db.flush()
    if org is not None:
        test_db.add(
            ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=owner_id,
            )
        )
        test_db.flush()
    return p


class _Membership:
    """Bare pure-decider stand-in (only role/org/is_active are read)."""

    def __init__(self, org_id, role, is_active=True):
        self.organization_id = org_id
        self.role = role
        self.is_active = is_active


class _Memberships:
    def __init__(self, *memberships):
        self.organization_memberships = list(memberships)


class _U:
    def __init__(self, uid):
        self.id = uid


class _P:
    def __init__(self, kind="exam", is_private=False, created_by="owner"):
        self.kind = kind
        self.is_private = is_private
        self.created_by = created_by


class TestOrgGrantsFullTierPredicate:
    def test_annotator_denied_on_exam(self):
        m = _Membership("o1", OrganizationRole.ANNOTATOR)
        assert _org_grants_full_tier(_P(kind="exam"), m) is False

    def test_contributor_and_admin_allowed_on_exam(self):
        for role in (OrganizationRole.CONTRIBUTOR, OrganizationRole.ORG_ADMIN):
            assert _org_grants_full_tier(_P(kind="exam"), _Membership("o1", role)) is True

    def test_annotator_allowed_on_non_exam_kinds(self):
        m = _Membership("o1", OrganizationRole.ANNOTATOR)
        for kind in (None, "korrektur", "benchmark"):
            assert _org_grants_full_tier(_P(kind=kind), m) is True


class TestPureDeciders:
    def test_context_mode_annotator_denied_contributor_allowed(self):
        project = _P(kind="exam", is_private=False)
        annotator = _Memberships(_Membership("o1", OrganizationRole.ANNOTATOR))
        contributor = _Memberships(_Membership("o1", OrganizationRole.CONTRIBUTOR))
        args = (_U("u1"), project, "o1", ["o1"])
        assert _decide_project_accessible_context_mode(*args, annotator) is False
        assert _decide_project_accessible_context_mode(*args, contributor) is True

    def test_legacy_mode_annotator_denied_contributor_allowed(self):
        project = _P(kind="exam", is_private=False)
        annotator = _Memberships(_Membership("o1", OrganizationRole.ANNOTATOR))
        contributor = _Memberships(_Membership("o1", OrganizationRole.CONTRIBUTOR))
        args = (_U("u1"), project, ["o1"])
        assert _decide_project_accessible_legacy_mode(*args, annotator) is False
        assert _decide_project_accessible_legacy_mode(*args, contributor) is True

    def test_private_exam_stays_creator_only_for_all_roles(self):
        project = _P(kind="exam", is_private=True, created_by="creator")
        contributor = _Memberships(_Membership("o1", OrganizationRole.CONTRIBUTOR))
        assert (
            _decide_project_accessible_context_mode(
                _U("creator"), project, "o1", ["o1"], contributor
            )
            is True
        )
        assert (
            _decide_project_accessible_context_mode(
                _U("someone-else"), project, "o1", ["o1"], contributor
            )
            is False
        )

    def test_annotator_keeps_access_to_non_exam_org_projects(self):
        project = _P(kind="korrektur", is_private=False)
        annotator = _Memberships(_Membership("o1", OrganizationRole.ANNOTATOR))
        assert (
            _decide_project_accessible_context_mode(
                _U("u1"), project, "o1", ["o1"], annotator
            )
            is True
        )
        assert (
            _decide_project_accessible_legacy_mode(_U("u1"), project, ["o1"], annotator)
            is True
        )


class TestCheckProjectAccessibleSync:
    def test_annotator_denied_full_tier_on_org_exam_both_modes(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)

        assert check_project_accessible(test_db, student, exam.id, org.id) is False
        assert check_project_accessible(test_db, student, exam.id, None) is False

    def test_contributor_keeps_full_tier_on_org_exam(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        staff = _user(test_db, "staff")
        _member(test_db, staff, org, OrganizationRole.CONTRIBUTOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)

        assert check_project_accessible(test_db, staff, exam.id, org.id) is True
        assert check_project_accessible(test_db, staff, exam.id, None) is True

    def test_annotator_keeps_full_tier_on_non_exam_org_project(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        proj = _project(test_db, owner.id, org, kind="korrektur", is_private=False)

        assert check_project_accessible(test_db, student, proj.id, org.id) is True
        assert check_project_accessible(test_db, student, proj.id, None) is True

    def test_archived_org_exam_denied_to_annotator(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(
            test_db, owner.id, org, kind="exam", is_private=False, is_archived=True
        )
        assert check_project_accessible(test_db, student, exam.id, org.id) is False


class TestOrgExamParticipantSource:
    def test_active_member_gets_participant_access_on_org_exam(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)

        assert get_student_read_access(test_db, student, exam.id) is True

    def test_private_org_exam_not_granted_by_membership(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=True)

        assert get_student_read_access(test_db, student, exam.id) is False

    def test_archived_org_exam_not_granted(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(
            test_db, owner.id, org, kind="exam", is_private=False, is_archived=True
        )
        assert get_student_read_access(test_db, student, exam.id) is False

    def test_windowed_org_exam_not_granted_by_membership(self, test_db):
        """Scheduled finals (access window set) are excluded from the org
        catalog grant — enterable only via LTI launch / share / entitlement,
        so the Sachverhalt can't be pre-read before the window opens."""
        from datetime import timedelta

        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        now = datetime.now(timezone.utc)
        exam = _project(
            test_db, owner.id, org, kind="exam", is_private=False,
            window_start_at=now + timedelta(days=1),
            window_end_at=now + timedelta(days=2),
        )
        assert get_student_read_access(test_db, student, exam.id) is False

        # Entitlement (e.g. the LTI resource-link grant) still pierces it.
        test_db.add(
            MarketplaceEntitlement(
                id=str(uuid.uuid4()),
                user_id=student.id,
                project_id=exam.id,
                source="lti",
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, exam.id) is True

    def test_non_exam_org_project_not_granted_via_this_source(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        proj = _project(test_db, owner.id, org, kind="korrektur", is_private=False)

        assert get_student_read_access(test_db, student, proj.id) is False

    def test_non_member_and_inactive_member_denied(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        stranger = _user(test_db, "stranger")
        inactive = _user(test_db, "inactive")
        _member(test_db, inactive, org, OrganizationRole.ANNOTATOR, active=False)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)

        assert get_student_read_access(test_db, stranger, exam.id) is False
        assert get_student_read_access(test_db, inactive, exam.id) is False

    def test_membership_grants_even_with_revoked_entitlement(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)
        test_db.add(
            MarketplaceEntitlement(
                id=str(uuid.uuid4()),
                user_id=student.id,
                project_id=exam.id,
                source="lti",
                revoked_at=datetime.now(timezone.utc),
            )
        )
        test_db.flush()
        assert get_student_read_access(test_db, student, exam.id) is True


class TestAccessibleProjectIdsAnnotatorFilter:
    def test_annotator_org_list_excludes_exams(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        student = _user(test_db, "student")
        _member(test_db, student, org, OrganizationRole.ANNOTATOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)
        research = _project(
            test_db, owner.id, org, kind="korrektur", is_private=False,
            title="OXA research",
        )

        ids = get_accessible_project_ids(test_db, student, org_context=org.id)
        assert research.id in ids
        assert exam.id not in ids

    def test_contributor_org_list_includes_exams(self, test_db):
        org = _org(test_db)
        owner = _user(test_db, "owner")
        staff = _user(test_db, "staff")
        _member(test_db, staff, org, OrganizationRole.CONTRIBUTOR)
        exam = _project(test_db, owner.id, org, kind="exam", is_private=False)

        ids = get_accessible_project_ids(test_db, staff, org_context=org.id)
        assert exam.id in ids


from contextlib import contextmanager


@contextmanager
def _as_org_user(db_user):
    """Override the org routers' ``get_current_user`` dependency (they use it,
    not ``require_user``) with an auth-model user built from the DB row."""
    from auth_module import get_current_user
    from auth_module.models import User as AuthUser
    from main import app

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
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestMemberListGating:
    async def _setup(self, async_test_db, role):
        suffix = uuid.uuid4().hex[:8]
        org = Organization(
            id=f"mlg-org-{suffix}",
            name=f"MLG {suffix}",
            display_name=f"MLG {suffix}",
            slug=f"mlg-{suffix}",
            is_active=True,
        )
        user = User(
            id=f"mlg-{suffix}",
            username=f"mlg-{suffix}",
            email=f"mlg-{suffix}@test.com",
            name="MLG member",
            hashed_password="x",
            is_active=True,
            email_verified=True,
        )
        async_test_db.add_all([org, user])
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
            )
        )
        await async_test_db.flush()
        return org, user

    async def test_annotator_gets_403_contributor_200(
        self, async_test_client, async_test_db
    ):
        org_a, annotator = await self._setup(
            async_test_db, OrganizationRole.ANNOTATOR
        )
        with _as_org_user(annotator):
            r = await async_test_client.get(f"/api/organizations/{org_a.id}/members")
            assert r.status_code == 403

        org_c, contributor = await self._setup(
            async_test_db, OrganizationRole.CONTRIBUTOR
        )
        with _as_org_user(contributor):
            r = await async_test_client.get(f"/api/organizations/{org_c.id}/members")
            assert r.status_code == 200
            assert len(r.json()) == 1

    async def test_manage_users_empty_for_annotator_only_caller(
        self, async_test_client, async_test_db
    ):
        org, annotator = await self._setup(async_test_db, OrganizationRole.ANNOTATOR)
        with _as_org_user(annotator):
            r = await async_test_client.get("/api/organizations/manage/users")
            assert r.status_code == 200
            assert r.json() == []
