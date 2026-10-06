"""Pure-predicate matrix for organization-group scoping (shared/org_groups).

The single rule (attachment_role, and attachment_eligible / grants_full_tier /
lti_staff_role / drop_protected_lti_attachments derived from it) is the
foundation every enforcement surface composes - list arms, per-project
deciders, participant arms, admin gates, key resolution. These tests pin the
rule itself plus the group-aware effective-role resolution so any drift in
the shared module fails loudly here before it leaks anywhere.
"""

from unittest.mock import Mock

import pytest

from models import OrganizationRole
from org_groups import (
    ROLE_RANK,
    attachment_eligible,
    attachment_role,
    best_role,
    drop_protected_lti_attachments,
    grants_full_tier,
    lti_staff_role,
    role_at_least,
)
from routers.projects.helpers import _resolve_effective_role

ROLES = ("ANNOTATOR", "CONTRIBUTOR", "ORG_ADMIN")


class TestAttachmentRole:
    @pytest.mark.parametrize("org_role", ROLES)
    @pytest.mark.parametrize("group_role", (None,) + ROLES)
    def test_ungrouped_attachment_gives_org_role(self, org_role, group_role):
        groups = {"g1": group_role} if group_role else {}
        assert attachment_role(None, org_role, groups) == org_role

    @pytest.mark.parametrize("group_role", (None,) + ROLES)
    def test_org_admin_is_admin_in_every_group(self, group_role):
        groups = {"g1": group_role} if group_role else {}
        assert attachment_role("g1", "ORG_ADMIN", groups) == "ORG_ADMIN"

    @pytest.mark.parametrize("org_role", ("ANNOTATOR", "CONTRIBUTOR"))
    @pytest.mark.parametrize("group_role", ROLES)
    def test_group_role_decides_in_either_direction(self, org_role, group_role):
        assert attachment_role("g1", org_role, {"g1": group_role}) == group_role

    @pytest.mark.parametrize("org_role", ("ANNOTATOR", "CONTRIBUTOR"))
    def test_not_a_group_member_gives_nothing(self, org_role):
        assert attachment_role("g1", org_role, {"g2": "ORG_ADMIN"}) is None
        assert attachment_role("g1", org_role, None) is None
        assert attachment_role("g1", org_role, {}) is None

    def test_enum_and_string_inputs(self):
        assert (
            attachment_role(
                "g1", OrganizationRole.ANNOTATOR, {"g1": OrganizationRole.CONTRIBUTOR}
            )
            == "CONTRIBUTOR"
        )
        assert attachment_role(None, OrganizationRole.CONTRIBUTOR) == "CONTRIBUTOR"
        assert attachment_role("g1", "org_admin") == "ORG_ADMIN"

    def test_no_org_role_on_ungrouped_attachment(self):
        assert attachment_role(None, None) is None


class TestRanks:
    def test_rank_order(self):
        assert ROLE_RANK == {"ANNOTATOR": 0, "CONTRIBUTOR": 1, "ORG_ADMIN": 2}

    def test_best_role(self):
        assert best_role([]) is None
        assert best_role([None, None]) is None
        assert best_role(["ANNOTATOR", None, OrganizationRole.CONTRIBUTOR]) == "CONTRIBUTOR"
        assert best_role(["ORG_ADMIN", "ANNOTATOR"]) == "ORG_ADMIN"

    def test_role_at_least(self):
        assert role_at_least("ORG_ADMIN", "CONTRIBUTOR") is True
        assert role_at_least(OrganizationRole.CONTRIBUTOR, "CONTRIBUTOR") is True
        assert role_at_least("ANNOTATOR", "CONTRIBUTOR") is False
        assert role_at_least(None, "ANNOTATOR") is False


