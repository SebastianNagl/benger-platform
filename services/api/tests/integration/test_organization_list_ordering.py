"""
Organization lists come back alphabetically by name, ignoring case (#385).

Both GET /api/organizations/ and GET /api/auth/me/contexts feed org pickers
(the Organizations page switcher and the account menu); without an ORDER BY
they listed orgs in whatever order Postgres returned.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, OrganizationRole, User

# Inserted out of order; "bonn" must land between "Aachen" and "Coburg".
NAMES = ["Coburg", "bonn", "Aachen", "Dresden"]
EXPECTED = ["Aachen", "bonn", "Coburg", "Dresden"]


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at,
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed(db, *, is_superadmin):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=_uid(),
        username=f"order_{suffix}",
        email=f"order_{suffix}@test.com",
        name="Order User",
        hashed_password="x",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    org_ids = set()
    for name in NAMES:
        org = Organization(
            id=_uid(),
            name=f"{name} {suffix}",
            display_name=name,
            slug=f"{name.lower()}-{suffix}",
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        await db.flush()
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.ANNOTATOR,
                is_active=True,
            )
        )
        org_ids.add(org.id)
    await db.commit()
    return user, org_ids


def _seeded_names_in_order(orgs, org_ids):
    # Superadmins see every org in the DB; keep only the seeded ones, in the
    # order the endpoint returned them.
    return [o["name"].split(" ")[0] for o in orgs if o["id"] in org_ids]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("is_superadmin", [True, False])
async def test_list_organizations_sorted_by_name(
    async_test_client, async_test_db, is_superadmin
):
    user, org_ids = await _seed(async_test_db, is_superadmin=is_superadmin)
    with _as_user(user):
        resp = await async_test_client.get("/api/organizations/")
    assert resp.status_code == 200
    assert _seeded_names_in_order(resp.json(), org_ids) == EXPECTED


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("is_superadmin", [True, False])
async def test_me_contexts_organizations_sorted_by_name(
    async_test_client, async_test_db, is_superadmin
):
    user, org_ids = await _seed(async_test_db, is_superadmin=is_superadmin)
    with _as_user(user):
        resp = await async_test_client.get("/api/auth/me/contexts")
    assert resp.status_code == 200
    orgs = resp.json()["organizations"]
    assert _seeded_names_in_order(orgs, org_ids) == EXPECTED
