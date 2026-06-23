"""
Deep integration tests for evaluation results, per-sample analysis, and export.

Covers routers/evaluations/results/ (core.py, distributions.py):
- GET /evaluations/results/{project_id} — automated + human results
- POST /evaluations/export/{project_id} — JSON and CSV export
- GET /evaluations/{evaluation_id}/samples — per-sample with filters
- GET /evaluations/{evaluation_id}/metrics/{metric}/distribution — histogram, quartiles
- GET /evaluations/{evaluation_id}/confusion-matrix — classification confusion matrix

The results router package is now fully async (every endpoint is
``async def`` with ``db: AsyncSession = Depends(get_async_db)`` and
``await check_project_accessible_async(...)``). These tests therefore seed
real rows via ``async_test_db`` and drive the surface through
``async_test_client``. ``require_user`` is overridden per-request to return a
superadmin auth User matching the seeded owner (the sync auth dependency
can't see the async test transaction); a superadmin satisfies
``check_project_accessible_async`` so no org-context header is needed. The
two access-denied tests instead use a non-superadmin override plus a patched
access helper that returns False, to exercise the 403 branch deterministically.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, *, is_superadmin=None):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin if is_superadmin is None else is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_owner(db):
    """Seed a superadmin owner + a minimal org, independent of sync fixtures."""
    org = Organization(
        id=_uid(),
        name=f"EvalOrg {uuid.uuid4().hex[:6]}",
        display_name=f"EvalOrg {uuid.uuid4().hex[:6]}",
        slug=f"evalorg-{uuid.uuid4().hex[:8]}",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    owner = User(
        id=_uid(),
        username=f"eval-owner-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Owner",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.flush()
    return owner, org


async def _setup(db, admin, org, *, num_tasks=5, with_human=False, with_generations=True):
    """Build a complete evaluation data graph (async)."""
    project = Project(
        id=_uid(),
        title=f"EvalResult {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    await db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Eval text #{i}", "question": f"Q{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    # Annotations
    annotations = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    await db.flush()

    # Generations
    generations = []
    if with_generations:
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            rg = ResponseGeneration(
                id=_uid(), project_id=project.id, model_id=model_id,
                status="completed", created_by=admin.id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(rg)
            await db.flush()
            for i, t in enumerate(tasks):
                gen = Generation(
                    id=_uid(), generation_id=rg.id, task_id=t.id,
                    model_id=model_id, run_index=i,
                    case_data=json.dumps(t.data),
                    response_content=f"Answer from {model_id} for task {i}",
                    label_config_version="v1", status="completed",
                )
                db.add(gen)
                generations.append(gen)
        await db.flush()

    # Evaluation runs with per-sample results
    eval_runs = []
    task_evals = []
    for model_id in ["gpt-4o", "claude-3-sonnet"]:
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": 0.80, "f1_score": 0.75},
            status="completed", samples_evaluated=num_tasks,
            has_sample_results=True,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(er)
        await db.flush()
        eval_runs.append(er)

        # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; use the
        # catch-all judge-run shape that orphan backfill uses.
        judge_run = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        db.add(judge_run)
        await db.flush()
        er._test_judge_run = judge_run

        # Per-sample TaskEvaluations
        model_gens = [g for g in generations if g.model_id == model_id]
        for i, t in enumerate(tasks):
            gen_id = model_gens[i].id if i < len(model_gens) else None
            accuracy_val = 1.0 if i % 3 != 0 else 0.0
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id,
                judge_run_id=judge_run.id,
                task_id=t.id,
                generation_id=gen_id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if accuracy_val == 1.0 else "Nein"},
                metrics={"accuracy": accuracy_val, "f1": 0.8 + (i * 0.02)},
                passed=accuracy_val == 1.0,
                confidence_score=0.9 - (i * 0.05),
                processing_time_ms=100 + i * 10,
            )
            db.add(te)
            task_evals.append(te)
    await db.flush()

    # Human evaluation sessions
    human_sessions = []
    if with_human:
        hs = HumanEvaluationSession(
            id=_uid(), project_id=project.id,
            evaluator_id=admin.id,
            session_type="likert", status="completed",
            items_evaluated=3, total_items=num_tasks,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(hs)
        await db.flush()
        human_sessions.append(hs)

        # Likert evaluations
        for dim in ["fluency", "accuracy", "relevance"]:
            for rating_val in [3, 4, 5]:
                le = LikertScaleEvaluation(
                    id=_uid(), session_id=hs.id,
                    task_id=tasks[0].id,
                    response_id="resp-1",
                    dimension=dim, rating=rating_val,
                )
                db.add(le)
        await db.flush()

        # Preference rankings
        pr = PreferenceRanking(
            id=_uid(), session_id=hs.id,
            task_id=tasks[0].id,
            response_a_id="resp-a", response_b_id="resp-b",
            winner="a", confidence=0.85,
        )
        db.add(pr)
        pr2 = PreferenceRanking(
            id=_uid(), session_id=hs.id,
            task_id=tasks[1].id,
            response_a_id="resp-a", response_b_id="resp-b",
            winner="b", confidence=0.7,
        )
        db.add(pr2)
        await db.flush()

    await db.commit()
    return {
        "owner": admin,
        "project": project,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "task_evals": task_evals,
        "human_sessions": human_sessions,
    }


async def _seeded(db, **kwargs):
    """Seed an owner + org, then the full graph; return (data, owner)."""
    owner, org = await _make_owner(db)
    data = await _setup(db, owner, org, **kwargs)
    return data, owner


# ===================================================================
# EVALUATION RESULTS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationResultsDeep:
    """GET /api/evaluations/results/{project_id}"""

    @pytest.mark.asyncio
    async def test_results_automated_only(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=False)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?include_human=false",
            )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert all(r["results"]["type"] == "automated" for r in results)

    @pytest.mark.asyncio
    async def test_results_human_only(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=True)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?include_automated=false",
            )
        assert resp.status_code == 200
        results = resp.json()
        human_types = [r["results"]["type"] for r in results if r["results"]["type"].startswith("human")]
        assert len(human_types) >= 1

    @pytest.mark.asyncio
    async def test_results_both_automated_and_human(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=True)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}",
            )
        assert resp.status_code == 200
        results = resp.json()
        types = {r["results"]["type"] for r in results}
        assert "automated" in types

    @pytest.mark.asyncio
    async def test_results_with_limit(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?limit=1",
            )
        assert resp.status_code == 200
        results = resp.json()
        # Limited to 1 automated result
        automated = [r for r in results if r["results"]["type"] == "automated"]
        assert len(automated) <= 1

    @pytest.mark.asyncio
    async def test_results_empty_project(self, async_test_client, async_test_db):
        owner, org = await _make_owner(async_test_db)
        project = Project(
            id=_uid(), title="Empty Eval", created_by=owner.id,
            label_config="<View/>",
        )
        async_test_db.add(project)
        await async_test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=org.id, assigned_by=owner.id,
        )
        async_test_db.add(po)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{project.id}",
            )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_results_likert_aggregation(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=True)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?include_automated=false",
            )
        assert resp.status_code == 200
        results = resp.json()
        likert = [r for r in results if r["results"]["type"] == "human_likert"]
        if likert:
            dims = likert[0]["results"]["dimensions"]
            assert "fluency" in dims
            assert "accuracy" in dims
            assert "relevance" in dims
            # Average of 3, 4, 5 = 4.0
            assert dims["fluency"]["average_rating"] == pytest.approx(4.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_results_preference_aggregation(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=True)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?include_automated=false",
            )
        assert resp.status_code == 200
        results = resp.json()
        prefs = [r for r in results if r["results"]["type"] == "human_preference"]
        if prefs:
            counts = prefs[0]["results"]["counts"]
            assert "a" in counts or "b" in counts
            assert prefs[0]["results"]["total_comparisons"] == 2

    @pytest.mark.asyncio
    async def test_results_access_denied(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        # Non-superadmin user + denied access helper exercises the 403 branch.
        with _as_user(owner, is_superadmin=False), patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}",
            )
        assert resp.status_code == 403


# ===================================================================
# EVALUATION EXPORT
# ===================================================================

@pytest.mark.integration
class TestExportEvaluationResultsDeep:
    """POST /api/evaluations/export/{project_id}"""

    @pytest.mark.asyncio
    async def test_export_json_with_metrics(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=json",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project"].id
        assert "results" in body
        assert len(body["results"]) >= 1

    @pytest.mark.asyncio
    async def test_export_csv_format(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=csv",
            )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert "timestamp" in lines[0]
        assert len(lines) >= 2  # header + data

    @pytest.mark.asyncio
    async def test_export_csv_with_human_data(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, with_human=True)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=csv",
            )
        assert resp.status_code == 200
        # Should include human evaluation rows
        content = resp.text
        # Human likert or preference data should be present
        assert len(content.strip().split("\n")) >= 2

    @pytest.mark.asyncio
    async def test_export_empty_project(self, async_test_client, async_test_db):
        owner, org = await _make_owner(async_test_db)
        project = Project(
            id=_uid(), title="Empty Export", created_by=owner.id,
            label_config="<View/>",
        )
        async_test_db.add(project)
        await async_test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=org.id, assigned_by=owner.id,
        )
        async_test_db.add(po)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{project.id}?format=json",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []


# ===================================================================
# PER-SAMPLE RESULTS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationSamples:
    """GET /api/evaluations/{evaluation_id}/samples"""

    @pytest.mark.asyncio
    async def test_get_samples_basic(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5

    @pytest.mark.asyncio
    async def test_get_samples_filter_by_passed(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?passed=true",
            )
        assert resp.status_code == 200
        body = resp.json()
        # All returned should be passed
        for item in body["items"]:
            assert item["passed"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_filter_by_failed(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?passed=false",
            )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["passed"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_filter_by_field_name(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?field_name=answer",
            )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["field_name"] == "answer"

    @pytest.mark.asyncio
    async def test_get_samples_pagination(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=10)
        eval_id = data["eval_runs"][0].id

        # Page 1
        with _as_user(owner):
            resp1 = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?page=1&page_size=3",
            )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["items"]) == 3
        assert body1["has_next"] == True  # noqa: E712
        assert body1["total"] == 10

        # Page 2
        with _as_user(owner):
            resp2 = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?page=2&page_size=3",
            )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 3

        # Ensure different items
        ids1 = {item["id"] for item in body1["items"]}
        ids2 = {item["id"] for item in body2["items"]}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_get_samples_nonexistent_evaluation(self, async_test_client, async_test_db):
        owner, _org = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/nonexistent-eval-id/samples",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_samples_response_structure(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples?page_size=1",
            )
        assert resp.status_code == 200
        body = resp.json()
        item = body["items"][0]
        assert "id" in item
        assert "evaluation_id" in item
        assert "task_id" in item
        assert "field_name" in item
        assert "ground_truth" in item
        assert "prediction" in item
        assert "metrics" in item
        assert "passed" in item


# ===================================================================
# METRIC DISTRIBUTION
# ===================================================================

@pytest.mark.integration
class TestMetricDistribution:
    """GET /api/evaluations/{evaluation_id}/metrics/{metric}/distribution"""

    @pytest.mark.asyncio
    async def test_distribution_accuracy(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=10)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/metrics/accuracy/distribution",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric_name"] == "accuracy"
        assert "mean" in body
        assert "median" in body
        assert "std" in body
        assert "min" in body
        assert "max" in body
        assert "quartiles" in body
        assert "histogram" in body
        assert body["min"] >= 0.0
        assert body["max"] <= 1.0

    @pytest.mark.asyncio
    async def test_distribution_f1(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/metrics/f1/distribution",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric_name"] == "f1"
        # Histogram should have 10 buckets
        assert len(body["histogram"]) == 10

    @pytest.mark.asyncio
    async def test_distribution_filter_by_field(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=6)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/metrics/accuracy/distribution?field_name=answer",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_distribution_nonexistent_metric(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/metrics/nonexistent_metric/distribution",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_distribution_nonexistent_evaluation(self, async_test_client, async_test_db):
        owner, _org = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/nonexistent/metrics/accuracy/distribution",
            )
        assert resp.status_code == 404


# ===================================================================
# CONFUSION MATRIX
# ===================================================================

@pytest.mark.integration
class TestConfusionMatrix:
    """GET /api/evaluations/{evaluation_id}/confusion-matrix"""

    @pytest.mark.asyncio
    async def test_confusion_matrix_basic(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=6)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["field_name"] == "answer"
        assert "labels" in body
        assert "matrix" in body
        assert "accuracy" in body
        # Should have labels "ja" and "nein"
        assert len(body["labels"]) >= 1

    @pytest.mark.asyncio
    async def test_confusion_matrix_metrics(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "precision_per_class" in body
        assert "recall_per_class" in body
        assert "f1_per_class" in body
        assert 0 <= body["accuracy"] <= 1.0

    @pytest.mark.asyncio
    async def test_confusion_matrix_nonexistent_field(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/confusion-matrix?field_name=nonexistent",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_confusion_matrix_access_denied(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        eval_id = data["eval_runs"][0].id
        # Non-superadmin user + denied access helper exercises the 403 branch.
        with _as_user(owner, is_superadmin=False), patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_confusion_matrix_nonexistent_eval(self, async_test_client, async_test_db):
        owner, _org = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/nonexistent/confusion-matrix?field_name=answer",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_confusion_matrix_labels_lowercase(self, async_test_client, async_test_db):
        """Labels in the confusion matrix should be normalized to lowercase."""
        data, owner = await _seeded(async_test_db, num_tasks=8)
        eval_id = data["eval_runs"][0].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/confusion-matrix?field_name=answer",
            )
        assert resp.status_code == 200
        body = resp.json()
        for label in body["labels"]:
            assert label == label.lower()


# ===================================================================
# MULTIPLE EVALUATION RUNS
# ===================================================================

@pytest.mark.integration
class TestMultipleEvaluationRuns:
    """Test behavior with multiple evaluation runs for the same project."""

    @pytest.mark.asyncio
    async def test_results_multiple_models(self, async_test_client, async_test_db):
        """Results should include data from all models."""
        data, owner = await _seeded(async_test_db, num_tasks=5)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}",
            )
        assert resp.status_code == 200
        results = resp.json()
        # Should have results from both gpt-4o and claude-3-sonnet
        assert len([r for r in results if r["results"]["type"] == "automated"]) >= 2

    @pytest.mark.asyncio
    async def test_samples_from_second_run(self, async_test_client, async_test_db):
        """Per-sample results for the second evaluation run."""
        data, owner = await _seeded(async_test_db, num_tasks=5)
        eval_id = data["eval_runs"][1].id  # claude-3-sonnet
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/samples",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5

    @pytest.mark.asyncio
    async def test_distribution_from_second_run(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db, num_tasks=8)
        eval_id = data["eval_runs"][1].id
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{eval_id}/metrics/f1/distribution",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_includes_all_runs(self, async_test_client, async_test_db):
        data, owner = await _seeded(async_test_db)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=json",
            )
        assert resp.status_code == 200
        body = resp.json()
        # Export should have >= 2 automated results
        automated = [r for r in body["results"] if r["results"]["type"] == "automated"]
        assert len(automated) >= 2
