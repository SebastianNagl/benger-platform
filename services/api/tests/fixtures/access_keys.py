"""Plain helpers (not fixtures) for the access-key tests: seed users, orgs,
groups and memberships on a sync ``Session`` or an ``AsyncSession``."""

from __future__ import annotations

import uuid
from typing import Optional

from models import (
    Organization,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def make_user(*, superadmin: bool = False, active: bool = True, name: str = "Key Tester") -> User:
    tag = _uid()
    return User(
        id=str(uuid.uuid4()),
        username=f"ak-{tag}",
        email=f"ak-{tag}@example.com",
        name=name,
        hashed_password="x",
        is_superadmin=superadmin,
        is_active=active,
        email_verified=True,
    )


def make_org(*, active: bool = True) -> Organization:
    tag = _uid()
    return Organization(
        id=str(uuid.uuid4()),
        name=f"AK Org {tag}",
        display_name=f"AK Org {tag}",
        slug=f"ak-org-{tag}",
        is_active=active,
        settings={},
    )


def make_group(org_id: str) -> OrganizationGroup:
    return OrganizationGroup(
        id=str(uuid.uuid4()), organization_id=org_id, name=f"Group {_uid()}"
    )


def make_membership(user_id: str, org_id: str, role: OrganizationRole) -> OrganizationMembership:
    return OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=True,
    )


def make_group_membership(
    user_id: str, group_id: str, role: OrganizationRole
) -> OrganizationGroupMembership:
    return OrganizationGroupMembership(
        id=str(uuid.uuid4()), group_id=group_id, user_id=user_id, role=role
    )


def seed_world_sync(db, *, group: bool = True, org_active: bool = True) -> dict:
    """Org admin, group admin, plain member, outsider, superadmin."""
    org = make_org(active=org_active)
    admin = make_user(name="Org Admin")
    group_admin = make_user(name="Group Admin")
    member = make_user(name="Member")
    outsider = make_user(name="Outsider")
    superadmin = make_user(superadmin=True, name="Super")
    db.add_all([org, admin, group_admin, member, outsider, superadmin])
    db.flush()
    grp: Optional[OrganizationGroup] = None
    rows = [
        make_membership(admin.id, org.id, OrganizationRole.ORG_ADMIN),
        make_membership(group_admin.id, org.id, OrganizationRole.ANNOTATOR),
        make_membership(member.id, org.id, OrganizationRole.CONTRIBUTOR),
    ]
    db.add_all(rows)
    db.flush()
    if group:
        grp = make_group(org.id)
        db.add(grp)
        db.flush()
        db.add(make_group_membership(group_admin.id, grp.id, OrganizationRole.ORG_ADMIN))
        db.flush()
    return {
        "org": org,
        "group": grp,
        "admin": admin,
        "group_admin": group_admin,
        "member": member,
        "outsider": outsider,
        "superadmin": superadmin,
    }


async def seed_world(db, *, group: bool = True, org_active: bool = True) -> dict:
    org = make_org(active=org_active)
    admin = make_user(name="Org Admin")
    group_admin = make_user(name="Group Admin")
    member = make_user(name="Member")
    outsider = make_user(name="Outsider")
    superadmin = make_user(superadmin=True, name="Super")
    db.add_all([org, admin, group_admin, member, outsider, superadmin])
    await db.flush()
    db.add_all(
        [
            make_membership(admin.id, org.id, OrganizationRole.ORG_ADMIN),
            make_membership(group_admin.id, org.id, OrganizationRole.ANNOTATOR),
            make_membership(member.id, org.id, OrganizationRole.CONTRIBUTOR),
        ]
    )
    await db.flush()
    grp = None
    if group:
        grp = make_group(org.id)
        db.add(grp)
        await db.flush()
        db.add(make_group_membership(group_admin.id, grp.id, OrganizationRole.ORG_ADMIN))
        await db.flush()
    return {
        "org": org,
        "group": grp,
        "admin": admin,
        "group_admin": group_admin,
        "member": member,
        "outsider": outsider,
        "superadmin": superadmin,
    }
