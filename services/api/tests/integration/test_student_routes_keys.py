"""Access keys on the personal student reads (``/api/student/*`` of the
platform: score-history, retention, activity).

Each of these routes aggregates the caller's data across all their projects
(project ids, titles and scores of graded attempts, flashcard reviews of
every deck, exam submissions per project). They name no project, so a
project-restricted key (a project list or a group) is refused, as on the
other cross-project lists; unrestricted keys and browser sessions read them
as before."""

import uuid
from datetime import datetime, timezone

import pytest

from models import EvaluationJudgeRun, EvaluationRun, OrganizationRole, TaskEvaluation
from project_models import Annotation, FlashcardReview
from services import api_key_service as svc
from tests.fixtures.access_keys import make_group_membership, seed_world
from tests.fixtures.v1 import bearer, make_project, make_tasks

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

STUDENT_ROUTES = [
    "/api/student/score-history?scope=all",
    "/api/student/retention",
    "/api/student/activity",
]


async def _graded_attempt(db, project, task, student, *, score: float) -> None:
    """One annotation of ``student`` on ``task`` with an immediate AI grading."""
    annotation = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=student.id,
        result=[],
    )
    db.add(annotation)
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id="immediate",
        evaluation_type_ids=[],
        metrics={},
        created_by=student.id,
    )
    db.add(run)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id="judge"
    )
    db.add(judge_run)
    await db.flush()
    db.add(
        TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            judge_run_id=judge_run.id,
            task_id=task.id,
            annotation_id=annotation.id,
            field_name="loesung",
            answer_type="long_text",
            ground_truth="...",
            prediction="...",
            metrics={"llm_judge_falloesung": {"value": score, "details": {}}},
            passed=score >= 0.5,
        )
    )
    db.add(
        FlashcardReview(
            id=str(uuid.uuid4()),
            task_id=task.id,
            user_id=student.id,
            project_id=project.id,
            mode="quick",
            rating="good",
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=True)
    member = w["member"]
    w["mine"] = await make_project(
        db, w["admin"].id, org_id=w["org"].id, title="Project A", kind="exam"
    )
    w["other"] = await make_project(
        db,
        w["admin"].id,
        org_id=w["org"].id,
        group_id=w["group"].id,
        title="Project B",
        kind="exam",
    )
    for project, score in ((w["mine"], 0.4), (w["other"], 0.9)):
        task = (await make_tasks(db, project, 1, w["admin"].id))[0]
        await _graded_attempt(db, project, task, member, score=score)
    # The member also belongs to the group, so a group key acts for them.
    db.add(make_group_membership(member.id, w["group"].id, OrganizationRole.CONTRIBUTOR))
    await db.flush()
    return w


async def _personal(db, user, **extra):
    body = {"name": "k", "scopes": ["results:read"], **extra}
    return (await svc.create_personal_key(db, user.id, body))[1]


def _code(response):
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


@pytest.mark.parametrize("path", STUDENT_ROUTES)
async def test_project_restricted_key_is_refused(async_test_client, async_test_db, world, path):
    plain = await _personal(async_test_db, world["member"], project_ids=[world["mine"].id])
    r = await async_test_client.get(path, headers=bearer(plain))
    assert r.status_code == 403, r.text
    assert _code(r) == "key_project_restricted"
    assert "Project B" not in r.text


async def test_restricted_key_cannot_read_other_projects_scores(
    async_test_client, async_test_db, world
):
    """The reported leak: a key limited to project A listed the project ids,
    titles and scores of every other graded project of its user."""
    plain = await _personal(async_test_db, world["member"], project_ids=[world["mine"].id])
    r = await async_test_client.get(
        "/api/student/score-history", params={"scope": "all"}, headers=bearer(plain)
    )
    assert r.status_code == 403, r.text
    assert world["other"].id not in r.text and "Project B" not in r.text


@pytest.mark.parametrize("path", STUDENT_ROUTES)
async def test_group_key_is_refused(async_test_client, async_test_db, world, path):
    body = {
        "name": "g",
        "org_role": "CONTRIBUTOR",
        "scopes": ["results:read"],
        "group_id": world["group"].id,
    }
    _, plain = await svc.create_org_key(async_test_db, world["admin"].id, world["org"].id, body)
    r = await async_test_client.get(path, headers=bearer(plain))
    assert r.status_code == 403, r.text
    assert _code(r) == "key_project_restricted"


async def test_unrestricted_key_reads_every_project(async_test_client, async_test_db, world):
    plain = await _personal(async_test_db, world["member"])
    c = async_test_client
    r = await c.get("/api/student/score-history", params={"scope": "all"}, headers=bearer(plain))
    assert r.status_code == 200, r.text
    assert {p["project_id"] for p in r.json()} == {world["mine"].id, world["other"].id}
    r = await c.get("/api/student/retention", headers=bearer(plain))
    assert r.status_code == 200, r.text
    assert sum(day["reviews"] for day in r.json()) == 2
    r = await c.get("/api/student/activity", headers=bearer(plain))
    assert r.status_code == 200, r.text
    assert {e["project_id"] for e in r.json()["exams"]} == {world["mine"].id, world["other"].id}


@pytest.mark.parametrize("path", STUDENT_ROUTES)
async def test_unrestricted_key_still_needs_results_read(
    async_test_client, async_test_db, world, path
):
    plain = (
        await svc.create_personal_key(
            async_test_db, world["member"].id, {"name": "k", "scopes": ["account:read"]}
        )
    )[1]
    r = await async_test_client.get(path, headers=bearer(plain))
    assert r.status_code == 403, r.text
    assert _code(r) == "insufficient_scope"


async def test_restricted_key_keeps_account_routes(async_test_client, async_test_db, world):
    """Neutral account routes stay open to the restricted key."""
    plain = await _personal(async_test_db, world["member"], project_ids=[world["mine"].id])
    r = await async_test_client.get("/api/access-keys/scopes", headers=bearer(plain))
    assert r.status_code == 200, r.text


async def test_session_user_reads_every_project(async_test_client, async_test_db, world):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    member = world["member"]
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id=member.id,
        username=member.username,
        email=member.email,
        name=member.name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    try:
        r = await async_test_client.get("/api/student/score-history", params={"scope": "all"})
    finally:
        app.dependency_overrides.pop(require_user, None)
    assert r.status_code == 200, r.text
    assert {p["project_id"] for p in r.json()} == {world["mine"].id, world["other"].id}
