"""Integration tests for the Safe Exam Browser gate (real PostgreSQL).

Three layers:
  1. ``enforce_seb_async`` / ``seb_request_allowed_async`` — who is exempt
     (flag off, editors, superadmin, attempted tier, reads of own submitted
     tasks) and who is gated.
  2. The async endpoints: single-task reads and writes refuse without a
     proof; task lists (project task list, /api/data) narrow to the user's
     own submitted tasks.
  3. The sync endpoints (draft, checkpoint, submit, my-tasks) via the sync
     ``client``.

A valid proof is ``X-SafeExamBrowser-ConfigKeyHash`` over the request URL
the API rebuilds: ``FRONTEND_URL``'s scheme + the ``testserver`` host.
"""

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Annotation, Project, ProjectOrganization, Task
from routers.projects.helpers import enforce_seb_async, seb_request_allowed_async

CK = "e" * 64
BASE = "http://testserver"


@pytest.fixture(autouse=True)
def _frontend(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", BASE)
    monkeypatch.delenv("VERTRETBAR_FRONTEND_URL", raising=False)


def _uid():
    return str(uuid.uuid4())


def _proof(path):
    """Native SEB header proving CK for ``path`` on the test host."""
    digest = hashlib.sha256((BASE + path + CK).encode()).hexdigest()
    return {"X-SafeExamBrowser-ConfigKeyHash": digest}


class _Request:
    """Minimal stand-in for ``fastapi.Request`` in the guard unit tests."""

    def __init__(self, path, headers=None):
        from starlette.datastructures import URL, Headers

        self.url = URL(BASE + path)
        self.headers = Headers({"host": "testserver", **(headers or {})})


# ── world builders (sync + async share the row shapes) ──────────────────────


def _rows(seb_required=True):
    org = Organization(
        id=_uid(),
        name=f"org-{_uid()[:8]}",
        slug=f"org-{_uid()[:8]}",
        display_name="Org",
        created_at=datetime.now(timezone.utc),
    )

    def user(**kw):
        return User(
            id=_uid(),
            username=f"u-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="Test User",
            **kw,
        )

    owner, student, superadmin = user(), user(), user(is_superadmin=True)
    project = Project(
        id=_uid(),
        title="SEB exam",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode="open",
        seb_required=seb_required,
        seb_config={"generated_config_key": CK},
    )
    tasks = [
        Task(id=_uid(), project_id=project.id, data={"text": f"t{i}"}, inner_id=i)
        for i in (1, 2)
    ]
    links = [
        OrganizationMembership(
            id=_uid(),
            user_id=owner.id,
            organization_id=org.id,
            role="ORG_ADMIN",
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        ),
        OrganizationMembership(
            id=_uid(),
            user_id=student.id,
            organization_id=org.id,
            role="ANNOTATOR",
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        ),
        ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=owner.id
        ),
    ]
    return {
        "org": org,
        "owner": owner,
        "student": student,
        "superadmin": superadmin,
        "project": project,
        "tasks": tasks,
        "links": links,
    }


def _submission(world, task):
    return Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=world["project"].id,
        completed_by=world["student"].id,
        result=[{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}],
    )


async def _async_world(db, **kw):
    w = _rows(**kw)
    db.add_all([w["org"], w["owner"], w["student"], w["superadmin"]])
    await db.flush()
    db.add(w["project"])
    await db.flush()
    db.add_all(w["tasks"] + w["links"])
    await db.flush()
    return w


def _sync_world(db, **kw):
    w = _rows(**kw)
    db.add_all([w["org"], w["owner"], w["student"], w["superadmin"]])
    db.flush()
    db.add(w["project"])
    db.flush()
    db.add_all(w["tasks"] + w["links"])
    db.flush()
    return w


@contextmanager
def _as_user(db_user):
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
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _code(coro):
    try:
        await coro
        return None
    except HTTPException as e:
        assert e.status_code == 403
        return e.detail["code"]


