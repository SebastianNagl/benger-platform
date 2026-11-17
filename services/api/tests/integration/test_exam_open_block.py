"""The exam-open seam of the read guards (CORE 2.54, real PostgreSQL).

An overlay keeps an exam closed for its participants through the optional
worker attribute ``<package>.workers.get_exam_open_block_fn`` (e.g. until every
task has a checked grading sheet). The platform asks it in
``enforce_project_read_window(_async)`` after the window rule and in the
``/api/data`` scope:

- a participant read answers 403 ``{code: "exam_not_ready", reason}``;
- editors, superadmins and the attempted tier pass; any other caller with an
  own submission is demoted to the attempted tier (own submissions only);
- the window rule keeps its own answer before the hook;
- a failing hook counts as open; without a package nothing changes;
- writes never ask the hook.

The extended package is faked through ``sys.modules``.
"""

import sys
import types
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    ProjectShareLink,
    ProjectShareMember,
    Task,
)
from routers.projects.helpers import (
    EXAM_NOT_READY_CODE,
    TIER_ATTEMPTED,
    TIER_PARTICIPANT,
    get_project_access_tier_async,
    enforce_project_read_window,
    enforce_project_read_window_async,
    enforce_project_write_window_async,
    exam_open_block,
)


def _uid():
    return str(uuid.uuid4())


class _Hook:
    """A controllable ``get_exam_open_block_fn`` result."""

    def __init__(self, block=None, error=None, only=None):
        self.block = block
        self.error = error
        self.only = only
        self.calls = []

    def __call__(self, db, *, project, user_id):
        self.calls.append((project.id, user_id))
        if self.error is not None:
            raise self.error
        if self.only is not None and project.id != self.only:
            return None
        return self.block


@contextmanager
def _extended(hook):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    if hook is not None:
        workers.get_exam_open_block_fn = lambda: hook
    pkg.workers = workers
    with patch.dict(sys.modules, {"benger_extended": pkg, "benger_extended.workers": workers}):
        yield


def _rows(*, window=None):
    now = datetime.now(timezone.utc)
    org = Organization(
        id=_uid(),
        name=f"org-{_uid()[:8]}",
        slug=f"org-{_uid()[:8]}",
        display_name="Org",
        created_at=now,
    )

    def user(**kw):
        return User(
            id=_uid(),
            username=f"u-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="Test User",
            **kw,
        )

    owner, contributor, student = user(), user(), user()
    superadmin = user(is_superadmin=True)
    start, end = (None, None)
    if window == "upcoming":
        start, end = now + timedelta(hours=1), now + timedelta(hours=3)
    project = Project(
        id=_uid(),
        title="Exam not ready",
        created_by=owner.id,
        kind="exam",
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode="open",
        rubric_review_required=True,
        window_start_at=start,
        window_end_at=end,
    )
    task = Task(id=_uid(), project_id=project.id, data={"text": "Sachverhalt"}, inner_id=1)

    def member(u, role):
        return OrganizationMembership(
            id=_uid(),
            user_id=u.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=now,
        )

    links = [
        member(owner, "ORG_ADMIN"),
        member(contributor, "CONTRIBUTOR"),
        member(student, "ANNOTATOR"),
        ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=owner.id
        ),
    ]
    return {
        "org": org,
        "owner": owner,
        "contributor": contributor,
        "student": student,
        "superadmin": superadmin,
        "project": project,
        "task": task,
        "links": links,
    }


async def _world(db, **kw):
    w = _rows(**kw)
    db.add_all([w["org"], w["owner"], w["contributor"], w["student"], w["superadmin"]])
    await db.flush()
    db.add(w["project"])
    await db.flush()
    db.add_all([w["task"], *w["links"]])
    await db.flush()
    return w


def _sync_world(db, **kw):
    w = _rows(**kw)
    db.add_all([w["org"], w["owner"], w["contributor"], w["student"], w["superadmin"]])
    db.flush()
    db.add(w["project"])
    db.flush()
    db.add_all([w["task"], *w["links"]])
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


async def _refusal(coro):
    """The 403 detail if the guard refused, else None."""
    try:
        await coro
        return None
    except HTTPException as e:
        assert e.status_code == 403
        return e.detail


RUBRIC_BLOCK = {"reason": "rubric_missing", "tasks_without_sheet": 1}


@pytest.mark.asyncio
async def test_participant_is_refused_with_the_reason(async_test_db):
    db = async_test_db
    w = await _world(db)
    p, student = w["project"], w["student"]
    hook = _Hook(block=RUBRIC_BLOCK)

    with _extended(hook):
        detail = await _refusal(enforce_project_read_window_async(db, student, p))

    assert detail == {
        "code": EXAM_NOT_READY_CODE,
        "reason": "rubric_missing",
        "message": "This exam is not open yet.",
        "project_id": p.id,
    }
    assert hook.calls == [(p.id, student.id)]


