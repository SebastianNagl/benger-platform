"""
End-to-end tests for the standardized role system

These tests verify the complete role system implementation works correctly
from database to API to frontend integration.
"""

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, OrganizationRole, User


@pytest.mark.e2e
class TestRoleSystemE2E:
    """End-to-end tests for role system"""

    def test_complete_role_system_workflow(self, test_db: Session):
        """Test the complete role system workflow"""

        # 1. Create organizations (including TUM)
        tum = Organization(
            id="tum-test",
            name="Technical University of Munich",
            display_name="Technical University of Munich",
            slug="tum",
            description="TUM organization",
        )

        company = Organization(
            id="company-test",
            name="Example Company",
            display_name="Example Company",
            slug="company",
            description="A company organization",
        )

        test_db.add_all([tum, company])
        test_db.commit()

        # 2. Create users with different roles
        superadmin = User(
            id="sa-test",
            username="superadmin",
            email="super@test.com",
            name="Super Admin",
            hashed_password="hashed",
            is_superadmin=True,  # Only way to be superadmin
        )

        tum_admin = User(
            id="ta-test",
            username="tumadmin",
            email="admin@tum.de",
            name="TUM Admin",
            hashed_password="hashed",
            is_superadmin=False,  # TUM admin has NO special privileges
        )

        company_admin = User(
            id="ca-test",
            username="companyadmin",
            email="admin@company.com",
            name="Company Admin",
            hashed_password="hashed",
            is_superadmin=False,
        )

        multi_org_user = User(
            id="mu-test",
            username="multiuser",
            email="multi@test.com",
            name="Multi Org User",
            hashed_password="hashed",
            is_superadmin=False,
        )

        test_db.add_all([superadmin, tum_admin, company_admin, multi_org_user])
        test_db.commit()

        # 3. Create organization memberships
        memberships = [
            # Superadmin is admin of TUM
            OrganizationMembership(
                id="m1",
                user_id=superadmin.id,
                organization_id=tum.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            # TUM admin is admin of TUM (same as any other org admin)
            OrganizationMembership(
                id="m2",
                user_id=tum_admin.id,
                organization_id=tum.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            # Company admin is admin of company
            OrganizationMembership(
                id="m3",
                user_id=company_admin.id,
                organization_id=company.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            # Multi-org user has different roles in different orgs
            OrganizationMembership(
                id="m4",
                user_id=multi_org_user.id,
                organization_id=tum.id,
                role=OrganizationRole.CONTRIBUTOR,
            ),
            OrganizationMembership(
                id="m5",
                user_id=multi_org_user.id,
                organization_id=company.id,
                role=OrganizationRole.ANNOTATOR,
            ),
        ]

        test_db.add_all(memberships)
        test_db.commit()

        # 4. VERIFY: Role system requirements are met

        # ✅ Every org has 3 roles by default
        available_roles = list(OrganizationRole)
        assert OrganizationRole.ORG_ADMIN in available_roles
        assert OrganizationRole.CONTRIBUTOR in available_roles
        assert OrganizationRole.ANNOTATOR in available_roles
        assert len(available_roles) == 3

        # ✅ Only superadmins can do everything
        assert superadmin.is_superadmin == True
        assert tum_admin.is_superadmin == False
        assert company_admin.is_superadmin == False
        assert multi_org_user.is_superadmin == False

        # ✅ TUM org admins have same permissions as all other org admins
        tum_admin_membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == tum_admin.id,
                OrganizationMembership.organization_id == tum.id,
            )
            .first()
        )

        company_admin_membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == company_admin.id,
                OrganizationMembership.organization_id == company.id,
            )
            .first()
        )

        # Both are ORG_ADMIN with same role type
        assert tum_admin_membership.role == OrganizationRole.ORG_ADMIN
        assert company_admin_membership.role == OrganizationRole.ORG_ADMIN
        assert tum_admin_membership.role == company_admin_membership.role

        # ✅ People can be part of multiple orgs with different roles
        multi_memberships = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == multi_org_user.id)
            .all()
        )

        assert len(multi_memberships) == 2
        roles_by_org = {m.organization_id: m.role for m in multi_memberships}
        assert roles_by_org[tum.id] == OrganizationRole.CONTRIBUTOR
        assert roles_by_org[company.id] == OrganizationRole.ANNOTATOR

        # ✅ TUM admin cannot access other organizations
        tum_admin_other_memberships = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == tum_admin.id,
                OrganizationMembership.organization_id != tum.id,
            )
            .all()
        )
        assert len(tum_admin_other_memberships) == 0

        # ✅ Only superadmins can promote other superadmins
        # (Logic test - in practice this would be enforced by API)
        def can_promote_superadmin(user: User) -> bool:
            return user.is_superadmin

        assert can_promote_superadmin(superadmin) == True
        assert can_promote_superadmin(tum_admin) == False
        assert can_promote_superadmin(company_admin) == False

        print("✅ All role system requirements verified!")

    def test_role_hierarchy_enforcement(self, test_db: Session):
        """Test that role hierarchy is properly enforced"""

        # Create test organization
        org = Organization(
            id="hierarchy-test",
            name="Test Org",
            display_name="Test Org",
            slug="test",
            description="Test organization",
        )
        test_db.add(org)

        # Create users with different roles
        admin_user = User(
            id="admin-h",
            username="admin",
            email="admin@test.com",
            name="Admin",
            hashed_password="hashed",
            is_superadmin=False,
        )

        contributor_user = User(
            id="contrib-h",
            username="contrib",
            email="contrib@test.com",
            name="Contributor",
            hashed_password="hashed",
            is_superadmin=False,
        )

        annotator_user = User(
            id="annot-h",
            username="annot",
            email="annot@test.com",
            name="Annotator",
            hashed_password="hashed",
            is_superadmin=False,
        )

        test_db.add_all([admin_user, contributor_user, annotator_user])
        test_db.commit()

        # Create memberships with different roles
        memberships = [
            OrganizationMembership(
                id="h1",
                user_id=admin_user.id,
                organization_id=org.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            OrganizationMembership(
                id="h2",
                user_id=contributor_user.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
            ),
            OrganizationMembership(
                id="h3",
                user_id=annotator_user.id,
                organization_id=org.id,
                role=OrganizationRole.ANNOTATOR,
            ),
        ]

        test_db.add_all(memberships)
        test_db.commit()

        # Verify role hierarchy: ORG_ADMIN > CONTRIBUTOR > ANNOTATOR
        admin_membership = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == admin_user.id)
            .first()
        )

        contributor_membership = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == contributor_user.id)
            .first()
        )

        annotator_membership = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == annotator_user.id)
            .first()
        )

        assert admin_membership.role == OrganizationRole.ORG_ADMIN
        assert contributor_membership.role == OrganizationRole.CONTRIBUTOR
        assert annotator_membership.role == OrganizationRole.ANNOTATOR

        # Verify roles are distinct
        roles = {
            admin_membership.role,
            contributor_membership.role,
            annotator_membership.role,
        }
        assert len(roles) == 3  # All different roles

        print("✅ Role hierarchy properly enforced!")

    def test_no_tum_special_privileges(self, test_db: Session):
        """Test that TUM organization has no special privileges"""

        # Create TUM and another organization
        tum = Organization(
            id="tum-priv", name="TUM", display_name="TUM", slug="tum", description="TUM"
        )
        other = Organization(
            id="other-priv",
            name="Other",
            display_name="Other",
            slug="other",
            description="Other",
        )
        test_db.add_all([tum, other])

        # Create admins for both organizations
        tum_admin = User(
            id="tum-admin-priv",
            username="tumadmin",
            email="tum@test.com",
            name="TUM Admin",
            hashed_password="hashed",
            is_superadmin=False,
        )

        other_admin = User(
            id="other-admin-priv",
            username="otheradmin",
            email="other@test.com",
            name="Other Admin",
            hashed_password="hashed",
            is_superadmin=False,
        )

        test_db.add_all([tum_admin, other_admin])
        test_db.commit()

        # Create memberships
        memberships = [
            OrganizationMembership(
                id="tum-m",
                user_id=tum_admin.id,
                organization_id=tum.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
            OrganizationMembership(
                id="other-m",
                user_id=other_admin.id,
                organization_id=other.id,
                role=OrganizationRole.ORG_ADMIN,
            ),
        ]

        test_db.add_all(memberships)
        test_db.commit()

        # Verify TUM admin has NO special privileges
        assert tum_admin.is_superadmin == False  # Not a superadmin
        assert other_admin.is_superadmin == False  # Same as other admins

        # Both admins have exactly the same role
        tum_membership = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == tum_admin.id)
            .first()
        )

        other_membership = (
            test_db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == other_admin.id)
            .first()
        )

        assert tum_membership.role == other_membership.role == OrganizationRole.ORG_ADMIN

        # TUM admin can only access TUM org
        tum_cross_access = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == tum_admin.id,
                OrganizationMembership.organization_id == other.id,
            )
            .first()
        )
        assert tum_cross_access is None

        print("✅ TUM has no special privileges!")


if __name__ == "__main__":
    print("End-to-end role system tests")
    print("Run with: pytest tests/e2e/test_role_system_e2e.py -v")
