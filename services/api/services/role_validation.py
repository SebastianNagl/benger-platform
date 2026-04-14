"""
Organization Role Validation Utilities

This module provides utilities for validating and working with OrganizationRole enums
to prevent common validation errors when creating memberships programmatically.
"""

from typing import List, Union

from models import OrganizationRole


def validate_organization_role(role: Union[str, OrganizationRole]) -> OrganizationRole:
    """Validate and convert a role to OrganizationRole enum

    Args:
        role: String or OrganizationRole enum value

    Returns:
        OrganizationRole enum value

    Raises:
        ValueError: If role is invalid with descriptive error message

    Example:
        >>> validate_organization_role("ORG_ADMIN")
        OrganizationRole.ORG_ADMIN

        >>> validate_organization_role("org_admin")  # Case insensitive
        OrganizationRole.ORG_ADMIN

        >>> validate_organization_role("invalid")
        ValueError: Invalid organization role 'invalid'. Valid roles are: ORG_ADMIN, CONTRIBUTOR, ANNOTATOR
    """
    if isinstance(role, OrganizationRole):
        return role

    if isinstance(role, str):
        return OrganizationRole.from_string(role)

    raise ValueError(f"Role must be string or OrganizationRole enum, got {type(role)}")


def get_valid_organization_roles() -> List[str]:
    """Get list of all valid organization role values

    Returns:
        List of valid role strings

    Example:
        >>> get_valid_organization_roles()
        ['ORG_ADMIN', 'CONTRIBUTOR', 'ANNOTATOR']
    """
    return OrganizationRole.get_valid_roles()


def is_valid_organization_role(role: str) -> bool:
    """Check if a string is a valid organization role

    Args:
        role: String to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_organization_role("ORG_ADMIN")
        True

        >>> is_valid_organization_role("org_admin")  # Case insensitive
        True

        >>> is_valid_organization_role("invalid")
        False
    """
    return OrganizationRole.is_valid_role(role)


def create_safe_membership_data(
    user_id: str, org_id: str, role: Union[str, OrganizationRole]
) -> tuple:
    """Create safe membership data tuple with validated role

    This function prevents the common error of using incorrect string values
    when creating organization memberships programmatically.

    Args:
        user_id: User ID
        org_id: Organization ID
        role: Role as string or OrganizationRole enum

    Returns:
        Tuple of (user_id, org_id, validated_role_enum)

    Raises:
        ValueError: If role is invalid

    Example:
        >>> create_safe_membership_data("user-123", "org-456", "ORG_ADMIN")
        ('user-123', 'org-456', OrganizationRole.ORG_ADMIN)

        >>> create_safe_membership_data("user-123", "org-456", "org_admin")  # Auto-corrected
        ('user-123', 'org-456', OrganizationRole.ORG_ADMIN)

        >>> create_safe_membership_data("user-123", "org-456", "invalid")
        ValueError: Invalid organization role 'invalid'. Valid roles are: ORG_ADMIN, CONTRIBUTOR, ANNOTATOR
    """
    validated_role = validate_organization_role(role)
    return (user_id, org_id, validated_role)


# Common role mapping for migration and compatibility
ROLE_MAPPING = {
    # Legacy role names
    "org_admin": OrganizationRole.ORG_ADMIN,
    "org_contributor": OrganizationRole.CONTRIBUTOR,
    "org_user": OrganizationRole.ANNOTATOR,
    "contributor": OrganizationRole.CONTRIBUTOR,
    "annotator": OrganizationRole.ANNOTATOR,
    "admin": OrganizationRole.ORG_ADMIN,
    # Current role names (case variations)
    "ORG_ADMIN": OrganizationRole.ORG_ADMIN,
    "CONTRIBUTOR": OrganizationRole.CONTRIBUTOR,
    "ANNOTATOR": OrganizationRole.ANNOTATOR,
}


def normalize_role_string(role_str: str) -> OrganizationRole:
    """Normalize a role string using common mappings

    This function handles common variations and legacy role names.

    Args:
        role_str: Role string to normalize

    Returns:
        OrganizationRole enum value

    Raises:
        ValueError: If role cannot be normalized

    Example:
        >>> normalize_role_string("org_admin")
        OrganizationRole.ORG_ADMIN

        >>> normalize_role_string("contributor")
        OrganizationRole.CONTRIBUTOR
    """
    # Try exact mapping first
    normalized = ROLE_MAPPING.get(role_str.lower())
    if normalized:
        return normalized

    # Try case-insensitive enum lookup
    try:
        return OrganizationRole(role_str.upper())
    except ValueError:
        valid_roles = get_valid_organization_roles()
        legacy_roles = list(ROLE_MAPPING.keys())
        raise ValueError(
            f"Cannot normalize role '{role_str}'. "
            f"Valid roles: {', '.join(valid_roles)}. "
            f"Legacy role mappings: {', '.join(legacy_roles)}"
        )
