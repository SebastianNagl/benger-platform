"""POST /api/projects/{project_id}/generations/reparse: stored answers re-read
with the current response parser (routers/projects/generation_reparse.py).

The Grundprinzipien ``default`` prompt asked for ``answer``/``reasoning``
while the label config names ``kurzantwort``/``begruendung``; answers that
followed the prompt were stored as parsed without either field. The parser
now maps those keys, and this route applies it to stored answers. Requests
run through the real app, key gate and superadmin check on the async test
session, with a superadmin's ``admin:platform`` key.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project, Task
from response_parser import ResponseParser
from services import api_key_service as svc
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import bearer

pytestmark = pytest.mark.asyncio

# The Grundprinzipien label config: case text and question, two answer fields.
GERMAN_QA_CONFIG = """<View>
  <Text name="fall" value="$fall"/>
  <Text name="task" value="$task"/>
  <TextArea name="kurzantwort" toName="task" rows="1"/>
  <TextArea name="begruendung" toName="task" rows="3"/>
</View>"""

STRUCTURE = {
    "name": "Default",
    "system_prompt": "Du bist Jurist.",
    "instruction_prompt": "{{fall}} {{task}}",
}

ENGLISH_KEYS = '{"answer": "Ja", "reasoning": "§ 242 BGB, Verwirkung."}'
INVALID_JSON = 'Thinking Process: the answer is "Ja" because {"answer": "Ja", '
MISSPELLED_KEYS = '{"Kurzantwort": "Nein", "begründung": "§ 311b BGB."}'


def _uid() -> str:
    return str(uuid.uuid4())


async def _key(db, user, scopes):
    return (await svc.create_personal_key(db, user.id, {"name": "k", "scopes": scopes}))[1]


async def _project(db, owner_id, *, structures=None):
    project = Project(
        id=_uid(),
        title="Grundprinzipien",
        created_by=owner_id,
        label_config=GERMAN_QA_CONFIG,
        generation_config={
            "prompt_structures": structures if structures is not None else {"default": STRUCTURE}
        },
    )
    db.add(project)
    await db.flush()
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=1,
        data={"fall": "A verlangt von B ...", "task": "Ist der Anspruch verwirkt?"},
        created_by=owner_id,
        updated_by=owner_id,
    )
    db.add(task)
    await db.flush()
    return project, task


def _as_generated(response: str) -> dict:
    """The parse fields the current parser gives a new answer."""
    result = ResponseParser(generation_structure=STRUCTURE, label_config=GERMAN_QA_CONFIG).parse(
        response
    )
    return {
        "parsed_annotation": result.parsed_annotation,
        "parse_status": result.status,
        "parse_error": result.error,
        "status": "completed" if result.status == "success" else "parse_failed",
    }


async def _answer(db, project, task, owner_id, response, *, structure_key="default", **parse):
    run = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id,
        model_id="custom-kolibri",
        structure_key=structure_key,
        status="completed",
        created_by=owner_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    fields = {
        "parsed_annotation": None,
        "parse_status": "success",
        "parse_error": None,
        "status": "completed",
    }
    fields.update(parse)
    answer = DBGeneration(
        id=_uid(),
        generation_id=run.id,
        task_id=task.id,
        model_id="custom-kolibri",
        case_data="{}",
        response_content=response,
        parse_metadata={"retry_count": 1, "last_attempt": "2026-05-01T10:00:00"},
        label_config_version="v1",
        **fields,
    )
    db.add(answer)
    await db.flush()
    return answer


async def _reload(db, answer_id):
    db.expire_all()
    return (
        await db.execute(select(DBGeneration).where(DBGeneration.id == answer_id))
    ).scalar_one()


@pytest.fixture
async def world(async_test_db):
    w = await seed_world(async_test_db, group=False)
    w["project"], w["task"] = await _project(async_test_db, w["superadmin"].id)
    w["key"] = await _key(async_test_db, w["superadmin"], ["admin:platform"])
    # Plain ids: the tests expire the session to re-read rows.
    w["superadmin_id"] = w["superadmin"].id
    w["project_id"] = w["project"].id
    return w


def _url(project_id):
    return f"/api/projects/{project_id}/generations/reparse"


async def test_english_keys_are_read_as_the_german_fields(async_test_client, async_test_db, world):
    db = async_test_db
    answer = await _answer(db, world["project"], world["task"], world["superadmin"].id, ENGLISH_KEYS)
    answer_id = answer.id

    r = await async_test_client.post(
        _url(world["project_id"]), json={"generation_ids": [answer_id]}, headers=bearer(world["key"])
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is False
    assert (body["changed"], body["unchanged"], body["not_found"], body["skipped"]) == (1, 0, 0, 0)
    item = body["results"][0]
    assert item["outcome"] == "changed"
    assert item["before"]["fields"] == {}
    assert item["after"]["fields"] == {
        "kurzantwort": "Ja",
        "begruendung": "§ 242 BGB, Verwirkung.",
    }
    assert item["after"]["mapped_keys"] == {"answer": "kurzantwort", "reasoning": "begruendung"}

    row = await _reload(db, answer_id)
    assert row.response_content == ENGLISH_KEYS
    assert {a["from_name"]: a["value"]["text"][0] for a in row.parsed_annotation} == {
        "kurzantwort": "Ja",
        "begruendung": "§ 242 BGB, Verwirkung.",
    }
    assert row.parse_status == "success"
    assert row.status == "completed"
    assert row.parse_metadata["retry_count"] == 1
    assert row.parse_metadata["mapped_keys"] == {"answer": "kurzantwort", "reasoning": "begruendung"}
    (entry,) = row.parse_metadata["reparse_history"]
    assert entry["reparsed_by"] == world["superadmin_id"]
    assert entry["reparsed_at"]
    assert entry["superseded"]["parsed_annotation"] is None
    assert entry["superseded"]["parse_status"] == "success"
    assert entry["superseded"]["mapped_keys"] == {}
    assert entry["superseded"]["label_config_version"] == "v1"
    assert row.label_config_snapshot == GERMAN_QA_CONFIG

    # Idempotent: a second call finds nothing to change and writes nothing.
    r = await async_test_client.post(
        _url(world["project_id"]), json={"generation_ids": [answer_id]}, headers=bearer(world["key"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["outcome"] == "unchanged"
    row = await _reload(db, answer_id)
    assert len(row.parse_metadata["reparse_history"]) == 1


async def test_dry_run_reports_and_writes_nothing(async_test_client, async_test_db, world):
    db = async_test_db
    answer = await _answer(db, world["project"], world["task"], world["superadmin"].id, ENGLISH_KEYS)

    r = await async_test_client.post(
        _url(world["project"].id),
        json={"generation_ids": [answer.id], "dry_run": True},
        headers=bearer(world["key"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True and body["changed"] == 1
    item = body["results"][0]
    assert item["outcome"] == "changed"
    assert item["before"]["fields"] == {}
    assert item["after"]["fields"]["kurzantwort"] == "Ja"

    row = await _reload(db, answer.id)
    assert row.parsed_annotation is None
    assert row.parse_metadata == {"retry_count": 1, "last_attempt": "2026-05-01T10:00:00"}
    assert row.label_config_snapshot is None


@pytest.mark.parametrize("response", [INVALID_JSON, MISSPELLED_KEYS], ids=["invalid-json", "misspelled-keys"])
async def test_unreadable_answers_stay_as_they_are(async_test_client, async_test_db, world, response):
    db = async_test_db
    stored = _as_generated(response)
    assert "kurzantwort" not in str(stored["parsed_annotation"])
    answer = await _answer(db, world["project"], world["task"], world["superadmin"].id, response, **stored)

    r = await async_test_client.post(
        _url(world["project"].id), json={"generation_ids": [answer.id]}, headers=bearer(world["key"])
    )
    assert r.status_code == 200, r.text
    item = r.json()["results"][0]
    assert item["outcome"] == "unchanged"
    assert "kurzantwort" not in item["after"]["fields"]
    assert "begruendung" not in item["after"]["fields"]

    row = await _reload(db, answer.id)
    assert row.response_content == response
    assert row.parsed_annotation == stored["parsed_annotation"]
    assert row.parse_status == stored["parse_status"]
    assert "reparse_history" not in row.parse_metadata


async def test_a_failed_parse_that_now_succeeds_completes_the_row(async_test_client, async_test_db, world):
    db = async_test_db
    answer = await _answer(
        db,
        world["project"],
        world["task"],
        world["superadmin"].id,
        ENGLISH_KEYS,
        parse_status="validation_error",
        parse_error="'kurzantwort' is a required property",
        status="parse_failed_max_retries",
    )
    r = await async_test_client.post(
        _url(world["project"].id), json={"generation_ids": [answer.id]}, headers=bearer(world["key"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["after"]["status"] == "completed"
    row = await _reload(db, answer.id)
    assert (row.parse_status, row.parse_error, row.status) == ("success", None, "completed")
    superseded = row.parse_metadata["reparse_history"][0]["superseded"]
    assert superseded["status"] == "parse_failed_max_retries"
    assert superseded["parse_error"] == "'kurzantwort' is a required property"


async def test_other_projects_answers_and_deleted_structures(async_test_client, async_test_db, world):
    db = async_test_db
    other, other_task = await _project(db, world["superadmin"].id)
    foreign = await _answer(db, other, other_task, world["superadmin"].id, ENGLISH_KEYS)
    orphan = await _answer(
        db, world["project"], world["task"], world["superadmin"].id, ENGLISH_KEYS, structure_key="gone"
    )
    missing = _uid()
    foreign_id, orphan_id = foreign.id, orphan.id

    r = await async_test_client.post(
        _url(world["project"].id),
        json={"generation_ids": [foreign_id, orphan_id, missing, missing]},
        headers=bearer(world["key"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(i["generation_id"], i["outcome"]) for i in body["results"]] == [
        (foreign_id, "not_found"),
        (orphan_id, "skipped"),
        (missing, "not_found"),
    ]
    assert "gone" in body["results"][1]["reason"]
    assert (await _reload(db, foreign_id)).parsed_annotation is None
    assert (await _reload(db, orphan_id)).parsed_annotation is None


async def test_list_format_structures_resolve_by_key(async_test_client, async_test_db, world):
    db = async_test_db
    project, task = await _project(
        db, world["superadmin"].id, structures=[{"key": "default", "structure": STRUCTURE}]
    )
    answer = await _answer(db, project, task, world["superadmin"].id, ENGLISH_KEYS)
    r = await async_test_client.post(
        _url(project.id), json={"generation_ids": [answer.id]}, headers=bearer(world["key"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["outcome"] == "changed"


async def test_superadmin_only(async_test_client, async_test_db, world):
    db = async_test_db
    answer = await _answer(db, world["project"], world["task"], world["superadmin"].id, ENGLISH_KEYS)
    body = {"generation_ids": [answer.id]}

    # A superadmin's key without admin:platform, and an org admin's key.
    for user, scopes in ((world["superadmin"], ["runs:write"]), (world["admin"], ["runs:write"])):
        plain = await _key(db, user, scopes)
        r = await async_test_client.post(_url(world["project"].id), json=body, headers=bearer(plain))
        assert r.status_code == 403, r.text
    assert (await _reload(db, answer.id)).parsed_annotation is None


async def test_unknown_project_and_empty_list(async_test_client, world):
    r = await async_test_client.post(
        _url(_uid()), json={"generation_ids": ["x"]}, headers=bearer(world["key"])
    )
    assert r.status_code == 404
    r = await async_test_client.post(
        _url(world["project"].id), json={"generation_ids": []}, headers=bearer(world["key"])
    )
    assert r.status_code == 422
