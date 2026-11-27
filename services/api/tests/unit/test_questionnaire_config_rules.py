"""Post-annotation questionnaire rules (Issue #1208).

- ``<Likert>`` is a supported label-config tag (the frontend renders it, the
  validator used to reject it, so the shipped UTAUT template could not be
  validated).
- ``questionnaire_config`` is validated when a project is saved.
- ``required="true"`` questions must be answered to submit a response.
- Each response records the SHA-256 of the config it answered.
- One response per annotation is held by a unique index.
"""

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, PostAnnotationResponse, Project, Task
from services.label_config.questionnaire import (
    missing_required_answers,
    questionnaire_config_hash,
    required_questions,
    validate_questionnaire_config,
)
from services.label_config.validator import LabelConfigValidator

# The three templates the project settings offer, copied verbatim from
# QUESTIONNAIRE_TEMPLATES in frontend/src/components/projects/AdvancedSettingsCard.tsx.
CONFIDENCE_TEMPLATE = """<View>
  <Header value="Post-Annotation Feedback"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true" label="How confident are you in your annotation?"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true" label="How difficult was this task?"/>
</View>"""

EXTENDED_TEMPLATE = """<View>
  <Header value="Post-Annotation Feedback"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true" label="How confident are you in your annotation?"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true" label="How difficult was this task?"/>
  <Choices name="guideline_clarity" toName="guideline_clarity" choice="single" layout="horizontal" required="true" label="How clear were the annotation guidelines?">
    <Choice value="Very Clear"/>
    <Choice value="Clear"/>
    <Choice value="Neutral"/>
    <Choice value="Unclear"/>
    <Choice value="Very Unclear"/>
  </Choices>
  <TextArea name="comments" toName="comments" rows="3" label="Additional comments (optional)" placeholder="Note any edge cases, ambiguities, or concerns..."/>
</View>"""

UTAUT_TEMPLATE = """<View>
  <Header value="Post-Annotations-Fragebogen" level="3"/>

  <Header value="Allgemeine Fragen" level="4"/>
  <Likert name="difficulty" toName="difficulty" min="1" max="7" required="true" label="Es fiel mir leicht die Aufgabe zu lösen."/>
  <Likert name="responsibility" toName="responsibility" min="1" max="7" required="true" label="Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis."/>

  <Header value="Fragen zur KI-Unterstützung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Likert name="ai_adequate" toName="ai_adequate" min="1" max="7" label="Der Output der KI war auf Anhieb adäquat."/>
  <Likert name="ai_reviewed" toName="ai_reviewed" min="1" max="7" label="Ich habe den Output der KI überprüft."/>
  <Likert name="utaut_pe" toName="utaut_pe" min="1" max="7" label="Ich würde die KI in meiner Arbeit/meinem Studium als nützlich empfinden."/>
  <Likert name="utaut_ee" toName="utaut_ee" min="1" max="7" label="Ich empfinde die KI als einfach zu nutzen."/>
  <Likert name="utaut_att1" toName="utaut_att1" min="1" max="7" label="Die Nutzung der KI ist eine gute Idee."/>
  <Likert name="utaut_att2" toName="utaut_att2" min="1" max="7" label="Die Arbeit mit der KI macht Spaß."/>
  <Likert name="utaut_att3" toName="utaut_att3" min="1" max="7" label="Ich arbeite gerne mit der KI."/>

  <Header value="Anteil an der Fallbearbeitung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Number name="human_share" toName="human_share" min="0" max="100" label="x Prozent der Fallbearbeitung gehen auf mich zurück." hint="Wert zwischen 0 und 100"/>
  <Number name="ai_share" toName="ai_share" min="0" max="100" label="y Prozent der Fallbearbeitung gehen auf die KI zurück." hint="Wert zwischen 0 und 100"/>

  <Header value="Frage ohne KI (nur beantworten, wenn du NICHT in der KI-Gruppe warst)" level="4"/>
  <Likert name="desired_ai" toName="desired_ai" min="1" max="7" label="Ich hätte mir die KI für die Bearbeitung dieser Aufgabe gewünscht."/>
</View>"""


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


