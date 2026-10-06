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


@pytest.mark.parametrize("seb_required", [True, False])
def test_checkpoint_reads_follow_the_task_read_rule(test_db, client, seb_required):
    """Own checkpoints of an unsubmitted task need the proof like the task
    itself (no reading the draft on a second device); once the task is
    submitted they open anywhere. Projects without SEB are unaffected."""
    w = _sync_world(test_db, seb_required=seb_required)
    p, task = w["project"], w["tasks"][0]
    p.restorable_checkpoints_enabled = True
    test_db.flush()
    base = f"/api/projects/{p.id}/tasks/{task.id}"
    result = [{"from_name": "x", "to_name": "text", "type": "textarea", "value": {"text": ["a"]}}]

    with _as_user(w["student"]):
        saved = client.post(
            f"{base}/checkpoint", json={"result": result}, headers=_proof(f"{base}/checkpoint")
        )
        assert saved.status_code == 200, saved.text
        reads = [f"{base}/checkpoints", f"{base}/checkpoints/{saved.json()['checkpoint_id']}"]

        for path in reads:
            r = client.get(path)
            if not seb_required:
                assert r.status_code == 200, (path, r.text)
                continue
            assert r.status_code == 403, (path, r.text)
            assert r.json()["detail"] == {
                "code": "seb_required",
                "message": "This exam must be opened in Safe Exam Browser.",
                "project_id": p.id,
            }
            assert client.get(path, headers=_proof(path)).status_code == 200, path

        submit = f"/api/projects/tasks/{task.id}/annotations"
        r = client.post(submit, json={"result": result}, headers=_proof(submit))
        assert r.status_code == 200, r.text
        for path in reads:
            assert client.get(path).status_code == 200, path
        assert len(client.get(reads[0]).json()["checkpoints"]) == 1

    with _as_user(w["owner"]):
        assert client.get(reads[0]).status_code == 200


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


async def _eval_run(db, project):
    from models import EvaluationRun

    run = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["exact_match"],
        metrics={"accuracy": 0.9},
        eval_metadata={"type": "auto"},
        status="completed",
        samples_evaluated=1,
        has_sample_results=True,
        created_by=project.created_by,
    )
    db.add(run)
    await db.flush()
    return run


