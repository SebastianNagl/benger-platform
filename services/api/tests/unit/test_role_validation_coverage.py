"""
Unit tests for services/role_validation.py — 0% coverage (26 uncovered lines).

Tests role validation, normalization, and safe membership data creation.
"""

import pytest


class TestValidateOrganizationRole:
    """Test validate_organization_role function."""

    def test_valid_enum_passthrough(self):
        from models import OrganizationRole
        from services.role_validation import validate_organization_role
        result = validate_organization_role(OrganizationRole.ORG_ADMIN)
        assert result == OrganizationRole.ORG_ADMIN

    def test_valid_string_uppercase(self):
        from models import OrganizationRole
        from services.role_validation import validate_organization_role
        result = validate_organization_role("ORG_ADMIN")
        assert result == OrganizationRole.ORG_ADMIN

    def test_valid_string_lowercase(self):
        from models import OrganizationRole
        from services.role_validation import validate_organization_role
        result = validate_organization_role("org_admin")
        assert result == OrganizationRole.ORG_ADMIN

    def test_contributor(self):
        from models import OrganizationRole
        from services.role_validation import validate_organization_role
        result = validate_organization_role("CONTRIBUTOR")
        assert result == OrganizationRole.CONTRIBUTOR

    def test_annotator(self):
        from models import OrganizationRole
        from services.role_validation import validate_organization_role
        result = validate_organization_role("ANNOTATOR")
        assert result == OrganizationRole.ANNOTATOR

    def test_invalid_string_raises(self):
        from services.role_validation import validate_organization_role
        with pytest.raises(ValueError):
            validate_organization_role("invalid_role")

    def test_non_string_non_enum_raises(self):
        from services.role_validation import validate_organization_role
        with pytest.raises(ValueError, match="must be string or OrganizationRole"):
            validate_organization_role(42)


class TestGetValidOrganizationRoles:
    """Test get_valid_organization_roles."""

    def test_returns_list(self):
        from services.role_validation import get_valid_organization_roles
        roles = get_valid_organization_roles()
        assert isinstance(roles, list)
        assert len(roles) >= 3

    def test_contains_expected_roles(self):
        from services.role_validation import get_valid_organization_roles
        roles = get_valid_organization_roles()
        assert "ORG_ADMIN" in roles
        assert "CONTRIBUTOR" in roles
        assert "ANNOTATOR" in roles


class TestIsValidOrganizationRole:
    """Test is_valid_organization_role."""

    def test_valid_role(self):
        from services.role_validation import is_valid_organization_role
        assert is_valid_organization_role("ORG_ADMIN") is True

    def test_valid_role_lowercase(self):
        from services.role_validation import is_valid_organization_role
        assert is_valid_organization_role("org_admin") is True

    def test_invalid_role(self):
        from services.role_validation import is_valid_organization_role
        assert is_valid_organization_role("invalid") is False


class TestCreateSafeMembershipData:
    """Test create_safe_membership_data."""

    def test_valid_string_role(self):
        from models import OrganizationRole
        from services.role_validation import create_safe_membership_data
        uid, oid, role = create_safe_membership_data("user-1", "org-1", "ORG_ADMIN")
        assert uid == "user-1"
        assert oid == "org-1"
        assert role == OrganizationRole.ORG_ADMIN

    def test_valid_enum_role(self):
        from models import OrganizationRole
        from services.role_validation import create_safe_membership_data
        uid, oid, role = create_safe_membership_data("user-1", "org-1", OrganizationRole.CONTRIBUTOR)
        assert role == OrganizationRole.CONTRIBUTOR

    def test_case_insensitive(self):
        from models import OrganizationRole
        from services.role_validation import create_safe_membership_data
        _, _, role = create_safe_membership_data("u", "o", "org_admin")
        assert role == OrganizationRole.ORG_ADMIN

    def test_invalid_role_raises(self):
        from services.role_validation import create_safe_membership_data
        with pytest.raises(ValueError):
            create_safe_membership_data("u", "o", "invalid")


class TestNormalizeRoleString:
    """Test normalize_role_string."""

    def test_legacy_org_admin(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("org_admin") == OrganizationRole.ORG_ADMIN

    def test_legacy_contributor(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("contributor") == OrganizationRole.CONTRIBUTOR

    def test_legacy_annotator(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("annotator") == OrganizationRole.ANNOTATOR

    def test_legacy_org_contributor(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("org_contributor") == OrganizationRole.CONTRIBUTOR

    def test_legacy_org_user(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("org_user") == OrganizationRole.ANNOTATOR

    def test_legacy_admin(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("admin") == OrganizationRole.ORG_ADMIN

    def test_current_uppercase(self):
        from models import OrganizationRole
        from services.role_validation import normalize_role_string
        assert normalize_role_string("ORG_ADMIN") == OrganizationRole.ORG_ADMIN

    def test_invalid_raises(self):
        from services.role_validation import normalize_role_string
        with pytest.raises(ValueError, match="Cannot normalize"):
            normalize_role_string("totally_invalid_role_name")


class TestRoleMapping:
    """Test ROLE_MAPPING constant."""

    def test_mapping_has_all_legacy_roles(self):
        from services.role_validation import ROLE_MAPPING
        assert "org_admin" in ROLE_MAPPING
        assert "org_contributor" in ROLE_MAPPING
        assert "org_user" in ROLE_MAPPING
        assert "contributor" in ROLE_MAPPING
        assert "annotator" in ROLE_MAPPING
        assert "admin" in ROLE_MAPPING

    def test_mapping_has_current_roles(self):
        from services.role_validation import ROLE_MAPPING
        assert "ORG_ADMIN" in ROLE_MAPPING
        assert "CONTRIBUTOR" in ROLE_MAPPING
        assert "ANNOTATOR" in ROLE_MAPPING
