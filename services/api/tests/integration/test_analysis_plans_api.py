"""Analysis plans in ``evaluation_config.analysis_plans`` (CORE 2.71).

Both writers of the document validate every plan's spec with the analysis
engine and store it with the hash of its normalized form:

- the eval-config PUT (sync lane: ``client``/``test_db``, read back after
  ``expire_all()``), with the engine's messages on a 422, sibling keys that
  survive, and server-owned hash and stamps;
- ``PATCH /api/projects/{id}`` (async lane), a GET that keeps the plans when
  it regenerates the document, and a run started from a saved plan's spec,
  which records the plan's ``spec_hash``.
"""

from __future__ import annotations

import copy
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from models import AnalysisRun
from project_models import Project, ProjectOrganization

BASE = "/api/evaluations"

SPEC = {
    "spec_version": 1,
    "name": "role swap",
    "inputs": {"designs": ["role_swap"]},
    "measures": {
        "share": {"kind": "field", "field": "share"},
        "x_p": {"kind": "expression", "expr": "1 * (x_role == 'P')"},
    },
    "estimands": [
        {
            "id": "role",
            "estimator": "fe_ols",
            "outcome": "share",
            "terms": ["x_p"],
            "fixed_effects": [["unit", "system"]],
            "vcov": {"type": "cluster", "by": ["unit"]},
            "contrasts": [{"id": "role", "weights": {"x_p": 1}, "tost": {"margin": 3}}],
        }
    ],
}


def _hash(spec):
    from analysis.spec import normalize_spec, spec_hash

    return spec_hash(normalize_spec(spec))


def _uid():
    return str(uuid.uuid4())


def _seed_project(test_db, test_users, test_org, evaluation_config=None):
    project = Project(
        id=_uid(),
        title="Plans Project",
        created_by=test_users[0].id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_users[0].id,
        )
    )
    test_db.commit()
    return project


def _stored(test_db, project_id):
    test_db.expire_all()
    return test_db.query(Project).filter(Project.id == project_id).first().evaluation_config


def _put(client, project_id, body, headers):
    return client.put(f"{BASE}/projects/{project_id}/evaluation-config", json=body, headers=headers)


STORED = {
    "default_temperature": 0.2,
    "defaults_mode": "custom",
    "evaluation_configs": [
        {
            "id": "a",
            "metric": "bleu",
            "prediction_fields": ["__all_model__"],
            "reference_fields": ["task.expected"],
            "enabled": True,
        }
    ],
}


