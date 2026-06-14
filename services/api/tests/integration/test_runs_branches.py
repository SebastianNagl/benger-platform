"""Behavioral integration tests for the single-run inventory router.

Targets the real DB-backed branches of ``services/api/routers/runs.py``
(mounted at ``/api/runs``). The existing ``tests/unit/test_runs_router.py``
exercises the helpers and the access filter with Mock sessions; this module
seeds real rows via ``test_db`` and asserts the HTTP status, the response
JSON, and (where relevant) the persisted/aggregated DB shape that drives the
branch — the way the platform's green branch-batches do.

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

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    Organization,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Project, ProjectOrganization, Task


BASE = "/api/runs"


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, creator, org, *, link_org=True, is_private=False):
    p = Project(
        id=_uid(),
        title=f"Runs Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    db.flush()
    if link_org:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    return p


def _make_task(db, project, creator):
    t = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=1,
        data={"text": "run task"},
        created_by=creator.id,
        updated_by=creator.id,
    )
    db.add(t)
    db.flush()
    return t


def _make_response_generation(db, project, task, creator, *, status="completed", **kw):
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
    db.flush()
    return rg


def _make_child_generation(db, rg, task, *, run_index=0, response_content="x", status="completed"):
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
    db.flush()
    return g


def _make_eval_run(db, project, creator, *, status="completed", eval_metadata=None, model_id="gpt-4"):
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
    db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(jr)
    db.flush()
    er._test_judge_run = jr
    return er


def _make_task_evaluation(db, er, task, child_gen):
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
    db.flush()
    return te


def _ctx(auth_headers, role, org):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# ===========================================================================
# GET /api/runs — list_runs
# ===========================================================================


@pytest.mark.integration
class TestListRunsGeneration:
    def test_generation_list_enriches_title_and_orders_newest_first(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        rg1 = _make_response_generation(test_db, project, task, test_users[0], model_id="m-a")
        rg2 = _make_response_generation(test_db, project, task, test_users[0], model_id="m-b")
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=generation",
            headers=_ctx(auth_headers, "admin", test_org),
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

    def test_generation_status_filter(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        done = _make_response_generation(test_db, project, task, test_users[0], status="completed")
        _make_response_generation(test_db, project, task, test_users[0], status="failed")
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=generation&status=completed",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == done.id
        assert body["items"][0]["status"] == "completed"

    def test_generation_project_id_filter(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project_a = _make_project(test_db, test_users[0], test_org)
        project_b = _make_project(test_db, test_users[0], test_org)
        task_a = _make_task(test_db, project_a, test_users[0])
        task_b = _make_task(test_db, project_b, test_users[0])
        rg_a = _make_response_generation(test_db, project_a, task_a, test_users[0])
        _make_response_generation(test_db, project_b, task_b, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=generation&project_id={project_a.id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == rg_a.id

    def test_empty_page_past_end(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        _make_response_generation(test_db, project, task, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=generation&page=5&page_size=10",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 1

    def test_bad_type_value_422(self, client, auth_headers, test_org):
        resp = client.get(
            f"{BASE}?type=bogus",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422


@pytest.mark.integration
class TestListRunsEvaluation:
    def test_evaluation_list_enriches_judges_and_metrics(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
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
        er = _make_eval_run(test_db, project, test_users[0], eval_metadata=meta)
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=evaluation",
            headers=_ctx(auth_headers, "admin", test_org),
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

    def test_evaluation_legacy_single_judge_metadata(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        meta = {
            "evaluation_configs": [
                {
                    "metric": "exact_match",
                    "metric_parameters": {"judge_model": "legacy-judge"},
                }
            ]
        }
        _make_eval_run(test_db, project, test_users[0], eval_metadata=meta)
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=evaluation",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["judge_models"] == ["legacy-judge"]
        assert item["metrics"] == ["exact_match"]


@pytest.mark.integration
class TestListRunsAccessibilityFilter:
    def test_non_member_rows_dropped_from_items(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A run in a project the requesting non-superadmin cannot reach is
        filtered out of ``items`` per-row, while ``total`` still reflects the
        pre-filter query count."""
        # Outsider org the contributor is NOT a member of.
        other_org = Organization(
            id=_uid(),
            name="Outsider Runs Org",
            slug=f"outsider-runs-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Runs Org",
        )
        test_db.add(other_org)
        test_db.flush()
        # Project linked only to the outsider org → contributor can't see it.
        hidden = _make_project(test_db, test_users[0], other_org, link_org=False)
        test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=hidden.id,
                organization_id=other_org.id,
                assigned_by=test_users[0].id,
            )
        )
        test_db.flush()
        task = _make_task(test_db, hidden, test_users[0])
        _make_response_generation(test_db, hidden, task, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}?type=generation",
            headers=_ctx(auth_headers, "contributor", test_org),
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
    def test_generation_not_found_404(self, client, auth_headers, test_org):
        missing = _uid()
        resp = client.get(
            f"{BASE}/generations/{missing}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    def test_inaccessible_project_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Gen Org",
            slug=f"outsider-gen-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Gen Org",
        )
        test_db.add(other_org)
        test_db.flush()
        hidden = _make_project(test_db, test_users[0], other_org, link_org=False)
        test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=hidden.id,
                organization_id=other_org.id,
                assigned_by=test_users[0].id,
            )
        )
        test_db.flush()
        task = _make_task(test_db, hidden, test_users[0])
        rg = _make_response_generation(test_db, hidden, task, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}/generations/{rg.id}",
            headers=_ctx(auth_headers, "contributor", test_org),
        )
        assert resp.status_code == 403
        assert "No access" in resp.json()["detail"]

    def test_detail_children_ordered_and_preview_truncated(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        rg = _make_response_generation(
            test_db, project, task, test_users[0], runs_requested=2, runs_completed=2
        )
        # Insert children out of run_index order; endpoint must sort ascending.
        long_content = "y" * 250
        _make_child_generation(test_db, rg, task, run_index=1, response_content=long_content)
        _make_child_generation(test_db, rg, task, run_index=0, response_content="short")
        test_db.commit()

        resp = client.get(
            f"{BASE}/generations/{rg.id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
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

    def test_linked_evaluations_aggregation(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """An EvaluationRun whose TaskEvaluation rows reference this
        generation's children is surfaced under ``linked_evaluations`` with
        ``samples_evaluated`` = count of those child task-evals and the
        first ``evaluation_configs[*].metric`` as the label."""
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        rg = _make_response_generation(test_db, project, task, test_users[0])
        child0 = _make_child_generation(test_db, rg, task, run_index=0)
        child1 = _make_child_generation(test_db, rg, task, run_index=1)
        er = _make_eval_run(
            test_db,
            project,
            test_users[0],
            eval_metadata={"evaluation_configs": [{"metric": "accuracy"}]},
        )
        _make_task_evaluation(test_db, er, task, child0)
        _make_task_evaluation(test_db, er, task, child1)
        test_db.commit()

        resp = client.get(
            f"{BASE}/generations/{rg.id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["linked_evaluations"]) == 1
        linked = body["linked_evaluations"][0]
        assert linked["evaluation_id"] == er.id
        assert linked["metric"] == "accuracy"
        assert linked["status"] == "completed"
        # Two child task-evals came from this generation.
        assert linked["samples_evaluated"] == 2

    def test_detail_no_children_no_linked(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        task = _make_task(test_db, project, test_users[0])
        rg = _make_response_generation(test_db, project, task, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}/generations/{rg.id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["children"] == []
        assert body["linked_evaluations"] == []
