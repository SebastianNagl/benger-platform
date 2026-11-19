"""Analysis runs in the counts and listings: ``analysis_count`` on the
project detail and list, the dashboard's ``analyses_count`` and its
corrected key names, ``GET /api/runs?type=analysis`` and the report
statistics.

Synthetic projects and runs only; no worker runs (the rows are written as a
finished run stores them).
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import AnalysisRun
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import make_project, v1_auth

SPEC = {"spec_version": 1, "name": "synthetic", "inputs": {"designs": ["d"]}}

# Rows written in one test transaction share now(); explicit, increasing
# creation times keep the newest-first order of the listings deterministic.
_CLOCK = itertools.count()
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _created_at() -> datetime:
    return _EPOCH + timedelta(minutes=next(_CLOCK))


@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=False)
    w["project"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="only analyses")
    w["sibling"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="sibling")
    other = await seed_world(db, group=False)
    w["foreign"] = await make_project(db, other["admin"].id, org_id=other["org"].id, title="foreign")
    await db.commit()
    return w


async def _run(db, project, user, *, status="completed", name="run", inputs=None) -> AnalysisRun:
    spec = dict(SPEC)
    if inputs:
        spec["inputs"] = {"designs": ["d"], "projects": [{"project_id": p, "designs": ["d"]} for p in inputs]}
    run = AnalysisRun(
        id=str(uuid.uuid4()), project_id=project.id, created_by=user.id, name=name, status=status,
        spec=spec, normalized_spec=spec, spec_hash=uuid.uuid4().hex * 2, spec_version=1,
        engine_version="1.0.0", frame_rows=12 if status == "completed" else None,
        estimates_count=3 if status == "completed" else 0, created_at=_created_at(),
    )
    db.add(run)
    await db.flush()
    return run


async def _seed_runs(db, w):
    """Project with three completed runs (one reading a foreign project) and
    a pending and a failed one; a completed run in the sibling."""
    p, admin = w["project"], w["admin"]
    runs = {
        "a": await _run(db, p, admin, name="a"),
        "b": await _run(db, p, admin, name="b"),
        "cross": await _run(db, p, admin, name="cross", inputs=[w["foreign"].id]),
        "pending": await _run(db, p, admin, status="pending", name="pending"),
        "failed": await _run(db, p, admin, status="failed", name="failed"),
        "sibling": await _run(db, w["sibling"], admin, name="sibling"),
    }
    await db.commit()
    return runs


# --------------------------------------------------------------------------- #
# project detail and list
# --------------------------------------------------------------------------- #


async def test_a_project_with_only_analysis_runs_shows_its_count_on_detail_and_list(
    async_test_client, async_test_db, world
):
    db = async_test_db
    await _seed_runs(db, world)
    empty = await make_project(db, world["admin"].id, org_id=world["org"].id, title="empty")
    await db.commit()
    pid = world["project"].id
    with v1_auth(db, session_user=world["member"]):
        detail = await async_test_client.get(f"/api/projects/{pid}")
        listing = await async_test_client.get("/api/projects/", params={"page_size": 100})
    assert detail.status_code == 200, detail.text
    # completed runs only; the cross-project run counts for its own project
    assert detail.json()["analysis_count"] == 3
    assert detail.json()["evaluation_count"] == 0
    assert listing.status_code == 200, listing.text
    by_id = {item["id"]: item for item in listing.json()["items"]}
    assert by_id[pid]["analysis_count"] == detail.json()["analysis_count"]
    assert by_id[world["sibling"].id]["analysis_count"] == 1
    assert by_id[empty.id]["analysis_count"] == 0


def test_batch_and_detail_counts_agree(test_db):
    """The list's grouped count (count_analysis_runs_by_project over many
    ids) and the detail (calculate_project_stats) give the same
    analysis_count, with and without a precomputed project summary."""
    from models import ProjectSummary
    from project_models import Project
    from project_schemas import ProjectResponse
    from routers.projects.helpers import calculate_project_stats, count_analysis_runs_by_project
    from tests.fixtures.access_keys import seed_world_sync

    w = seed_world_sync(test_db, group=False)
    projects = []
    for n in (0, 1, 4):
        project = Project(
            id=str(uuid.uuid4()), title=f"p{n}", created_by=w["admin"].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        for i in range(n):
            test_db.add(AnalysisRun(
                id=str(uuid.uuid4()), project_id=project.id, created_by=w["admin"].id, name=f"r{i}",
                status="completed", spec=SPEC, normalized_spec=SPEC, spec_hash="h" * 64,
                spec_version=1, engine_version="1.0.0",
            ))
        test_db.add(AnalysisRun(
            id=str(uuid.uuid4()), project_id=project.id, created_by=w["admin"].id, name="running",
            status="running", spec=SPEC, normalized_spec=SPEC, spec_hash="h" * 64,
            spec_version=1, engine_version="1.0.0",
        ))
        projects.append(project)
    # one project read from a precomputed summary, the others live
    test_db.add(ProjectSummary(
        project_id=projects[2].id, period="overall", total_tasks=0, labeled_tasks=0,
        annotations_count=0, evaluation_pairs_count=0, computed_at=datetime.now(timezone.utc),
    ))
    test_db.flush()

    batch = count_analysis_runs_by_project(test_db, [p.id for p in projects])
    for project, expected in zip(projects, (0, 1, 4)):
        response = ProjectResponse(
            id=project.id, title=project.title, created_by=project.created_by,
            created_at=datetime.now(timezone.utc),
        )
        calculate_project_stats(test_db, project.id, response, project=project)
        assert response.analysis_count == expected
        assert batch[project.id] == expected


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #


async def test_dashboard_counts_analyses_and_keeps_the_old_keys_as_aliases(
    async_test_client, async_test_db, world
):
    db = async_test_db
    await _seed_runs(db, world)
    with patch("routers.dashboard.cache") as cache:
        cache.get.return_value = None
        with v1_auth(db, session_user=world["member"]):
            member = (await async_test_client.get("/api/dashboard/stats")).json()
        with v1_auth(db, session_user=world["superadmin"]):
            superadmin = (await async_test_client.get("/api/dashboard/stats")).json()
    assert member["scope"] == "overview"
    # the member's org holds the project (3 completed) and the sibling (1)
    assert member["analyses_count"] == 4
    for stats in (member, superadmin):
        assert stats["projects_with_generations"] == stats["generations_count"]
        assert stats["projects_with_evaluations"] == stats["evaluations_count"]
    # the superadmin sees every listed project, the foreign one included
    assert superadmin["analyses_count"] >= 4


async def test_dashboard_leaves_out_runs_of_deleted_projects(async_test_client, async_test_db, world):
    db = async_test_db
    await _seed_runs(db, world)
    world["sibling"].deleted_at = datetime.now(timezone.utc)
    await db.commit()
    with patch("routers.dashboard.cache") as cache:
        cache.get.return_value = None
        with v1_auth(db, session_user=world["member"]):
            stats = (await async_test_client.get("/api/dashboard/stats")).json()
    assert stats["analyses_count"] == 3


# --------------------------------------------------------------------------- #
# /api/runs?type=analysis
# --------------------------------------------------------------------------- #


async def test_runs_lists_analysis_runs_with_their_summary(async_test_client, async_test_db, world):
    db = async_test_db
    runs = await _seed_runs(db, world)
    with v1_auth(db, session_user=world["superadmin"]):
        resp = await async_test_client.get(
            "/api/runs", params={"type": "analysis", "project_id": world["project"].id}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    # newest first
    assert [item["name"] for item in body["items"]] == ["failed", "pending", "cross", "b", "a"]
    a = next(item for item in body["items"] if item["id"] == runs["a"].id)
    assert a["type"] == "analysis"
    assert a["project_title"] == "only analyses"
    assert a["status"] == "completed"
    assert a["frame_rows"] == 12
    assert a["estimates_count"] == 3
    assert a["spec_hash"] == runs["a"].spec_hash
    assert a["engine_version"] == "1.0.0"


async def test_runs_pages_and_filters_analysis_runs_by_project_and_status(
    async_test_client, async_test_db, world
):
    db = async_test_db
    await _seed_runs(db, world)

    async def get(**params):
        resp = await async_test_client.get("/api/runs", params={"type": "analysis", **params})
        assert resp.status_code == 200, resp.text
        return resp.json()

    with v1_auth(db, session_user=world["superadmin"]):
        first = await get(project_id=world["project"].id, page=1, page_size=2)
        second = await get(project_id=world["project"].id, page=2, page_size=2)
        third = await get(project_id=world["project"].id, page=3, page_size=2)
        completed = await get(project_id=world["project"].id, status="completed")
        failed = await get(status="failed", project_id=world["project"].id)
        sibling = await get(project_id=world["sibling"].id)
    assert first["total"] == second["total"] == third["total"] == 5
    names = [i["name"] for page in (first, second, third) for i in page["items"]]
    assert names == ["failed", "pending", "cross", "b", "a"]
    assert [len(p["items"]) for p in (first, second, third)] == [2, 2, 1]
    assert completed["total"] == 3 and {i["name"] for i in completed["items"]} == {"a", "b", "cross"}
    assert [i["name"] for i in failed["items"]] == ["failed"]
    assert [i["name"] for i in sibling["items"]] == ["sibling"]


async def test_runs_leaves_out_analysis_runs_the_viewer_cannot_open(async_test_client, async_test_db, world):
    """A member does not see the run that reads a foreign project (the run
    page answers 404 for it) nor runs of projects outside their org, and the
    total counts only what is listed, so the pages add up."""
    db = async_test_db
    runs = await _seed_runs(db, world)
    other_owner = await seed_world(db, group=False)
    await _run(db, world["foreign"], other_owner["admin"], name="foreign")
    await db.commit()
    with v1_auth(db, session_user=world["member"]):
        resp = await async_test_client.get("/api/runs", params={"type": "analysis", "page_size": 2})
        rest = await async_test_client.get("/api/runs", params={"type": "analysis", "page_size": 2, "page": 3})
        cross = await async_test_client.get(f"/api/analysis-runs/{runs['cross'].id}")
    body = resp.json()
    assert body["total"] == 5  # a, b, pending, failed, sibling
    assert len(body["items"]) == 2
    assert [i["name"] for i in rest.json()["items"]] == ["a"]
    assert cross.status_code == 404
    with v1_auth(db, session_user=world["member"]):
        everything = await async_test_client.get("/api/runs", params={"type": "analysis", "page_size": 200})
    names = {i["name"] for i in everything.json()["items"]}
    assert names == {"a", "b", "pending", "failed", "sibling"}
    with v1_auth(db, session_user=world["outsider"]):
        outsider = await async_test_client.get("/api/runs", params={"type": "analysis"})
    assert outsider.json() == {"items": [], "total": 0, "page": 1, "page_size": 25}


async def test_runs_rejects_an_unknown_type(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]):
        resp = await async_test_client.get("/api/runs", params={"type": "coding"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# report statistics
# --------------------------------------------------------------------------- #


def test_report_statistics_count_completed_analysis_runs(test_db):
    from project_models import Project
    from report_service import get_report_statistics, get_report_statistics_batch
    from report_snapshot import build_report_snapshot
    from tests.fixtures.access_keys import seed_world_sync

    w = seed_world_sync(test_db, group=False)
    projects = []
    for n in (2, 0):
        project = Project(
            id=str(uuid.uuid4()), title=f"r{n}", created_by=w["admin"].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        for status in ["completed"] * n + ["failed"]:
            test_db.add(AnalysisRun(
                id=str(uuid.uuid4()), project_id=project.id, created_by=w["admin"].id, name="r",
                status=status, spec=SPEC, normalized_spec=SPEC, spec_hash="h" * 64,
                spec_version=1, engine_version="1.0.0",
            ))
        projects.append(project)
    test_db.flush()

    batch = get_report_statistics_batch(test_db, [p.id for p in projects])
    for project, expected in zip(projects, (2, 0)):
        single = get_report_statistics(test_db, project.id)
        assert single["analysis_count"] == expected
        assert batch[project.id] == single
        assert build_report_snapshot(test_db, project.id)["statistics"]["analysis_count"] == expected
