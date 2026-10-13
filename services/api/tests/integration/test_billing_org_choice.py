"""The "billed to" choice for generation and evaluation runs.

A caller who may bill more than one org on a project picks the payer
(``billing_organization_id``). The options are the attached orgs that
provide keys there and that the caller is an active member of; superadmins
may bill any attached org that provides keys. Anything else is a 403, and
without a choice the default rule (``org_resolution``) still applies.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration,
    User,
)
from project_models import Project, ProjectOrganization, Task

pytestmark = [pytest.mark.integration]


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import get_current_user, require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _org(db, name, *, pays, members=()) -> Organization:
    org = Organization(
        id=str(uuid.uuid4()),
        name=name,
        display_name=name,
        slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}",
        settings={"require_private_keys": not pays},
    )
    db.add(org)
    await db.flush()
    for user, active in members:
        db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=active,
            )
        )
    await db.flush()
    return org


async def _world(db):
    """A member of Alpha + Beta (both pay), of Gamma (members pay) and an
    inactive member of Delta (pays); Epsilon pays but has no attachment.
    The project is attached to Alpha, Beta, Gamma and Delta."""
    member = await _user(db)
    admin = await _user(db, superadmin=True)
    stranger = await _user(db)
    alpha = await _org(db, "Alpha", pays=True, members=[(member, True)])
    beta = await _org(db, "Beta", pays=True, members=[(member, True)])
    gamma = await _org(db, "Gamma", pays=False, members=[(member, True)])
    delta = await _org(db, "Delta", pays=True, members=[(member, False)])
    epsilon = await _org(db, "Epsilon", pays=True, members=[(member, True)])
    project = Project(
        id=str(uuid.uuid4()),
        title="billing choice",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={"selected_configuration": {"models": ["model-A"]}},
    )
    db.add(project)
    await db.flush()
    for org in (alpha, beta, gamma, delta):
        db.add(
            ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=admin.id,
            )
        )
    db.add(
        Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=1,
            data={"text": "x"},
            created_by=admin.id,
        )
    )
    await db.commit()
    return {
        "member": member,
        "admin": admin,
        "stranger": stranger,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "epsilon": epsilon,
        "project": project,
    }


def _providers_by_org():
    async def _providers(db_, user_id, org_id, project_id=None):
        return [f"P-{org_id[:4]}"]

    return patch(
        "services.org_api_key_service.org_api_key_service.get_available_providers_for_context_async",
        new=AsyncMock(side_effect=_providers),
    )


@pytest.mark.asyncio
async def test_member_options_are_their_paying_orgs(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _providers_by_org(), _as_user(w["member"]):
        r = await async_test_client.get(
            "/api/users/api-keys/billing-options",
            params={"project_id": w["project"].id},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [o["name"] for o in body["options"]] == ["Alpha", "Beta"]
    assert body["options"][0]["providers"] == [f"P-{w['alpha'].id[:4]}"]
    # The default rule picks one of the member's attached orgs (unchanged).
    assert body["default_organization_id"] in {
        w["alpha"].id,
        w["beta"].id,
        w["gamma"].id,
    }


@pytest.mark.asyncio
async def test_superadmin_may_bill_any_attached_paying_org(
    async_test_client, async_test_db
):
    w = await _world(async_test_db)
    with _providers_by_org(), _as_user(w["admin"]):
        r = await async_test_client.get(
            "/api/users/api-keys/billing-options",
            params={"project_id": w["project"].id},
        )
    assert r.status_code == 200, r.text
    assert [o["name"] for o in r.json()["options"]] == ["Alpha", "Beta", "Delta"]


@pytest.mark.asyncio
async def test_stranger_is_refused(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["stranger"]):
        r = await async_test_client.get(
            "/api/users/api-keys/billing-options",
            params={"project_id": w["project"].id},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_model_list_follows_the_chosen_payer(async_test_client, async_test_db):
    w = await _world(async_test_db)
    seen = []

    async def _providers(db_, user_id, org_id, project_id=None):
        seen.append(org_id)
        return []

    with patch(
        "services.org_api_key_service.org_api_key_service.get_available_providers_for_context_async",
        new=AsyncMock(side_effect=_providers),
    ), _as_user(w["member"]):
        url = "/api/users/api-keys/available-models"
        params = {"project_id": w["project"].id}
        r = await async_test_client.get(
            url, params={**params, "billing_organization_id": w["beta"].id}
        )
        assert r.status_code == 200, r.text
        assert seen[-1] == w["beta"].id
        # Not an option: members pay (Gamma), inactive membership (Delta),
        # not attached (Epsilon).
        for org in ("gamma", "delta", "epsilon"):
            r = await async_test_client.get(
                url, params={**params, "billing_organization_id": w[org].id}
            )
            assert r.status_code == 403, org


@pytest.mark.asyncio
async def test_generation_is_billed_to_the_chosen_org(
    async_test_client, async_test_db
):
    w = await _world(async_test_db)
    project_id, delta_id = w["project"].id, w["delta"].id
    url = f"/api/generation-tasks/projects/{project_id}/generate"
    with patch("routers.generation_task_list.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        with _as_user(w["admin"]):
            r = await async_test_client.post(
                url,
                json={"mode": "all", "billing_organization_id": w["gamma"].id},
            )
            assert r.status_code == 403, r.text
            mock_celery.send_task.assert_not_called()

            r = await async_test_client.post(
                url,
                json={"mode": "all", "billing_organization_id": w["delta"].id},
            )
            assert r.status_code == 200, r.text

    async_test_db.expire_all()
    rows = (
        (
            await async_test_db.execute(
                select(ResponseGeneration).where(
                    ResponseGeneration.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows and {r.organization_id for r in rows} == {delta_id}
    # The org also travels to the worker with every dispatched cell.
    sent = mock_celery.send_task.call_args_list
    assert sent and all(delta_id in str(c) for c in sent)


def test_evaluation_run_checks_the_chosen_payer(client, test_db):
    """``POST /evaluations/run`` (sync lane). An empty config list passes
    every gate and then 400s, so 400 == "payer accepted", 403 == refused."""
    member = User(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Person",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )
    test_db.add(member)
    test_db.flush()
    orgs = {}
    for name, pays in (("Alpha", True), ("Gamma", False)):
        org = Organization(
            id=str(uuid.uuid4()),
            name=name,
            display_name=name,
            slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}",
            settings={"require_private_keys": not pays},
        )
        test_db.add(org)
        test_db.flush()
        test_db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=member.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=True,
            )
        )
        orgs[name] = org
    project = Project(id=str(uuid.uuid4()), title="eval payer", created_by=member.id)
    test_db.add(project)
    test_db.flush()
    for org in orgs.values():
        test_db.add(
            ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=member.id,
            )
        )
    test_db.commit()

    with _as_user(member):
        for org_name, expected in (("Alpha", 400), ("Gamma", 403)):
            r = client.post(
                "/api/evaluations/run",
                json={
                    "project_id": project.id,
                    "evaluation_configs": [],
                    "billing_organization_id": orgs[org_name].id,
                },
            )
            assert r.status_code == expected, (org_name, r.text)
