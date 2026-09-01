"""Membership gate on org-pays key resolution + the shared dispatch-org
resolver (2026-08-31).

An org that pays (``require_private_keys`` False) pays for its ACTIVE members
and superadmins only; everyone else degrades to their personal key. Covers
both ``resolve_api_key`` twins (api + shared/worker) and
``org_resolution.resolve_dispatch_org_for_project`` /
``validate_org_context_header``.
"""

import pytest
from sqlalchemy.orm import Session

from encryption_service import EncryptionService
from models import Organization, OrganizationMembership, OrganizationRole, User
from services.org_api_key_service import OrgApiKeyService

ORG_KEY = "sk-orgkey1234567890abcdef"
PERSONAL_KEY = "sk-personal1234567890abcd"


@pytest.fixture
def service():
    return OrgApiKeyService(EncryptionService())


@pytest.fixture
def paying_org(test_db: Session) -> Organization:
    org = Organization(
        id="org-pays-gate",
        name="Paying Org",
        display_name="Paying Org",
        slug="org-pays-gate",
        settings={"require_private_keys": False},
    )
    test_db.add(org)
    test_db.commit()
    return org


def _mk_user(db, uid, *, superadmin=False):
    user = User(
        id=uid,
        username=f"{uid}@test.com",
        email=f"{uid}@test.com",
        name=uid,
        hashed_password="!",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    return user


def _mk_member(db, user, org, *, active=True):
    m = OrganizationMembership(
        id=f"m-{user.id}-{org.id}",
        user_id=user.id,
        organization_id=org.id,
        role=OrganizationRole.ANNOTATOR,
        is_active=active,
    )
    db.add(m)
    db.commit()
    return m


def _seed_keys(service, db, org, admin_uid, *, personal_for=None):
    admin = _mk_user(db, admin_uid, superadmin=True)
    assert service.set_org_api_key(db, org.id, "openai", ORG_KEY, admin.id)
    if personal_for is not None:
        from services.user_api_key_service import user_api_key_service

        assert user_api_key_service.set_user_api_key(
            db, personal_for.id, "openai", PERSONAL_KEY
        )
    return admin


@pytest.mark.unit
class TestResolveApiKeyMembershipGate:
    def test_active_member_gets_the_org_key(self, service, test_db, paying_org):
        member = _mk_user(test_db, "gate-member")
        _mk_member(test_db, member, paying_org)
        _seed_keys(service, test_db, paying_org, "gate-admin-1")

        assert (
            service.resolve_api_key(test_db, member.id, paying_org.id, "openai")
            == ORG_KEY
        )

    def test_non_member_falls_back_to_the_personal_key(
        self, service, test_db, paying_org
    ):
        outsider = _mk_user(test_db, "gate-outsider")
        _seed_keys(service, test_db, paying_org, "gate-admin-2", personal_for=outsider)

        assert (
            service.resolve_api_key(test_db, outsider.id, paying_org.id, "openai")
            == PERSONAL_KEY
        )

    def test_non_member_without_personal_key_gets_none(
        self, service, test_db, paying_org
    ):
        outsider = _mk_user(test_db, "gate-outsider-nokey")
        _seed_keys(service, test_db, paying_org, "gate-admin-3")

        assert (
            service.resolve_api_key(test_db, outsider.id, paying_org.id, "openai")
            is None
        )

    def test_inactive_membership_does_not_count(self, service, test_db, paying_org):
        former = _mk_user(test_db, "gate-former")
        _mk_member(test_db, former, paying_org, active=False)
        _seed_keys(service, test_db, paying_org, "gate-admin-4", personal_for=former)

        assert (
            service.resolve_api_key(test_db, former.id, paying_org.id, "openai")
            == PERSONAL_KEY
        )

    def test_superadmin_bypasses_the_membership_gate(
        self, service, test_db, paying_org
    ):
        admin = _seed_keys(service, test_db, paying_org, "gate-admin-5")

        assert (
            service.resolve_api_key(test_db, admin.id, paying_org.id, "openai")
            == ORG_KEY
        )

    def test_shared_worker_twin_applies_the_same_gate(self, test_db, paying_org):
        from shared_org_api_key_service import OrgApiKeyService as SharedService

        shared = SharedService(EncryptionService())
        member = _mk_user(test_db, "gate-shared-member")
        _mk_member(test_db, member, paying_org)
        outsider = _mk_user(test_db, "gate-shared-outsider")
        _seed_keys(
            OrgApiKeyService(EncryptionService()),
            test_db,
            paying_org,
            "gate-admin-6",
            personal_for=outsider,
        )

        assert (
            shared.resolve_api_key(test_db, member.id, paying_org.id, "openai")
            == ORG_KEY
        )
        assert (
            shared.resolve_api_key(test_db, outsider.id, paying_org.id, "openai")
            == PERSONAL_KEY
        )

    def test_providers_for_context_mirror_the_gate(
        self, service, test_db, paying_org
    ):
        member = _mk_user(test_db, "gate-prov-member")
        _mk_member(test_db, member, paying_org)
        outsider = _mk_user(test_db, "gate-prov-outsider")
        _seed_keys(service, test_db, paying_org, "gate-admin-7")

        assert service.get_available_providers_for_context(
            test_db, member.id, paying_org.id
        ) == ["OpenAI"]
        # The UI must not advertise a provider resolve_api_key would refuse.
        assert (
            service.get_available_providers_for_context(
                test_db, outsider.id, paying_org.id
            )
            == []
        )


@pytest.mark.unit
class TestDispatchOrgResolver:
    def _project_with_org(self, db, org):
        from project_models import Project, ProjectOrganization

        creator = db.query(User).filter(User.id == f"res-creator-{org.id}").first()
        if creator is None:
            creator = _mk_user(db, f"res-creator-{org.id}")
        project = Project(
            id=f"proj-{org.id}", title="Gate Project", created_by=creator.id
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectOrganization(
                id=f"po-{org.id}",
                project_id=project.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.commit()
        return db.query(Project).filter(Project.id == project.id).first()

    def test_member_resolves_their_org(self, test_db, paying_org):
        from org_resolution import resolve_dispatch_org_for_project

        member = _mk_user(test_db, "res-member")
        _mk_member(test_db, member, paying_org)
        project = self._project_with_org(test_db, paying_org)

        assert (
            resolve_dispatch_org_for_project(test_db, member, project)
            == paying_org.id
        )

    def test_non_member_resolves_none(self, test_db, paying_org):
        from org_resolution import resolve_dispatch_org_for_project

        outsider = _mk_user(test_db, "res-outsider")
        project = self._project_with_org(test_db, paying_org)

        assert resolve_dispatch_org_for_project(test_db, outsider, project) is None

    def test_superadmin_keeps_the_first_org_fallback(self, test_db, paying_org):
        from org_resolution import resolve_dispatch_org_for_project

        admin = _mk_user(test_db, "res-admin", superadmin=True)
        project = self._project_with_org(test_db, paying_org)

        assert (
            resolve_dispatch_org_for_project(test_db, admin, project)
            == paying_org.id
        )

    def test_bare_user_id_is_accepted(self, test_db, paying_org):
        from org_resolution import resolve_dispatch_org_for_project

        member = _mk_user(test_db, "res-bare-id")
        _mk_member(test_db, member, paying_org)
        project = self._project_with_org(test_db, paying_org)

        assert (
            resolve_dispatch_org_for_project(test_db, member.id, project)
            == paying_org.id
        )

    def test_orgless_project_resolves_none(self, test_db):
        from org_resolution import resolve_dispatch_org_for_project
        from project_models import Project

        user = _mk_user(test_db, "res-orgless")
        project = Project(id="proj-orgless-gate", title="No Org", created_by=user.id)
        test_db.add(project)
        test_db.commit()

        assert resolve_dispatch_org_for_project(test_db, user, project) is None

    def test_header_validation(self, test_db, paying_org):
        from org_resolution import validate_org_context_header

        member = _mk_user(test_db, "hdr-member")
        _mk_member(test_db, member, paying_org)
        outsider = _mk_user(test_db, "hdr-outsider")
        admin = _mk_user(test_db, "hdr-admin", superadmin=True)

        assert (
            validate_org_context_header(test_db, member, paying_org.id)
            == paying_org.id
        )
        assert validate_org_context_header(test_db, outsider, paying_org.id) is None
        assert (
            validate_org_context_header(test_db, admin, paying_org.id)
            == paying_org.id
        )
        assert validate_org_context_header(test_db, member, None) is None


@pytest.mark.unit
class TestConsumerBillingFlag:
    """org_billing_authorized: policy-asserted consumer inheritance
    (2026-08-31). Bypasses only the membership gate — never the
    require_private_keys check."""

    def test_flag_lets_a_non_member_spend_the_org_pays_key(
        self, service, test_db, paying_org
    ):
        consumer = _mk_user(test_db, "flag-consumer")
        _seed_keys(service, test_db, paying_org, "flag-admin-1")

        assert (
            service.resolve_api_key(
                test_db,
                consumer.id,
                paying_org.id,
                "openai",
                org_billing_authorized=True,
            )
            == ORG_KEY
        )

    def test_flag_never_overrides_require_private_keys(self, service, test_db):
        org = Organization(
            id="org-private-flag",
            name="Private Org",
            display_name="Private Org",
            slug="org-private-flag",
            settings={"require_private_keys": True},
        )
        test_db.add(org)
        test_db.commit()
        consumer = _mk_user(test_db, "flag-private-consumer")
        _seed_keys(service, test_db, org, "flag-admin-2", personal_for=consumer)

        assert (
            service.resolve_api_key(
                test_db, consumer.id, org.id, "openai", org_billing_authorized=True
            )
            == PERSONAL_KEY
        )

    def test_default_false_preserves_the_gate(self, service, test_db, paying_org):
        consumer = _mk_user(test_db, "flag-default-consumer")
        _seed_keys(service, test_db, paying_org, "flag-admin-3", personal_for=consumer)

        assert (
            service.resolve_api_key(test_db, consumer.id, paying_org.id, "openai")
            == PERSONAL_KEY
        )

    def test_shared_worker_twin_honors_the_flag(self, test_db, paying_org):
        from shared_org_api_key_service import OrgApiKeyService as SharedService

        shared = SharedService(EncryptionService())
        consumer = _mk_user(test_db, "flag-shared-consumer")
        _seed_keys(
            OrgApiKeyService(EncryptionService()),
            test_db,
            paying_org,
            "flag-admin-4",
        )

        assert (
            shared.resolve_api_key(
                test_db,
                consumer.id,
                paying_org.id,
                "openai",
                org_billing_authorized=True,
            )
            == ORG_KEY
        )
        assert (
            shared.resolve_api_key(test_db, consumer.id, paying_org.id, "openai")
            is None
        )

    def test_route_stamp_marks_consumer_resolution(self, test_db, paying_org):
        from ai_services.user_aware_ai_service import user_aware_ai_service

        consumer = _mk_user(test_db, "flag-route-consumer")
        _seed_keys(
            OrgApiKeyService(EncryptionService()), test_db, paying_org, "flag-admin-5"
        )

        svc = user_aware_ai_service.get_ai_service_for_user(
            test_db,
            consumer.id,
            "openai",
            organization_id=paying_org.id,
            org_billing_authorized=True,
        )
        assert svc is not None
        assert svc._key_resolution_route == "org_resolved_consumer"


@pytest.mark.unit
class TestProjectConsumers:
    def test_predicates(self, test_db, paying_org):
        from datetime import datetime, timezone

        from project_consumers import is_project_consumer, project_linked_org_ids
        from project_models import (
            MarketplaceEntitlement,
            Project,
            ProjectOrganization,
            ProjectShareLink,
            ProjectShareMember,
        )

        creator = _mk_user(test_db, "pc-creator")
        project = Project(id="pc-project", title="PC", created_by=creator.id)
        test_db.add(project)
        test_db.flush()
        test_db.add(
            ProjectOrganization(
                id="pc-po",
                project_id=project.id,
                organization_id=paying_org.id,
                assigned_by=creator.id,
            )
        )
        test_db.commit()

        assert project_linked_org_ids(test_db, project) == [paying_org.id]
        assert project_linked_org_ids(test_db, project.id) == [paying_org.id]

        entitled = _mk_user(test_db, "pc-entitled")
        test_db.add(
            MarketplaceEntitlement(
                id="pc-ent",
                user_id=entitled.id,
                project_id=project.id,
                source="purchase",
            )
        )
        revoked = _mk_user(test_db, "pc-revoked")
        test_db.add(
            MarketplaceEntitlement(
                id="pc-rev",
                user_id=revoked.id,
                project_id=project.id,
                source="discovered",
                revoked_at=datetime.now(timezone.utc),
            )
        )
        link = ProjectShareLink(
            id="pc-link",
            token="pc-token",
            project_id=project.id,
            created_by=creator.id,
            password_hash="!",
        )
        test_db.add(link)
        test_db.flush()
        consented = _mk_user(test_db, "pc-consented")
        test_db.add(
            ProjectShareMember(
                id="pc-sm1",
                share_link_id=link.id,
                user_id=consented.id,
                project_id=project.id,
                gdpr_consent_at=datetime.now(timezone.utc),
            )
        )
        unconsented = _mk_user(test_db, "pc-unconsented")
        test_db.add(
            ProjectShareMember(
                id="pc-sm2",
                share_link_id=link.id,
                user_id=unconsented.id,
                project_id=project.id,
                gdpr_consent_at=None,
            )
        )
        test_db.commit()

        assert is_project_consumer(test_db, entitled.id, project.id) is True
        assert is_project_consumer(test_db, consented.id, project.id) is True
        assert is_project_consumer(test_db, revoked.id, project.id) is False
        assert is_project_consumer(test_db, unconsented.id, project.id) is False
        assert is_project_consumer(test_db, creator.id, project.id) is False
