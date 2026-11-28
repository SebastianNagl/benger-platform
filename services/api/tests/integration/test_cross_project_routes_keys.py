"""Access keys on the full-API routes that name no project but return or
change data of many projects (``app/core/key_routes.py``).

These routes used to be neutral, so a key limited to one project (a project
list, or a group) read through them the titles, ids, counts and scores of
its user's other projects: the dashboard counters, the report list, a
model's leaderboard details and per-project scores, the notification texts,
the share and marketplace directories, the user's files, the key lists, and
the superadmin and LTI reads over all projects. Now a restricted key gets
403 ``key_project_restricted`` there, or, where the route takes a project
filter, only a project of its own (404 ``not_found`` otherwise). The public
leaderboard and its statistics stay neutral. Unrestricted keys and browser
sessions are unchanged."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import Notification, NotificationType, OrganizationRole, UploadedData
from project_models import Annotation, MarketplaceListing, ProjectShareLink
from report_models import ProjectReport
from services import api_key_service as svc
from tests.fixtures.access_keys import make_group_membership, seed_world
from tests.fixtures.v1 import bearer, make_project, make_tasks

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

#: Every scope the routes below need, so the gate's scope check passes and
#: only the project restriction decides.
ALL_SCOPES = [
    "account:read",
    "account:write",
    "admin:platform",
    "evaluations:read",
    "files:read",
    "files:write",
    "keys:manage",
    "models:read",
    "org:read",
    "org:manage",
    "projects:read",
    "projects:write",
    "results:read",
]

#: Codes only the key gate answers with.
GATE_CODES = {
    "key_project_restricted",
    "insufficient_scope",
    "api_key_not_allowed_here",
    "not_found",
}

DUMMY = "00000000-0000-0000-0000-000000000000"

#: Routes that name no project and are now closed to a restricted key
#: (method, path, JSON body). ``{org}`` is the seeded organization.
REFUSED = [
    ("GET", "/api/dashboard/stats", None),
    ("GET", "/api/reports", None),
    ("GET", "/api/leaderboards/llm-models/gpt-4o", None),
    ("GET", "/api/leaderboards/llm-models/gpt-4o/projects", None),
    ("GET", "/api/notifications/", None),
    ("GET", "/api/notifications/groups", None),
    ("GET", "/api/notifications/stream", None),
    ("GET", "/api/shares/discover", None),
    ("GET", "/api/marketplace/discover", None),
    ("GET", "/api/marketplace/entitlements", None),
    ("GET", "/api/marketplace/grading/credits", None),
    ("GET", "/api/marketplace/grading/requests", None),
    ("GET", "/api/marketplace/grading/queue?organization_id={org}", None),
    ("GET", "/api/marketplace/vendor/listings?organization_id={org}", None),
    ("POST", "/api/marketplace/listings", {"price_cents": 500}),
    ("GET", "/api/files/", None),
    ("GET", f"/api/files/{DUMMY}/download", None),
    ("DELETE", f"/api/files/{DUMMY}", None),
    ("GET", f"/storage/download-url/{DUMMY}", None),
    ("DELETE", f"/storage/file/{DUMMY}", None),
    ("GET", "/api/users/me/access-keys", None),
    ("POST", f"/api/users/me/access-keys/{DUMMY}/revoke", None),
    ("GET", "/api/organizations/{org}/access-keys", None),
    ("PATCH", "/api/organizations/{org}/access-keys/" + DUMMY, {"name": "x"}),
    ("GET", "/api/admin/access-keys", None),
    ("GET", "/api/users/api-keys/billing-options", None),
    ("POST", "/api/evaluations/validate-config", None),
    ("GET", "/api/admin/grading-feedback/export", None),
    ("POST", "/api/admin/evaluation-runs/relabel", {"dry_run": True}),
    ("GET", "/api/admin/rubric-generation-jobs", None),
    ("GET", f"/api/admin/lti/registrations/{DUMMY}/resource-links", None),
    ("GET", "/api/admin/lti/grade-syncs", None),
    ("POST", f"/api/admin/lti/grade-syncs/{DUMMY}/retry", None),
    ("POST", f"/api/admin/lti/registrations/{DUMMY}/grade-syncs/resend-all", None),
    ("PUT", f"/api/admin/lti/registrations/{DUMMY}", {"name": "x"}),
    ("DELETE", f"/api/admin/lti/registrations/{DUMMY}", None),
]

#: Neutral routes that stay open to a restricted key without a project.
STILL_NEUTRAL = [
    "/api/leaderboards/llm-models?min_generation_count=0&min_samples_evaluated=0",
    "/api/leaderboards/statistics",
    "/api/notifications/unread-count",
    "/api/notifications/summary",
    "/api/notifications/preferences",
    "/api/users/api-keys/available-models",
    "/api/access-keys/scopes",
    "/api/auth/me",
]


def _code(response):
    try:
        detail = response.json().get("detail")
    except Exception:
        return None
    return detail.get("code") if isinstance(detail, dict) else None


async def _request(client, method, path, body, headers):
    return await client.request(method, path, json=body, headers=headers)


@pytest.fixture
async def world(async_test_db):
    """Org with a member (CONTRIBUTOR, also in the group) and two projects:
    ``mine`` (the restricted key's) and ``other`` (in the group), each with a
    task and a submitted answer of the member; on ``other`` a published
    report, a listed share, a published marketplace listing, a file of the
    member and a notification about it."""
    db = async_test_db
    w = await seed_world(db, group=True)
    member, admin, org = w["member"], w["admin"], w["org"]
    w["mine"] = await make_project(db, admin.id, org_id=org.id, title="Project A", kind="exam")
    w["other"] = await make_project(
        db,
        admin.id,
        org_id=org.id,
        group_id=w["group"].id,
        title="Project B",
        kind="exam",
    )
    db.add(make_group_membership(member.id, w["group"].id, OrganizationRole.CONTRIBUTOR))
    for key in ("mine", "other"):
        task = (await make_tasks(db, w[key], 1, admin.id))[0]
        w[f"{key}_task"] = task
        db.add(
            Annotation(
                id=str(uuid.uuid4()),
                task_id=task.id,
                project_id=w[key].id,
                completed_by=member.id,
                result=[{"from_name": "answer", "type": "textarea", "value": {"text": ["x"]}}],
            )
        )
        db.add(
            MarketplaceListing(
                id=str(uuid.uuid4()),
                project_id=w[key].id,
                vendor_org_id=org.id,
                price_cents=500,
                currency="eur",
                published=True,
            )
        )
    await db.flush()
    db.add(
        ProjectReport(
            id=str(uuid.uuid4()),
            project_id=w["other"].id,
            content={"sections": {}},
            is_published=True,
            published_at=datetime.now(timezone.utc),
            published_by=admin.id,
            created_by=admin.id,
        )
    )
    db.add(
        ProjectShareLink(
            id=str(uuid.uuid4()),
            token=uuid.uuid4().hex,
            project_id=w["other"].id,
            created_by=admin.id,
            password_hash="x",
            is_listed=True,
        )
    )
    db.add(
        UploadedData(
            id=str(uuid.uuid4()),
            name="other.pdf",
            original_filename="other.pdf",
            file_path="uploads/other.pdf",
            size=1,
            format="pdf",
            task_id=w["other_task"].id,
            uploaded_by=member.id,
        )
    )
    db.add(
        Notification(
            id=str(uuid.uuid4()),
            user_id=member.id,
            type=NotificationType.PROJECT_CREATED,
            title="New Project Created: Project B",
            message="A new project 'Project B'",
            data={"project_id": w["other"].id},
        )
    )
    await db.flush()
    w["listing"] = {
        key: (
            await db.execute(
                select(MarketplaceListing.id).where(MarketplaceListing.project_id == w[key].id)
            )
        ).scalar_one()
        for key in ("mine", "other")
    }
    return w


async def _personal(db, user, **extra):
    body = {"name": "k", "scopes": ALL_SCOPES, **extra}
    return (await svc.create_personal_key(db, user.id, body))[1]


async def _restricted(db, world, user="member"):
    return bearer(await _personal(db, world[user], project_ids=[world["mine"].id]))


def _fill(path, world):
    return path.replace("{org}", world["org"].id)


# --------------------------------------------------------------------------- #
# Refused without a project
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method,path,body", REFUSED)
async def test_project_restricted_key_is_refused(
    async_test_client, async_test_db, world, method, path, body
):
    headers = await _restricted(async_test_db, world, "superadmin")
    r = await _request(async_test_client, method, _fill(path, world), body, headers)
    assert r.status_code == 403, r.text
    assert _code(r) == "key_project_restricted"
    assert "Project B" not in r.text


@pytest.mark.parametrize("method,path,body", REFUSED)
async def test_group_key_is_refused(async_test_client, async_test_db, world, method, path, body):
    payload = {
        "name": "g",
        "org_role": "ORG_ADMIN",
        "scopes": ALL_SCOPES,
        "group_id": world["group"].id,
    }
    _, plain = await svc.create_org_key(async_test_db, world["admin"].id, world["org"].id, payload)
    r = await _request(async_test_client, method, _fill(path, world), body, bearer(plain))
    assert r.status_code == 403, r.text
    assert _code(r) == "key_project_restricted"


@pytest.mark.parametrize(
    "method,path,body",
    [entry for entry in REFUSED if entry[1] != "/api/notifications/stream"],
)
async def test_unrestricted_key_passes_the_gate(
    async_test_client, async_test_db, world, method, path, body
):
    """The handler, not the gate, answers an unrestricted key (the stream
    is left out: it never ends)."""
    headers = bearer(await _personal(async_test_db, world["superadmin"]))
    r = await _request(async_test_client, method, _fill(path, world), body, headers)
    assert _code(r) not in GATE_CODES, r.text


@pytest.mark.parametrize("path", STILL_NEUTRAL)
async def test_restricted_key_keeps_neutral_routes(async_test_client, async_test_db, world, path):
    r = await async_test_client.get(path, headers=await _restricted(async_test_db, world))
    assert r.status_code == 200, r.text
    assert "Project B" not in r.text


# --------------------------------------------------------------------------- #
# The leaks, with data
# --------------------------------------------------------------------------- #


async def test_dashboard_counts_every_project_only_without_restriction(
    async_test_client, async_test_db, world
):
    c, db = async_test_client, async_test_db
    r = await c.get("/api/dashboard/stats", headers=bearer(await _personal(db, world["member"])))
    assert r.status_code == 200, r.text
    assert r.json()["project_count"] >= 2
    r = await c.get("/api/dashboard/stats", headers=await _restricted(db, world))
    assert r.status_code == 403 and _code(r) == "key_project_restricted"


async def test_report_list_of_other_project_needs_unrestricted_key(
    async_test_client, async_test_db, world
):
    c, db = async_test_client, async_test_db
    r = await c.get("/api/reports", headers=bearer(await _personal(db, world["member"])))
    assert r.status_code == 200, r.text
    assert world["other"].id in {item["project_id"] for item in r.json()}
    r = await c.get("/api/reports", headers=await _restricted(db, world))
    assert r.status_code == 403 and world["other"].id not in r.text


async def test_share_directory_needs_unrestricted_key(async_test_client, async_test_db, world):
    c, db = async_test_client, async_test_db
    r = await c.get(
        "/api/shares/discover",
        params={"scope": "all"},
        headers=bearer(await _personal(db, world["member"])),
    )
    assert r.status_code == 200, r.text
    assert "Project B" in r.text
    r = await c.get(
        "/api/shares/discover", params={"scope": "all"}, headers=await _restricted(db, world)
    )
    assert r.status_code == 403 and "Project B" not in r.text


async def test_marketplace_listing_is_bound_to_its_project(async_test_client, async_test_db, world):
    c, db = async_test_client, async_test_db
    headers = await _restricted(db, world)
    r = await c.get(f"/api/marketplace/listings/{world['listing']['other']}", headers=headers)
    assert r.status_code == 404 and _code(r) == "not_found"
    assert "Project B" not in r.text
    r = await c.get(f"/api/marketplace/listings/{world['listing']['mine']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Project A"
    r = await c.get(f"/api/marketplace/listings/{DUMMY}", headers=headers)
    assert r.status_code == 404
    r = await c.post(
        "/api/marketplace/listings",
        json={"project_id": world["other"].id, "price_cents": 500},
        headers=headers,
    )
    assert r.status_code == 404 and _code(r) == "not_found"
    unrestricted = bearer(await _personal(db, world["member"]))
    r = await c.get("/api/marketplace/discover", headers=unrestricted)
    assert r.status_code == 200, r.text
    assert {"Project A", "Project B"} <= {item["title"] for item in r.json()}


async def test_files_of_other_projects_need_unrestricted_key(
    async_test_client, async_test_db, world
):
    c, db = async_test_client, async_test_db
    unrestricted = bearer(await _personal(db, world["member"]))
    r = await c.get("/api/files/", headers=unrestricted)
    assert r.status_code == 200, r.text
    assert "other.pdf" in r.text
    headers = await _restricted(db, world)
    r = await c.get("/api/files/", headers=headers)
    assert r.status_code == 403 and "other.pdf" not in r.text
    r = await c.get("/api/files/", params={"task_id": world["other_task"].id}, headers=headers)
    assert r.status_code == 404 and "other.pdf" not in r.text
    r = await c.get("/api/files/", params={"task_id": world["mine_task"].id}, headers=headers)
    assert r.status_code == 200 and r.json() == []
    r = await c.post(
        "/api/files/upload",
        params={"task_id": world["other_task"].id},
        files={"file": ("a.txt", b"a", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 404 and _code(r) == "not_found"


async def test_leaderboard_project_filter_is_bound(async_test_client, async_test_db, world):
    """The reported leak: the statistics of the leaderboard counted the
    answers of any project the user reaches when a restricted key named it."""
    c, db = async_test_client, async_test_db
    unrestricted = bearer(await _personal(db, world["member"]))
    r = await c.get(
        "/api/leaderboards/statistics",
        params={"project_ids": world["other"].id},
        headers=unrestricted,
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_annotations"] == 1
    headers = await _restricted(db, world)
    for path in (
        "/api/leaderboards/statistics",
        "/api/leaderboards/llm-models",
        "/api/leaderboards/llm-models/gpt-4o",
    ):
        r = await c.get(path, params={"project_ids": world["other"].id}, headers=headers)
        assert r.status_code == 404 and _code(r) == "not_found", (path, r.text)
        r = await c.get(
            path,
            params=[("project_ids", world["mine"].id), ("project_ids", world["other"].id)],
            headers=headers,
        )
        assert r.status_code == 404, (path, r.text)
    r = await c.get(
        "/api/leaderboards/statistics", params={"project_ids": world["mine"].id}, headers=headers
    )
    assert r.status_code == 200 and r.json()["total_annotations"] == 1
    r = await c.get(
        "/api/leaderboards/llm-models/gpt-4o",
        params={"project_ids": world["mine"].id},
        headers=headers,
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/users/api-keys/billing-options?project_id={pid}"),
        ("GET", "/api/users/api-keys/available-models?project_id={pid}"),
        ("POST", "/api/evaluations/validate-config?project_id={pid}"),
    ],
)
async def test_project_parameter_is_bound(async_test_client, async_test_db, world, method, path):
    c, headers = async_test_client, await _restricted(async_test_db, world)
    r = await c.request(method, path.format(pid=world["other"].id), headers=headers)
    assert r.status_code == 404 and _code(r) == "not_found", r.text
    r = await c.request(method, path.format(pid=world["mine"].id), headers=headers)
    assert _code(r) not in GATE_CODES, r.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/admin/grading-feedback/export?format=json&project_id={pid}", None),
        ("GET", "/api/admin/rubric-generation-jobs?project_id={pid}", None),
        ("GET", "/api/admin/lti/grade-syncs?project_id={pid}", None),
        ("POST", "/api/admin/evaluation-runs/relabel", {"project_id": "{pid}"}),
    ],
)
async def test_superadmin_filters_are_bound(
    async_test_client, async_test_db, world, method, path, body
):
    """A superadmin key limited to a project reads the cross-project admin
    views of that project only."""
    c = async_test_client
    headers = await _restricted(async_test_db, world, "superadmin")

    def _with(pid):
        return path.format(pid=pid), (
            {k: v.format(pid=pid) for k, v in body.items()} if body else None
        )

    p, b = _with(world["other"].id)
    r = await c.request(method, p, json=b, headers=headers)
    assert r.status_code == 404 and _code(r) == "not_found", r.text
    p, b = _with(world["mine"].id)
    r = await c.request(method, p, json=b, headers=headers)
    assert _code(r) not in GATE_CODES, r.text


async def test_session_user_reads_every_project(async_test_client, async_test_db, world):
    from auth_module.dependencies import optional_user, require_user
    from auth_module.models import User as AuthUser
    from main import app

    member = world["member"]
    user = AuthUser(
        id=member.id,
        username=member.username,
        email=member.email,
        name=member.name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[optional_user] = lambda: user
    c = async_test_client
    try:
        stats = await c.get("/api/dashboard/stats")
        reports = await c.get("/api/reports")
        shares = await c.get("/api/shares/discover", params={"scope": "all"})
        files = await c.get("/api/files/")
        market = await c.get("/api/marketplace/discover")
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(optional_user, None)
    assert stats.status_code == 200 and stats.json()["project_count"] >= 2, stats.text
    assert world["other"].id in {item["project_id"] for item in reports.json()}
    assert "Project B" in shares.text
    assert "other.pdf" in files.text
    assert "Project B" in market.text
