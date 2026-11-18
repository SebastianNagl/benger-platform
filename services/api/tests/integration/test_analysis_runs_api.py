"""The analysis-run API: spec validation, starting runs, reading runs,
estimates and the frame snapshot, and the /api/v1 read routes.

The worker body is covered in services/workers/tests/integration/
test_analysis_run_e2e.py; here ``send_task_safe`` and the storage URL are
patched so only the endpoints run.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from models import AnalysisEstimate, AnalysisRun, OrganizationRole
from services import api_key_service as svc
from tests.fixtures.access_keys import make_membership, make_user, seed_world
from tests.fixtures.v1 import bearer, make_project, v1_auth

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


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=False)
    annotator = make_user(name="Annotator")
    db.add(annotator)
    await db.flush()
    db.add(make_membership(annotator.id, w["org"].id, OrganizationRole.ANNOTATOR))
    w["annotator"] = annotator
    w["project"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="variants")
    other = await seed_world(db, group=False)
    other["project"] = await make_project(db, other["admin"].id, org_id=other["org"].id, title="other")
    w["other"] = other
    await db.commit()
    return w


def _queued(task_id="celery-analysis-1"):
    result = MagicMock()
    result.id = task_id
    return patch("routers.analysis.send_task_safe", return_value=result)


async def _start(client, project_id, spec=SPEC, **extra):
    return await client.post(f"/api/projects/{project_id}/analysis-runs", json={"spec": spec, **extra})


async def _completed_run(db, project, user, estimates=3, frame_key=None) -> AnalysisRun:
    from analysis.spec import normalize_spec, spec_hash

    normalized = normalize_spec(SPEC)
    run = AnalysisRun(
        id=str(uuid.uuid4()), project_id=project.id, created_by=user.id, name="done", status="completed",
        spec=SPEC, normalized_spec=normalized, spec_hash=spec_hash(normalized), spec_version=1,
        engine_version="1.0.0", frame_hash="f" * 64, frame_rows=12, estimates_count=estimates,
        frame_object_key=frame_key, frame_sha256="a" * 64 if frame_key else None,
        warnings=["one warning"], fits=[{"estimand": "role", "scope": "pooled", "rows": 12}],
        library_versions={"numpy": "x"}, frame_counts={"observations": 12},
    )
    db.add(run)
    await db.flush()
    for i in range(estimates):
        db.add(AnalysisEstimate(
            run_id=run.id, position=i, estimand_id="role" if i < 2 else "other", contrast_id="role",
            estimator="fe_ols", kind="linear", outcome="share", scope="pooled" if i == 0 else f"system=s{i}",
            scope_values={} if i == 0 else {"system": f"s{i}"}, status="ok", estimate=-2.5 + i, std_error=0.5,
            p_value=0.01 * (i + 1), ci_level=0.95, ci_lower=-3.0, ci_upper=-2.0, equivalent=True,
            tost=[{"lower": -3, "upper": 3, "equivalent": True}], family="primary" if i == 0 else None,
            p_adjusted=0.03 if i == 0 else None, adjustments=[], n_obs=12, n_clusters=[3], k_params=1,
            conventions={"ssc": "statsmodels"},
        ))
    await db.commit()
    return run


# --------------------------------------------------------------------------- #
# engine and spec validation
# --------------------------------------------------------------------------- #


async def test_engine_info(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await async_test_client.get("/api/analysis/engine")
    assert r.status_code == 200
    body = r.json()
    assert body["engine_version"] and body["spec_version"] == 1
    assert "fe_ols" in body["estimators"] and "if" in body["expression_functions"]
    assert body["spec_schema"]["title"] == "BenGER analysis spec"
    assert body["default_conventions"]["ssc"] == "statsmodels"


async def test_validate_spec(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]):
        ok = await async_test_client.post("/api/analysis/specs/validate", json={"spec": SPEC})
        bad = await async_test_client.post(
            "/api/analysis/specs/validate",
            json={"spec": {**SPEC, "measures": {"x": {"kind": "expression", "expr": "open('f')"}}}},
        )
        missing = await async_test_client.post("/api/analysis/specs/validate", json={})
    assert ok.status_code == 200 and ok.json()["valid"] is True
    assert len(ok.json()["spec_hash"]) == 64
    assert ok.json()["normalized_spec"]["estimands"][0]["conventions"]["ssc"] == "statsmodels"
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "invalid_analysis_spec"
    assert any("unknown function" in e for e in bad.json()["detail"]["errors"])
    assert missing.status_code == 422


# --------------------------------------------------------------------------- #
# starting runs
# --------------------------------------------------------------------------- #


async def test_contributor_starts_a_run(async_test_client, async_test_db, world):
    project = world["project"]
    with v1_auth(async_test_db, session_user=world["member"]), _queued() as send:
        r = await _start(async_test_client, project.id, name="first analysis")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending" and body["name"] == "first analysis"
    assert r.headers["location"] == f"/api/analysis-runs/{body['id']}"
    send.assert_called_once()
    assert send.call_args.args[0] == "tasks.run_analysis"
    assert send.call_args.kwargs["args"] == [body["id"]]
    run = (await async_test_db.execute(select(AnalysisRun).where(AnalysisRun.id == body["id"]))).scalar_one()
    assert run.celery_task_id == "celery-analysis-1" and run.created_by == world["member"].id
    assert run.spec == SPEC and run.normalized_spec["estimands"][0]["vcov"]["type"] == "cluster"
    assert run.spec_hash == body["spec_hash"]


async def test_the_spec_name_is_the_default_run_name(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]), _queued():
        r = await _start(async_test_client, world["project"].id)
    assert r.json()["name"] == "role swap"


async def test_starting_needs_edit_rights_and_a_valid_spec(async_test_client, async_test_db, world):
    project = world["project"]
    with _queued() as send:
        with v1_auth(async_test_db, session_user=world["annotator"]):
            denied = await _start(async_test_client, project.id)
        with v1_auth(async_test_db, session_user=world["member"]):
            invalid = await _start(async_test_client, project.id, spec={"spec_version": 1})
            no_spec = await async_test_client.post(f"/api/projects/{project.id}/analysis-runs", json={})
            bad_name = await _start(async_test_client, project.id, name="  ")
            unknown = await _start(async_test_client, str(uuid.uuid4()))
        with v1_auth(async_test_db, session_user=world["other"]["admin"]):
            foreign = await _start(async_test_client, project.id)
    assert denied.status_code == 403
    assert invalid.status_code == 422 and invalid.json()["detail"]["errors"]
    assert no_spec.status_code == 422 and bad_name.status_code == 422
    assert unknown.status_code == 404
    assert foreign.status_code in (403, 404)
    send.assert_not_called()
    count = (await async_test_db.execute(select(AnalysisRun).where(AnalysisRun.project_id == project.id))).all()
    assert count == []


async def test_an_unreachable_queue_fails_the_run(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]), patch(
        "routers.analysis.send_task_safe", side_effect=RuntimeError("broker down at redis://secret")
    ):
        r = await _start(async_test_client, world["project"].id)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "analysis_queue_unavailable"
    run = (
        await async_test_db.execute(select(AnalysisRun).where(AnalysisRun.project_id == world["project"].id))
    ).scalar_one()
    assert run.status == "failed" and "secret" not in run.error_message


# --------------------------------------------------------------------------- #
# reading runs, estimates and the frame
# --------------------------------------------------------------------------- #


async def test_list_and_read_runs(async_test_client, async_test_db, world):
    run = await _completed_run(async_test_db, world["project"], world["admin"])
    with v1_auth(async_test_db, session_user=world["annotator"]):
        listed = await async_test_client.get(f"/api/projects/{world['project'].id}/analysis-runs")
        one = await async_test_client.get(f"/api/analysis-runs/{run.id}")
    assert listed.status_code == 200 and listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["id"] == run.id and "normalized_spec" not in item
    detail = one.json()
    assert detail["normalized_spec"]["name"] == "role swap" and detail["warnings"] == ["one warning"]
    assert detail["frame_available"] is False and detail["fits"][0]["estimand"] == "role"


async def test_runs_are_invisible_outside_the_project(async_test_client, async_test_db, world):
    run = await _completed_run(async_test_db, world["project"], world["admin"])
    with v1_auth(async_test_db, session_user=world["outsider"]):
        listed = await async_test_client.get(f"/api/projects/{world['project'].id}/analysis-runs")
        one = await async_test_client.get(f"/api/analysis-runs/{run.id}")
        estimates = await async_test_client.get(f"/api/analysis-runs/{run.id}/estimates")
        missing = await async_test_client.get(f"/api/analysis-runs/{uuid.uuid4()}")
    assert listed.status_code in (403, 404)
    assert one.status_code == 404 and estimates.status_code == 404 and missing.status_code == 404


async def test_estimates_in_engine_order_with_filters(async_test_client, async_test_db, world):
    run = await _completed_run(async_test_db, world["project"], world["admin"], estimates=4)
    with v1_auth(async_test_db, session_user=world["member"]):
        everything = await async_test_client.get(f"/api/analysis-runs/{run.id}/estimates")
        role = await async_test_client.get(f"/api/analysis-runs/{run.id}/estimates", params={"estimand_id": "role"})
        pooled = await async_test_client.get(f"/api/analysis-runs/{run.id}/estimates", params={"scope": "pooled", "family": "primary"})
        page = await async_test_client.get(f"/api/analysis-runs/{run.id}/estimates", params={"limit": 2, "offset": 1})
    items = everything.json()["items"]
    assert [i["position"] for i in items] == [0, 1, 2, 3]
    assert items[0]["tost"][0]["equivalent"] is True and items[0]["p_adjusted"] == 0.03
    assert [i["position"] for i in role.json()["items"]] == [0, 1]
    assert [i["position"] for i in pooled.json()["items"]] == [0]
    assert [i["position"] for i in page.json()["items"]] == [1, 2]


async def test_frame_download_needs_full_data_access(async_test_client, async_test_db, world):
    stored = await _completed_run(async_test_db, world["project"], world["admin"], frame_key="analysis/2026/11/f.parquet")
    pending = await _completed_run(async_test_db, world["project"], world["admin"])
    with patch(
        "storage.object_storage.object_storage.get_download_url", return_value="https://storage.example/frame"
    ) as url:
        with v1_auth(async_test_db, session_user=world["annotator"]):
            denied = await async_test_client.get(f"/api/analysis-runs/{stored.id}/frame")
        with v1_auth(async_test_db, session_user=world["member"]):
            redirect = await async_test_client.get(f"/api/analysis-runs/{stored.id}/frame", follow_redirects=False)
            as_json = await async_test_client.get(f"/api/analysis-runs/{stored.id}/frame", params={"json": True})
            not_stored = await async_test_client.get(f"/api/analysis-runs/{pending.id}/frame")
    assert denied.status_code == 403
    assert redirect.status_code == 302 and redirect.headers["location"] == "https://storage.example/frame"
    assert as_json.json() == {"url": "https://storage.example/frame", "frame_hash": "f" * 64, "frame_sha256": "a" * 64}
    assert not_stored.status_code == 404
    assert url.call_args.args[0] == "analysis/2026/11/f.parquet"
    assert url.call_args.kwargs["response_content_type"] == "application/vnd.apache.parquet"


# --------------------------------------------------------------------------- #
# /api/v1
# --------------------------------------------------------------------------- #


async def _key(db, world, scopes):
    body = {"name": "k", "org_role": "CONTRIBUTOR", "scopes": scopes}
    return (await svc.create_org_key(db, world["admin"].id, world["org"].id, body))[1]


async def test_v1_reads_runs_and_estimates_with_results_read(async_test_client, async_test_db, world):
    db = async_test_db
    first = await _completed_run(db, world["project"], world["admin"], estimates=3)
    second = await _completed_run(db, world["project"], world["admin"], estimates=1)
    key = await _key(db, world, ["results:read"])
    with v1_auth(db):
        c = async_test_client
        page1 = await c.get(f"/api/v1/projects/{world['project'].id}/analysis-runs", params={"limit": 1}, headers=bearer(key))
        assert page1.status_code == 200, page1.text
        cursor = page1.json()["next_cursor"]
        page2 = await c.get(
            f"/api/v1/projects/{world['project'].id}/analysis-runs", params={"limit": 1, "cursor": cursor}, headers=bearer(key)
        )
        run = await c.get(f"/api/v1/analysis-runs/{first.id}", headers=bearer(key))
        est1 = await c.get(f"/api/v1/analysis-runs/{first.id}/estimates", params={"limit": 2}, headers=bearer(key))
        est2 = await c.get(
            f"/api/v1/analysis-runs/{first.id}/estimates",
            params={"limit": 2, "cursor": est1.json()["next_cursor"]},
            headers=bearer(key),
        )
        bad_cursor = await c.get(f"/api/v1/analysis-runs/{first.id}/estimates", params={"cursor": "x"}, headers=bearer(key))
    ids = [page1.json()["items"][0]["id"], page2.json()["items"][0]["id"]]
    assert sorted(ids) == sorted([first.id, second.id]) and page2.json()["next_cursor"] is None
    assert run.json()["normalized_spec"]["name"] == "role swap" and "spec" not in run.json()
    assert [e["position"] for e in est1.json()["items"]] == [0, 1]
    assert [e["position"] for e in est2.json()["items"]] == [2] and est2.json()["next_cursor"] is None
    assert bad_cursor.status_code == 400


async def test_v1_needs_the_scope_and_hides_other_organizations(async_test_client, async_test_db, world):
    db = async_test_db
    run = await _completed_run(db, world["project"], world["admin"])
    without_scope = await _key(db, world, ["projects:read"])
    foreign = await _key(db, world["other"], ["results:read"])
    with v1_auth(db):
        c = async_test_client
        r1 = await c.get(f"/api/v1/analysis-runs/{run.id}", headers=bearer(without_scope))
        r2 = await c.get(f"/api/v1/projects/{world['project'].id}/analysis-runs", headers=bearer(without_scope))
        r3 = await c.get(f"/api/v1/analysis-runs/{run.id}", headers=bearer(foreign))
        r4 = await c.get(f"/api/v1/analysis-runs/{run.id}/estimates", headers=bearer(foreign))
        r5 = await c.get(f"/api/v1/projects/{world['project'].id}/analysis-runs", headers=bearer(foreign))
    assert r1.status_code == 403 and r1.json()["error"]["code"] == "insufficient_scope"
    assert r2.status_code == 403
    assert r3.status_code == 404 and r3.json()["error"]["code"] == "analysis_run_not_found"
    assert r4.status_code == 404 and r5.status_code == 404
