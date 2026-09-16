"""Deleting a group while an LTI registration invite still points at it.

The invite's group FK is ``ON DELETE SET NULL``, and a Dynamic Registration
connection is active right away. Deleting the group under an open invite
would therefore turn a group-scoped onboarding link into an org-wide
connection. The delete endpoint refuses while an unused, unexpired invite
references the group; used and expired invites do not block.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import (
    LtiRegistrationInvite,
    OrganizationGroup,
    OrganizationRole,
)
from tests.integration.test_group_visibility import _as_user, _org, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _group(db, org) -> OrganizationGroup:
    group = OrganizationGroup(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name=f"LS {uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    db.add(group)
    await db.commit()
    return group


async def _invite(db, org, group, admin, *, expires_in, used=False):
    now = datetime.now(timezone.utc)
    invite = LtiRegistrationInvite(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        group_id=group.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        created_by=admin.id,
        expires_at=now + expires_in,
        used_at=now if used else None,
    )
    db.add(invite)
    await db.commit()
    return invite


async def _delete(client, org, group):
    return await client.delete(f"/api/organizations/{org.id}/groups/{group.id}")


async def test_open_invite_blocks_the_delete(async_test_client, async_test_db):
    db = async_test_db
    admin = await _user(db)
    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN))
    group = await _group(db, org)
    invite = await _invite(db, org, group, admin, expires_in=timedelta(days=14))

    with _as_user(admin):
        response = await _delete(async_test_client, org, group)

    assert response.status_code == 409
    assert "1 open LTI invite(s)" in response.json()["detail"]
    await db.refresh(invite)
    assert invite.group_id == group.id
    assert await db.get(OrganizationGroup, group.id) is not None


@pytest.mark.parametrize(
    "expires_in, used",
    [(timedelta(days=-1), False), (timedelta(days=14), True)],
    ids=["expired", "used"],
)
async def test_used_or_expired_invites_do_not_block(
    async_test_client, async_test_db, expires_in, used
):
    db = async_test_db
    admin = await _user(db)
    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN))
    group = await _group(db, org)
    await _invite(db, org, group, admin, expires_in=expires_in, used=used)

    with _as_user(admin):
        response = await _delete(async_test_client, org, group)

    assert response.status_code == 200, response.text


async def test_invite_of_another_group_does_not_block(
    async_test_client, async_test_db
):
    db = async_test_db
    admin = await _user(db)
    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN))
    group = await _group(db, org)
    other = await _group(db, org)
    await _invite(db, org, other, admin, expires_in=timedelta(days=14))

    with _as_user(admin):
        response = await _delete(async_test_client, org, group)

    assert response.status_code == 200, response.text
