"""GET /api/dashboard/stats: the personal view of users who only answer tasks.

The dashboard summed every project the user reaches through any of their
organizations, so a student (ANNOTATOR) of an organization saw the totals of
every course of that organization, an annotation count made of everyone
else's answers, and the teachers' generation and evaluation counts. Users
without an ORG_ADMIN or CONTRIBUTOR membership (the rule that also hides the
teacher quick actions) now get ``scope: "personal"`` with their own counters
only; teachers and admins keep the overview.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from models import EvaluationJudgeRun, EvaluationRun, OrganizationRole, TaskEvaluation
from project_models import (
    Annotation,
    ProjectShareLink,
    ProjectShareMember,
    Task,
    TaskAssignment,
)
from tests.integration.test_group_visibility import (
    _as_user,
    _attach,
    _org,
    _project,
    _user,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/api/dashboard/stats"
OVERVIEW_KEYS = {
    "project_count",
    "task_count",
    "annotation_count",
    "projects_with_generations",
    "projects_with_evaluations",
}
PERSONAL_KEYS = {"open_exams", "open_tasks", "submitted_answers", "released_results"}
NOW = datetime.now(timezone.utc)


async def _tasks(db, project):
    return (
        (await db.execute(select(Task).where(Task.project_id == project.id).order_by(Task.inner_id)))
        .scalars()
        .all()
    )


async def _answer(db, task, user, *, result=None, cancelled=False):
    a = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=task.project_id,
        completed_by=user.id,
        result=[{"value": {"text": ["Antwort"]}}] if result is None else result,
        was_cancelled=cancelled,
    )
    db.add(a)
    await db.commit()
    return a


async def _grade(db, annotation, model_id, metrics):
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=annotation.project_id,
        model_id=model_id,
        evaluation_type_ids=[],
        metrics={},
        created_by=annotation.completed_by,
    )
    db.add(run)
    await db.flush()
    judge = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id="judge")
    db.add(judge)
    await db.flush()
    db.add(
        TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            judge_run_id=judge.id,
            task_id=annotation.task_id,
            annotation_id=annotation.id,
            field_name="loesung",
            answer_type="long_text",
            ground_truth="...",
            prediction="...",
            metrics=metrics,
            passed=True,
        )
    )
    await db.commit()


def _score(value, **details):
    return {"falloesung": {"value": value, "details": details}}


async def _stats(client, user):
    with _as_user(user):
        r = await client.get(URL)
    assert r.status_code == 200, r.text
    return r.json()


async def _school(db):
    """One organization with two courses of two teachers and two students.

    ``course`` (2 tasks) and ``other_course`` (3 tasks, one answered by the
    classmate) are ordinary org projects every member lists. Both keep the
    default of one answer per task, so the classmate's answer leaves two
    tasks of ``other_course`` to the student.
    """
    teacher, other_teacher, student, classmate = [await _user(db) for _ in range(4)]
    org = await _org(
        db,
        (teacher, OrganizationRole.CONTRIBUTOR),
        (other_teacher, OrganizationRole.CONTRIBUTOR),
        (student, OrganizationRole.ANNOTATOR),
        (classmate, OrganizationRole.ANNOTATOR),
    )
    course = await _project(db, teacher, tasks=2)
    other_course = await _project(db, other_teacher, tasks=3)
    await _attach(db, course, org, teacher)
    await _attach(db, other_course, org, other_teacher)
    await _answer(db, (await _tasks(db, other_course))[0], classmate)
    return {
        "org": org, "teacher": teacher, "other_teacher": other_teacher,
        "student": student, "classmate": classmate,
        "course": course, "other_course": other_course,
    }


async def test_a_student_gets_no_org_wide_counts(async_test_client, async_test_db):
    """Regression: the student was served the organization's totals
    (2 projects, 5 tasks, the classmate's annotation)."""
    w = await _school(async_test_db)

    stats = await _stats(async_test_client, w["student"])

    assert stats["scope"] == "personal"
    assert not OVERVIEW_KEYS & stats.keys()
    # Their own counters: the four tasks they can still answer, nothing
    # submitted.
    assert stats == {
        "scope": "personal",
        "open_exams": 0,
        "open_tasks": 4,
        "submitted_answers": 0,
        "released_results": 0,
    }


async def test_a_teacher_keeps_the_overview(async_test_client, async_test_db):
    w = await _school(async_test_db)

    stats = await _stats(async_test_client, w["teacher"])

    assert stats["scope"] == "overview"
    assert OVERVIEW_KEYS <= stats.keys() and not PERSONAL_KEYS & stats.keys()
    assert stats["project_count"] == 2
    assert stats["task_count"] == 5
    assert stats["annotation_count"] == 1


@pytest.mark.parametrize("role", [OrganizationRole.CONTRIBUTOR, OrganizationRole.ORG_ADMIN])
async def test_staff_in_any_org_keeps_the_overview(async_test_client, async_test_db, role):
    w = await _school(async_test_db)
    await _org(async_test_db, (w["student"], role))

    assert (await _stats(async_test_client, w["student"]))["scope"] == "overview"


async def test_a_superadmin_keeps_the_overview(async_test_client, async_test_db):
    admin = await _user(async_test_db, superadmin=True)

    assert (await _stats(async_test_client, admin))["scope"] == "overview"


async def test_a_user_without_an_organization_gets_the_personal_view(
    async_test_client, async_test_db
):
    """No membership is no teacher role (the quick actions are hidden too):
    e.g. a student who joined by share link. Public projects of others are
    not summed up for them either."""
    db = async_test_db
    loner, stranger = await _user(db), await _user(db)
    public = await _project(db, stranger, tasks=2)
    public.is_public, public.public_role = True, "ANNOTATOR"
    await db.commit()
    await _answer(db, (await _tasks(db, public))[0], stranger)

    stats = await _stats(async_test_client, loner)

    assert stats["scope"] == "personal"
    assert not OVERVIEW_KEYS & stats.keys()
    assert stats["submitted_answers"] == 0


async def test_an_inactive_staff_membership_does_not_keep_the_overview(
    async_test_client, async_test_db
):
    from models import OrganizationMembership

    db = async_test_db
    w = await _school(db)
    former = await _org(db, (w["student"], OrganizationRole.CONTRIBUTOR))
    membership = (
        await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == former.id
            )
        )
    ).scalar_one()
    membership.is_active = False
    await db.commit()

    assert (await _stats(async_test_client, w["student"]))["scope"] == "personal"


