"""Coding projects and code validations through the API, the references an
analysis spec makes to them, and the ``text_pattern`` evaluation config.

The validation itself runs in the workers
(services/workers/tests/integration/test_codes_e2e.py); here
``send_task_safe`` is patched so only the endpoints run.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from models import CodeValidation, CodingProject, Generation, OrganizationRole, ResponseGeneration
from project_models import Project, ProjectOrganization, Task
from tests.fixtures.access_keys import make_membership, make_user, seed_world
from tests.fixtures.v1 import make_project, v1_auth

SCHEME = (
    '<View><Text name="answer" value="$answer"/><Text name="case" value="$sachverhalt"/>'
    '<Choices name="side" toName="answer"><Choice value="P"/><Choice value="D"/></Choices></View>'
)
PATTERN_SET = {"name": "blame", "version": "1",
               "codes": {"claimant": {"mode": "any", "patterns": ["claimant"]}}}


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=False)
    annotator = make_user(name="Annotator")
    db.add(annotator)
    await db.flush()
    db.add(make_membership(annotator.id, w["org"].id, OrganizationRole.ANNOTATOR))
    w["annotator"] = annotator
    project = await make_project(db, w["admin"].id, org_id=w["org"].id, title="answers")
    w["project"] = project
    w["generations"] = []
    for i in range(6):
        task = Task(id=str(uuid.uuid4()), project_id=project.id, inner_id=i + 1,
                    data={"sachverhalt": f"case {i}", "secret": "gold"},
                    meta={})
        db.add(task)
        await db.flush()
        model = "m-a" if i % 2 == 0 else "m-b"
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=project.id, task_id=task.id, model_id=model,
                                status="completed", created_by=w["admin"].id, structure_key="default")
        db.add(rg)
        await db.flush()
        gid = str(uuid.uuid4())
        db.add(Generation(
            id=gid, generation_id=rg.id, task_id=task.id, model_id=model, case_data="{}",
            response_content="" if i == 5 else f"answer {i}: the claimant", status="completed",
            parsed_annotation=[{"from_name": "begr", "type": "textarea", "value": {"text": [f"reason {i}"]}}],
            parse_status="success",
            response_metadata=json.dumps({"system": {"key": f"{model}@aaaaaaaaaaaa"}}),
        ))
        w["generations"].append(gid)
    other = await seed_world(db, group=False)
    other["project"] = await make_project(db, other["admin"].id, org_id=other["org"].id, title="other")
    w["other"] = other
    await db.commit()
    return w


def _queued(module="routers.coding"):
    result = MagicMock()
    result.id = "celery-coding-1"
    return patch(f"{module}.send_task_safe", return_value=result)


def _body(**over):
    body = {
        "title": "Coding: side",
        "label_config": SCHEME,
        "context_fields": ["sachverhalt"],
        "sample": {"seed": 42, "size": 3},
    }
    body.update(over)
    return body


async def _create(client, project_id, **over):
    return await client.post(f"/api/projects/{project_id}/coding-projects", json=_body(**over))


async def test_create_draws_a_seeded_sample_into_a_new_project(async_test_client, async_test_db, world):
    from analysis.coding import draw_sample

    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await _create(async_test_client, project.id)
        again = await _create(async_test_client, project.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_project_id"] == project.id and body["tasks"] == 3
    assert body["sample"]["candidates"] == 6 and body["sample"]["drawn"] == 3
    assert body["sample"]["hash"] == again.json()["sample"]["hash"]
    # the first three by seeded rank among the answers with text (answer 5 is empty)
    usable = [g for g in world["generations"][:5]]
    expected = [g for g, _ in draw_sample(world["generations"], 42)][:4]
    expected = [g for g in expected if g in usable][:3]
    tasks = (
        await async_test_db.execute(select(Task).where(Task.project_id == body["project_id"]).order_by(Task.inner_id))
    ).scalars().all()
    assert [t.meta["coding"]["source_generation_id"] for t in tasks] == expected
    first = tasks[0]
    assert first.data["answer"].endswith("the claimant") and set(first.data) == {"answer", "sachverhalt"}
    assert first.meta["coding"]["source_project_id"] == project.id
    assert first.meta["coding"]["answer_source"] == "answer" and first.meta["coding"]["sample_seed"] == 42
    coding = (await async_test_db.execute(select(Project).where(Project.id == body["project_id"]))).scalar_one()
    assert coding.label_config == SCHEME and coding.is_private is False
    orgs = (
        await async_test_db.execute(
            select(ProjectOrganization.organization_id).where(ProjectOrganization.project_id == coding.id)
        )
    ).scalars().all()
    assert orgs == [world["org"].id]


async def test_create_from_a_field_and_with_filters(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await _create(async_test_client, project.id, answer={"field": "begr"},
                          sample={"seed": 1, "systems": ["m-b@aaaaaaaaaaaa"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sample"]["candidates"] == 3 and body["tasks"] == 3
    tasks = (await async_test_db.execute(select(Task).where(Task.project_id == body["project_id"]))).scalars().all()
    assert {t.data["answer"] for t in tasks} == {"reason 1", "reason 3", "reason 5"}


async def test_create_refuses_bad_requests(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        no_answer = await _create(async_test_client, project.id,
                                  label_config='<View><Text name="t" value="$x"/><Choices name="c" toName="t"><Choice value="a"/></Choices></View>')
        bad_sample = await _create(async_test_client, project.id, sample={"seed": -1, "size": 0, "colour": 1})
        clash = await _create(async_test_client, project.id, context_fields=["answer"])
        empty = await _create(async_test_client, project.id, sample={"seed": 1, "designs": ["none"]})
    with v1_auth(async_test_db, session_user=world["annotator"]):
        denied = await _create(async_test_client, project.id)
    with v1_auth(async_test_db, session_user=world["other"]["admin"]):
        foreign = await _create(async_test_client, project.id)
    assert no_answer.status_code == 422
    assert any('value="$answer"' in e for e in no_answer.json()["detail"]["errors"])
    errors = bad_sample.json()["detail"]["errors"]
    assert any("/sample/seed" in e for e in errors) and any("/sample/size" in e for e in errors)
    assert any("unknown key(s) colour" in e for e in errors)
    assert clash.status_code == 422
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "empty_coding_sample"
    assert denied.status_code == 403 and foreign.status_code in (403, 404)


async def test_list_and_read_coding_projects(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        created = (await _create(async_test_client, project.id)).json()
        listed = await async_test_client.get(f"/api/projects/{project.id}/coding-projects")
        info = await async_test_client.get(f"/api/projects/{created['project_id']}/coding")
        not_coding = await async_test_client.get(f"/api/projects/{project.id}/coding")
    assert [i["project_id"] for i in listed.json()["items"]] == [created["project_id"]]
    assert listed.json()["items"][0]["title"] == "Coding: side"
    assert info.status_code == 200 and info.json()["tasks"] == 3 and info.json()["source_project_id"] == project.id
    assert not_coding.status_code == 404


async def test_validations_are_queued_listed_and_read(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        coding_id = (await _create(async_test_client, project.id)).json()["project_id"]
        with _queued() as send:
            r = await async_test_client.post(f"/api/projects/{coding_id}/code-validations", json={
                "code": {"kind": "text_pattern", "set": PATTERN_SET, "code": "claimant"},
                "control": "side", "value_map": {"1": "P", "0": "D"},
            })
            judge = await async_test_client.post(f"/api/projects/{coding_id}/code-validations", json={
                "code": {"kind": "judge_code", "system": "judge-m"}, "control": "side", "name": "judge",
            })
        bad = await async_test_client.post(f"/api/projects/{coding_id}/code-validations", json={
            "code": {"kind": "text_pattern", "set": PATTERN_SET, "code": "nope"}, "control": "colour",
            "missing": "zero",
        })
        not_coding = await async_test_client.post(f"/api/projects/{project.id}/code-validations", json={
            "code": {"kind": "judge_code", "system": "x"}, "control": "side",
        })
        listed = await async_test_client.get(f"/api/projects/{coding_id}/code-validations")
    assert r.status_code == 202, r.text
    body = r.json()
    assert r.headers["location"] == f"/api/code-validations/{body['id']}"
    assert body["status"] == "pending" and body["code_kind"] == "text_pattern"
    assert body["source_project_id"] == project.id and body["name"] == "text_pattern on side"
    assert body["normalized_code"]["input"] == "answer" and body["options"]["value_map"] == {"1": "P", "0": "D"}
    assert send.call_args_list[0].args[0] == "tasks.run_code_validation"
    assert judge.json()["normalized_code"] == {
        "kind": "judge_code", "coding_project": coding_id, "system": "judge-m", "run_index": 0,
        "type": "text", "field": "side",
    }
    errors = bad.json()["detail"]["errors"]
    assert any("/control" in e for e in errors) and any("/missing" in e for e in errors)
    assert any("no code 'nope'" in e for e in errors)
    assert not_coding.status_code == 404
    assert listed.json()["total"] == 2

    v = (await async_test_db.execute(select(CodeValidation).where(CodeValidation.id == body["id"]))).scalar_one()
    v.status, v.items, v.kappa = "completed", [{"task_id": "t", "automatic": "P", "human": {}}], 0.5
    await async_test_db.commit()
    with v1_auth(async_test_db, session_user=world["member"]):
        full = await async_test_client.get(f"/api/code-validations/{v.id}")
    with v1_auth(async_test_db, session_user=world["annotator"]):
        blinded = await async_test_client.get(f"/api/code-validations/{v.id}")
    with v1_auth(async_test_db, session_user=world["other"]["admin"]):
        hidden = await async_test_client.get(f"/api/code-validations/{v.id}")
    assert full.json()["items"] and full.json()["kappa"] == 0.5
    assert blinded.status_code == 200 and "items" not in blinded.json()
    assert hidden.status_code == 404


async def test_analysis_specs_may_only_name_this_projects_codes(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        coding_id = (await _create(async_test_client, project.id)).json()["project_id"]
    other_coding = CodingProject(project_id=world["other"]["project"].id, source_project_id=world["other"]["project"].id,
                                 answer_source="answer", context_fields=[], sample={}, coding_version=1)
    async_test_db.add(other_coding)
    await async_test_db.commit()

    def spec(measure):
        return {"spec_version": 1, "name": "j", "inputs": {"designs": ["d"]},
                "measures": {"side": measure, "p": {"kind": "expression", "expr": "1 * (side == 'P')"}},
                "estimands": [{"id": "e", "estimator": "mean_rate", "outcome": "p"}]}

    judge = {"kind": "judge_code", "field": "side", "system": "judge-m"}
    with v1_auth(async_test_db, session_user=world["member"]), _queued("routers.analysis"):
        ok = await async_test_client.post(f"/api/projects/{project.id}/analysis-runs",
                                          json={"spec": spec({**judge, "coding_project": coding_id})})
        foreign = await async_test_client.post(f"/api/projects/{project.id}/analysis-runs",
                                               json={"spec": spec({**judge, "coding_project": other_coding.project_id})})
        unknown_v = await async_test_client.post(f"/api/projects/{project.id}/analysis-runs", json={
            "spec": spec({**judge, "coding_project": coding_id, "validation": str(uuid.uuid4())})})
    assert ok.status_code == 202, ok.text
    assert foreign.status_code == 422
    assert "not a coding project drawn from this project" in json.dumps(foreign.json())
    assert unknown_v.status_code == 422 and "not a validation" in json.dumps(unknown_v.json())


async def test_engine_lists_the_code_kinds(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await async_test_client.get("/api/analysis/engine")
    body = r.json()
    assert {"list", "text_pattern", "coder", "judge_code"} <= set(body["measure_kinds"])
    assert body["text_pattern_set_schema"]["title"] == "BenGER text pattern set"
    assert "recall" in body["list_statistics"]


def test_text_pattern_evaluation_configs_are_checked():
    """The config check every writer of evaluation_configs runs."""
    from fastapi import HTTPException

    from routers.evaluations.config import validate_evaluation_config_entries

    def config(params):
        return [{
            "id": "codes", "metric": "text_pattern", "prediction_fields": ["__all_model__"],
            "reference_fields": ["task.sachverhalt"], "metric_parameters": params, "enabled": True,
        }]

    validate_evaluation_config_entries(config({"pattern_set": PATTERN_SET, "code": "claimant"}))
    with pytest.raises(HTTPException) as bad_set:
        validate_evaluation_config_entries(config({"pattern_set": {"name": "x"}, "code": "a"}))
    assert bad_set.value.status_code == 422 and bad_set.value.detail["code"] == "invalid_pattern_set"
    with pytest.raises(HTTPException) as bad_code:
        validate_evaluation_config_entries(config({"pattern_set": PATTERN_SET, "code": "nope"}))
    assert bad_code.value.status_code == 422 and "claimant" in bad_code.value.detail
