"""Compliance records CRUD (core 2.57, migration 145).

Pinned here: the routes under ``/api/compliance`` for assessments, suite runs
and findings; organization access (editors read and write, admins delete,
everyone else 404); the registration lock and the read-only states; the
suite-run transition table; findings that reference analysis runs and
estimates and come back in full double precision; and the filters by those
references, limited to the caller's organizations.
"""

import math
import uuid

import pytest
from sqlalchemy import select

import compliance_records as records
from models import (
    ComplianceAssessment,
    ComplianceFinding,
    ComplianceSuiteRun,
    LLMModel,
    OrganizationRole,
)
from tests.integration.test_group_visibility import _as_user, _attach, _org, _project, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.flags_on("compliance_records")]

BASE = "/api/compliance"

# Synthetic estimates with full double precision.
ESTIMATE = -14.107355442212345
CI_LOW = -14.226588617309871
CI_HIGH = -13.988122267114819


async def _world(db):
    admin, editor, annotator, outsider = [await _user(db) for _ in range(4)]
    org = await _org(
        db,
        (admin, OrganizationRole.ORG_ADMIN),
        (editor, OrganizationRole.CONTRIBUTOR),
        (annotator, OrganizationRole.ANNOTATOR),
    )
    other_org = await _org(db, (outsider, OrganizationRole.ORG_ADMIN))
    return {
        "admin": admin,
        "editor": editor,
        "annotator": annotator,
        "outsider": outsider,
        "org": org,
        "other_org": other_org,
    }


async def _model(db):
    model = LLMModel(
        id=f"sys-{uuid.uuid4().hex[:8]}",
        name="System under test",
        provider="openai",
        model_type="chat",
        capabilities=["text_generation"],
        is_official=True,
        is_active=True,
    )
    db.add(model)
    await db.commit()
    return model