class TestValidator:
    def test_likert_is_a_supported_named_tag(self):
        ok, errors = LabelConfigValidator.validate(
            '<View><Likert name="q" toName="q" min="1" max="7"/></View>'
        )
        assert ok, errors
        ok, errors = LabelConfigValidator.validate('<View><Likert toName="q"/></View>')
        assert not ok
        assert "Field type 'Likert' requires a 'name' attribute" in errors

    @pytest.mark.parametrize(
        "template", [CONFIDENCE_TEMPLATE, EXTENDED_TEMPLATE, UTAUT_TEMPLATE]
    )
    def test_shipped_templates_validate(self, template):
        assert validate_questionnaire_config(template) == (True, [])

    def test_questionnaire_without_question_rejected(self):
        ok, errors = validate_questionnaire_config('<View><Header value="Hi"/></View>')
        assert not ok
        assert "has no question" in errors[0]

    @pytest.mark.parametrize(
        "tag", ["Checkbox", "Radio", "DateTime", "Taxonomy", "Ranker", "Pairwise"]
    )
    def test_tag_the_modal_cannot_render_is_no_question(self, tag):
        config = f'<View><{tag} name="q" toName="q"/></View>'
        assert LabelConfigValidator.validate(config)[0]
        ok, errors = validate_questionnaire_config(config)
        assert not ok
        assert "has no question" in errors[0]

    def test_label_config_errors_pass_through(self):
        ok, errors = validate_questionnaire_config('<View><Bogus name="x"/></View>')
        assert not ok
        assert "Unsupported field type: 'Bogus'" in errors


class TestRequiredQuestions:
    def test_lists_required_answer_fields_with_labels(self):
        assert required_questions(UTAUT_TEMPLATE) == [
            ("difficulty", "Es fiel mir leicht die Aufgabe zu lösen."),
            (
                "responsibility",
                "Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis.",
            ),
        ]

    def test_required_on_object_tag_is_not_a_question(self):
        config = (
            '<View><Text name="t" value="$text" required="true"/>'
            '<TextArea name="a" toName="t" required="true"/></View>'
        )
        assert required_questions(config) == [("a", "a")]

    def test_required_tag_the_modal_cannot_render_is_not_demanded(self):
        config = (
            '<View><Rating name="r" toName="r"/>'
            '<DateTime name="d" toName="d" required="true"/></View>'
        )
        assert required_questions(config) == []
        assert missing_required_answers(config, []) == []

    def test_empty_or_broken_config_has_no_required_questions(self):
        assert required_questions(None) == []
        assert required_questions("") == []
        assert required_questions("<View>") == []

    def test_missing_answers(self):
        result = [
            {"from_name": "confidence", "type": "rating", "value": {"rating": 4}},
            {"from_name": "comments", "type": "textarea", "value": {"text": ["ok"]}},
        ]
        assert missing_required_answers(EXTENDED_TEMPLATE, result) == [
            "How difficult was this task?",
            "How clear were the annotation guidelines?",
        ]

    @pytest.mark.parametrize(
        "entry",
        [
            {"from_name": "q", "type": "rating", "value": {"rating": 0}},
            {"from_name": "q", "type": "rating", "value": 0},
            {"from_name": "q", "type": "choices", "value": {"choices": []}},
            {"from_name": "q", "type": "choices", "value": None},
            {"from_name": "q", "type": "textarea", "value": {"text": ["   "]}},
            {"from_name": "q", "type": "textarea", "value": ""},
        ],
    )
    def test_empty_values_do_not_answer(self, entry):
        config = '<View><Rating name="q" toName="q" required="true"/></View>'
        if entry["type"] != "rating":
            config = '<View><TextArea name="q" toName="q" required="true"/></View>'
        assert missing_required_answers(config, [entry]) == ["q"]

    @pytest.mark.parametrize(
        "entry",
        [
            {"from_name": "q", "type": "likert", "value": 1},
            {"from_name": "q", "type": "number", "value": 0},
            {"from_name": "q", "type": "number", "value": {"number": 0}},
            {"from_name": "q", "type": "choices", "value": {"choices": ["Clear"]}},
            # A control without toName submits its raw value as textarea
            {"from_name": "q", "type": "textarea", "value": "Clear"},
        ],
    )
    def test_given_values_answer(self, entry):
        config = '<View><Number name="q" toName="q" required="true"/></View>'
        assert missing_required_answers(config, [entry]) == []

    def test_config_hash(self):
        assert questionnaire_config_hash(None) is None
        assert questionnaire_config_hash("") is None
        assert (
            questionnaire_config_hash(UTAUT_TEMPLATE)
            == hashlib.sha256(UTAUT_TEMPLATE.encode("utf-8")).hexdigest()
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user: User):
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