async def test_submitted_answers_count_only_own_submitted_answers(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _school(db)
    t1, t2 = await _tasks(db, w["course"])
    await _answer(db, t1, w["student"])
    await _answer(db, t2, w["student"], cancelled=True)
    await _answer(db, t2, w["student"], result=[])  # a draft-only row

    stats = await _stats(async_test_client, w["student"])

    assert stats["submitted_answers"] == 1
    # t1 is answered; t2 is still open (cancelled and empty rows are no
    # answer), as are two tasks of the other course.
    assert stats["open_tasks"] == 1 + 2


async def test_open_exams_follow_the_participant_tier_and_the_window(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _school(db)
    teacher, student = w["teacher"], w["student"]

    running = await _project(db, teacher, kind="exam", tasks=2)
    closed = await _project(db, teacher, kind="exam", tasks=1)
    closed.window_start_at, closed.window_end_at = NOW - timedelta(days=2), NOW - timedelta(days=1)
    upcoming = await _project(db, teacher, kind="exam", tasks=1)
    upcoming.window_start_at = NOW + timedelta(days=1)
    done = await _project(db, teacher, kind="exam", tasks=1)
    for exam in (running, closed, upcoming, done):
        await _attach(db, exam, w["org"], teacher)
    await db.commit()
    await _answer(db, (await _tasks(db, done))[0], student)
    # An exam of another organization is none of the student's business.
    foreign = await _project(db, w["other_teacher"], kind="exam", tasks=4)
    await _attach(db, foreign, await _org(db, (w["other_teacher"], OrganizationRole.ORG_ADMIN)),
                  w["other_teacher"])

    stats = await _stats(async_test_client, student)

    # Only the running exam is open, with its two tasks (plus the four open
    # tasks of the two ordinary courses); the closed, the upcoming and the
    # answered exam are not, nor is the foreign one.
    assert stats["open_exams"] == 1
    assert stats["open_tasks"] == 2 + 4
    assert stats["submitted_answers"] == 1


async def test_a_shared_exam_counts_as_open(async_test_client, async_test_db):
    db = async_test_db
    owner, student = await _user(db), await _user(db)
    exam = await _project(db, owner, private=True, kind="exam", tasks=3)
    link = ProjectShareLink(
        id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=exam.id,
        created_by=owner.id, password_hash="x",
    )
    db.add(link)
    await db.flush()
    db.add(ProjectShareMember(
        id=str(uuid.uuid4()), share_link_id=link.id, project_id=exam.id,
        user_id=student.id, gdpr_consent_at=NOW,
    ))
    await db.commit()

    stats = await _stats(async_test_client, student)

    assert (stats["open_exams"], stats["open_tasks"]) == (1, 3)


async def test_assignment_projects_count_only_own_open_assignments(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _school(db)
    course = w["course"]
    course.assignment_mode = "manual"
    await db.commit()
    t1, t2 = await _tasks(db, course)
    db.add(TaskAssignment(
        id=str(uuid.uuid4()), task_id=t1.id, user_id=w["student"].id,
        assigned_by=w["teacher"].id, status="assigned",
    ))
    db.add(TaskAssignment(
        id=str(uuid.uuid4()), task_id=t2.id, user_id=w["classmate"].id,
        assigned_by=w["teacher"].id, status="assigned",
    ))
    await db.commit()

    stats = await _stats(async_test_client, w["student"])

    # t1 of the course (assigned to them) + the two open tasks of the other
    # course.
    assert stats["open_tasks"] == 1 + 2


async def test_tasks_filled_up_by_others_are_not_open(async_test_client, async_test_db):
    db = async_test_db
    w = await _school(db)

    # The first task of other_course holds the classmate's answer, and the
    # project takes one answer per task: the student cannot answer it.
    assert (await _stats(async_test_client, w["student"]))["open_tasks"] == 2 + 2

    w["other_course"].maximum_annotations = 0  # unlimited answers per task
    await db.commit()
    assert (await _stats(async_test_client, w["student"]))["open_tasks"] == 2 + 3


async def test_released_results_count_only_what_the_student_sees(
    async_test_client, async_test_db
):
    db = async_test_db
    w = await _school(db)
    student = w["student"]
    t1, t2 = await _tasks(db, w["course"])
    o1, o2, o3 = await _tasks(db, w["other_course"])
    w["other_course"].maximum_annotations = 0
    await db.commit()
    graded_ki = await _answer(db, t1, student)
    graded_human = await _answer(db, t2, student)
    batch_only = await _answer(db, o1, student)
    draft_feedback = await _answer(db, o2, student)
    released_feedback = await _answer(db, o3, student)

    await _grade(db, graded_ki, "immediate", _score(0.7))
    await _grade(db, graded_ki, "human", _score(0.8))  # same answer: counted once
    await _grade(db, graded_human, "human", _score(0.5))
    await _grade(db, batch_only, "gpt-5", _score(0.9))  # a teacher's research run
    await _grade(db, draft_feedback, "immediate",
                 _score(0.6, feedback_only=True, review={"status": "draft"}))
    await _grade(db, released_feedback, "immediate",
                 _score(0.6, feedback_only=True, review={"status": "released"}))
    # A classmate's graded answer is not the student's result.
    await _grade(db, await _answer(db, t1, w["classmate"]), "immediate", _score(1.0))

    stats = await _stats(async_test_client, student)

    assert stats["submitted_answers"] == 5
    assert stats["released_results"] == 3


async def test_the_cache_key_carries_the_view(async_test_client, async_test_db):
    db = async_test_db
    w = await _school(db)
    with patch("routers.dashboard.cache") as cache:
        cache.get.return_value = None
        await _stats(async_test_client, w["student"])
        await _org(db, (w["student"], OrganizationRole.CONTRIBUTOR))
        promoted = await _stats(async_test_client, w["student"])

    keys = [c.args[0] for c in cache.get.call_args_list]
    assert keys == [
        f"dashboard_stats:v5:{w['student'].id}:personal",
        f"dashboard_stats:v5:{w['student'].id}:overview",
    ]
    assert promoted["scope"] == "overview"
    # The personal view is cached for a minute, the overview for five.
    assert [c.kwargs["ttl"] for c in cache.set.call_args_list] == [60, 300]
