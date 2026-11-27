"""Project questionnaires: settings, the three moments, answers, CSV.

Real rows through ``async_test_db`` and ``async_test_client``; only the
access helpers (not under test here) are patched: the caller's tier
(``full``, ``participant``, ``attempted``), whether they may edit the project,
and the task assignment check.
"""

import csv
import io
import uuid
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
from project_models import (
    Annotation,
    Project,
    ProjectQuestionnaire,
    ProjectQuestionnaireVersion,
    QuestionnaireResponse,
    Task,
)

BEFORE = (
    '<View><Header value="Vorab"/>'
    '<Likert name="motivation" toName="motivation" min="1" max="7" required="true" '
    'label="Ich bin motiviert."/>'
    '<TextArea name="note" toName="note"/></View>'
)
AFTER = (
    '<View><Rating name="confidence" toName="confidence" maxRating="5" required="true" '
    'label="Wie sicher bist du?"/></View>'
)
GRADER = (
    '<View><Choices name="effort" toName="effort" choice="single" required="true">'
    '<Choice value="gering"/><Choice value="hoch"/></Choices></View>'
)

MOTIVATION = [{"from_name": "motivation", "to_name": "motivation", "type": "likert", "value": 5}]
CONFIDENCE = [{"from_name": "confidence", "to_name": "confidence", "type": "rating", "value": 4}]
EFFORT = [{"from_name": "effort", "to_name": "effort", "type": "choices",
           "value": {"choices": ["hoch"]}}]


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as(db_user: User, *, tier="full", can_edit=False, assigned=True):
    auth_user = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email, name=db_user.name,
        is_superadmin=False, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    edit = AsyncMock(return_value=can_edit)
    with ExitStack() as stack:
        stack.enter_context(patch(
            "routers.projects.deps.get_project_access_tier_async",
            new=AsyncMock(return_value=tier),
        ))
        stack.enter_context(patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ))
        stack.enter_context(patch("routers.projects.deps.check_user_can_edit_project_async", new=edit))
        stack.enter_context(patch("routers.projects.questionnaire.check_user_can_edit_project_async", new=edit))
        stack.enter_context(patch("routers.projects.helpers.check_user_can_edit_project_async", new=edit))
        stack.enter_context(patch(
            "routers.projects.questionnaire.check_task_assigned_to_user_async",
            new=AsyncMock(return_value=assigned),
        ))
        try:
            yield auth_user
        finally:
            app.dependency_overrides.pop(require_user, None)


