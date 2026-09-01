"""Pure-predicate matrix for organization-group scoping (shared/org_groups).

The single eligibility rule (attachment_eligible / grants_full_tier) is the
foundation every enforcement surface composes — list arms, per-project
deciders, participant arms, admin gates, key resolution. These tests pin the
rule itself plus the group-aware effective-role resolution so any drift in
the shared module fails loudly here before it leaks anywhere.
"""

from unittest.mock import Mock

from models import OrganizationRole
from org_groups import attachment_eligible, grants_full_tier
from routers.projects.helpers import _resolve_effective_role


class TestAttachmentEligible:
    def test_ungrouped_attachment_is_org_wide(self):
        assert attachment_eligible(None) is True
        assert attachment_eligible(None, membership_role=OrganizationRole.ANNOTATOR) is True

    def test_group_member_eligible(self):
        assert attachment_eligible(
            "g1",
            membership_role=OrganizationRole.ANNOTATOR,
            user_groups={"g1": False},
        ) is True

    def test_non_member_ineligible(self):
        assert attachment_eligible(
            "g1",
            membership_role=OrganizationRole.CONTRIBUTOR,
            user_groups={"g2": True},
        ) is False
        assert attachment_eligible("g1", user_groups=None) is False
        assert attachment_eligible("g1", user_groups={}) is False

    def test_org_admin_sees_through_groups(self):
        assert attachment_eligible(
            "g1", membership_role=OrganizationRole.ORG_ADMIN, user_groups={}
        ) is True
        # Role passed as a bare string (authorization.py lane) works too.
        assert attachment_eligible("g1", membership_role="ORG_ADMIN") is True

    def test_creator_never_loses_own_project(self):
        assert attachment_eligible(
            "g1", is_creator=True, membership_role=OrganizationRole.ANNOTATOR
        ) is True

    def test_superadmin_eligible(self):
        assert attachment_eligible("g1", is_superadmin=True) is True


class TestGrantsFullTier:
    def test_non_exam_always_full(self):
        assert grants_full_tier(None, OrganizationRole.ANNOTATOR) is True
        assert grants_full_tier("flashcard_collection", OrganizationRole.ANNOTATOR) is True

    def test_exam_staff_roles_full(self):
        assert grants_full_tier("exam", OrganizationRole.CONTRIBUTOR) is True
        assert grants_full_tier("exam", OrganizationRole.ORG_ADMIN) is True

    def test_exam_annotator_denied(self):
        assert grants_full_tier("exam", OrganizationRole.ANNOTATOR) is False
        assert grants_full_tier("exam", OrganizationRole.ANNOTATOR, "g1", {"g1": False}) is False

    def test_exam_annotator_group_admin_of_attachment_group_full(self):
        # Invariant: group admin ⇒ admin powers on the group's projects,
        # regardless of org role.
        assert grants_full_tier("exam", OrganizationRole.ANNOTATOR, "g1", {"g1": True}) is True
        # ...but only for THAT attachment's group.
        assert grants_full_tier("exam", OrganizationRole.ANNOTATOR, "g2", {"g1": True}) is False


def _membership(org_id, role, active=True):
    return Mock(organization_id=org_id, role=role, is_active=active)


def _uwm(*memberships):
    return Mock(organization_memberships=list(memberships))


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

    def test_group_member_keeps_org_role(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.CONTRIBUTOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={"g1": False},
        )
        assert role == OrganizationRole.CONTRIBUTOR

    def test_group_admin_upgrades_to_org_admin_scoped(self):
        user = Mock(id="u1")
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.ANNOTATOR)),
            ["o1"],
            attachment_groups={"o1": "g1"},
            user_groups={"g1": True},
        )
        assert role == "ORG_ADMIN"
        # No upgrade on an UNGROUPED attachment of the same org.
        role = _resolve_effective_role(
            user,
            self._project(),
            _uwm(_membership("o1", OrganizationRole.ANNOTATOR)),
            ["o1"],
            attachment_groups={"o1": None},
            user_groups={"g1": True},
        )
        assert role == OrganizationRole.ANNOTATOR

    def test_best_eligible_role_wins_not_first_match(self):
        # Membership order must not decide: first org's attachment is
        # ineligible, second grants CONTRIBUTOR — CONTRIBUTOR wins over
        # falling through to public_role/None.
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