def _content_views(p, task, run):
    return [
        (f"/api/generation-tasks/projects/{p.id}/task-status", None),
        (f"/api/evaluations/projects/{p.id}/results/by-task-model", None),
        (f"/api/evaluations/{run.id}/results/by-task-model", None),
        (f"/api/evaluations/{run.id}/samples", None),
        ("/api/evaluations/sample-result", {"task_id": task.id, "model_id": "m"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("seb_required", [True, False])
async def test_project_wide_content_views_are_for_contributors(
    async_test_db, async_test_client, seb_required
):
    """Generation and evaluation views carry every task's content, the
    reference answers and other people's work. Plain members were let in
    before (a leak past blinding, windows and the SEB gate)."""
    db = async_test_db
    w = await _async_world(db, seb_required=seb_required)
    p, task = w["project"], w["tasks"][0]
    run = await _eval_run(db, p)
    client = async_test_client
    with _as_user(w["student"]):
        for path, params in _content_views(p, task, run):
            r = await client.get(path, params=params, headers=_proof(path))
            assert r.status_code == 403, (path, r.text)
    with _as_user(w["owner"]):
        for path, params in _content_views(p, task, run)[:4]:
            assert (await client.get(path, params=params)).status_code == 200, path


@pytest.mark.asyncio
@pytest.mark.parametrize("seb_required, allowed", [(False, True), (True, False)])
async def test_public_contributors_see_content_views_except_on_seb_exams(
    async_test_db, async_test_client, seb_required, allowed
):
    """A public project's CONTRIBUTOR visitors may generate and evaluate, so
    they see these views; a Safe Exam Browser exam keeps them to its editors."""
    db = async_test_db
    w = await _async_world(db, seb_required=seb_required)
    p = w["project"]
    p.is_public, p.public_role = True, "CONTRIBUTOR"
    visitor = User(
        id=_uid(), username=f"v-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com", name="V"
    )
    db.add(visitor)
    await db.flush()
    path = f"/api/generation-tasks/projects/{p.id}/task-status"
    with _as_user(visitor):
        r = await async_test_client.get(path)
    assert (r.status_code == 200) is allowed, r.text


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
def test_bulk_exports_are_for_contributors(test_db, client, seb_required):
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


@pytest.mark.asyncio
async def test_next_done_counts_skipped_tasks(async_test_db, async_test_client):
    from project_models import SkippedTask

    db = async_test_db
    w = await _async_world(db)
    p = w["project"]
    done, skipped = w["tasks"]
    db.add(_submission(w, done))
    db.add(SkippedTask(id=_uid(), task_id=skipped.id, project_id=p.id, skipped_by=w["student"].id))
    await db.flush()
    with _as_user(w["student"]):
        r = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert r.status_code == 200, r.text
        assert r.json()["task"] is None
        # The skipped task itself stays behind the gate.
        r = await async_test_client.get(f"/api/projects/tasks/{skipped.id}")
        assert r.status_code == 403


# ── 5. channels, pinned builds and exports over HTTP (issue #135 follow-up) ──

BEK = "b" * 64


def _digest(url, key):
    return hashlib.sha256((url + key).encode()).hexdigest()


def _js_proof(page, *, load=None, hashed=None, bek=None):
    """The headers ``lib/seb.ts`` sends: SEB's hash plus the page URLs.

    ``hashed`` is the URL SEB computed the hash over (default: ``page``).
    """
    headers = {"X-Benger-SEB-CK": _digest(hashed or page, CK), "X-Benger-SEB-URL": page}
    if load:
        headers["X-Benger-SEB-Load-URL"] = load
    if bek:
        headers["X-Benger-SEB-BEK"] = _digest(hashed or page, bek)
    return headers


@pytest.mark.asyncio
async def test_js_channel_passes_the_endpoints(async_test_db, async_test_client):
    """macOS / iOS: the proof rides our own headers, hashed over the page URL."""
    db = async_test_db
    w = await _async_world(db)
    p, task = w["project"], w["tasks"][0]
    read = f"/api/projects/tasks/{task.id}"
    draft = f"/api/projects/{p.id}/tasks/{task.id}/draft"
    exam_page = f"{BASE}/projects/{p.id}/label"
    student_page = f"{BASE}/student/exams/{p.id}"
    elsewhere = f"{BASE}/dashboard"
    client = async_test_client
    with _as_user(w["student"]):
        for page in (exam_page, student_page):
            r = await client.get(read, headers=_js_proof(page))
            assert r.status_code == 200, (page, r.text)
        # After client-side navigation SEB may still hold the hash of the URL
        # the document was loaded with: the load URL counts too.
        r = await client.get(read, headers=_js_proof(elsewhere, load=exam_page, hashed=exam_page))
        assert r.status_code == 200, r.text
        # Neither URL is this exam's page: refused, although the hash is right.
        r = await client.get(read, headers=_js_proof(elsewhere, load=elsewhere))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "seb_required"
        # Another exam's page does not prove this one.
        other = f"{BASE}/projects/{_uid()}/label"
        r = await client.get(read, headers=_js_proof(other))
        assert r.status_code == 403, r.text
        # A hash over the right page with another key is refused.
        wrong = {"X-Benger-SEB-CK": _digest(exam_page, "f" * 64), "X-Benger-SEB-URL": exam_page}
        r = await client.get(read, headers=wrong)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "seb_required"
        # Writes take the same proof.
        body = {"result": [{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}]}
        assert (await client.put(draft, json=body)).status_code == 403


@pytest.mark.asyncio
async def test_pinned_browser_exam_key_over_http(async_test_db, async_test_client):
    """With a Browser Exam Key pinned, the right configuration in another SEB
    build is refused with its own code, on both channels."""
    db = async_test_db
    w = await _async_world(db)
    p, task = w["project"], w["tasks"][0]
    p.seb_config = {
        "generated_config_key": CK,
        "browser_exam_keys": [{"key": BEK, "label": "SEB 3.7 macOS"}],
    }
    await db.flush()
    read = f"/api/projects/tasks/{task.id}"
    page = f"{BASE}/projects/{p.id}/label"
    native = _proof(read)
    cases = [
        (native, 403),
        ({**native, "X-SafeExamBrowser-RequestHash": _digest(BASE + read, "a" * 64)}, 403),
        ({**native, "X-SafeExamBrowser-RequestHash": _digest(BASE + read, BEK)}, 200),
        (_js_proof(page), 403),
        (_js_proof(page, bek="a" * 64), 403),
        (_js_proof(page, bek=BEK), 200),
    ]
    with _as_user(w["student"]):
        for headers, expected in cases:
            r = await async_test_client.get(read, headers=headers)
            assert r.status_code == expected, (headers, r.text)
            if expected == 403:
                assert r.json()["detail"]["code"] == "seb_version_not_allowed", headers
        # No configuration proof at all stays the plain "open in SEB" refusal.
        r = await async_test_client.get(read)
        assert r.json()["detail"]["code"] == "seb_required"
    with _as_user(w["owner"]):
        assert (await async_test_client.get(read)).status_code == 200


@pytest.mark.asyncio
async def test_questionnaire_response_is_gated(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    p, task = w["project"], w["tasks"][0]
    p.questionnaire_enabled = True
    submission = _submission(w, task)
    db.add(submission)
    await db.flush()
    path = f"/api/projects/{p.id}/tasks/{task.id}/questionnaire-response"
    body = {"annotation_id": submission.id, "result": [{"from_name": "q", "value": {"rating": 3}}]}
    with _as_user(w["student"]):
        r = await async_test_client.post(path, json=body)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "seb_required"
        r = await async_test_client.post(path, json=body, headers=_proof(path))
        assert r.status_code == 200, r.text


def _public_contributor_project(w):
    visitor = User(
        id=_uid(), username=f"v-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com", name="V"
    )
    w["project"].is_public, w["project"].public_role = True, "CONTRIBUTOR"
    return visitor


@pytest.mark.parametrize("seb_required, allowed", [(False, True), (True, False)])
def test_task_export_is_for_editors_on_seb_exams(test_db, client, seb_required, allowed):
    """The per-project task export dumps unblinded task data. A public
    project's CONTRIBUTOR visitors get it, except on a Safe Exam Browser exam."""
    w = _sync_world(test_db, seb_required=seb_required)
    visitor = _public_contributor_project(w)
    test_db.add(visitor)
    test_db.flush()
    path = f"/api/projects/{w['project'].id}/tasks/bulk-export"
    body = {"format": "json", "task_ids": [t.id for t in w["tasks"]]}
    with _as_user(visitor):
        r = client.post(path, json=body)
        assert r.status_code == (200 if allowed else 403), r.text
        assert ('"t1"' in r.text) is allowed
    with _as_user(w["student"]):
        r = client.post(path, json=body)
        assert r.status_code == 403 and '"t1"' not in r.text
    with _as_user(w["owner"]):
        r = client.post(path, json=body)
        assert r.status_code == 200 and '"t1"' in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("seb_required, allowed", [(False, True), (True, False)])
async def test_export_job_is_for_editors_on_seb_exams(
    async_test_db, async_test_client, seb_required, allowed
):
    db = async_test_db
    w = await _async_world(db, seb_required=seb_required)
    visitor = _public_contributor_project(w)
    db.add(visitor)
    await db.flush()
    path = f"/api/projects/{w['project'].id}/exports"
    with _as_user(visitor):
        r = await async_test_client.post(path, json={})
        assert r.status_code == (202 if allowed else 403), r.text
    with _as_user(w["owner"]):
        r = await async_test_client.post(path, json={})
        assert r.status_code == 202, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("seb_required, allowed", [(False, True), (True, False)])
async def test_someone_elses_export_job_is_for_editors_on_seb_exams(
    async_test_db, async_test_client, seb_required, allowed
):
    """Polling or downloading a colleague's export follows the same rule as
    creating one: a public CONTRIBUTOR visitor may on a normal project, not
    on a Safe Exam Browser exam."""
    from models import ExportJob

    db = async_test_db
    w = await _async_world(db, seb_required=seb_required)
    visitor = _public_contributor_project(w)
    db.add(visitor)
    job = ExportJob(
        id=_uid(), project_id=w["project"].id, requested_by=w["owner"].id,
        format="json", status="pending", progress=0,
    )
    db.add(job)
    await db.flush()
    path = f"/api/projects/{w['project'].id}/exports/{job.id}"
    with _as_user(visitor):
        r = await async_test_client.get(path)
        assert r.status_code == (200 if allowed else 403), r.text
    with _as_user(w["student"]):
        assert (await async_test_client.get(path)).status_code == 403
    with _as_user(w["owner"]):
        assert (await async_test_client.get(path)).status_code == 200