@pytest.mark.asyncio
async def test_editors_superadmins_and_the_attempted_tier_pass(async_test_db):
    db = async_test_db
    w = await _world(db)
    p = w["project"]

    with _extended(_Hook(block=RUBRIC_BLOCK)):
        for editor in (w["owner"], w["contributor"], w["superadmin"]):
            assert await _refusal(enforce_project_read_window_async(db, editor, p)) is None
        # The attempted tier reads an own submission after the fact.
        assert (
            await _refusal(
                enforce_project_read_window_async(db, w["student"], p, tier=TIER_ATTEMPTED)
            )
            is None
        )
        # Without a tier the guard looks the attempt up itself.
        db.add(
            Annotation(
                id=_uid(),
                task_id=w["task"].id,
                project_id=p.id,
                completed_by=w["student"].id,
                result=[{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}],
            )
        )
        await db.flush()
        assert await _refusal(enforce_project_read_window_async(db, w["student"], p)) is None


@pytest.mark.asyncio
async def test_no_block_no_hook_and_a_failing_hook_keep_the_exam_open(async_test_db):
    db = async_test_db
    w = await _world(db)
    p, student = w["project"], w["student"]

    with _extended(_Hook(block=None)):
        assert await _refusal(enforce_project_read_window_async(db, student, p)) is None
    with _extended(None):
        assert await _refusal(enforce_project_read_window_async(db, student, p)) is None
    failing = _Hook(error=RuntimeError("readiness query broke"))
    with _extended(failing):
        assert await _refusal(enforce_project_read_window_async(db, student, p)) is None
    assert failing.calls == [(p.id, student.id)]
    # The failed hook ran in a savepoint: the session is still usable.
    assert (await db.get(Project, p.id)).id == p.id


@pytest.mark.asyncio
async def test_the_window_answers_first(async_test_db):
    db = async_test_db
    w = await _world(db, window="upcoming")
    hook = _Hook(block=RUBRIC_BLOCK)

    with _extended(hook):
        detail = await _refusal(enforce_project_read_window_async(db, w["student"], w["project"]))

    assert detail["code"] == "project_window_upcoming"
    assert hook.calls == []


@pytest.mark.asyncio
async def test_writes_never_ask_the_hook(async_test_db):
    db = async_test_db
    w = await _world(db)
    hook = _Hook(block=RUBRIC_BLOCK)

    with _extended(hook):
        assert (
            await _refusal(enforce_project_write_window_async(db, w["student"], w["project"]))
            is None
        )
    assert hook.calls == []


def test_sync_guard_and_string_blocks(test_db):
    w = _sync_world(test_db)
    p, student = w["project"], w["student"]

    with _extended(_Hook(block="rubric_missing")):
        assert exam_open_block(test_db, student, p) == {"reason": "rubric_missing"}
        with pytest.raises(HTTPException) as exc:
            enforce_project_read_window(test_db, student, p)
        assert exc.value.detail["code"] == EXAM_NOT_READY_CODE
        assert exc.value.detail["reason"] == "rubric_missing"
        enforce_project_read_window(test_db, w["owner"], p)
    with _extended(_Hook(block={"code": "custom_gate"})):
        # A dict without a reason falls back to its code.
        assert exam_open_block(test_db, student, p)["reason"] == "custom_gate"
    with _extended(None):
        assert exam_open_block(test_db, student, p) is None
        enforce_project_read_window(test_db, student, p)


# ── HTTP wiring ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_task_reads_refuse_the_participant(async_test_db, async_test_client):
    db = async_test_db
    w = await _world(db)
    p, task = w["project"], w["task"]
    client = async_test_client

    with _extended(_Hook(block=RUBRIC_BLOCK)):
        with _as_user(w["student"]):
            for path in (
                f"/api/projects/tasks/{task.id}",
                f"/api/projects/{p.id}/tasks",
                f"/api/projects/{p.id}/next",
            ):
                r = await client.get(path)
                assert r.status_code == 403, path
                assert r.json()["detail"]["code"] == EXAM_NOT_READY_CODE, path
                assert r.json()["detail"]["reason"] == "rubric_missing", path
        with _as_user(w["owner"]):
            r = await client.get(f"/api/projects/tasks/{task.id}")
            assert r.status_code == 200
            assert r.json()["data"]["text"] == "Sachverhalt"


@pytest.mark.asyncio
async def test_data_explorer_hides_the_exam_from_participants(async_test_db, async_test_client):
    db = async_test_db
    w = await _world(db)
    other = await _world(db)
    p = w["project"]
    client = async_test_client

    with _as_user(w["student"]):
        r = await client.get("/api/data/", params={"project_ids": [p.id]})
        assert [t["id"] for t in r.json()["items"]] == [w["task"].id]
        with _extended(_Hook(block=RUBRIC_BLOCK, only=p.id)):
            r = await client.get("/api/data/", params={"project_ids": [p.id]})
            assert r.status_code == 200
            assert r.json()["items"] == []
    # Another exam the hook leaves open stays visible to its participant.
    with _as_user(other["student"]):
        with _extended(_Hook(block=RUBRIC_BLOCK, only=p.id)):
            r = await client.get("/api/data/", params={"project_ids": [other["project"].id]})
            assert [t["id"] for t in r.json()["items"]] == [other["task"].id]
    with _as_user(w["owner"]):
        with _extended(_Hook(block=RUBRIC_BLOCK)):
            r = await client.get("/api/data/", params={"project_ids": [p.id]})
            assert r.json()["total"] == 1