class TestAttachmentEligible:
    def test_ungrouped_attachment_is_org_wide(self):
        assert attachment_eligible(None) is True
        assert attachment_eligible(None, membership_role=OrganizationRole.ANNOTATOR) is True

    @pytest.mark.parametrize("group_role", ROLES)
    def test_group_member_eligible_whatever_the_role(self, group_role):
        assert attachment_eligible(
            "g1",
            membership_role=OrganizationRole.ANNOTATOR,
            user_groups={"g1": group_role},
        ) is True

    def test_non_member_ineligible(self):
        assert attachment_eligible(
            "g1",
            membership_role=OrganizationRole.CONTRIBUTOR,
            user_groups={"g2": "ORG_ADMIN"},
        ) is False
        assert attachment_eligible("g1", user_groups=None) is False
        assert attachment_eligible("g1", user_groups={}) is False

    def test_org_admin_sees_through_groups(self):
        assert attachment_eligible(
            "g1", membership_role=OrganizationRole.ORG_ADMIN, user_groups={}
        ) is True
        assert attachment_eligible("g1", membership_role="ORG_ADMIN") is True

    def test_creator_never_loses_own_project(self):
        assert attachment_eligible(
            "g1", is_creator=True, membership_role=OrganizationRole.ANNOTATOR
        ) is True

    def test_superadmin_eligible(self):
        assert attachment_eligible("g1", is_superadmin=True) is True


class TestGrantsFullTier:
    @pytest.mark.parametrize("role", ROLES)
    def test_non_exam_always_full(self, role):
        assert grants_full_tier(None, role) is True
        assert grants_full_tier("flashcard_collection", role) is True

    def test_exam_staff_roles_full(self):
        assert grants_full_tier("exam", OrganizationRole.CONTRIBUTOR) is True
        assert grants_full_tier("exam", "ORG_ADMIN") is True

    def test_exam_annotator_denied(self):
        assert grants_full_tier("exam", OrganizationRole.ANNOTATOR) is False
        assert grants_full_tier("exam", "ANNOTATOR") is False

    @pytest.mark.parametrize(
        "org_role,group_role,full",
        [
            # org ANNOTATOR + group Admin: admin on the group's exam
            ("ANNOTATOR", "ORG_ADMIN", True),
            ("ANNOTATOR", "CONTRIBUTOR", True),
            ("ANNOTATOR", "ANNOTATOR", False),
            # org CONTRIBUTOR + group ANNOTATOR: only the participant tier
            ("CONTRIBUTOR", "ANNOTATOR", False),
            ("ORG_ADMIN", "ANNOTATOR", True),
        ],
    )
    def test_exam_grouped_attachment_uses_group_role(self, org_role, group_role, full):
        role = attachment_role("g1", org_role, {"g1": group_role})
        assert grants_full_tier("exam", role) is full


def _membership(org_id, role, active=True):
    return Mock(organization_id=org_id, role=role, is_active=active)


def _uwm(*memberships):
    return Mock(organization_memberships=list(memberships))


class TestLtiStaffRole:
    @pytest.mark.parametrize(
        "org_role,group_role,expected",
        [
            ("ANNOTATOR", None, None),
            ("ANNOTATOR", "ANNOTATOR", None),
            ("ANNOTATOR", "CONTRIBUTOR", "CONTRIBUTOR"),
            ("ANNOTATOR", "ORG_ADMIN", "ORG_ADMIN"),
            ("CONTRIBUTOR", None, None),
            ("CONTRIBUTOR", "ANNOTATOR", None),
            ("CONTRIBUTOR", "CONTRIBUTOR", "CONTRIBUTOR"),
            ("ORG_ADMIN", None, "ORG_ADMIN"),
            ("ORG_ADMIN", "ANNOTATOR", "ORG_ADMIN"),
        ],
    )
    def test_grouped_link(self, org_role, group_role, expected):
        groups = {"g1": group_role} if group_role else {}
        assert (
            lti_staff_role("exam", [_membership("o1", org_role)], {"o1": "g1"}, groups)
            == expected
        )

    @pytest.mark.parametrize(
        "org_role,expected",
        [("ANNOTATOR", None), ("CONTRIBUTOR", "CONTRIBUTOR"), ("ORG_ADMIN", "ORG_ADMIN")],
    )
    def test_org_wide_link(self, org_role, expected):
        assert (
            lti_staff_role(
                "exam", [_membership("o1", org_role)], {"o1": None}, {"g1": "ORG_ADMIN"}
            )
            == expected
        )

    def test_non_exam_and_inactive(self):
        assert lti_staff_role(None, [_membership("o1", "ORG_ADMIN")], {"o1": None}) is None
        assert (
            lti_staff_role("exam", [_membership("o1", "ORG_ADMIN", active=False)], {"o1": None})
            is None
        )

    def test_protected_org_counts_admins_only(self):
        assert (
            lti_staff_role(
                "exam",
                [_membership("o1", "CONTRIBUTOR")],
                {"o1": "g1"},
                {"g1": "CONTRIBUTOR"},
                protected_org_ids={"o1"},
            )
            is None
        )
        assert (
            lti_staff_role(
                "exam",
                [_membership("o1", "ANNOTATOR")],
                {"o1": "g1"},
                {"g1": "ORG_ADMIN"},
                protected_org_ids={"o1"},
            )
            == "ORG_ADMIN"
        )

    def test_best_role_over_memberships(self):
        assert (
            lti_staff_role(
                "exam",
                [_membership("o1", "CONTRIBUTOR"), _membership("o2", "ANNOTATOR")],
                {"o1": None, "o2": "g2"},
                {"g2": "ORG_ADMIN"},
            )
            == "ORG_ADMIN"
        )


