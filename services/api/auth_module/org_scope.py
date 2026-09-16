"""Admin scope of a user inside one organization.

Generalizes ``routers/org_api_keys._require_scope_admin`` for endpoints that
org admins and group admins both operate (LMS connections first):

* an **org admin** holds an active ``ORG_ADMIN`` membership and covers the
  whole org, including every group;
* a **group admin** covers only the groups they administer. The grant needs
  all three of: ``is_group_admin`` on the group membership, an active
  membership in the org (any role; deactivating a member leaves the group
  row in place) and an active group;
* a **superadmin** covers everything.

For everyone but superadmins the organization must exist and be active;
otherwise the answer is a 404, so a caller cannot probe foreign or deleted
orgs. Real names of org members are for org admins and superadmins only
(``sees_real_names``); group admins see pseudonyms.

Errors use the structured shape ``{"detail": {"code", "message"}}``.
Async functions serve the async lane; the ``*_sync`` twins run the same
queries on a sync ``Session``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import (
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
)


@dataclass(frozen=True)
class OrgAdminScope:
    """What ``user`` may administer in ``org_id``."""

    org_id: str
    is_superadmin: bool = False
    is_org_admin: bool = False
    admin_group_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def org_wide(self) -> bool:
        """Covers the whole org (org admin or superadmin)."""
        return self.is_superadmin or self.is_org_admin

    @property
    def is_admin(self) -> bool:
        """Holds any admin power in this org (org-wide or for a group)."""
        return self.org_wide or bool(self.admin_group_ids)

    @property
    def sees_real_names(self) -> bool:
        return self.is_superadmin or self.is_org_admin

    def covers(self, group_id: Optional[str]) -> bool:
        """May administer the org-wide scope (``None``) or that group."""
        if self.org_wide:
            return True
        return group_id is not None and group_id in self.admin_group_ids


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def _org_not_found() -> HTTPException:
    return _error(
        status.HTTP_404_NOT_FOUND, "organization_not_found", "Organization not found"
    )


def _group_not_found() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "group_not_found", "Group not found")


def _forbidden(group_id: Optional[str]) -> HTTPException:
    what = "this group" if group_id is not None else "this organization"
    return _error(
        status.HTTP_403_FORBIDDEN,
        "scope_admin_required",
        f"You do not have permission to manage {what}.",
    )


def _select_org(org_id: str):
    return select(Organization.id, Organization.is_active).where(
        Organization.id == org_id
    )


def _select_membership_role(user_id: str, org_id: str):
    return select(OrganizationMembership.role).where(
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.is_active == True,  # noqa: E712
    )


def _select_admin_group_ids(user_id: str, org_id: str):
    return (
        select(OrganizationGroup.id)
        .join(
            OrganizationGroupMembership,
            OrganizationGroupMembership.group_id == OrganizationGroup.id,
        )
        .where(
            OrganizationGroup.organization_id == org_id,
            OrganizationGroup.is_active == True,  # noqa: E712
            OrganizationGroupMembership.user_id == user_id,
            OrganizationGroupMembership.is_group_admin == True,  # noqa: E712
        )
    )


def _select_group(org_id: str, group_id: str):
    return select(OrganizationGroup.id).where(
        OrganizationGroup.id == group_id,
        OrganizationGroup.organization_id == org_id,
    )


def _is_org_admin_role(role: Any) -> bool:
    return str(getattr(role, "value", role)).upper() == OrganizationRole.ORG_ADMIN.value


def _check_org(row, is_superadmin: bool) -> None:
    if row is None:
        raise _org_not_found()
    if not is_superadmin and not row.is_active:
        raise _org_not_found()


def _check_cover(
    scope: OrgAdminScope, group_id: Optional[str], any_group: bool
) -> None:
    if group_id is None and any_group:
        allowed = scope.is_admin
    else:
        allowed = scope.covers(group_id)
    if not allowed:
        raise _forbidden(group_id)


async def load_org_admin_scope(
    db: AsyncSession, user: Any, org_id: str
) -> OrgAdminScope:
    """The caller's admin scope in ``org_id``. Raises 404 only.

    A user without any admin power gets an empty scope, not an error; use
    :func:`require_scope_admin` to enforce one.
    """
    is_superadmin = bool(getattr(user, "is_superadmin", False))
    org = (await db.execute(_select_org(org_id))).first()
    _check_org(org, is_superadmin)
    if is_superadmin:
        return OrgAdminScope(org_id=org_id, is_superadmin=True)

    role = (await db.execute(_select_membership_role(user.id, org_id))).scalar()
    if role is None:
        return OrgAdminScope(org_id=org_id)
    group_ids = (
        (await db.execute(_select_admin_group_ids(user.id, org_id))).scalars().all()
    )
    return OrgAdminScope(
        org_id=org_id,
        is_org_admin=_is_org_admin_role(role),
        admin_group_ids=frozenset(group_ids),
    )


async def require_scope_admin(
    db: AsyncSession,
    user: Any,
    org_id: str,
    group_id: Optional[str] = None,
    *,
    any_group: bool = False,
) -> OrgAdminScope:
    """Enforce admin rights for the org-wide scope or one group.

    ``group_id=None`` needs an org admin, unless ``any_group`` is set: then
    any group admin of the org passes too (list endpoints that filter their
    rows by ``scope.admin_group_ids``). A ``group_id`` must belong to the org
    (404 otherwise) and be covered by the scope (403 otherwise).
    """
    scope = await load_org_admin_scope(db, user, org_id)
    if group_id is not None:
        found = (await db.execute(_select_group(org_id, group_id))).first()
        if found is None:
            raise _group_not_found()
    _check_cover(scope, group_id, any_group)
    return scope


def load_org_admin_scope_sync(db: Session, user: Any, org_id: str) -> OrgAdminScope:
    """Sync twin of :func:`load_org_admin_scope`."""
    is_superadmin = bool(getattr(user, "is_superadmin", False))
    org = db.execute(_select_org(org_id)).first()
    _check_org(org, is_superadmin)
    if is_superadmin:
        return OrgAdminScope(org_id=org_id, is_superadmin=True)

    role = db.execute(_select_membership_role(user.id, org_id)).scalar()
    if role is None:
        return OrgAdminScope(org_id=org_id)
    group_ids = db.execute(_select_admin_group_ids(user.id, org_id)).scalars().all()
    return OrgAdminScope(
        org_id=org_id,
        is_org_admin=_is_org_admin_role(role),
        admin_group_ids=frozenset(group_ids),
    )


def require_scope_admin_sync(
    db: Session,
    user: Any,
    org_id: str,
    group_id: Optional[str] = None,
    *,
    any_group: bool = False,
) -> OrgAdminScope:
    """Sync twin of :func:`require_scope_admin`."""
    scope = load_org_admin_scope_sync(db, user, org_id)
    if group_id is not None:
        if db.execute(_select_group(org_id, group_id)).first() is None:
            raise _group_not_found()
    _check_cover(scope, group_id, any_group)
    return scope