async def _share_members(db, w, n):
    """``n`` consented share members of the exam (participant tier) and a
    second task, so an own submission and an unsubmitted task both exist."""
    p, owner = w["project"], w["owner"]
    members = [
        User(id=_uid(), username=f"m-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com", name="M")
        for _ in range(n)
    ]
    link = ProjectShareLink(
        id=_uid(), token=uuid.uuid4().hex, project_id=p.id, created_by=owner.id,
        password_hash="x", is_listed=False,
    )
    db.add_all(members)
    db.add(link)
    await db.flush()
    db.add_all(
        ProjectShareMember(
            id=_uid(), share_link_id=link.id, project_id=p.id, user_id=m.id, attempts=0,
            gdpr_consent_at=datetime.now(timezone.utc), consent_version="1",
        )
        for m in members
    )
    other = Task(id=_uid(), project_id=p.id, data={"text": "Zweiter Sachverhalt"}, inner_id=2)
    db.add(other)
    await db.flush()
    return members, other


@pytest.mark.asyncio
async def test_a_blocked_submitter_keeps_only_their_own_submission(
    async_test_db, async_test_client
):
    from tests.fixtures.v1 import v1_auth

    db = async_test_db
    w = await _world(db)
    p, task = w["project"], w["task"]
    (submitter, newcomer), unsubmitted = await _share_members(db, w, 2)
    # The org ANNOTATOR student (full tier, not an editor) submitted as well.
    db.add_all(
        Annotation(
            id=_uid(),
            task_id=task.id,
            project_id=p.id,
            completed_by=u.id,
            result=[{"from_name": "x", "to_name": "text", "type": "textarea", "value": {}}],
            was_cancelled=False,
        )
        for u in (submitter, w["student"])
    )
    await db.flush()
    client = async_test_client
    # A share member with a submission still resolves to the participant tier.
    assert await get_project_access_tier_async(db, submitter, p.id) == TIER_PARTICIPANT

    with _extended(_Hook(block=RUBRIC_BLOCK)):
        assert (
            await enforce_project_read_window_async(db, submitter, p, tier=TIER_PARTICIPANT)
            == TIER_ATTEMPTED
        )
        detail = await _refusal(
            enforce_project_read_window_async(db, newcomer, p, tier=TIER_PARTICIPANT)
        )
        assert detail["code"] == EXAM_NOT_READY_CODE

        with _as_user(submitter):
            r = await client.get(f"/api/projects/tasks/{task.id}")
            assert r.status_code == 200, r.text
            assert r.json()["data"]["text"] == "Sachverhalt"
            r = await client.get(f"/api/projects/tasks/{unsubmitted.id}")
            assert r.status_code == 404
            r = await client.get(f"/api/projects/{p.id}/tasks")
            assert r.status_code == 200, r.text
            assert [t["id"] for t in r.json()["items"]] == [task.id]
            r = await client.get(f"/api/projects/{p.id}/next")
            assert r.status_code == 200
            assert r.json()["task"] is None
            r = await client.get(f"/api/projects/tasks/{task.id}/annotations")
            assert r.status_code == 200, r.text
            assert {a["completed_by"] for a in r.json()} == {submitter.id}
        with _as_user(w["student"]):
            r = await client.get("/api/data/", params={"project_ids": [p.id]})
            assert [t["id"] for t in r.json()["items"]] == [task.id]
            r = await client.get(f"/api/projects/{p.id}/tasks")
            assert [t["id"] for t in r.json()["items"]] == [task.id]

        with v1_auth(db, session_user=submitter):
            r = await client.get(f"/api/v1/projects/{p.id}/tasks")
            assert r.status_code == 200, r.text
            assert [t["id"] for t in r.json()["items"]] == [task.id]
            r = await client.get(f"/api/v1/projects/{p.id}/tasks/{task.id}")
            assert r.status_code == 200, r.text
            r = await client.get(f"/api/v1/projects/{p.id}/tasks/{unsubmitted.id}")
            assert r.status_code == 404

        with _as_user(newcomer):
            for path in (
                f"/api/projects/tasks/{task.id}",
                f"/api/projects/{p.id}/tasks",
                f"/api/projects/{p.id}/next",
                f"/api/projects/tasks/{task.id}/annotations",
            ):
                r = await client.get(path)
                assert r.status_code == 403, path
                assert r.json()["detail"]["code"] == EXAM_NOT_READY_CODE, path

    # Once the exam is open, the submitters get the whole exam back.
    with _as_user(submitter):
        r = await client.get(f"/api/projects/{p.id}/tasks")
        assert sorted(t["id"] for t in r.json()["items"]) == sorted([task.id, unsubmitted.id])
    with _as_user(w["student"]):
        r = await client.get("/api/data/", params={"project_ids": [p.id]})
        assert sorted(t["id"] for t in r.json()["items"]) == sorted([task.id, unsubmitted.id])