async def _user(db, name="Q"):
    u = User(
        id=_uid(), username=f"q-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com", name=name,
        is_superadmin=False, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _world(db):
    owner = await _user(db, "Owner")
    student = await _user(db, "Student")
    grader = await _user(db, "Grader")
    project = Project(id=_uid(), title="Questionnaires", created_by=owner.id)
    db.add(project)
    await db.flush()
    tasks = []
    for i in range(2):
        t = Task(id=_uid(), project_id=project.id, data={"text": f"t{i}"}, inner_id=i + 1)
        db.add(t)
        tasks.append(t)
    await db.flush()
    annotation = Annotation(
        id=_uid(), task_id=tasks[0].id, project_id=project.id, completed_by=student.id, result=[]
    )
    db.add(annotation)
    await db.flush()
    await db.commit()
    return dict(owner=owner, student=student, grader=grader, project=project,
                tasks=tasks, annotation=annotation, pid=project.id)


async def _grade(db, w, *, by):
    run = EvaluationRun(
        id=_uid(), project_id=w["project"].id, model_id="human", evaluation_type_ids=["korrektur"],
        status="completed", metrics={}, samples_evaluated=1,
        eval_metadata={"evaluation_type": "human"}, created_by=by.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    judge = EvaluationJudgeRun(id=_uid(), evaluation_id=run.id, judge_model_id=None,
                               run_index=0, status="completed")
    db.add(judge)
    await db.flush()
    te = TaskEvaluation(
        id=_uid(), evaluation_id=run.id, judge_run_id=judge.id, task_id=w["tasks"][0].id,
        annotation_id=w["annotation"].id, field_name="loesung", answer_type="text",
        metrics={"korrektur_falloesung": 12}, passed=True, ground_truth={}, prediction={},
        created_by=by.id,
    )
    db.add(te)
    await db.flush()
    await db.commit()
    return te


def _base(w):
    # The id string, not the row: a refused save rolls the session back and
    # expires the seeded objects.
    return f"/api/projects/{w['pid']}/questionnaires"


async def _save(client, w, trigger, **body):
    payload = {"enabled": True, "config": "", "required": True, **body}
    return await client.put(f"{_base(w)}/{trigger}", json=payload)


@pytest.mark.asyncio
class TestSettings:
    async def test_every_moment_is_listed_with_defaults_for_editors(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            resp = await async_test_client.get(_base(w))
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_edit"] is True
        by = {q["trigger"]: q for q in body["questionnaires"]}
        assert list(by) == ["before_task", "after_submit", "korrektur"]
        assert all(not q["enabled"] and q["version"] == 0 for q in by.values())
        assert by["before_task"]["allowed_frequencies"] == ["once_per_project", "once_per_task"]
        assert by["after_submit"]["frequency"] == "once_per_submission"
        assert by["korrektur"]["required"] is False

    async def test_invalid_xml_is_refused_with_the_errors(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            resp = await _save(async_test_client, w, "before_task",
                               config='<View><Ratng name="q" toName="q"/></View>')
            check = await async_test_client.post(
                f"{_base(w)}/validate", json={"config": "<View><Rating"}
            )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "questionnaire_config_invalid"
        assert detail["errors"] == ["Unsupported field type: 'Ratng'"]
        assert check.status_code == 200
        assert check.json()["valid"] is False
        assert check.json()["errors"][0].startswith("XML parsing failed")

    async def test_switching_on_needs_a_config(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            resp = await _save(async_test_client, w, "before_task", config="")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "questionnaire_config_missing"

    async def test_a_changed_text_is_a_new_version(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            first = await _save(async_test_client, w, "before_task", config=BEFORE)
            same = await _save(async_test_client, w, "before_task", config=BEFORE, required=False)
            edited = await _save(async_test_client, w, "before_task", config=BEFORE.replace("Vorab", "Vor dem Start"))
        assert first.status_code == 200, first.text
        assert first.json()["version"] == 1 and first.json()["active"] is True
        assert same.json()["version"] == 1 and same.json()["required"] is False
        assert edited.json()["version"] == 2
        versions = (await async_test_db.execute(
            select(ProjectQuestionnaireVersion.version, ProjectQuestionnaireVersion.config)
            .join(ProjectQuestionnaire,
                  ProjectQuestionnaireVersion.questionnaire_id == ProjectQuestionnaire.id)
            .where(ProjectQuestionnaire.project_id == w["pid"])
            .order_by(ProjectQuestionnaireVersion.version)
        )).all()
        assert [v for v, _ in versions] == [1, 2]
        assert versions[0][1] == BEFORE

    async def test_frequency_must_fit_the_moment(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            resp = await _save(async_test_client, w, "before_task", config=BEFORE,
                               frequency="once_per_submission")
            unknown = await _save(async_test_client, w, "on_signup", config=BEFORE)
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "questionnaire_frequency_invalid"
        assert unknown.status_code == 404

    async def test_non_editors_cannot_save(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["student"], can_edit=False):
            resp = await _save(async_test_client, w, "before_task", config=BEFORE)
        assert resp.status_code == 403

    async def test_after_submit_keeps_the_1208_fields_in_step(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            resp = await _save(async_test_client, w, "after_submit", config=AFTER)
        assert resp.status_code == 200
        await async_test_db.refresh(w["project"])
        assert w["project"].questionnaire_enabled is True
        assert w["project"].questionnaire_config == AFTER

    async def test_patch_of_the_1208_fields_writes_the_after_submit_questionnaire(
        self, async_test_client, async_test_db
    ):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True), patch(
            "routers.projects.crud.check_user_can_edit_project_async",
            new=AsyncMock(return_value=True),
        ):
            resp = await async_test_client.patch(
                f"/api/projects/{w['project'].id}",
                json={"questionnaire_enabled": True, "questionnaire_config": AFTER},
            )
            listed = await async_test_client.get(_base(w))
        assert resp.status_code == 200, resp.text
        after = next(q for q in listed.json()["questionnaires"] if q["trigger"] == "after_submit")
        assert after["enabled"] is True and after["config"] == AFTER and after["version"] == 1

    async def test_participants_see_only_active_moments_and_never_the_graders(
        self, async_test_client, async_test_db
    ):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
            await _save(async_test_client, w, "korrektur", config=GRADER)
        with _as(w["student"], tier="participant"):
            resp = await async_test_client.get(_base(w))
        assert [q["trigger"] for q in resp.json()["questionnaires"]] == ["before_task"]
        assert resp.json()["can_edit"] is False


@pytest.mark.asyncio
class TestBeforeTask:
    async def _status(self, client, w, task):
        return await client.get(f"{_base(w)}/before_task/status", params={"task_id": task.id})

    async def _answer(self, client, w, task, result=MOTIVATION, skipped=False):
        return await client.post(
            f"{_base(w)}/before_task/responses",
            json={"task_id": task.id, "result": result, "skipped": skipped},
        )

    async def test_once_per_project_is_asked_once(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        t0, t1 = w["tasks"]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="participant"):
            due = await self._status(async_test_client, w, t0)
            answered = await self._answer(async_test_client, w, t0)
            again = await self._answer(async_test_client, w, t1)
            later = await self._status(async_test_client, w, t1)
        assert due.json()["due"] is True
        assert due.json()["questionnaire"]["config"] == BEFORE
        assert answered.status_code == 200, answered.text
        row = answered.json()
        assert (row["trigger"], row["subject_key"], row["questionnaire_version"]) == (
            "before_task", "project", 1)
        assert row["task_id"] == t0.id and row["user_id"] == w["student"].id
        assert again.status_code == 409
        assert later.json() == {"due": False, "questionnaire": None}

    async def test_once_per_task_is_asked_for_every_task(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        t0, t1 = w["tasks"]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE, frequency="once_per_task")
        with _as(w["student"], tier="participant"):
            await self._answer(async_test_client, w, t0)
            first = await self._status(async_test_client, w, t0)
            second = await self._status(async_test_client, w, t1)
        assert first.json()["due"] is False
        assert second.json()["due"] is True

    async def test_required_questions_and_skips(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        t0 = w["tasks"][0]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="participant"):
            missing = await self._answer(async_test_client, w, t0, result=[])
            skip = await self._answer(async_test_client, w, t0, skipped=True)
        assert missing.status_code == 422
        assert missing.json()["detail"]["missing"] == ["Ich bin motiviert."]
        assert skip.status_code == 422
        assert skip.json()["detail"]["code"] == "questionnaire_required"

    async def test_an_optional_questionnaire_records_the_skip(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        t0 = w["tasks"][0]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE, required=False)
        with _as(w["student"], tier="participant"):
            skip = await self._answer(async_test_client, w, t0, result=MOTIVATION, skipped=True)
            due = await self._status(async_test_client, w, t0)
        assert skip.status_code == 200
        assert skip.json()["skipped"] is True and skip.json()["result"] == []
        assert due.json()["due"] is False

    async def test_an_answer_to_a_replaced_version_is_refused(self, async_test_client, async_test_db):
        """A student who rendered v1 while the editor saved v2 is told to
        reload instead of having the v1 answers stored as v2."""
        w = await _world(async_test_db)
        t0 = w["tasks"][0]
        edited = BEFORE.replace("Vorab", "Vor dem Start")
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="participant"):
            shown = (await self._status(async_test_client, w, t0)).json()["questionnaire"]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=edited)
        with _as(w["student"], tier="participant"):
            stale = await async_test_client.post(
                f"{_base(w)}/before_task/responses",
                json={"task_id": t0.id, "result": MOTIVATION,
                      "questionnaire_version": shown["version"]},
            )
            reloaded = (await self._status(async_test_client, w, t0)).json()["questionnaire"]
            current = await async_test_client.post(
                f"{_base(w)}/before_task/responses",
                json={"task_id": t0.id, "result": MOTIVATION,
                      "questionnaire_version": reloaded["version"]},
            )
        assert shown["version"] == 1
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "questionnaire_version_changed"
        assert stale.json()["detail"]["current_version"] == 2
        assert reloaded["config"] == edited
        assert current.status_code == 200, current.text
        assert current.json()["questionnaire_version"] == 2

    async def test_switched_off_is_never_due(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE, enabled=False)
        with _as(w["student"], tier="participant"):
            due = await self._status(async_test_client, w, w["tasks"][0])
            answer = await self._answer(async_test_client, w, w["tasks"][0])
        assert due.json()["due"] is False
        assert answer.status_code == 400

    async def test_read_only_access_owes_nothing_and_cannot_answer(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="attempted"):
            due = await self._status(async_test_client, w, w["tasks"][0])
            answer = await self._answer(async_test_client, w, w["tasks"][0])
        assert due.json()["due"] is False
        assert answer.status_code == 403

    async def test_an_unassigned_task_is_not_found(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="participant", assigned=False):
            answer = await self._answer(async_test_client, w, w["tasks"][0])
        assert answer.status_code == 404


def test_timer_helper_reports_the_pending_questionnaire(test_db):
    """``before_task_questionnaire_pending`` (sync, for the overlay's timer
    routes) holds until the moment's answer exists."""
    from services.questionnaire_service import before_task_questionnaire_pending
    from tests.fixtures.questionnaires import questionnaire

    owner = User(id=_uid(), username=f"q-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
                 name="Owner", is_active=True, email_verified=True)
    test_db.add(owner)
    test_db.flush()
    project = Project(id=_uid(), title="Timer", created_by=owner.id)
    test_db.add(project)
    test_db.flush()
    t0 = Task(id=_uid(), project_id=project.id, data={}, inner_id=1)
    t1 = Task(id=_uid(), project_id=project.id, data={}, inner_id=2)
    test_db.add_all([t0, t1])
    test_db.flush()

    assert before_task_questionnaire_pending(test_db, project.id, owner.id, t0.id) is False
    q = questionnaire(test_db, project.id, "before_task", config=BEFORE,
                      frequency="once_per_task", version=1)
    assert before_task_questionnaire_pending(test_db, project.id, owner.id, t0.id) is True
    q.enabled = False
    test_db.flush()
    assert before_task_questionnaire_pending(test_db, project.id, owner.id, t0.id) is False
    q.enabled = True
    test_db.add(QuestionnaireResponse(
        id=_uid(), project_id=project.id, questionnaire_id=q.id, trigger="before_task",
        user_id=owner.id, task_id=t0.id, subject_key=f"task:{t0.id}", result=MOTIVATION,
    ))
    test_db.flush()
    assert before_task_questionnaire_pending(test_db, project.id, owner.id, t0.id) is False
    assert before_task_questionnaire_pending(test_db, project.id, owner.id, t1.id) is True


@pytest.mark.asyncio
class TestAfterSubmit:
    async def test_answered_once_per_submission(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        ann = w["annotation"]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "after_submit", config=AFTER)
        with _as(w["student"], tier="participant"):
            due = await async_test_client.get(
                f"{_base(w)}/after_submit/status", params={"annotation_id": ann.id})
            answer = await async_test_client.post(
                f"{_base(w)}/after_submit/responses",
                json={"annotation_id": ann.id, "result": CONFIDENCE})
            legacy = await async_test_client.post(
                f"/api/projects/{w['project'].id}/tasks/{ann.task_id}/questionnaire-response",
                json={"annotation_id": ann.id, "result": CONFIDENCE})
        assert due.json()["due"] is True
        assert answer.status_code == 200, answer.text
        assert answer.json()["subject_key"] == f"annotation:{ann.id}"
        assert answer.json()["task_id"] == ann.task_id
        # The #1208 route sees the same answer.
        assert legacy.status_code == 400
        assert "already submitted" in legacy.json()["detail"]

    async def test_only_the_own_submission(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "after_submit", config=AFTER)
        with _as(w["grader"], tier="participant"):
            resp = await async_test_client.post(
                f"{_base(w)}/after_submit/responses",
                json={"annotation_id": w["annotation"].id, "result": CONFIDENCE})
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestKorrektur:
    async def test_the_grader_answers_after_saving_the_grade(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        te = await _grade(async_test_db, w, by=w["grader"])
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "korrektur", config=GRADER)
        with _as(w["grader"]):
            due = await async_test_client.get(
                f"{_base(w)}/korrektur/status", params={"task_evaluation_id": te.id})
            answer = await async_test_client.post(
                f"{_base(w)}/korrektur/responses",
                json={"task_evaluation_id": te.id, "result": EFFORT})
            after = await async_test_client.get(
                f"{_base(w)}/korrektur/status", params={"task_evaluation_id": te.id})
        assert due.json()["due"] is True
        assert answer.status_code == 200, answer.text
        row = answer.json()
        # The grader's answer, linked to the grade row and the graded submission.
        assert row["user_id"] == w["grader"].id
        assert row["task_evaluation_id"] == te.id
        assert row["annotation_id"] == w["annotation"].id
        assert row["subject_key"] == f"annotation:{w['annotation'].id}"
        assert after.json()["due"] is False

    async def test_nobody_else_answers_for_the_grader(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        te = await _grade(async_test_db, w, by=w["grader"])
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "korrektur", config=GRADER)
            other = await async_test_client.post(
                f"{_base(w)}/korrektur/responses",
                json={"task_evaluation_id": te.id, "result": EFFORT})
        with _as(w["student"], tier="participant"):
            student = await async_test_client.post(
                f"{_base(w)}/korrektur/responses",
                json={"task_evaluation_id": te.id, "result": EFFORT})
        assert other.status_code == 403
        assert other.json()["detail"]["code"] == "questionnaire_not_grader"
        assert student.status_code == 403

    async def test_an_unknown_grade_is_not_found(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "korrektur", config=GRADER)
        with _as(w["grader"]):
            resp = await async_test_client.post(
                f"{_base(w)}/korrektur/responses",
                json={"task_evaluation_id": _uid(), "result": EFFORT})
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestReading:
    async def _fill(self, client, db, w):
        te = await _grade(db, w, by=w["grader"])
        with _as(w["owner"], can_edit=True):
            await _save(client, w, "before_task", config=BEFORE)
            await _save(client, w, "after_submit", config=AFTER)
            await _save(client, w, "korrektur", config=GRADER)
        with _as(w["student"], tier="participant"):
            await client.post(f"{_base(w)}/before_task/responses",
                              json={"task_id": w["tasks"][0].id, "result": MOTIVATION})
            await client.post(f"{_base(w)}/after_submit/responses",
                              json={"annotation_id": w["annotation"].id, "result": CONFIDENCE})
        with _as(w["grader"]):
            await client.post(f"{_base(w)}/korrektur/responses",
                              json={"task_evaluation_id": te.id, "result": EFFORT})

    async def test_list_defaults_to_the_after_submit_answers(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        await self._fill(async_test_client, async_test_db, w)
        url = f"/api/projects/{w['project'].id}/questionnaire-responses"
        with _as(w["owner"], can_edit=True):
            default = await async_test_client.get(url)
            everything = await async_test_client.get(url, params={"trigger": "all"})
            grader = await async_test_client.get(url, params={"trigger": "korrektur"})
        assert [r["trigger"] for r in default.json()] == ["after_submit"]
        assert default.json()[0]["annotation_id"] == w["annotation"].id
        assert sorted(r["trigger"] for r in everything.json()) == [
            "after_submit", "before_task", "korrektur"]
        assert [r["user_id"] for r in grader.json()] == [w["grader"].id]

    async def test_wide_csv(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        await self._fill(async_test_client, async_test_db, w)
        url = f"/api/projects/{w['project'].id}/questionnaire-responses/export.csv"
        with _as(w["owner"], can_edit=True):
            one = await async_test_client.get(url, params={"trigger": "korrektur"})
            every = await async_test_client.get(url)
        assert one.status_code == 200
        assert one.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(one.text)))
        assert len(rows) == 1
        assert rows[0]["effort"] == "hoch"
        assert rows[0]["trigger"] == "korrektur"
        assert rows[0]["questionnaire_version"] == "1"
        rows = list(csv.DictReader(io.StringIO(every.text)))
        assert {r["trigger"] for r in rows} == {"before_task", "after_submit", "korrektur"}
        header = next(csv.reader(io.StringIO(every.text)))
        assert {"before_task.motivation", "after_submit.confidence", "korrektur.effort"} <= set(header)
        by = {r["trigger"]: r for r in rows}
        assert by["before_task"]["before_task.motivation"] == "5"
        assert by["after_submit"]["after_submit.confidence"] == "4"

    async def test_wide_csv_cells_never_run_as_formulas(self, async_test_client, async_test_db):
        """Free text a participant typed (and the question names in the
        answer they sent) reach the CSV as text, not as spreadsheet
        formulas (OWASP CSV injection: = + - @ tab CR start a formula)."""
        w = await _world(async_test_db)
        payload = '=HYPERLINK("http://x","klick")'
        result = [
            *MOTIVATION,
            {"from_name": "note", "to_name": "note", "type": "textarea",
             "value": {"text": [payload]}},
            {"from_name": "@evil", "to_name": "@evil", "type": "textarea",
             "value": {"text": ["+1"]}},
        ]
        with _as(w["owner"], can_edit=True):
            await _save(async_test_client, w, "before_task", config=BEFORE)
        with _as(w["student"], tier="participant"):
            answered = await async_test_client.post(
                f"{_base(w)}/before_task/responses",
                json={"task_id": w["tasks"][0].id, "result": result})
        url = f"/api/projects/{w['project'].id}/questionnaire-responses/export.csv"
        with _as(w["owner"], can_edit=True):
            one = await async_test_client.get(url, params={"trigger": "before_task"})
        assert answered.status_code == 200, answered.text
        header = next(csv.reader(io.StringIO(one.text)))
        assert "'@evil" in header and "@evil" not in header
        row = next(csv.DictReader(io.StringIO(one.text)))
        assert row["note"] == "'" + payload
        assert row["'@evil"] == "'+1"
        assert row["motivation"] == "5"

    async def test_only_editors_read_answers(self, async_test_client, async_test_db):
        w = await _world(async_test_db)
        with _as(w["student"], tier="participant", can_edit=False):
            resp = await async_test_client.get(
                f"/api/projects/{w['project'].id}/questionnaire-responses")
            csv_resp = await async_test_client.get(
                f"/api/projects/{w['project'].id}/questionnaire-responses/export.csv")
        assert resp.status_code == 403
        assert csv_resp.status_code == 403


@pytest.mark.asyncio
async def test_legacy_columns_without_a_row_still_work(async_test_client, async_test_db):
    """A project whose #1208 columns were written past the API (no
    after_submit row) is read through them and gets its row on first use."""
    w = await _world(async_test_db)
    w["project"].questionnaire_enabled = True
    w["project"].questionnaire_config = AFTER
    await async_test_db.commit()
    with _as(w["student"], tier="participant"):
        due = await async_test_client.get(
            f"{_base(w)}/after_submit/status", params={"annotation_id": w["annotation"].id})
    assert due.json()["due"] is True
    rows = (await async_test_db.execute(
        select(ProjectQuestionnaire).where(ProjectQuestionnaire.project_id == w["project"].id)
    )).scalars().all()
    assert [(r.trigger, r.version, r.config) for r in rows] == [("after_submit", 1, AFTER)]
    assert (await async_test_db.execute(select(QuestionnaireResponse))).scalars().all() == []