async def _seed(db, *, questionnaire_config=EXTENDED_TEMPLATE, superadmin=False):
    user = User(
        id=_uid(),
        username=f"q-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Questionnaire User",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    project = Project(
        id=_uid(),
        title="Questionnaire Project",
        created_by=user.id,
        questionnaire_enabled=True,
        questionnaire_config=questionnaire_config,
    )
    db.add(project)
    await db.flush()
    task = Task(id=_uid(), project_id=project.id, data={"text": "x"}, inner_id=1)
    db.add(task)
    await db.flush()
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=[],
    )
    db.add(annotation)
    await db.commit()
    return user, project, task, annotation


def _patch_access():
    return [
        patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "routers.projects.deps.check_user_can_edit_project_async",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "routers.projects.questionnaire.check_task_assigned_to_user_async",
            new=AsyncMock(return_value=True),
        ),
    ]


ALL_REQUIRED_ANSWERED = [
    {"from_name": "confidence", "to_name": "confidence", "type": "rating",
     "value": {"rating": 4}},
    {"from_name": "difficulty", "to_name": "difficulty", "type": "rating",
     "value": {"rating": 2}},
    {"from_name": "guideline_clarity", "to_name": "guideline_clarity",
     "type": "choices", "value": {"choices": ["Clear"]}},
]


async def _submit(client, project, task, annotation, result):
    p = _patch_access()
    with p[0], p[1], p[2]:
        return await client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/questionnaire-response",
            json={"annotation_id": annotation.id, "result": result},
        )


async def _stored(db, annotation):
    return (
        await db.execute(
            select(PostAnnotationResponse).where(
                PostAnnotationResponse.annotation_id == annotation.id
            )
        )
    ).scalars().all()