# ── 1. guard ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guard_exemptions_and_gate(async_test_db):
    db = async_test_db
    w = await _async_world(db)
    p, student = w["project"], w["student"]
    path = f"/api/projects/{p.id}/tasks/{w['tasks'][0].id}/draft"
    bare = _Request(path)
    proven = _Request(path, _proof(path))

    assert await _code(enforce_seb_async(db, student, p, bare)) == "seb_required"
    assert await _code(enforce_seb_async(db, student, p, proven)) is None
    # Editors and superadmins set up and review in a normal browser.
    assert await _code(enforce_seb_async(db, w["owner"], p, bare)) is None
    assert await _code(enforce_seb_async(db, w["superadmin"], p, bare)) is None
    # The read-only attempted tier is never gated.
    assert await _code(enforce_seb_async(db, student, p, bare, tier="attempted")) is None

    # A wrong key is still refused.
    wrong = _Request(path, {"X-SafeExamBrowser-ConfigKeyHash": "0" * 64})
    assert await _code(enforce_seb_async(db, student, p, wrong)) == "seb_required"


@pytest.mark.asyncio
async def test_guard_is_a_noop_without_the_flag(async_test_db):
    db = async_test_db
    w = await _async_world(db, seb_required=False)
    bare = _Request("/api/projects/x")
    assert await _code(enforce_seb_async(db, w["student"], w["project"], bare)) is None
    assert await _code(enforce_seb_async(db, w["student"], None, bare)) is None


@pytest.mark.asyncio
async def test_guard_reads_of_submitted_work_stay_open(async_test_db):
    db = async_test_db
    w = await _async_world(db)
    p, student = w["project"], w["student"]
    done, open_task = w["tasks"]
    db.add(_submission(w, done))
    await db.flush()
    bare = _Request("/api/projects/x")

    # Task-level: the submitted task is readable, the other one is not.
    assert await _code(
        enforce_seb_async(db, student, p, bare, read_task_id=done.id)
    ) is None
    assert await _code(
        enforce_seb_async(db, student, p, bare, read_task_id=open_task.id)
    ) == "seb_required"
    # Writes never pass without a proof, submitted or not.
    assert await _code(enforce_seb_async(db, student, p, bare)) == "seb_required"


@pytest.mark.asyncio
async def test_request_allowed_for_list_endpoints(async_test_db):
    db = async_test_db
    w = await _async_world(db)
    p, student = w["project"], w["student"]
    path = "/api/projects/x"
    bare, proven = _Request(path), _Request(path, _proof(path))
    assert await seb_request_allowed_async(db, student, p, bare) is False
    assert await seb_request_allowed_async(db, student, p, proven) is True
    assert await seb_request_allowed_async(db, w["owner"], p, bare) is True
    # Attempted tier: own submissions only, so list endpoints narrow.
    assert await seb_request_allowed_async(db, student, p, proven, tier="attempted") is False
    off = await _async_world(db, seb_required=False)
    assert await seb_request_allowed_async(db, off["student"], off["project"], bare) is True


# ── 2. async endpoints ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_task_reads_are_gated(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    p, task = w["project"], w["tasks"][0]
    client = async_test_client

    reads = [f"/api/projects/tasks/{task.id}", f"/api/projects/{p.id}/next"]
    with _as_user(w["student"]):
        for path in reads:
            r = await client.get(path)
            assert r.status_code == 403, path
            assert r.json()["detail"]["code"] == "seb_required", path
            r = await client.get(path, headers=_proof(path))
            assert r.status_code == 200, (path, r.text)
    with _as_user(w["owner"]):
        for path in reads:
            assert (await client.get(path)).status_code == 200, path


