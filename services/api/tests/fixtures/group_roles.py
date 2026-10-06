"""Group-role helpers for tests that seed organization group memberships.

Group memberships carry a role since migration 111. Most fixtures still
describe a membership as "group admin or not"; :func:`legacy_group_role`
turns that flag into a role the way the migration's backfill does: an admin
is ORG_ADMIN, anyone else gets their active org role in the group's org
(ANNOTATOR without one). A role (enum or string) passes through unchanged.
"""

from sqlalchemy import select

from models import OrganizationGroup, OrganizationMembership, OrganizationRole


def _explicit(admin_or_role):
    if isinstance(admin_or_role, bool):
        return OrganizationRole.ORG_ADMIN if admin_or_role else None
    return OrganizationRole(str(getattr(admin_or_role, "value", admin_or_role)).upper())


def _select_org_role(group_id, user_id):
    return (
        select(OrganizationMembership.role)
        .join(
            OrganizationGroup,
            OrganizationGroup.organization_id == OrganizationMembership.organization_id,
        )
        .where(
            OrganizationGroup.id == str(group_id),
            OrganizationMembership.user_id == str(user_id),
            OrganizationMembership.is_active.is_(True),
        )
    )


def legacy_group_role(db, group_id, user_id, admin_or_role) -> OrganizationRole:
    """Sync: the group role for a ``(group, user, admin flag | role)`` seed."""
    role = _explicit(admin_or_role)
    if role is not None:
        return role
    db.flush()
    found = db.execute(_select_org_role(group_id, user_id)).scalars().first()
    return OrganizationRole(found) if found else OrganizationRole.ANNOTATOR


async def legacy_group_role_async(db, group_id, user_id, admin_or_role) -> OrganizationRole:
    """Async twin of :func:`legacy_group_role`."""
    role = _explicit(admin_or_role)
    if role is not None:
        return role
    await db.flush()
    found = (await db.execute(_select_org_role(group_id, user_id))).scalars().first()
    return OrganizationRole(found) if found else OrganizationRole.ANNOTATOR
