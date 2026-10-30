"""Access keys on the full API (core 2.44): the gate in
``middleware/key_gate.py`` with the rules of ``app/core/key_routes.py``.

The requests run through the real app and the real gate on the async test
session; only routes on the async lane are used, so the handlers see the
test transaction too."""

import pytest

from models import OrganizationRole
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import bearer, make_project, make_tasks

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=True)
    w["project"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="Mine")
    w["other"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="Other")
    w["tasks"] = await make_tasks(db, w["project"], 1, w["admin"].id)
    w["other_tasks"] = await make_tasks(db, w["other"], 1, w["admin"].id)
    return w


async def _personal(db, user, scopes, **extra):
    return (await svc.create_personal_key(db, user.id, {"name": "k", "scopes": scopes, **extra}))[1]


async def _org(db, world, scopes, **extra):
    body = {"name": "k", "org_role": "CONTRIBUTOR", "scopes": scopes, **extra}
    return (await svc.create_org_key(db, world["admin"].id, world["org"].id, body))[1]


def _code(response):
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


async def test_personal_key_reads_a_project(async_test_client, async_test_db, world):
    plain = await _personal(async_test_db, world["member"], ["projects:read"])
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}", headers=bearer(plain)
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == world["project"].id
    # The limiter itself is off under TESTING (tests/unit/test_rate_limiter_api_key.py).
    assert r.headers.get("x-request-id")


async def test_missing_scope_is_403(async_test_client, async_test_db, world):
    plain = await _personal(async_test_db, world["member"], ["projects:read"])
    r = await async_test_client.patch(
        f"/api/projects/{world['project'].id}",
        json={"title": "renamed"},
        headers=bearer(plain),
    )
    assert r.status_code == 403
    assert _code(r) == "insufficient_scope"
    assert r.json()["detail"]["required_scopes"] == ["projects:write"]


async def test_write_scope_reaches_the_handler(async_test_client, async_test_db, world):
    plain = await _personal(async_test_db, world["admin"], ["projects:write"])
    r = await async_test_client.patch(
        f"/api/projects/{world['project'].id}",
        json={"title": "renamed by key"},
        headers=bearer(plain),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "renamed by key"


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/auth/change-password"),
        ("POST", "/api/auth/logout"),
        ("PUT", "/api/auth/profile"),
        ("POST", "/api/test/seed/annotations"),
    ],
)
async def test_routes_closed_to_keys(async_test_client, async_test_db, world, method, path):
    plain = await _personal(
        async_test_db, world["member"], ["account:write", "projects:write"]
    )
    r = await async_test_client.request(method, path, json={}, headers=bearer(plain))
    assert r.status_code == 401
    assert _code(r) == "api_key_not_allowed_here"


async def test_invalid_key_is_401(async_test_client, world):
    plain, _ = svc.generate_api_key("test")
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}", headers=bearer(plain)
    )
    assert r.status_code == 401
    assert _code(r) == "invalid_api_key"


async def test_revoked_key_is_401(async_test_client, async_test_db, world):
    key, plain = await svc.create_personal_key(
        async_test_db, world["member"].id, {"name": "k", "scopes": ["projects:read"]}
    )
    await svc.revoke_key(async_test_db, key, world["member"].id, "test")
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}", headers=bearer(plain)
    )
    assert r.status_code == 401
    assert _code(r) == "api_key_revoked"


@pytest.mark.public_api_gate
async def test_feature_off_is_404(async_test_client, async_test_db, world, monkeypatch):
    import extensions

    async def _closed(db, user, *, organization_id=None):
        return False

    monkeypatch.setattr(extensions, "public_api_enabled", _closed)
    plain = await _personal(async_test_db, world["member"], ["projects:read"])
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}", headers=bearer(plain)
    )
    assert r.status_code == 404
    assert _code(r) == "feature_disabled"


async def test_project_list_restricts_the_key(async_test_client, async_test_db, world):
    plain = await _personal(
        async_test_db,
        world["member"],
        ["projects:read", "tasks:read_reference", "account:read"],
        project_ids=[world["project"].id],
    )
    c = async_test_client
    assert (await c.get(f"/api/projects/{world['project'].id}", headers=bearer(plain))).status_code == 200
    r = await c.get(f"/api/projects/{world['other'].id}", headers=bearer(plain))
    assert r.status_code == 404 and _code(r) == "not_found"
    # A task id leads to its project.
    r = await c.get(f"/api/projects/tasks/{world['other_tasks'][0].id}", headers=bearer(plain))
    assert r.status_code == 404 and _code(r) == "not_found"
    # An unknown id leaks nothing either.
    r = await c.get("/api/projects/tasks/does-not-exist", headers=bearer(plain))
    assert r.status_code == 404
    # The project list names no project: closed to a restricted key.
    r = await c.get("/api/projects/", headers=bearer(plain))
    assert r.status_code == 403 and _code(r) == "key_project_restricted"
    # Account-level routes stay open.
    r = await c.get("/api/access-keys/scopes", headers=bearer(plain))
    assert r.status_code == 200, r.text