class TestDropProtectedLtiAttachments:
    def test_keeps_rows_for_admin_roles_only(self):
        attachments = {"o1": "g1", "o2": None}
        protected = {"o1"}
        assert drop_protected_lti_attachments(
            attachments, protected, [_membership("o1", "CONTRIBUTOR")], {"g1": "CONTRIBUTOR"}
        ) == {"o2": None}
        assert drop_protected_lti_attachments(
            attachments, protected, [_membership("o1", "ANNOTATOR")], {"g1": "ORG_ADMIN"}
        ) == attachments
        assert drop_protected_lti_attachments(
            attachments, protected, [_membership("o1", "ORG_ADMIN")], {}
        ) == attachments


class TestResolveEffectiveRoleGroups:
    def _project(self, **kw):
        defaults = dict(created_by="owner", is_public=False, public_role=None, kind=None)
        defaults.update(kw)
        return Mock(**defaults)

    def test_ungrouped_behavior_unchanged(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.CONTRIBUTOR)),
            ["o1"],
        )
        assert role == OrganizationRole.CONTRIBUTOR

    def test_ineligible_grouped_attachment_yields_none(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.CONTRIBUTOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={},
        )
        assert role is None

    def test_group_role_replaces_org_role_on_grouped_attachment(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.CONTRIBUTOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={"g1": "ANNOTATOR"},
        )
        assert role == "ANNOTATOR"

    def test_group_admin_is_org_admin_on_grouped_attachment_only(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.ANNOTATOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={"g1": "ORG_ADMIN"},
        )
        assert role == "ORG_ADMIN"
        # No upgrade on an UNGROUPED attachment of the same org.
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.ANNOTATOR)),
            ["o1"],
            attachment_groups={"o1": None},
            user_groups={"g1": "ORG_ADMIN"},
        )
        assert role == OrganizationRole.ANNOTATOR

    def test_best_eligible_role_wins_not_first_match(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(
                _membership("o1", OrganizationRole.ORG_ADMIN, active=False),
                _membership("o2", OrganizationRole.ANNOTATOR),
                _membership("o3", OrganizationRole.CONTRIBUTOR),
            ),
            ["o1", "o2", "o3"],
            attachment_groups={"o1": None, "o2": None, "o3": None},
            user_groups={},
        )
        assert role == OrganizationRole.CONTRIBUTOR

    def test_creator_eligible_through_foreign_group(self):
        user = Mock(id="owner")
        role = _resolve_effective_role(
            user,
            self._project(created_by="owner"),
            _uwm(_membership("o1", OrganizationRole.ANNOTATOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={},
        )
        # Creator stays eligible (the wrappers short-circuit creators to
        # ORG_ADMIN before ever reaching this, but the pure decider must not
        # hide the membership either).
        assert role == OrganizationRole.ANNOTATOR

    def test_public_role_fallback_when_no_eligible_membership(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(is_public=True, public_role="ANNOTATOR"),
            _uwm(_membership("o1", OrganizationRole.CONTRIBUTOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={},
        )
        assert role == "ANNOTATOR"