@pytest.mark.asyncio
async def test_task_list_narrows_to_submitted_outside_seb(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    p = w["project"]
    done = w["tasks"][0]
    path = f"/api/projects/{p.id}/tasks"
    client = async_test_client

    with _as_user(w["student"]):
        r = await client.get(path)
        assert r.status_code == 200 and r.json()["items"] == []
        r = await client.get(path, headers=_proof(path))
        assert r.json()["total"] == 2

        # One submission opens exactly that task, never the others.
        db.add(_submission(w, done))
        await db.flush()
        r = await client.get(path)
        assert [t["id"] for t in r.json()["items"]] == [done.id]
    with _as_user(w["owner"]):
        assert (await client.get(path)).json()["total"] == 2


@pytest.mark.asyncio
async def test_next_after_everything_submitted_is_done_not_403(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    for task in w["tasks"]:
        db.add(_submission(w, task))
    await db.flush()
    with _as_user(w["student"]):
        r = await async_test_client.get(f"/api/projects/{w['project'].id}/next")
    assert r.status_code == 200
    assert r.json()["task"] is None


@pytest.mark.asyncio
async def test_data_explorer_shows_only_submitted_tasks(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    p = w["project"]
    done = w["tasks"][0]
    client = async_test_client
    with _as_user(w["student"]):
        r = await client.get("/api/data/", params={"project_ids": [p.id]})
        assert r.status_code == 200 and r.json()["items"] == []
        db.add(_submission(w, done))
        await db.flush()
        r = await client.get("/api/data/", params={"project_ids": [p.id]})
        assert [t["id"] for t in r.json()["items"]] == [done.id]
    with _as_user(w["owner"]):
        r = await client.get("/api/data/", params={"project_ids": [p.id]})
        assert r.json()["total"] == 2


@pytest.mark.asyncio
async def test_submitted_task_is_readable_outside_seb(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    done = w["tasks"][0]
    db.add(_submission(w, done))
    await db.flush()
    with _as_user(w["student"]):
        r = await async_test_client.get(f"/api/projects/tasks/{done.id}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_annotation_patch_and_skip_are_gated(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    ann = _submission(w, w["tasks"][0])
    db.add(ann)
    await db.flush()
    path = f"/api/projects/annotations/{ann.id}"
    body = {"result": [{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}]}
    skip = f"/api/projects/{w['project'].id}/tasks/{w['tasks'][1].id}/skip"
    with _as_user(w["student"]):
        r = await async_test_client.patch(path, json=body)
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "seb_required"
        r = await async_test_client.patch(path, json=body, headers=_proof(path))
        assert r.status_code == 200, r.text
        r = await async_test_client.post(skip, json={})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "seb_required"
        r = await async_test_client.post(skip, json={}, headers=_proof(skip))
        assert r.status_code == 200, r.text


# ── 3. sync endpoints ───────────────────────────────────────────────────────


def test_sync_write_endpoints_are_gated(test_db, client):
    w = _sync_world(test_db)
    p, task = w["project"], w["tasks"][0]
    draft = f"/api/projects/{p.id}/tasks/{task.id}/draft"
    checkpoint = f"/api/projects/{p.id}/tasks/{task.id}/checkpoint"
    submit = f"/api/projects/tasks/{task.id}/annotations"
    my_tasks = f"/api/projects/{p.id}/my-tasks"
    result = [{"from_name": "x", "to_name": "text", "type": "textarea", "value": {"text": ["a"]}}]

    with _as_user(w["student"]):
        for method, path, body in (
            ("put", draft, {"result": result}),
            ("post", checkpoint, {"result": result}),
            ("post", submit, {"result": result}),
        ):
            kwargs = {"json": body} if body is not None else {}
            r = getattr(client, method)(path, **kwargs)
            assert r.status_code == 403, (path, r.text)
            assert r.json()["detail"]["code"] == "seb_required", path

        # Outside SEB "my tasks" lists only submitted work: nothing yet.
        r = client.get(my_tasks)
        assert r.status_code == 200 and r.json()["tasks"] == []

        assert client.put(draft, json={"result": result}, headers=_proof(draft)).status_code == 200
        r = client.post(checkpoint, json={"result": result}, headers=_proof(checkpoint))
        assert r.status_code == 200, r.text
        r = client.post(submit, json={"result": result}, headers=_proof(submit))
        assert r.status_code == 200, r.text
        # Submitted: that task (and only that one) is listed outside SEB.
        r = client.get(my_tasks)
        assert [t["id"] for t in r.json()["tasks"]] == [task.id]

    with _as_user(w["owner"]):
        assert client.put(draft, json={"result": result}).status_code == 200


# ── 4. gaps found in the 2026-09-26 review ─────────────────────────────────


@pytest.mark.asyncio
async def test_attempted_tier_reads_only_its_own_submissions(async_test_db):
    """Leaving and rejoining (→ attempted tier) must not unlock other tasks."""
    db = async_test_db
    w = await _async_world(db)
    p, student = w["project"], w["student"]
    done, open_task = w["tasks"]
    db.add(_submission(w, done))
    await db.flush()
    bare = _Request("/api/projects/x")
    assert await _code(
        enforce_seb_async(db, student, p, bare, tier="attempted", read_task_id=done.id)
    ) is None
    assert await _code(
        enforce_seb_async(db, student, p, bare, tier="attempted", read_task_id=open_task.id)
    ) == "seb_required"


@pytest.mark.asyncio
async def test_js_proof_only_counts_on_this_exams_pages(async_test_db):
    db = async_test_db
    w = await _async_world(db)
    p, student = w["project"], w["student"]

    def js(page):
        digest = hashlib.sha256((page + CK).encode()).hexdigest()
        return _Request("/api/projects/x", {"X-Benger-SEB-CK": digest, "X-Benger-SEB-URL": page})

    assert await _code(enforce_seb_async(db, student, p, js(f"{BASE}/projects/{p.id}/label"))) is None
    assert await _code(enforce_seb_async(db, student, p, js(f"{BASE}/dashboard"))) == "seb_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("seb_required", [True, False])
async def test_project_wide_content_views_are_for_editors(
    async_test_db, async_test_client, seb_required
):
    """Generation and evaluation views carry every task's content and the
    reference answers. Plain members were let in before (a leak past
    blinding, windows and the SEB gate); now only editors, SEB or not."""
    db = async_test_db
    w = await _async_world(db, seb_required=seb_required)
    p, task = w["project"], w["tasks"][0]
    client = async_test_client
    paths = [
        f"/api/generation-tasks/projects/{p.id}/task-status",
        f"/api/evaluations/projects/{p.id}/results/by-task-model",
    ]
    sample = ("/api/evaluations/sample-result", {"task_id": task.id, "model_id": "m"})
    with _as_user(w["student"]):
        for path in paths:
            r = await client.get(path, headers=_proof(path))
            assert r.status_code == 403, (path, r.text)
        r = await client.get(sample[0], params=sample[1])
        assert r.status_code == 403, r.text
    with _as_user(w["owner"]):
        for path in paths:
            assert (await client.get(path)).status_code == 200, path


@pytest.mark.asyncio
async def test_next_done_counts_only_assigned_tasks(async_test_db, async_test_client):
    from project_models import TaskAssignment

    db = async_test_db
    w = await _async_world(db)
    p = w["project"]
    p.assignment_mode = "manual"
    mine = w["tasks"][0]
    db.add(
        TaskAssignment(
            id=_uid(), task_id=mine.id, user_id=w["student"].id, assigned_by=w["owner"].id
        )
    )
    db.add(_submission(w, mine))
    await db.flush()
    with _as_user(w["student"]):
        r = await async_test_client.get(f"/api/projects/{p.id}/next")
    assert r.status_code == 200, r.text
    assert r.json()["task"] is None


@pytest.mark.parametrize("seb_required", [True, False])
def test_bulk_exports_are_for_editors(test_db, client, seb_required):
    """Plain members used to get raw task data of any project they could see."""
    w = _sync_world(test_db, seb_required=seb_required)
    p = w["project"]
    body = {"project_ids": [p.id]}
    with _as_user(w["student"]):
        r = client.post("/api/projects/bulk-export", json=body)
        assert r.status_code == 200
        assert "t1" not in r.text and p.id not in r.text
        r = client.post("/api/projects/bulk-export-full", json=body)
        assert b"t1" not in r.content
    with _as_user(w["owner"]):
        r = client.post("/api/projects/bulk-export", json=body)
        assert r.status_code == 200 and p.id in r.text and "t1" in r.text
