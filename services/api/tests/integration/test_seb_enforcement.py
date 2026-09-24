"""Integration tests for the Safe Exam Browser gate (real PostgreSQL).

Three layers:
  1. ``enforce_seb_async`` — who is exempt (flag off, editors, superadmin,
     attempted tier, reads of own submitted work) and who is gated.
  2. The async endpoints (task read, next, task list, annotation PATCH).
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
from routers.projects.helpers import enforce_seb_async

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
        enforce_seb_async(db, student, p, bare, read=True, task_id=done.id)
    ) is None
    assert await _code(
        enforce_seb_async(db, student, p, bare, read=True, task_id=open_task.id)
    ) == "seb_required"
    # Project-level reads open once anything was submitted.
    assert await _code(enforce_seb_async(db, student, p, bare, read=True)) is None
    # Writes never pass without a proof, submitted or not.
    assert await _code(enforce_seb_async(db, student, p, bare)) == "seb_required"


# ── 2. async endpoints ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_read_endpoints(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    p, task = w["project"], w["tasks"][0]
    client = async_test_client

    reads = [
        f"/api/projects/tasks/{task.id}",
        f"/api/projects/{p.id}/next",
        f"/api/projects/{p.id}/tasks",
    ]
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
async def test_annotation_patch_is_gated(async_test_db, async_test_client):
    db = async_test_db
    w = await _async_world(db)
    ann = _submission(w, w["tasks"][0])
    db.add(ann)
    await db.flush()
    path = f"/api/projects/annotations/{ann.id}"
    body = {"result": [{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}]}
    with _as_user(w["student"]):
        r = await async_test_client.patch(path, json=body)
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "seb_required"
        r = await async_test_client.patch(path, json=body, headers=_proof(path))
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
            ("get", my_tasks, None),
        ):
            kwargs = {"json": body} if body is not None else {}
            r = getattr(client, method)(path, **kwargs)
            assert r.status_code == 403, (path, r.text)
            assert r.json()["detail"]["code"] == "seb_required", path

        assert client.put(draft, json={"result": result}, headers=_proof(draft)).status_code == 200
        r = client.post(checkpoint, json={"result": result}, headers=_proof(checkpoint))
        assert r.status_code == 200, r.text
        r = client.post(submit, json={"result": result}, headers=_proof(submit))
        assert r.status_code == 200, r.text
        # Submitted: the own task list is readable outside SEB again.
        assert client.get(my_tasks).status_code == 200

    with _as_user(w["owner"]):
        assert client.put(draft, json={"result": result}).status_code == 200