@pytest.mark.asyncio
class TestSubmitRequired:
    async def test_unanswered_required_questions_rejected(
        self, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed(async_test_db)
        only_comment = [
            {"from_name": "comments", "to_name": "comments", "type": "textarea",
             "value": {"text": ["edge case"]}},
        ]
        with _as_user(user):
            resp = await _submit(async_test_client, project, task, annotation, only_comment)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "questionnaire_required_missing"
        assert detail["missing"] == [
            "How confident are you in your annotation?",
            "How difficult was this task?",
            "How clear were the annotation guidelines?",
        ]
        assert await _stored(async_test_db, annotation) == []

    async def test_answered_response_stored_with_config_hash(
        self, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed(async_test_db)
        with _as_user(user):
            resp = await _submit(
                async_test_client, project, task, annotation, ALL_REQUIRED_ANSWERED
            )
        assert resp.status_code == 200, resp.text
        expected = hashlib.sha256(EXTENDED_TEMPLATE.encode("utf-8")).hexdigest()
        assert resp.json()["config_hash"] == expected
        rows = await _stored(async_test_db, annotation)
        assert [r.config_hash for r in rows] == [expected]

    async def test_second_submit_rejected_as_duplicate(
        self, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed(async_test_db)
        with _as_user(user):
            first = await _submit(
                async_test_client, project, task, annotation, ALL_REQUIRED_ANSWERED
            )
            second = await _submit(
                async_test_client, project, task, annotation, ALL_REQUIRED_ANSWERED
            )
        assert first.status_code == 200
        assert second.status_code == 400
        assert "already submitted" in second.json()["detail"]
        assert len(await _stored(async_test_db, annotation)) == 1

    async def test_racing_insert_reports_duplicate(self, async_test_client, async_test_db):
        """A submit that passes the duplicate check while another one commits
        hits the unique index and reports the duplicate, not a 500."""
        user, project, task, annotation = await _seed(async_test_db)
        real_execute = async_test_db.execute
        raced = False

        async def execute_then_race(statement, *args, **kwargs):
            nonlocal raced
            result = await real_execute(statement, *args, **kwargs)
            if not raced and "post_annotation_responses" in str(statement):
                raced = True
                async_test_db.add(
                    PostAnnotationResponse(
                        id=_uid(), annotation_id=annotation.id, task_id=task.id,
                        project_id=project.id, user_id=user.id, result=[],
                    )
                )
                await async_test_db.commit()
            return result

        with _as_user(user), patch.object(async_test_db, "execute", execute_then_race):
            resp = await _submit(
                async_test_client, project, task, annotation, ALL_REQUIRED_ANSWERED
            )
        assert raced
        assert resp.status_code == 400
        assert "already submitted" in resp.json()["detail"]


    async def test_integrity_error_without_duplicate_is_not_reported_as_one(
        self, async_test_client, async_test_db
    ):
        """A commit that fails for another reason (the annotation deleted
        meanwhile) is not reported as an already submitted response."""
        user, project, task, annotation = await _seed(async_test_db)
        real_commit = async_test_db.commit

        async def failing_commit():
            if any(isinstance(o, PostAnnotationResponse) for o in async_test_db.new):
                raise IntegrityError("INSERT", {}, Exception("fk violation"))
            await real_commit()

        with _as_user(user), patch.object(async_test_db, "commit", failing_commit):
            try:
                resp = await _submit(
                    async_test_client, project, task, annotation, ALL_REQUIRED_ANSWERED
                )
            except IntegrityError:
                resp = None
        assert resp is None or resp.status_code == 500


@pytest.mark.asyncio
class TestUniqueIndex:
    async def test_two_responses_for_one_annotation_rejected_by_db(self, async_test_db):
        user, project, task, annotation = await _seed(async_test_db)
        for _ in range(2):
            async_test_db.add(
                PostAnnotationResponse(
                    id=_uid(), annotation_id=annotation.id, task_id=task.id,
                    project_id=project.id, user_id=user.id, result=[],
                )
            )
        with pytest.raises(IntegrityError):
            await async_test_db.flush()
        await async_test_db.rollback()


@pytest.mark.asyncio
class TestSaveValidation:
    async def _patch(self, client, project, body):
        return await client.patch(f"/api/projects/{project.id}", json=body)

    async def test_invalid_config_rejected_with_errors(self, async_test_client, async_test_db):
        user, project, _, _ = await _seed(async_test_db, superadmin=True)
        with _as_user(user):
            resp = await self._patch(
                async_test_client,
                project,
                {"questionnaire_config": '<View><Ratng name="q" toName="q"/></View>'},
            )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "invalid_questionnaire_config"
        assert detail["errors"] == ["Unsupported field type: 'Ratng'"]
        # The toast shows ``message``: it carries the errors themselves.
        assert "Unsupported field type: 'Ratng'" in detail["message"]
        await async_test_db.refresh(project)
        assert project.questionnaire_config == EXTENDED_TEMPLATE

    async def test_malformed_xml_rejected(self, async_test_client, async_test_db):
        user, project, _, _ = await _seed(async_test_db, superadmin=True)
        with _as_user(user):
            resp = await self._patch(
                async_test_client, project, {"questionnaire_config": "<View><Rating"}
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["errors"][0].startswith("XML parsing failed")

    async def test_config_without_renderable_question_rejected(
        self, async_test_client, async_test_db
    ):
        user, project, _, _ = await _seed(async_test_db, superadmin=True)
        with _as_user(user):
            resp = await self._patch(
                async_test_client,
                project,
                {"questionnaire_config": '<View><Checkbox name="ok" toName="ok"/></View>'},
            )
        assert resp.status_code == 422
        assert "has no question" in resp.json()["detail"]["errors"][0]
        await async_test_db.refresh(project)
        assert project.questionnaire_config == EXTENDED_TEMPLATE

    async def test_likert_template_saves(self, async_test_client, async_test_db):
        user, project, _, _ = await _seed(async_test_db, superadmin=True)
        with _as_user(user):
            resp = await self._patch(
                async_test_client, project, {"questionnaire_config": UTAUT_TEMPLATE}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["questionnaire_config"] == UTAUT_TEMPLATE

    async def test_unchanged_stored_config_is_not_revalidated(
        self, async_test_client, async_test_db
    ):
        """Saving other settings echoes the stored config back: a config
        stored before validation existed must not block that save."""
        legacy = '<View><Header value="no question"/></View>'
        user, project, _, _ = await _seed(
            async_test_db, questionnaire_config=legacy, superadmin=True
        )
        with _as_user(user):
            resp = await self._patch(
                async_test_client,
                project,
                {"questionnaire_config": legacy, "questionnaire_enabled": False},
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("value", ["", None])
    async def test_empty_config_clears(self, async_test_client, async_test_db, value):
        user, project, _, _ = await _seed(async_test_db, superadmin=True)
        with _as_user(user):
            resp = await self._patch(
                async_test_client, project, {"questionnaire_config": value}
            )
        assert resp.status_code == 200, resp.text