async def _create_assessment(client, org, **extra):
    body = {
        "organization_id": org.id,
        "title": "Counterfactual fairness check",
        "catalog_version": "2026.11",
        "suites": ["fairness_counterfactual", {"id": "robustness_variants", "version": "1"}],
        "thresholds": {"fairness_counterfactual": {"default": {"op": "within", "bounds": [-2, 2]}}},
        **extra,
    }
    r = await client.post(f"{BASE}/assessments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_run(client, assessment_id, **extra):
    r = await client.post(
        f"{BASE}/assessments/{assessment_id}/suite-runs",
        json={"suite_id": "fairness_counterfactual", "suite_version": "1", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _finding(**extra):
    return {
        "requirement_ref": "art10_bias",
        "metric": "paired_contrast",
        "system_key": "model-a",
        "scope": {"contrast": "variant_b_minus_a", "subgroup": None},
        "n_tasks": 70,
        "n_runs": 3,
        "value": ESTIMATE,
        "ci_low": CI_LOW,
        "ci_high": CI_HIGH,
        "ci_level": 0.9,
        "ci_method": "cluster_two_way",
        "threshold": {"op": "within", "bounds": [-2, 2]},
        "verdict": "fail",
        "details": {"p_adjusted": 0.0012, "family": "primary"},
        "analysis_run_id": "analysis-run-1",
        "analysis_estimate_id": "estimate-1",
        **extra,
    }


async def _set_status(db, assessment_id, *statuses):
    row = await db.get(ComplianceAssessment, assessment_id)
    await db.refresh(row)
    for status in statuses:
        records.transition_assessment(row, status)
    await db.commit()
    return row


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


async def test_contributor_creates_a_draft_and_lists_it(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        created = await _create_assessment(async_test_client, w["org"])
        listed = (await async_test_client.get(f"{BASE}/assessments")).json()
        read = (await async_test_client.get(f"{BASE}/assessments/{created['id']}")).json()
    assert created["status"] == "draft"
    assert created["created_by"] == w["editor"].id
    assert created["thresholds_hash"] is None and created["registered_at"] is None
    assert [a["id"] for a in listed["items"]] == [created["id"]] and listed["total"] == 1
    assert read == created


async def test_status_cannot_be_set_through_the_routes(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["admin"]):
        created = await _create_assessment(async_test_client, w["org"])
        r_create = await async_test_client.post(
            f"{BASE}/assessments",
            json={"organization_id": w["org"].id, "title": "x", "status": "attested"},
        )
        r_patch = await async_test_client.patch(
            f"{BASE}/assessments/{created['id']}", json={"status": "registered"}
        )
        r_flag = await async_test_client.patch(
            f"{BASE}/assessments/{created['id']}", json={"contamination_suspected": False}
        )
    assert r_create.status_code == 422
    assert r_patch.status_code == 422
    assert r_flag.status_code == 422


async def test_other_organizations_and_annotators_see_nothing(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["admin"]):
        created = await _create_assessment(async_test_client, w["org"])
        run = await _create_run(async_test_client, created["id"])
        await async_test_client.post(
            f"{BASE}/suite-runs/{run['id']}/findings", json={"findings": [_finding()]}
        )
    for who in ("outsider", "annotator"):
        with _as_user(w[who]):
            c = async_test_client
            assert (await c.get(f"{BASE}/assessments/{created['id']}")).status_code == 404
            assert (await c.get(f"{BASE}/suite-runs/{run['id']}")).status_code == 404
            assert (await c.get(f"{BASE}/assessments")).json()["total"] == 0
            by_run = await c.get(f"{BASE}/findings", params={"analysis_run_id": "analysis-run-1"})
            assert by_run.status_code == 200 and by_run.json()["items"] == []
            r = await c.patch(f"{BASE}/assessments/{created['id']}", json={"title": "taken"})
            assert r.status_code == 404
            r = await c.post(
                f"{BASE}/assessments",
                json={"organization_id": w["org"].id, "title": "Not mine"},
            )
            assert r.status_code == 404


async def test_superadmin_sees_every_organization(async_test_client, async_test_db):
    w = await _world(async_test_db)
    root = await _user(async_test_db, superadmin=True)
    with _as_user(w["admin"]):
        created = await _create_assessment(async_test_client, w["org"])
    with _as_user(root):
        listed = (await async_test_client.get(
            f"{BASE}/assessments", params={"organization_id": w["org"].id}
        )).json()
    assert [a["id"] for a in listed["items"]] == [created["id"]]


async def test_superadmin_gets_404_for_an_unknown_organization(async_test_client, async_test_db):
    root = await _user(async_test_db, superadmin=True)
    with _as_user(root):
        r = await async_test_client.post(
            f"{BASE}/assessments",
            json={"organization_id": str(uuid.uuid4()), "title": "Mistyped organization"},
        )
    assert r.status_code == 404


async def test_targets_are_checked(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    model = await _model(db)
    own = await _project(db, w["editor"])
    foreign = await _project(db, w["outsider"], private=True)
    await _attach(db, foreign, w["other_org"], w["outsider"])
    with _as_user(w["editor"]):
        ok = await _create_assessment(
            async_test_client, w["org"], system_model_id=model.id, project_id=own.id,
            release_id="release-2026-1",
        )
        bad_model = await async_test_client.post(
            f"{BASE}/assessments",
            json={"organization_id": w["org"].id, "title": "x", "system_model_id": "nope"},
        )
        bad_project = await async_test_client.post(
            f"{BASE}/assessments",
            json={"organization_id": w["org"].id, "title": "x", "project_id": foreign.id},
        )
        other_org = await _create_assessment(async_test_client, w["org"])
    with _as_user(w["outsider"]):
        theirs = await _create_assessment(async_test_client, w["other_org"])
    with _as_user(w["editor"]):
        bad_supersede = await async_test_client.post(
            f"{BASE}/assessments",
            json={"organization_id": w["org"].id, "title": "x", "supersedes_id": theirs["id"]},
        )
        good_supersede = await _create_assessment(
            async_test_client, w["org"], supersedes_id=other_org["id"]
        )
    assert ok["system_model_id"] == model.id and ok["project_id"] == own.id
    assert ok["release_id"] == "release-2026-1"
    assert bad_model.status_code == 422
    assert bad_project.status_code == 422
    assert bad_supersede.status_code == 422
    assert good_supersede["supersedes_id"] == other_org["id"]


async def test_registration_fixes_suites_thresholds_and_target(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        created = await _create_assessment(async_test_client, w["org"])
        draft_edit = await async_test_client.patch(
            f"{BASE}/assessments/{created['id']}",
            json={"thresholds": {"fairness_counterfactual": {"chosen": {"bounds": [-3, 3]}}}},
        )
    assert draft_edit.status_code == 200
    row = await _set_status(async_test_db, created["id"], "registered")
    assert row.thresholds_hash == records.canonical_sha256(draft_edit.json()["thresholds"])
    with _as_user(w["editor"]):
        c = async_test_client
        locked = await c.patch(f"{BASE}/assessments/{created['id']}", json={"suites": []})
        same = await c.patch(
            f"{BASE}/assessments/{created['id']}",
            json={"thresholds": draft_edit.json()["thresholds"], "title": "Renamed"},
        )
        read = (await c.get(f"{BASE}/assessments/{created['id']}")).json()
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "assessment_registered"
    assert same.status_code == 200 and same.json()["title"] == "Renamed"
    assert read["status"] == "registered" and read["registered_at"] is not None
    assert read["thresholds_hash"] == row.thresholds_hash


async def test_withdrawn_assessment_is_read_only(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["admin"]):
        created = await _create_assessment(async_test_client, w["org"])
        run = await _create_run(async_test_client, created["id"])
    await _set_status(async_test_db, created["id"], "withdrawn")
    with _as_user(w["admin"]):
        c = async_test_client
        edit = await c.patch(f"{BASE}/assessments/{created['id']}", json={"title": "x"})
        new_run = await c.post(
            f"{BASE}/assessments/{created['id']}/suite-runs", json={"suite_id": "s"}
        )
        findings = await c.post(
            f"{BASE}/suite-runs/{run['id']}/findings", json={"findings": [_finding()]}
        )
        delete = await c.delete(f"{BASE}/assessments/{created['id']}")
    for response in (edit, new_run, findings):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "assessment_closed"
    assert delete.status_code == 409


async def test_only_admins_delete_and_only_drafts(async_test_client, async_test_db):
    db = async_test_db
    w = await _world(db)
    with _as_user(w["editor"]):
        draft = await _create_assessment(async_test_client, w["org"])
        run = await _create_run(async_test_client, draft["id"])
        await async_test_client.post(
            f"{BASE}/suite-runs/{run['id']}/findings", json={"findings": [_finding()]}
        )
        forbidden = await async_test_client.delete(f"{BASE}/assessments/{draft['id']}")
        registered = await _create_assessment(async_test_client, w["org"])
    await _set_status(db, registered["id"], "registered")
    with _as_user(w["admin"]):
        refused = await async_test_client.delete(f"{BASE}/assessments/{registered['id']}")
        deleted = await async_test_client.delete(f"{BASE}/assessments/{draft['id']}")
    assert forbidden.status_code == 403
    assert refused.status_code == 409
    assert deleted.status_code == 204
    db.expire_all()
    assert await db.get(ComplianceAssessment, draft["id"]) is None
    assert (
        await db.execute(select(ComplianceSuiteRun).where(ComplianceSuiteRun.id == run["id"]))
    ).scalar_one_or_none() is None
    assert (
        await db.execute(
            select(ComplianceFinding).where(ComplianceFinding.assessment_id == draft["id"])
        )
    ).scalars().all() == []


# ---------------------------------------------------------------------------
# Suite runs
# ---------------------------------------------------------------------------


async def test_suite_run_follows_the_transition_table(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        c = async_test_client
        assessment = await _create_assessment(c, w["org"])
        run = await _create_run(
            c, assessment["id"], analysis_run_ids=["analysis-run-1"], parameters={"design": "d1"}
        )
        skip = await c.patch(f"{BASE}/suite-runs/{run['id']}", json={"status": "succeeded"})
        started = await c.patch(
            f"{BASE}/suite-runs/{run['id']}",
            json={"status": "running", "celery_task_id": "celery-1", "inputs_hash": "abc"},
        )
        done = await c.patch(f"{BASE}/suite-runs/{run['id']}", json={"status": "succeeded"})
        after = await c.patch(f"{BASE}/suite-runs/{run['id']}", json={"error": "late"})
        findings = await c.post(
            f"{BASE}/suite-runs/{run['id']}/findings", json={"findings": [_finding()]}
        )
        listed = (await c.get(f"{BASE}/assessments/{assessment['id']}/suite-runs")).json()
    assert run["status"] == "queued" and run["analysis_run_ids"] == ["analysis-run-1"]
    assert run["parameters"] == {"design": "d1"} and run["submission_ids"] == []
    assert skip.status_code == 409 and skip.json()["detail"]["code"] == "invalid_transition"
    assert started.status_code == 200
    assert started.json()["started_at"] is not None and started.json()["finished_at"] is None
    assert started.json()["celery_task_id"] == "celery-1"
    assert done.json()["status"] == "succeeded" and done.json()["finished_at"] is not None
    assert after.status_code == 409 and after.json()["detail"]["code"] == "suite_run_finished"
    assert findings.status_code == 409
    assert [r["id"] for r in listed["items"]] == [run["id"]]


async def test_suite_runs_of_registered_assessments_are_kept(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["admin"]):
        assessment = await _create_assessment(async_test_client, w["org"])
        run = await _create_run(async_test_client, assessment["id"])
    await _set_status(async_test_db, assessment["id"], "registered")
    with _as_user(w["admin"]):
        refused = await async_test_client.delete(f"{BASE}/suite-runs/{run['id']}")
    assert refused.status_code == 409


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


async def test_findings_reference_analysis_runs_and_estimates(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        c = async_test_client
        assessment = await _create_assessment(c, w["org"])
        run = await _create_run(c, assessment["id"], analysis_run_ids=["analysis-run-1"])
        created = await c.post(
            f"{BASE}/suite-runs/{run['id']}/findings",
            json={
                "findings": [
                    _finding(),
                    _finding(
                        system_key="model-b", verdict="pass", value=0.3138821234567891,
                        ci_low=-0.1, ci_high=0.7, analysis_estimate_id="estimate-2",
                    ),
                    _finding(
                        metric="sensitivity_gate", system_key="model-b", verdict="informative",
                        analysis_run_id="analysis-run-2", analysis_estimate_id="estimate-3",
                    ),
                ]
            },
        )
        by_run = (
            await c.get(f"{BASE}/findings", params={"analysis_run_id": "analysis-run-1"})
        ).json()
        by_estimate = (
            await c.get(f"{BASE}/findings", params={"analysis_estimate_id": "estimate-2"})
        ).json()
        by_assessment = (
            await c.get(
                f"{BASE}/findings",
                params={"assessment_id": assessment["id"], "system_key": "model-b"},
            )
        ).json()
        failing = (
            await c.get(f"{BASE}/suite-runs/{run['id']}/findings", params={"verdict": "fail"})
        ).json()
        one = (await c.get(f"{BASE}/findings/{created.json()['items'][0]['id']}")).json()
    assert created.status_code == 201
    items = created.json()["items"]
    assert all(i["assessment_id"] == assessment["id"] for i in items)
    assert {i["analysis_estimate_id"] for i in by_run["items"]} == {"estimate-1", "estimate-2"}
    assert [i["value"] for i in by_estimate["items"]] == [0.3138821234567891]
    assert {i["metric"] for i in by_assessment["items"]} == {"paired_contrast", "sensitivity_gate"}
    assert [i["system_key"] for i in failing["items"]] == ["model-a"]
    # Double precision survives the database and the JSON round trip exactly.
    assert one["value"] == ESTIMATE and one["ci_low"] == CI_LOW and one["ci_high"] == CI_HIGH
    assert one["ci_level"] == 0.9 and one["n_tasks"] == 70
    assert one["details"] == {"p_adjusted": 0.0012, "family": "primary"}
    assert one["scope"] == {"contrast": "variant_b_minus_a", "subgroup": None}


async def test_findings_list_needs_a_reference(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        r = await async_test_client.get(f"{BASE}/findings", params={"verdict": "pass"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"verdict": "passed"},
        {"ci_low": 2.0, "ci_high": 1.0},
        {"ci_level": 1.0},
        {"n_tasks": -1},
        {"n_tasks": 2**31},
        {"n_runs": 2**31},
        {"value": math.inf},
        {"requirement_ref": ""},
        {"unknown_field": 1},
    ],
)
async def test_invalid_findings_are_refused_as_a_whole(async_test_client, async_test_db, bad):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        c = async_test_client
        assessment = await _create_assessment(c, w["org"])
        run = await _create_run(c, assessment["id"])
        r = await c.post(
            f"{BASE}/suite-runs/{run['id']}/findings",
            content=_json_with_inf({"findings": [_finding(), _finding(**bad)]}),
            headers={"Content-Type": "application/json"},
        )
        listed = (await c.get(f"{BASE}/suite-runs/{run['id']}/findings")).json()
    assert r.status_code == 422
    assert listed["total"] == 0


def _json_with_inf(body):
    import json

    return json.dumps(body, allow_nan=True)


async def test_out_of_range_integers_are_refused(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        c = async_test_client
        assessment = await _create_assessment(c, w["org"])
        run = await _create_run(c, assessment["id"])
        item = (
            await c.post(f"{BASE}/suite-runs/{run['id']}/findings", json={"findings": [_finding()]})
        ).json()["items"][0]
        patched = await c.patch(f"{BASE}/findings/{item['id']}", json={"n_runs": 2**31})
        paged = await c.get(
            f"{BASE}/suite-runs/{run['id']}/findings", params={"offset": 2**63}
        )
        kept = (await c.get(f"{BASE}/findings/{item['id']}")).json()
    assert patched.status_code == 422
    assert paged.status_code == 422
    assert kept["n_runs"] == 3


async def test_finding_edits_and_deletes_while_the_run_is_open(async_test_client, async_test_db):
    w = await _world(async_test_db)
    with _as_user(w["editor"]):
        c = async_test_client
        assessment = await _create_assessment(c, w["org"])
        run = await _create_run(c, assessment["id"])
        items = (
            await c.post(
                f"{BASE}/suite-runs/{run['id']}/findings",
                json={"findings": [_finding(), _finding(metric="flip_rate")]},
            )
        ).json()["items"]
        edited = await c.patch(
            f"{BASE}/findings/{items[0]['id']}",
            json={"verdict": "inconclusive", "details": {"note": "gate failed"}},
        )
        crossed = await c.patch(f"{BASE}/findings/{items[0]['id']}", json={"ci_low": 0.0})
        nulled = await c.patch(f"{BASE}/findings/{items[0]['id']}", json={"verdict": None})
        forbidden = await c.delete(f"{BASE}/findings/{items[1]['id']}")
    with _as_user(w["admin"]):
        removed = await c.delete(f"{BASE}/findings/{items[1]['id']}")
        await c.patch(f"{BASE}/suite-runs/{run['id']}", json={"status": "cancelled"})
        frozen = await c.patch(f"{BASE}/findings/{items[0]['id']}", json={"verdict": "pass"})
        frozen_delete = await c.delete(f"{BASE}/findings/{items[0]['id']}")
        listed = (await c.get(f"{BASE}/suite-runs/{run['id']}/findings")).json()
    assert edited.status_code == 200
    assert edited.json()["verdict"] == "inconclusive"
    assert edited.json()["value"] == ESTIMATE
    assert crossed.status_code == 422
    assert nulled.status_code == 422
    assert forbidden.status_code == 403
    assert removed.status_code == 204
    assert frozen.status_code == 409 and frozen_delete.status_code == 409
    assert [i["id"] for i in listed["items"]] == [items[0]["id"]]
    assert listed["items"][0]["verdict"] == "inconclusive"


async def test_access_keys_never_reach_compliance_routes():
    from app.core.key_routes import PLATFORM_OWNER, resolve_rule

    for method, template in (
        ("GET", "/api/compliance/assessments"),
        ("POST", "/api/compliance/suite-runs/{suite_run_id}/findings"),
        ("GET", "/api/compliance/findings"),
    ):
        rule = resolve_rule(PLATFORM_OWNER, method, template)
        assert rule is not None and not rule.allowed
