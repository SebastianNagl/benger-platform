"""Behavioral integration tests for the single-run inventory router.

Targets the real DB-backed branches of ``services/api/routers/runs.py``
(mounted at ``/api/runs``). The router was migrated to the async DB lane
(``Depends(get_async_db)``), so these tests seed real rows through the
``async_test_db`` AsyncSession and drive the HTTP surface through
``async_test_client`` — the sync ``client``/``test_db`` fixtures only override
``get_db`` (not ``get_async_db``), so a row written there would be invisible to
the migrated handler's async connection.

Auth: ``require_user`` is a sync dependency (``Depends(get_db)``) and cannot
see rows seeded into the async test transaction, so it's overridden per-test
to return an auth ``User`` built from the seeded DB user. The handler under
test still exercises the real async DB path end-to-end; only the auth
resolution is stubbed.

Endpoints / branches exercised:

- ``GET /api/runs`` (list_runs):
    * ``type=generation`` happy path with ``project_title`` enrichment +
      newest-first ordering.
    * ``type=evaluation`` happy path with ``judge_models`` / ``metrics`` /
      ``samples_evaluated`` enrichment from ``eval_metadata``.
    * ``project_id`` filter, ``status`` filter.
    * per-row accessibility filter: a non-superadmin only sees runs in
      projects they can reach (rows in an unreachable project are dropped
      from ``items`` while ``total`` reflects the pre-filter count).
    * empty page (page past the end).
    * ``type`` is a required, constrained query param (422 on a bad value).

- ``GET /api/runs/generations/{id}`` (get_generation_run):
    * 404 for a missing ResponseGeneration.
    * 403 when the parent's project is inaccessible to a non-superadmin.
    * happy path: child Generation rows ordered by ``run_index``, the
      ``has_response`` / ``response_preview`` truncation branch, and the
      ``linked_evaluations`` aggregation (an EvaluationRun whose
      TaskEvaluation rows reference this generation's children, with
      ``samples_evaluated`` = count of those child task-evals).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Project, ProjectOrganization, Task


BASE = "/api/runs"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override require_user to return an auth User mirroring db_user.

    The runs handlers only read current_user.id and current_user.is_superadmin
    so a minimal auth User suffices.
    """
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


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Runs User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name="Org"):
    o = Organization(
        id=_uid(),
        name=f"{name}-{_uid()[:8]}",
        slug=f"{name.lower()}-{_uid()[:8]}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(o)
    await db.flush()
    return o


async def _add_membership(db, user_id, org_id, role="CONTRIBUTOR", is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=is_active,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _make_project(db, creator, org, *, link_org=True, is_private=False):
    p = Project(
        id=_uid(),
        title=f"Runs Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    if link_org:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()
    return p


async def _make_task(db, project, creator):
    t = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=1,
        data={"text": "run task"},
        created_by=creator.id,
        updated_by=creator.id,
    )
    db.add(t)
    await db.flush()
    return t


async def _make_response_generation(db, project, task, creator, *, status="completed", **kw):
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id if task else None,
        model_id=kw.pop("model_id", "gpt-4"),
        status=status,
        created_by=creator.id,
        **kw,
    )
    db.add(rg)
    await db.flush()
    return rg


async def _make_child_generation(
    db, rg, task, *, run_index=0, response_content="x", status="completed"
):
    g = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id if task else None,
        model_id=rg.model_id,
        run_index=run_index,
        case_data="{}",
        response_content=response_content,
        status=status,
        parse_status="success",
    )
    db.add(g)
    await db.flush()
    return g


async def _make_eval_run(
    db, project, creator, *, status="completed", eval_metadata=None, model_id="gpt-4"
):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy"],
        metrics={"accuracy": 0.9},
        status=status,
        samples_evaluated=5,
        eval_metadata=eval_metadata or {"type": "automated"},
        created_by=creator.id,
    )
    db.add(er)
    await db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(jr)
    await db.flush()
    er._test_judge_run = jr
    return er


