"""Endpoints that expand a project's <Repeater> label config.

- ``GET /api/projects/{id}/label-config/label-studio``: the config in the
  expanded form Label Studio reads, to the longest array of the project.
- ``GET /api/projects/{id}/label-config/slots``: which control names hold
  which slot's answers in one task.
- Evaluation field detection lists the indexed fields, not the templates.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import pytest

from models import User
from project_models import Project, Task

DOCKET = """<View>
  <Repeater on="$doc.cases" indexFlag="{{idx}}" mode="pagination" answerKey="case">
    <Text name="case_{{idx}}" value="$doc.cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <TextArea name="note_{{idx}}" toName="case_{{idx}}"/>
  </Repeater>
  <Text name="facts" value="$facts"/>
  <Number name="months_1" toName="facts"/>
  <Number name="months_2" toName="facts"/>
</View>"""


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=db_user.is_active,
        email_verified=db_user.email_verified,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed(db, label_config=DOCKET, task_cases=((1, 2), (1, 2, 3, 4), None)):
    user = User(
        id=f"repeater-user-{_uid()}",
        username=f"repeater-{uuid.uuid4().hex[:8]}",
        email=f"repeater-{uuid.uuid4().hex[:8]}@test.com",
        name="Repeater User",
        hashed_password="hashed_password",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    project = Project(
        id=f"repeater-project-{_uid()}",
        title="Repeater Project",
        created_by=user.id,
        label_config=label_config,
    )
    db.add(project)
    await db.flush()
    tasks = []
    for inner_id, cases in enumerate(task_cases, start=1):
        # A task without the array (None) and one whose binding is no list
        # must not break the longest-array aggregate.
        if cases is None:
            data = {"facts": "no cases", "doc": {"cases": "not a list"}}
        else:
            data = {"facts": "f", "doc": {"cases": [{"text": f"case {n}"} for n in cases]}}
        task = Task(id=_uid(), project_id=project.id, data=data, inner_id=inner_id, created_by=user.id)
        db.add(task)
        tasks.append(task)
    await db.commit()
    return user, project, tasks


class TestLabelStudioConfigExport:
    @pytest.mark.asyncio
    async def test_expands_to_the_longest_array(self, async_test_client, async_test_db):
        user, project, _ = await _seed(async_test_db)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/label-studio"
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["expanded"] is True
        assert body["item_counts"] == {"$doc.cases": 4}
        root = ET.fromstring(body["label_config"])
        assert root.find(".//Repeater") is None
        assert [e.get("name") for e in root.iter("Number")] == [
            "risk_0", "risk_1", "risk_2", "risk_3", "months_1", "months_2",
        ]
        assert [e.get("value") for e in root.iter("Text")][:2] == [
            "$doc.cases[0].text",
            "$doc.cases[1].text",
        ]

    @pytest.mark.asyncio
    async def test_config_without_repeater_is_unchanged(self, async_test_client, async_test_db):
        plain = "<View><Text name='t' value='$t'/><TextArea name='a' toName='t'/></View>"
        user, project, _ = await _seed(async_test_db, label_config=plain)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/label-studio"
            )
        assert response.status_code == 200
        assert response.json() == {
            "project_id": project.id,
            "label_config": plain,
            "expanded": False,
            "item_counts": {},
        }

    @pytest.mark.asyncio
    async def test_unknown_project_is_404(self, async_test_client, async_test_db):
        user, _, _ = await _seed(async_test_db)
        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/no-such-project/label-config/label-studio"
            )
        assert response.status_code == 404


class TestSlotMap:
    @pytest.mark.asyncio
    async def test_repeater_and_pattern_groups(self, async_test_client, async_test_db):
        user, project, tasks = await _seed(async_test_db)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/slots",
                params={"task_id": tasks[0].id, "pattern": ["months_{idx}"]},
            )
        assert response.status_code == 200, response.text
        repeater, pattern = response.json()["groups"]
        assert repeater["source"] == "repeater"
        assert repeater["slots"] == [
            {"index": 0, "controls": {"risk": "risk_0", "note": "note_0"}},
            {"index": 1, "controls": {"risk": "risk_1", "note": "note_1"}},
        ]
        assert pattern["slots"] == [
            {"index": 1, "controls": {"months": "months_1"}},
            {"index": 2, "controls": {"months": "months_2"}},
        ]

    @pytest.mark.asyncio
    async def test_errors(self, async_test_client, async_test_db):
        user, project, tasks = await _seed(async_test_db)
        _, other_project, other_tasks = await _seed(async_test_db)
        with _as_user(user):
            missing = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/slots",
                params={"task_id": other_tasks[0].id},
            )
            bad_pattern = await async_test_client.get(
                f"/api/projects/{project.id}/label-config/slots",
                params={"task_id": tasks[0].id, "pattern": ["months"]},
            )
        assert missing.status_code == 404
        assert bad_pattern.status_code == 422
        assert "exactly once" in bad_pattern.json()["detail"]


class TestEvaluationFieldDetection:
    @pytest.mark.asyncio
    async def test_detected_fields_are_the_indexed_names(self, async_test_client, async_test_db):
        user, project, _ = await _seed(async_test_db)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert response.status_code == 200, response.text
        names = {t["name"] for t in response.json()["detected_types"]}
        assert {"risk_0", "risk_3", "note_2", "months_1"} <= names
        assert not any("{{idx}}" in name for name in names)


class TestPublicProjectView:
    @pytest.mark.asyncio
    async def test_answer_fields_are_the_indexed_names(self, async_test_client, async_test_db):
        from tests.fixtures.v1 import v1_auth

        user, project, _ = await _seed(async_test_db)
        with v1_auth(async_test_db, session_user=user):
            response = await async_test_client.get(f"/api/v1/projects/{project.id}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [f["name"] for f in body["answer_fields"]] == [
            "risk_0", "note_0", "risk_1", "note_1", "risk_2", "note_2",
            "risk_3", "note_3", "months_1", "months_2",
        ]
        assert body["answer_fields"][0]["to_name"] == "case_0"
        assert not any("{{idx}}" in name for name in body["bound_fields"])
        assert "doc.cases" in body["bound_fields"]


class TestStoredEvaluationConfig:
    @pytest.mark.asyncio
    async def test_follows_item_counts_of_later_imported_tasks(
        self, async_test_client, async_test_db
    ):
        user, project, _ = await _seed(async_test_db, task_cases=((1, 2, 3),))

        async def stored_names():
            response = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
            assert response.status_code == 200, response.text
            return {t["name"] for t in response.json()["detected_answer_types"]}

        with _as_user(user):
            before = await stored_names()
            assert {"risk_0", "risk_2"} <= before
            assert "risk_3" not in before

            async_test_db.add(
                Task(
                    id=_uid(),
                    project_id=project.id,
                    data={"facts": "f", "doc": {"cases": [{"text": f"c{n}"} for n in range(5)]}},
                    inner_id=2,
                    created_by=user.id,
                )
            )
            await async_test_db.commit()

            after = await stored_names()
            detected = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
            available = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/available-fields"
            )
        assert {"risk_3", "risk_4", "note_4"} <= after
        assert after == {t["name"] for t in detected.json()["detected_types"]}
        assert after <= set(available.json()["human_annotation_fields"])