async def test_body_binding_checks_the_project(async_test_client, async_test_db, world):
    plain = await _personal(
        async_test_db,
        world["member"],
        ["evaluations:run"],
        project_ids=[world["project"].id],
    )
    r = await async_test_client.post(
        "/api/evaluations/run",
        json={"project_id": world["other"].id, "evaluation_configs": []},
        headers=bearer(plain),
    )
    assert r.status_code == 404 and _code(r) == "not_found"
    r = await async_test_client.post(
        "/api/evaluations/run", json={"evaluation_configs": []}, headers=bearer(plain)
    )
    assert r.status_code == 403 and _code(r) == "key_project_restricted"


async def test_group_key_sees_only_its_group(async_test_client, async_test_db, world):
    db = async_test_db
    grouped = await make_project(
        db, world["admin"].id, org_id=world["org"].id, group_id=world["group"].id, title="G"
    )
    body = {"name": "g", "org_role": "ANNOTATOR", "scopes": ["projects:read"], "group_id": world["group"].id}
    _, plain = await svc.create_org_key(db, world["admin"].id, world["org"].id, body)
    c = async_test_client
    assert (await c.get(f"/api/projects/{grouped.id}", headers=bearer(plain))).status_code == 200
    r = await c.get(f"/api/projects/{world['project'].id}", headers=bearer(plain))
    assert r.status_code == 404


async def test_seb_project_is_closed_to_every_key(async_test_client, async_test_db, world):
    seb = await make_project(
        async_test_db, world["admin"].id, org_id=world["org"].id, title="SEB", seb_required=True
    )
    plain = await _personal(async_test_db, world["admin"], ["projects:read"])
    r = await async_test_client.get(f"/api/projects/{seb.id}", headers=bearer(plain))
    assert r.status_code == 404


async def test_superadmin_rights_need_admin_platform(async_test_client, async_test_db, world):
    db = async_test_db
    plain = await _personal(db, world["superadmin"], ["account:read"])
    r = await async_test_client.get("/api/users", headers=bearer(plain))
    assert r.status_code == 403
    plain = await _personal(db, world["superadmin"], ["admin:platform"])
    r = await async_test_client.get("/api/users", headers=bearer(plain))
    assert r.status_code == 200, r.text


async def test_key_creates_org_admin_key(async_test_client, async_test_db, world):
    plain = await _personal(
        async_test_db, world["admin"], ["keys:manage", "org:manage", "projects:read"]
    )
    url = f"/api/organizations/{world['org'].id}/access-keys"
    r = await async_test_client.post(
        url,
        json={"name": "admin bot", "org_role": "ORG_ADMIN", "scopes": ["org:manage"]},
        headers=bearer(plain),
    )
    assert r.status_code == 201, r.text
    assert r.json()["key"]["org_role"] == "ORG_ADMIN"
    # Never more than the creating key holds.
    r = await async_test_client.post(
        url,
        json={"name": "too much", "org_role": "CONTRIBUTOR", "scopes": ["projects:write"]},
        headers=bearer(plain),
    )
    assert r.status_code == 400 and _code(r) == "scope_not_grantable"
    # ORG_ADMIN keys are org-wide.
    r = await async_test_client.post(
        url,
        json={
            "name": "group admin bot",
            "org_role": "ORG_ADMIN",
            "group_id": world["group"].id,
            "scopes": ["org:read"],
        },
        headers=bearer(plain),
    )
    assert r.status_code == 403 and _code(r) == "role_exceeds_creator"


async def test_org_manage_needs_org_admin_role(async_test_client, async_test_db, world):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        from app.core.scopes import GrantContext, validate_scopes_for_grant

        validate_scopes_for_grant(GrantContext(is_org_admin=True), "org", "CONTRIBUTOR", ["org:manage"])
    assert ei.value.detail["code"] == "scope_not_grantable"
    plain = await _org(async_test_db, world, ["org:read"])
    r = await async_test_client.get(
        f"/api/organizations/{world['org'].id}/members", headers=bearer(plain)
    )
    assert r.status_code == 200, r.text


async def test_key_usage_is_logged_outside_v1(async_test_client, async_test_db, world, monkeypatch):
    from services import api_usage_writer

    events = []
    monkeypatch.setattr(api_usage_writer, "enqueue", events.append)
    plain = await _personal(async_test_db, world["member"], ["projects:read"])
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}", headers=bearer(plain)
    )
    assert r.status_code == 200
    assert len(events) == 1
    event = events[0]
    assert event["route"] == "/api/projects/{project_id}"
    assert event["project_id"] == world["project"].id
    assert event["scope_used"] == "projects:read"