async def _make_task_evaluation(db, er, task, child_gen):
    te = TaskEvaluation(
        id=_uid(),
        evaluation_id=er.id,
        judge_run_id=er._test_judge_run.id,
        task_id=task.id,
        generation_id=child_gen.id,
        annotation_id=None,
        field_name="answer",
        answer_type="choices",
        metrics={"score": 0.9},
        passed=True,
        ground_truth={"value": "Ja"},
        prediction={"value": "Ja"},
    )
    db.add(te)
    await db.flush()
    return te


def _ctx(org):
    return {"X-Organization-Context": org.id}


# ===========================================================================
# GET /api/runs — list_runs
# ===========================================================================


@pytest.mark.integration
class TestListRunsGeneration:
    @pytest.mark.asyncio
    async def test_generation_list_enriches_title_and_orders_newest_first(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        rg1 = await _make_response_generation(
            async_test_db, project, task, admin, model_id="m-a"
        )
        rg2 = await _make_response_generation(
            async_test_db, project, task, admin, model_id="m-b"
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=generation&project_id={project.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        ids = {item["id"] for item in body["items"]}
        assert {rg1.id, rg2.id} <= ids
        for item in body["items"]:
            assert item["type"] == "generation"
            assert item["project_title"] == project.title
            assert item["project_id"] == project.id

    @pytest.mark.asyncio
    async def test_generation_status_filter(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        done = await _make_response_generation(
            async_test_db, project, task, admin, status="completed"
        )
        await _make_response_generation(
            async_test_db, project, task, admin, status="failed"
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=generation&status=completed&project_id={project.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == done.id
        assert body["items"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_generation_project_id_filter(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project_a = await _make_project(async_test_db, admin, org)
        project_b = await _make_project(async_test_db, admin, org)
        task_a = await _make_task(async_test_db, project_a, admin)
        task_b = await _make_task(async_test_db, project_b, admin)
        rg_a = await _make_response_generation(async_test_db, project_a, task_a, admin)
        await _make_response_generation(async_test_db, project_b, task_b, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=generation&project_id={project_a.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == rg_a.id

    @pytest.mark.asyncio
    async def test_empty_page_past_end(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        await _make_response_generation(async_test_db, project, task, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=generation&page=5&page_size=10&project_id={project.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 1

    @pytest.mark.asyncio
    async def test_bad_type_value_422(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"{BASE}?type=bogus")
        assert resp.status_code == 422


@pytest.mark.integration
class TestListRunsEvaluation:
    @pytest.mark.asyncio
    async def test_evaluation_list_enriches_judges_and_metrics(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        meta = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_quality",
                    "metric_parameters": {
                        "judges": [
                            {"judge_model_id": "judge-a", "runs": 1},
                            {"judge_model_id": "judge-b", "runs": 1},
                        ]
                    },
                },
                {"metric": "accuracy", "metric_parameters": {}},
            ]
        }
        er = await _make_eval_run(async_test_db, project, admin, eval_metadata=meta)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=evaluation&project_id={project.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == er.id
        assert item["type"] == "evaluation"
        assert item["judge_models"] == ["judge-a", "judge-b"]
        assert item["metrics"] == ["llm_judge_quality", "accuracy"]
        assert item["samples_evaluated"] == 5
        assert item["project_title"] == project.title

    @pytest.mark.asyncio
    async def test_evaluation_legacy_single_judge_metadata(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        meta = {
            "evaluation_configs": [
                {
                    "metric": "exact_match",
                    "metric_parameters": {"judge_model": "legacy-judge"},
                }
            ]
        }
        await _make_eval_run(async_test_db, project, admin, eval_metadata=meta)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}?type=evaluation&project_id={project.id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["judge_models"] == ["legacy-judge"]
        assert item["metrics"] == ["exact_match"]


@pytest.mark.integration
class TestListRunsAccessibilityFilter:
    @pytest.mark.asyncio
    async def test_non_member_rows_dropped_from_items(
        self, async_test_client, async_test_db
    ):
        """A run in a project the requesting non-superadmin cannot reach is
        filtered out of ``items`` per-row, while ``total`` still reflects the
        pre-filter query count."""
        owner = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        member_org = await _make_org(async_test_db, name="Member")
        await _add_membership(
            async_test_db, contributor.id, member_org.id, role="CONTRIBUTOR"
        )
        # Outsider org the contributor is NOT a member of.
        other_org = await _make_org(async_test_db, name="Outsider")
        # Project linked only to the outsider org → contributor can't see it.
        hidden = await _make_project(async_test_db, owner, other_org)
        task = await _make_task(async_test_db, hidden, owner)
        await _make_response_generation(async_test_db, hidden, task, owner)
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                f"{BASE}?type=generation&project_id={hidden.id}",
                headers=_ctx(member_org),
            )
        assert resp.status_code == 200
        body = resp.json()
        # total reflects the unfiltered query; the inaccessible row is dropped.
        assert body["total"] == 1
        assert body["items"] == []


# ===========================================================================
# GET /api/runs/generations/{id} — get_generation_run
# ===========================================================================


@pytest.mark.integration
class TestGetGenerationRun:
    @pytest.mark.asyncio
    async def test_generation_not_found_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        missing = _uid()
        with _as_user(admin):
            resp = await async_test_client.get(f"{BASE}/generations/{missing}")
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_inaccessible_project_403(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        member_org = await _make_org(async_test_db, name="Member")
        await _add_membership(
            async_test_db, contributor.id, member_org.id, role="CONTRIBUTOR"
        )
        other_org = await _make_org(async_test_db, name="Outsider")
        hidden = await _make_project(async_test_db, owner, other_org)
        task = await _make_task(async_test_db, hidden, owner)
        rg = await _make_response_generation(async_test_db, hidden, task, owner)
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                f"{BASE}/generations/{rg.id}",
                headers=_ctx(member_org),
            )
        assert resp.status_code == 403
        assert "No access" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_detail_children_ordered_and_preview_truncated(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        rg = await _make_response_generation(
            async_test_db, project, task, admin, runs_requested=2, runs_completed=2
        )
        # Insert children out of run_index order; endpoint must sort ascending.
        long_content = "y" * 250
        await _make_child_generation(
            async_test_db, rg, task, run_index=1, response_content=long_content
        )
        await _make_child_generation(
            async_test_db, rg, task, run_index=0, response_content="short"
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"{BASE}/generations/{rg.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == rg.id
        assert body["project_title"] == project.title
        assert [c["run_index"] for c in body["children"]] == [0, 1]
        # run_index 0 → short content, not truncated.
        assert body["children"][0]["has_response"] is True
        assert body["children"][0]["response_preview"] == "short"
        # run_index 1 → 250 chars, truncated to 200 + ellipsis.
        preview = body["children"][1]["response_preview"]
        assert preview.endswith("…")
        assert len(preview) == 201

    @pytest.mark.asyncio
    async def test_linked_evaluations_aggregation(
        self, async_test_client, async_test_db
    ):
        """An EvaluationRun whose TaskEvaluation rows reference this
        generation's children is surfaced under ``linked_evaluations`` with
        ``samples_evaluated`` = count of those child task-evals and the
        first ``evaluation_configs[*].metric`` as the label."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, task, admin)
        child0 = await _make_child_generation(async_test_db, rg, task, run_index=0)
        child1 = await _make_child_generation(async_test_db, rg, task, run_index=1)
        er = await _make_eval_run(
            async_test_db,
            project,
            admin,
            eval_metadata={"evaluation_configs": [{"metric": "accuracy"}]},
        )
        await _make_task_evaluation(async_test_db, er, task, child0)
        await _make_task_evaluation(async_test_db, er, task, child1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"{BASE}/generations/{rg.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["linked_evaluations"]) == 1
        linked = body["linked_evaluations"][0]
        assert linked["evaluation_id"] == er.id
        assert linked["metric"] == "accuracy"
        assert linked["status"] == "completed"
        # Two child task-evals came from this generation.
        assert linked["samples_evaluated"] == 2

    @pytest.mark.asyncio
    async def test_detail_no_children_no_linked(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        task = await _make_task(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, task, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"{BASE}/generations/{rg.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["children"] == []
        assert body["linked_evaluations"] == []
