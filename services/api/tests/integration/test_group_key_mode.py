"""Who pays for AI calls, per organization group (migration 115).

``organization_groups.require_private_keys`` overrides the org's
``settings.require_private_keys`` for the group's projects (NULL = follow
the org). The scope is the PROJECT's attachment group, never the
dispatching user's groups. A paying group spends its own key, then the
org-wide key, also when the org itself does not pay (owner decision
2026-10-08). Exercised through the pure rule, both key-resolution services
(api + worker twin), provider availability, the BYOM org-credential read,
and the settings endpoints with their gates.
"""

import pytest

from models import Organization, OrganizationGroup, OrganizationRole
from tests.integration.test_group_visibility import _as_user, _group, _user, _world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

PERSONAL = "sk-personal-" + "p" * 24
ORG_WIDE = "sk-orgwide-" + "o" * 24
GROUP_A = "sk-group-a-" + "a" * 24


async def _set_modes(db, w, *, org, group_a=None, group_b=None):
    org_row = await db.get(Organization, w["org"].id)
    org_row.settings = {"require_private_keys": org}
    for key, value in (("group_a", group_a), ("group_b", group_b)):
        row = await db.get(OrganizationGroup, w[key].id)
        row.require_private_keys = value
    await db.commit()


async def _seed_keys(db, w, *, org_wide=True, group_a=True):
    from services.org_api_key_service import org_api_key_service
    from services.user_api_key_service import user_api_key_service

    org_id = w["org"].id

    def seed(s):
        for user in (w["contrib_a"], w["contrib_b"], w["loose"], w["orgadmin"]):
            assert user_api_key_service.set_user_api_key(s, user.id, "openai", PERSONAL)
        if org_wide:
            assert org_api_key_service.set_org_api_key(
                s, org_id, "openai", ORG_WIDE, w["orgadmin"].id
            )
        if group_a:
            assert org_api_key_service.set_org_api_key(
                s, org_id, "openai", GROUP_A, w["orgadmin"].id, group_id=w["group_a"].id
            )

    await db.run_sync(seed)


def _services():
    from services.org_api_key_service import org_api_key_service
    from shared_org_api_key_service import org_api_key_service as worker_svc

    assert org_api_key_service is not None and worker_svc is not None
    return (org_api_key_service, worker_svc)


async def _resolve(db, svc, w, user, project, group_id=None):
    return await db.run_sync(
        lambda s: svc.resolve_api_key(
            s,
            user.id,
            w["org"].id,
            "openai",
            project_id=project.id if project is not None else None,
            group_id=group_id,
        )
    )


def test_effective_rule():
    from org_groups import effective_require_private_keys as rule

    assert rule({}, None) is True  # unset org: members pay
    assert rule(None, None) is True
    assert rule({"require_private_keys": False}, None) is False
    assert rule({"require_private_keys": True}, False) is False
    assert rule({"require_private_keys": False}, True) is True
    assert rule({}, False) is False


async def test_paying_group_in_a_members_pay_org(async_test_db):
    """The Saarland setup: the org's members pay, one chair's projects run on
    the org's keys (its own key first, then the org-wide key)."""
    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=True, group_a=False)
    await _seed_keys(db, w)

    for svc in _services():
        # Group A's project spends group A's key, whoever dispatches it.
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_a"]) == GROUP_A
        assert await _resolve(db, svc, w, w["orgadmin"], w["p_a"]) == GROUP_A
        # Everything else in the org stays on personal keys.
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_org"]) == PERSONAL
        assert await _resolve(db, svc, w, w["loose"], None) == PERSONAL
        # The creation wizard for a new group-A project spends group A's key.
        assert await _resolve(db, svc, w, w["contrib_a"], None, w["group_a"].id) == GROUP_A
        # ...but only for someone who may create a project in group A.
        assert await _resolve(db, svc, w, w["contrib_b"], None, w["group_a"].id) == PERSONAL

    # Without a group key the paying group falls back to the org-wide key.
    from services.org_api_key_service import org_api_key_service

    await db.run_sync(
        lambda s: org_api_key_service.remove_org_api_key(
            s, w["org"].id, "openai", group_id=w["group_a"].id
        )
    )
    for svc in _services():
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_a"]) == ORG_WIDE


async def test_members_pay_group_in_a_paying_org(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=False, group_a=True)
    await _seed_keys(db, w)

    for svc in _services():
        # Group A opted out: personal keys, its group key stays untouched.
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_a"]) == PERSONAL
        assert await _resolve(db, svc, w, w["orgadmin"], w["p_a"]) == PERSONAL
        # The rest of the org keeps paying.
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_org"]) == ORG_WIDE


async def test_follow_org_keeps_todays_behaviour(async_test_db):
    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=False)
    await _seed_keys(db, w)
    for svc in _services():
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_a"]) == GROUP_A
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_org"]) == ORG_WIDE

    await _set_modes(db, w, org=True)
    for svc in _services():
        assert await _resolve(db, svc, w, w["contrib_a"], w["p_a"]) == PERSONAL


