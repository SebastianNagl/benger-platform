"""Human evaluation sessions and the projects they belong to.

The session routes (``routers/evaluations/human.py``) load a session by its
id, not by a project. The access-key gate used to bind only a
``project_id`` the caller sent, so a key limited to project A named A in the
query and read the next item (task data with the reference solution),
progress and ratings of a session of project B, or deleted it. Now the gate
resolves ``session_id`` (path, query or body) and ``task_id`` (body) to
their projects, ``next-item`` needs ``tasks:read_reference`` like every
route that returns task content, and the handlers stop serving a session
whose project the user can no longer see. Keys and users that stay inside
their projects are unchanged."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import HumanEvaluationSession, LikertScaleEvaluation
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import bearer, make_project, make_tasks

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SCOPES = ["annotations:write", "tasks:read_reference"]


def _code(response):
    try:
        detail = response.json().get("detail")
    except Exception:
        return None
    return detail.get("code") if isinstance(detail, dict) else None


def _session(project, evaluator, session_type="likert"):
    return HumanEvaluationSession(
        id=str(uuid.uuid4()),
        project_id=project.id,
        evaluator_id=evaluator.id,
        session_type=session_type,
        items_evaluated=0,
        total_items=1,
        status="active",
    )


@pytest.fixture
async def world(async_test_db):
    """An org whose member (CONTRIBUTOR) evaluates in two projects, ``mine``
    (the restricted key's) and ``other``, each with one task and an active
    Likert session of the member."""
    db = async_test_db
    w = await seed_world(db, group=False)
    admin, org, member = w["admin"], w["org"], w["member"]
    for key, title in (("mine", "Project A"), ("other", "Project B")):
        project = await make_project(db, admin.id, org_id=org.id, title=title)
        w[key] = project
        w[f"{key}_task"] = (await make_tasks(db, project, 1, admin.id))[0]
        w[f"{key}_session"] = _session(project, member)
        db.add(w[f"{key}_session"])
    await db.flush()
    return w


async def _key(db, world, **extra):
    body = {"name": "k", "scopes": SCOPES, **extra}
    return bearer((await svc.create_personal_key(db, world["member"].id, body))[1])


async def _restricted(db, world):
    return await _key(db, world, project_ids=[world["mine"].id])


def _likert(session, task):
    return {
        "session_id": session.id,
        "task_id": task.id,
        "response_id": "r1",
        "ratings": {"correctness": 4},
    }


async def test_restricted_key_cannot_reach_another_projects_session(
    async_test_client, async_test_db, world
):
    """The reported leak: naming the key's own project in the query opened a
    session of another project."""
    c, db = async_test_client, async_test_db
    headers = await _restricted(db, world)
    sid, mine = world["other_session"].id, world["mine"].id
    secret = world["other_task"].data["Musterloesung"]
    for method, path, body in (
        ("GET", f"/api/evaluations/human/next-item?session_id={sid}", None),
        ("GET", f"/api/evaluations/human/next-item?session_id={sid}&project_id={mine}", None),
        ("GET", f"/api/evaluations/human/session/{sid}/progress?project_id={mine}", None),
        (
            "POST",
            f"/api/evaluations/human/likert?project_id={mine}",
            _likert(world["other_session"], world["other_task"]),
        ),
        (
            "POST",
            f"/api/evaluations/human/preference?project_id={mine}",
            {
                "session_id": sid,
                "task_id": world["other_task"].id,
                "response_a_id": "a",
                "response_b_id": "b",
                "winner": "a",
            },
        ),
        ("DELETE", f"/api/evaluations/human/session/{sid}?project_id={mine}", None),
    ):
        r = await c.request(method, path, json=body, headers=headers)
        assert r.status_code == 404 and _code(r) == "not_found", (method, path, r.text)
        assert secret not in r.text
    assert await db.get(HumanEvaluationSession, sid) is not None
    rows = await db.execute(
        select(LikertScaleEvaluation).where(LikertScaleEvaluation.session_id == sid)
    )
    assert rows.scalars().all() == []


async def test_restricted_key_cannot_rate_another_projects_task_in_its_session(
    async_test_client, async_test_db, world
):
    c, db = async_test_client, async_test_db
    r = await c.post(
        "/api/evaluations/human/likert",
        json=_likert(world["mine_session"], world["other_task"]),
        headers=await _restricted(db, world),
    )
    assert r.status_code == 404 and _code(r) == "not_found", r.text


async def test_restricted_key_keeps_its_own_session(async_test_client, async_test_db, world):
    c, db = async_test_client, async_test_db
    headers = await _restricted(db, world)
    sid = world["mine_session"].id
    r = await c.get(f"/api/evaluations/human/next-item?session_id={sid}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["task_id"] == world["mine_task"].id
    r = await c.post(
        "/api/evaluations/human/likert",
        json=_likert(world["mine_session"], world["mine_task"]),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await c.get(f"/api/evaluations/human/session/{sid}/progress", headers=headers)
    assert r.status_code == 200 and r.json()["items_evaluated"] == 1, r.text
    r = await c.get(f"/api/evaluations/human/sessions/{world['mine'].id}", headers=headers)
    assert r.status_code == 200 and [s["id"] for s in r.json()] == [sid], r.text
    r = await c.delete(f"/api/evaluations/human/session/{sid}", headers=headers)
    assert r.status_code == 200, r.text


async def test_unrestricted_key_reaches_every_session_of_its_user(
    async_test_client, async_test_db, world
):
    c, headers = async_test_client, await _key(async_test_db, world)
    for key in ("mine", "other"):
        r = await c.get(
            f"/api/evaluations/human/next-item?session_id={world[f'{key}_session'].id}",
            headers=headers,
        )
        assert r.status_code == 200 and r.json()["task_id"] == world[f"{key}_task"].id, r.text


async def test_next_item_needs_read_reference(async_test_client, async_test_db, world):
    """It returns the task data, reference solution included."""
    c, db = async_test_client, async_test_db
    headers = await _key(db, world, scopes=["annotations:write"])
    sid = world["mine_session"].id
    r = await c.get(f"/api/evaluations/human/next-item?session_id={sid}", headers=headers)
    assert r.status_code == 403 and _code(r) == "insufficient_scope", r.text
    r = await c.get(f"/api/evaluations/human/session/{sid}/progress", headers=headers)
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# Browser sessions
# --------------------------------------------------------------------------- #


@pytest.fixture
def as_member(world):
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
    yield user
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(optional_user, None)


@pytest.fixture
async def lost(async_test_db, world):
    """A session of the member in a project they can no longer see (no
    organization, created by someone else)."""
    db = async_test_db
    project = await make_project(db, world["admin"].id, title="Project C")
    task = (await make_tasks(db, project, 1, world["admin"].id))[0]
    session = _session(project, world["member"])
    db.add(session)
    await db.flush()
    return {"project": project, "task": task, "session": session}


async def test_session_of_a_project_the_user_lost_is_closed(
    async_test_client, async_test_db, world, as_member, lost
):
    c = async_test_client
    sid = lost["session"].id
    secret = lost["task"].data["Musterloesung"]
    r = await c.get(f"/api/evaluations/human/next-item?session_id={sid}")
    assert r.status_code == 404 and secret not in r.text, r.text
    r = await c.get(f"/api/evaluations/human/session/{sid}/progress")
    assert r.status_code == 404, r.text
    r = await c.post("/api/evaluations/human/likert", json=_likert(lost["session"], lost["task"]))
    assert r.status_code == 404, r.text
    rows = await async_test_db.execute(
        select(LikertScaleEvaluation).where(LikertScaleEvaluation.session_id == sid)
    )
    assert rows.scalars().all() == []


async def test_session_of_a_project_the_user_lost_cannot_be_deleted(
    async_test_client, async_test_db, world, as_member, lost
):
    db = async_test_db
    sid = lost["session"].id
    db.add(
        LikertScaleEvaluation(
            id=str(uuid.uuid4()),
            session_id=sid,
            task_id=lost["task"].id,
            response_id="r1",
            dimension="correctness",
            rating=4,
        )
    )
    await db.flush()
    r = await async_test_client.delete(f"/api/evaluations/human/session/{sid}")
    assert r.status_code == 404, r.text
    db.expire_all()
    session = await db.execute(
        select(HumanEvaluationSession).where(HumanEvaluationSession.id == sid)
    )
    assert session.scalar_one_or_none() is not None
    rows = await db.execute(
        select(LikertScaleEvaluation).where(LikertScaleEvaluation.session_id == sid)
    )
    assert len(rows.scalars().all()) == 1


async def test_rating_names_a_task_of_the_sessions_project(
    async_test_client, async_test_db, world, as_member
):
    c = async_test_client
    r = await c.post(
        "/api/evaluations/human/likert",
        json=_likert(world["mine_session"], world["other_task"]),
    )
    assert r.status_code == 404, r.text
    r = await c.post(
        "/api/evaluations/human/likert",
        json=_likert(world["mine_session"], world["mine_task"]),
    )
    assert r.status_code == 200 and r.json()["items_evaluated"] == 1, r.text


async def test_member_keeps_reaching_own_sessions(async_test_client, world, as_member):
    c = async_test_client
    for key in ("mine", "other"):
        r = await c.get(
            f"/api/evaluations/human/next-item?session_id={world[f'{key}_session'].id}"
        )
        assert r.status_code == 200 and r.json()["task_id"] == world[f"{key}_task"].id, r.text