async def test_denied_key_calls_are_logged(async_test_client, async_test_db, world, monkeypatch):
    from services import api_usage_writer

    events = []
    monkeypatch.setattr(api_usage_writer, "enqueue", events.append)
    plain = await _personal(async_test_db, world["member"], ["projects:read"])
    r = await async_test_client.patch(
        f"/api/projects/{world['project'].id}", json={"title": "x"}, headers=bearer(plain)
    )
    assert r.status_code == 403
    assert [(e["route"], e["status_code"], e["project_id"]) for e in events] == [
        ("/api/projects/{project_id}", 403, world["project"].id)
    ]


async def test_session_requests_are_untouched(async_test_client, world):
    # No key: the gate stays out of the way (the handler answers 401).
    r = await async_test_client.get(f"/api/projects/{world['project'].id}")
    assert r.status_code == 401


async def test_org_role_annotator_cannot_read_task_content(async_test_client, async_test_db, world):
    body = {"name": "a", "org_role": "ANNOTATOR", "scopes": ["projects:read", "tasks:read"]}
    _, plain = await svc.create_org_key(async_test_db, world["admin"].id, world["org"].id, body)
    r = await async_test_client.get(
        f"/api/projects/{world['project'].id}/tasks", headers=bearer(plain)
    )
    assert r.status_code == 403
    assert r.json()["detail"]["required_scopes"] == ["tasks:read_reference"]


async def test_org_key_role_is_a_membership(async_test_db, world):
    key, _ = await svc.create_org_key(
        async_test_db,
        world["admin"].id,
        world["org"].id,
        {"name": "x", "org_role": "ORG_ADMIN", "scopes": ["org:manage"]},
    )
    assert key.org_role == OrganizationRole.ORG_ADMIN


async def test_restricted_key_polls_its_runs_by_id(async_test_client, async_test_db, world):
    """Evaluation and generation ids lead to their project, so a key limited
    to a project can poll its own runs by id, and not those of others."""
    import uuid as _uuid

    from models import EvaluationRun, ResponseGeneration

    db = async_test_db
    mine = EvaluationRun(
        id=str(_uuid.uuid4()), project_id=world["project"].id, model_id="m",
        evaluation_type_ids=[], metrics={}, status="running", created_by=world["admin"].id,
    )
    theirs = EvaluationRun(
        id=str(_uuid.uuid4()), project_id=world["other"].id, model_id="m",
        evaluation_type_ids=[], metrics={}, status="running", created_by=world["admin"].id,
    )
    gen = ResponseGeneration(
        id=str(_uuid.uuid4()), project_id=world["other"].id, model_id="m",
        status="pending", created_by=world["admin"].id,
    )
    db.add_all([mine, theirs, gen])
    await db.flush()
    plain = await _personal(
        db, world["member"], ["evaluations:read", "results:read", "runs:read"],
        project_ids=[world["project"].id],
    )
    c = async_test_client
    r = await c.get(f"/api/evaluations/evaluation/status/{mine.id}", headers=bearer(plain))
    assert _code(r) not in ("key_project_restricted", "not_found"), r.text
    for path in (
        f"/api/evaluations/evaluation/status/{theirs.id}",
        f"/api/evaluations/run/results/{theirs.id}",
        f"/api/generation/status/{gen.id}",
    ):
        r = await c.get(path, headers=bearer(plain))
        assert r.status_code == 404 and _code(r) == "not_found", (path, r.text)


async def test_generation_config_put_merges(async_test_client, async_test_db, world):
    """Selecting models with PUT keeps the prompt structures."""
    from sqlalchemy.orm.attributes import flag_modified

    project = world["project"]
    project.generation_config = {"prompt_structures": {"s1": {"system_prompt": "x"}}}
    flag_modified(project, "generation_config")
    await async_test_db.flush()
    plain = await _personal(async_test_db, world["admin"], ["runs:write"])
    r = await async_test_client.put(
        f"/api/projects/{project.id}/generation-config",
        json={"selected_configuration": {"models": ["m1"]}},
        headers=bearer(plain),
    )
    assert r.status_code == 200, r.text
    config = r.json()["config"]
    assert config["selected_configuration"]["models"] == ["m1"]
    assert config["prompt_structures"] == {"s1": {"system_prompt": "x"}}


async def test_generation_rejects_blank_model_ids(async_test_client, async_test_db, world):
    plain = await _personal(async_test_db, world["admin"], ["runs:write"])
    r = await async_test_client.post(
        f"/api/generation-tasks/projects/{world['project'].id}/generate",
        json={"mode": "missing", "model_ids": [""]},
        headers=bearer(plain),
    )
    assert r.status_code == 422, r.text
