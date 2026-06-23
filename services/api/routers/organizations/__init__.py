"""
Organization management API endpoints.

Tier 2.4 decomposition: the former single-file ``routers/organizations.py``
(1201 lines) was split into concern modules under this package. ``_common``
holds the shared ``router`` instance, permission helpers and Pydantic schemas;
the handlers live in ``crud`` (organization CRUD), ``members`` (membership +
email-verification management) and ``manage`` (global superadmin user
management). Importing those modules attaches their handlers onto the shared
``router``.

The public surface (``router`` plus every schema, helper and handler) is
re-exported here so that ``from routers.organizations import X`` and
``routers.organizations.X`` continue to resolve exactly as before.
"""

from ._common import (  # noqa: F401
    router,
    can_create_organization,
    can_manage_organization,
    OrganizationBase,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationMemberResponse,
    UpdateMemberRole,
)

# Importing the concern modules registers their handlers on ``router`` (in the
# same relative order as the original single file).
from . import crud  # noqa: E402,F401
from . import members  # noqa: E402,F401
from . import manage  # noqa: E402,F401

# Re-export handlers + schemas defined in the concern modules so that existing
# ``from routers.organizations import <name>`` imports keep working.
from .crud import (  # noqa: E402,F401
    list_organizations,
    create_organization,
    get_organization_by_slug,
    get_organization,
    update_organization,
    delete_organization,
)
from .members import (  # noqa: E402,F401
    list_organization_members,
    update_member_role,
    remove_member,
    add_user_to_organization,
    verify_member_email,
    bulk_verify_member_emails,
    AddUserToOrganization,
    VerifyEmailRequest,
    BulkVerifyEmailRequest,
)
from .manage import (  # noqa: E402,F401
    list_all_users,
    update_user_superadmin_status,
    delete_user,
    UserResponse,
    UserSuperadminUpdate,
)