@pytest.mark.integration
class TestAnalysisPlansPut:
    def test_a_valid_plan_is_stored_with_the_normalized_hash(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        resp = _put(
            client,
            project.id,
            {"analysis_plans": [{"name": "  Primary analysis ", "spec": SPEC}]},
            auth_headers["contributor"],
        )
        assert resp.status_code == 200, resp.text

        stored = _stored(test_db, project.id)
        [plan] = stored["analysis_plans"]
        assert plan["name"] == "Primary analysis"
        assert plan["spec"] == SPEC
        assert plan["spec_hash"] == _hash(SPEC) and len(plan["spec_hash"]) == 64
        assert plan["saved_by"] == test_users[1].id and plan["saved_at"]
        assert uuid.UUID(plan["id"])
        # The response carries the stored plans.
        assert resp.json()["config"]["analysis_plans"] == [plan]

        # Sibling keys survive the plan save.
        assert stored["default_temperature"] == 0.2
        assert stored["defaults_mode"] == "custom"
        assert stored["evaluation_configs"] == STORED["evaluation_configs"]

    def test_a_plan_save_leaves_the_plans_alone_when_absent(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        first = _put(
            client, project.id, {"analysis_plans": [{"name": "P", "spec": SPEC}]}, auth_headers["admin"]
        )
        assert first.status_code == 200, first.text
        plans = _stored(test_db, project.id)["analysis_plans"]

        other = _put(client, project.id, {"default_temperature": 0.7}, auth_headers["admin"])
        assert other.status_code == 200, other.text
        stored = _stored(test_db, project.id)
        assert stored["analysis_plans"] == plans
        assert stored["default_temperature"] == 0.7

    def test_an_invalid_spec_is_422_with_the_engine_messages(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        bad = {**SPEC, "measures": {"x": {"kind": "expression", "expr": "open('f')"}}}
        resp = _put(
            client,
            project.id,
            {
                "default_temperature": 0.9,
                "analysis_plans": [
                    {"name": "fine", "spec": SPEC},
                    {"name": "broken", "spec": bad},
                ],
            },
            auth_headers["admin"],
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "invalid_analysis_plan"
        # The engine's own messages, under the plan's path.
        from analysis.spec import SpecError, normalize_spec

        with pytest.raises(SpecError) as engine:
            normalize_spec(bad)
        assert detail["errors"] == [
            "/analysis_plans/1/spec" + (e[1:] if e.startswith("/: ") else e)
            for e in engine.value.errors
        ]
        assert any("unknown function" in e for e in detail["errors"])
        # Nothing was written.
        assert _stored(test_db, project.id) == STORED

    @pytest.mark.parametrize(
        "plans, fragment",
        [
            ({"name": "x", "spec": SPEC}, "/analysis_plans: must be a list"),
            (["spec"], "/analysis_plans/0: must be an object"),
            ([{"spec": SPEC}], "/analysis_plans/0/name"),
            ([{"name": "   ", "spec": SPEC}], "/analysis_plans/0/name"),
            ([{"name": "x" * 201, "spec": SPEC}], "at most 200 characters"),
            ([{"name": "x", "spec": "{}"}], "/analysis_plans/0/spec: must be an analysis spec object"),
            ([{"name": "x"}], "/analysis_plans/0/spec"),
            ([{"name": "x", "spec": {}}], "/analysis_plans/0/spec"),
            (
                [{"id": "p", "name": "x", "spec": SPEC}, {"id": "p", "name": "y", "spec": SPEC}],
                "duplicate plan id",
            ),
            ([{"id": "", "name": "x", "spec": SPEC}], "/analysis_plans/0/id"),
            ([{"name": f"p{i}", "spec": SPEC} for i in range(51)], "at most 50 plans"),
        ],
    )
    def test_a_malformed_plan_list_is_422(
        self, client, test_db, test_users, auth_headers, test_org, plans, fragment
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        resp = _put(client, project.id, {"analysis_plans": plans}, auth_headers["admin"])
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "invalid_analysis_plan"
        assert any(fragment in e for e in resp.json()["detail"]["errors"]), resp.json()
        assert _stored(test_db, project.id) == STORED

    def test_hash_and_stamps_are_server_owned(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        resp = _put(
            client,
            project.id,
            {
                "analysis_plans": [
                    {
                        "id": "plan-1",
                        "name": "P",
                        "spec": SPEC,
                        "spec_hash": "0" * 64,
                        "saved_at": "2000-01-01T00:00:00+00:00",
                        "saved_by": "someone-else",
                        "extra": "dropped",
                    }
                ]
            },
            auth_headers["org_admin"],
        )
        assert resp.status_code == 200, resp.text
        [plan] = _stored(test_db, project.id)["analysis_plans"]
        assert set(plan) == {"id", "name", "spec", "spec_hash", "saved_at", "saved_by"}
        assert plan["id"] == "plan-1"
        assert plan["spec_hash"] == _hash(SPEC)
        assert plan["saved_by"] == test_users[3].id
        assert not plan["saved_at"].startswith("2000")

    def test_a_rename_keeps_the_stamp_and_a_spec_change_renews_it(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        stamped = {
            "analysis_plans": [
                {
                    "id": "plan-1",
                    "name": "Old name",
                    "spec": SPEC,
                    "spec_hash": _hash(SPEC),
                    "saved_at": "2026-01-01T00:00:00+00:00",
                    "saved_by": test_users[3].id,
                }
            ]
        }
        project = _seed_project(test_db, test_users, test_org, stamped)
        renamed = _put(
            client,
            project.id,
            {"analysis_plans": [{"id": "plan-1", "name": "New name", "spec": SPEC}]},
            auth_headers["contributor"],
        )
        assert renamed.status_code == 200, renamed.text
        [plan] = _stored(test_db, project.id)["analysis_plans"]
        assert plan["name"] == "New name"
        assert plan["saved_at"] == "2026-01-01T00:00:00+00:00"
        assert plan["saved_by"] == test_users[3].id

        changed = {**SPEC, "description": "with a note"}
        resp = _put(
            client,
            project.id,
            {"analysis_plans": [{"id": "plan-1", "name": "New name", "spec": changed}]},
            auth_headers["contributor"],
        )
        assert resp.status_code == 200, resp.text
        [plan] = _stored(test_db, project.id)["analysis_plans"]
        assert plan["spec_hash"] == _hash(changed) != _hash(SPEC)
        assert plan["saved_by"] == test_users[1].id
        assert plan["saved_at"] != "2026-01-01T00:00:00+00:00"

    def test_an_empty_list_or_null_removes_the_plans(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        assert _put(
            client, project.id, {"analysis_plans": [{"name": "P", "spec": SPEC}]}, auth_headers["admin"]
        ).status_code == 200
        assert _put(client, project.id, {"analysis_plans": []}, auth_headers["admin"]).status_code == 200
        assert _stored(test_db, project.id)["analysis_plans"] == []
        assert _put(client, project.id, {"analysis_plans": None}, auth_headers["admin"]).status_code == 200
        stored = _stored(test_db, project.id)
        assert "analysis_plans" not in stored
        assert stored["default_temperature"] == 0.2

    def test_an_annotator_cannot_save_plans(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, copy.deepcopy(STORED))
        resp = _put(
            client, project.id, {"analysis_plans": [{"name": "P", "spec": SPEC}]}, auth_headers["annotator"]
        )
        assert resp.status_code == 403, resp.text
        assert _stored(test_db, project.id) == STORED


# --------------------------------------------------------------------------- #
# PATCH /api/projects/{id} and a run started from a plan (async lane)
# --------------------------------------------------------------------------- #


@pytest.fixture
async def world(async_test_db):
    from tests.fixtures.access_keys import seed_world
    from tests.fixtures.v1 import make_project

    db = async_test_db
    w = await seed_world(db, group=False)
    w["project"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="variants")
    await db.commit()
    return w


async def _stored_async(db, project_id):
    db.expire_all()
    return (
        await db.execute(select(Project.evaluation_config).where(Project.id == project_id))
    ).scalar_one()


@pytest.mark.integration
async def test_patch_validates_and_hashes_plans(async_test_client, async_test_db, world):
    from tests.fixtures.v1 import v1_auth

    project_id = world["project"].id
    member_id = world["member"].id
    bad = {**SPEC, "estimands": "nope"}
    with v1_auth(async_test_db, session_user=world["member"]):
        refused = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"evaluation_config": {"analysis_plans": [{"name": "B", "spec": bad}]}},
        )
        saved = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"evaluation_config": {"analysis_plans": [{"name": "Plan", "spec": SPEC}]}},
        )
        regenerated = await async_test_client.get(
            f"{BASE}/projects/{project_id}/evaluation-config?force_regenerate=true"
        )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "invalid_analysis_plan"
    assert all(e.startswith("/analysis_plans/0/spec") for e in refused.json()["detail"]["errors"])
    assert saved.status_code == 200, saved.text
    [plan] = (await _stored_async(async_test_db, project_id))["analysis_plans"]
    assert plan["spec_hash"] == _hash(SPEC)
    assert plan["saved_by"] == member_id

    # A GET that regenerates the document from the label config keeps them.
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["analysis_plans"] == [plan]
    assert (await _stored_async(async_test_db, project_id))["analysis_plans"] == [plan]


@pytest.mark.integration
async def test_a_run_started_from_a_plan_has_the_plans_hash(
    async_test_client, async_test_db, world
):
    from tests.fixtures.v1 import v1_auth

    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]):
        saved = await async_test_client.patch(
            f"/api/projects/{project.id}",
            json={"evaluation_config": {"analysis_plans": [{"name": "Plan", "spec": SPEC}]}},
        )
        assert saved.status_code == 200, saved.text
        read = await async_test_client.get(f"{BASE}/projects/{project.id}/evaluation-config")
        assert read.status_code == 200, read.text
        [plan] = read.json()["analysis_plans"]

        queued = MagicMock()
        queued.id = "celery-plan-run"
        with patch("routers.analysis.send_task_safe", return_value=queued):
            started = await async_test_client.post(
                f"/api/projects/{project.id}/analysis-runs",
                json={"spec": plan["spec"], "name": plan["name"]},
            )
    assert started.status_code == 202, started.text
    assert started.json()["spec_hash"] == plan["spec_hash"]
    run = (
        await async_test_db.execute(select(AnalysisRun).where(AnalysisRun.id == started.json()["id"]))
    ).scalar_one()
    assert run.spec_hash == plan["spec_hash"] and run.name == "Plan"