async def test_require_private_keys_for_ignores_foreign_groups(async_test_db):
    from org_groups import require_private_keys_for, require_private_keys_for_async
    from tests.integration.test_group_visibility import _org

    db = async_test_db
    w = await _world(db)
    other = await _org(db, (w["loose"], OrganizationRole.CONTRIBUTOR))
    foreign = await _group(db, other, "Elsewhere", (w["loose"], False))
    foreign_row = await db.get(OrganizationGroup, foreign.id)
    foreign_row.require_private_keys = False
    await db.commit()
    await _set_modes(db, w, org=True)

    assert await require_private_keys_for_async(db, w["org"].id, foreign.id) is True
    assert await db.run_sync(
        lambda s: require_private_keys_for(s, w["org"].id, foreign.id)
    ) is True
    assert await require_private_keys_for_async(db, None) is True
    assert await require_private_keys_for_async(db, "no-such-org") is True


async def test_available_providers_follow_the_scope(async_test_db):
    from services.org_api_key_service import org_api_key_service

    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=True, group_a=False)
    # Org-wide pool has anthropic, group A openai; personal keys: google.
    from services.user_api_key_service import user_api_key_service

    def seed(s):
        assert org_api_key_service.set_org_api_key(
            s, w["org"].id, "anthropic", "sk-ant-" + "x" * 40, w["orgadmin"].id
        )
        assert org_api_key_service.set_org_api_key(
            s, w["org"].id, "openai", GROUP_A, w["orgadmin"].id, group_id=w["group_a"].id
        )
        for user in (w["contrib_a"], w["contrib_b"]):
            assert user_api_key_service.set_user_api_key(
                s, user.id, "google", "AIza" + "g" * 35
            )

    await db.run_sync(seed)
    org_id = w["org"].id

    async def both(user, project=None):
        project_id = project.id if project is not None else None
        got_async = await org_api_key_service.get_available_providers_for_context_async(
            db, user.id, org_id, project_id=project_id
        )
        got_sync = await db.run_sync(
            lambda s: org_api_key_service.get_available_providers_for_context(
                s, user.id, org_id, project_id=project_id
            )
        )
        assert got_async == got_sync
        return got_async

    # Group A's project: group key + org-wide fallback, no personal keys.
    assert await both(w["contrib_a"], w["p_a"]) == ["OpenAI", "Anthropic"]
    # An org-wide project: members pay.
    assert await both(w["contrib_a"], w["p_org"]) == ["Google"]
    # No project: every scope the member is in.
    assert await both(w["contrib_a"]) == ["OpenAI", "Anthropic", "Google"]
    # A member of group B only (follows the org): personal keys.
    assert await both(w["contrib_b"]) == ["Google"]


async def test_byom_org_credential_follows_the_group(async_test_db):
    from custom_model_org_credential_service import org_requires_private_keys

    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=True, group_a=False)
    org_id = w["org"].id
    assert await db.run_sync(lambda s: org_requires_private_keys(s, org_id)) is True
    assert (
        await db.run_sync(lambda s: org_requires_private_keys(s, org_id, w["group_a"].id))
        is False
    )


async def test_settings_endpoint_gates_and_payloads(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    await _set_modes(db, w, org=True)
    org_id = w["org"].id
    base = f"/api/organizations/{org_id}/api-keys/settings"
    url_a = f"{base}?group_id={w['group_a'].id}"

    # Any member reads; the group scope reports both levels.
    with _as_user(w["annot_a"]):
        r = await async_test_client.get(url_a)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "require_private_keys": True,
        "group_require_private_keys": None,
        "org_require_private_keys": True,
    }

    # Group A's admin switches group A to org-provided keys...
    with _as_user(w["gadmin_a"]):
        r = await async_test_client.put(url_a, json={"require_private_keys": False})
        assert r.status_code == 200, r.text
        assert r.json()["group_require_private_keys"] is False
        assert (await async_test_client.get(url_a)).json()["require_private_keys"] is False
        # ...but may not touch the org-wide switch or another group.
        r = await async_test_client.put(base, json={"require_private_keys": False})
        assert r.status_code == 403
        r = await async_test_client.put(
            f"{base}?group_id={w['group_b'].id}", json={"require_private_keys": False}
        )
        assert r.status_code == 403
        # null = follow the org again.
        r = await async_test_client.put(url_a, json={"require_private_keys": None})
        assert r.status_code == 200
        assert r.json()["group_require_private_keys"] is None

    row = await db.get(OrganizationGroup, w["group_a"].id)
    await db.refresh(row)
    assert row.require_private_keys is None

    # Group members without admin rights cannot change it.
    with _as_user(w["contrib_a"]):
        r = await async_test_client.put(url_a, json={"require_private_keys": False})
    assert r.status_code == 403

    # Org admins set any group and the org; the org switch stays a boolean.
    with _as_user(w["orgadmin"]):
        r = await async_test_client.put(
            f"{base}?group_id={w['group_b'].id}", json={"require_private_keys": True}
        )
        assert r.status_code == 200
        assert (await async_test_client.put(base, json={"require_private_keys": None})).status_code == 400
        assert (await async_test_client.put(url_a, json={})).status_code == 400
        r = await async_test_client.put(base, json={"require_private_keys": False})
        assert r.status_code == 200
        # A group of another org is a 404, not a silent no-op.
        r = await async_test_client.get(f"{base}?group_id=nope")
        assert r.status_code == 404

    # Non-members read nothing.
    stranger = await _user(db)
    with _as_user(stranger):
        assert (await async_test_client.get(url_a)).status_code == 403
