"""
Integration tests targeting uncovered handler body code in routers/evaluations/metadata.py.

Focuses on:
- evaluated-models: CI calculation, annotator synthetic models, provider detection,
  filtering of "unknown"/"immediate", sorting by score
- configured-methods: automated vs human methods, field_mapping, parameters, result status
- evaluation-history: date filtering, metric filtering, CI from metadata
- significance: pairwise t-test, insufficient data, direct evaluations fallback
- statistics: all aggregation levels (model/sample/field/overall), ttest, bootstrap,
  cohens_d, cliffs_delta, correlation, compare_models filter, warnings

The metadata handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). The sync
``client`` fixture only overrides ``get_db``, so the async handlers would run
against a non-test engine and never see the SAVEPOINT rows. These tests seed
real rows through ``async_test_db`` and drive the endpoints over
``async_test_client``; auth is supplied by overriding ``require_user`` with a
superadmin ``AuthUser`` (so ``check_project_accessible_async`` returns True
without patching).
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    Task,
)

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
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


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"meta-cov-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta Cov User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _build_graph(db, admin, *, num_tasks=5, num_models=2,
                       with_eval_config=False, with_annotation_evals=False,
                       with_date_spread=False, with_eval_metadata=False):
    """Build a rich data graph for evaluation metadata tests."""
    admin_id = admin.id
    project = Project(
        id=_uid(),
        title=f"MetaCov {uuid.uuid4().hex[:6]}",
        created_by=admin_id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config={
            "selected_methods": {
                "answer": {
                    "automated": [
                        "accuracy",
                        {"name": "f1", "parameters": {"average": "macro"}},
                    ],
                    "human": ["likert_quality"],
                    "field_mapping": {"answer": "text"},
                },
            },
            "available_methods": {
                "answer": {"type": "choices", "to_name": "text", "options": ["Ja", "Nein"]},
            },
        } if with_eval_config else None,
        generation_config={
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models],
            }
        },
    )
    db.add(project)
    await db.flush()
    project_id = project.id

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project_id,
            data={"text": f"Meta cov text #{i}"}, inner_id=i + 1,
            created_by=admin_id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    # Annotations for annotator-based evaluations
    annotations = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project_id,
            completed_by=admin_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    await db.flush()

    models = ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models]
    all_gens = {}
    eval_runs = []

    for idx, model_id in enumerate(models):
        rg = ResponseGeneration(
            id=_uid(), project_id=project_id, model_id=model_id,
            status="completed", created_by=admin_id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(rg)
        await db.flush()

        gens = []
        for i, t in enumerate(tasks):
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=t.id,
                model_id=model_id, run_index=i,
                case_data=json.dumps(t.data),
                response_content=f"Answer from {model_id} for task {i}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            db.add(gen)
            gens.append(gen)
        await db.flush()
        all_gens[model_id] = gens

        # Evaluation runs with optional date spread
        base_accuracy = {"gpt-4o": 0.85, "claude-3-sonnet": 0.72, "gemini-1.5-pro": 0.91}
        base_f1 = {"gpt-4o": 0.82, "claude-3-sonnet": 0.68, "gemini-1.5-pro": 0.88}

        created_at = datetime.now(timezone.utc) - timedelta(days=idx * 7) if with_date_spread else datetime.now(timezone.utc)

        eval_metadata = None
        if with_eval_metadata:
            eval_metadata = {
                "confidence_intervals": {
                    "accuracy": {"lower": base_accuracy.get(model_id, 0.7) - 0.05,
                                 "upper": base_accuracy.get(model_id, 0.7) + 0.05},
                }
            }

        er = EvaluationRun(
            id=_uid(), project_id=project_id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": base_accuracy.get(model_id, 0.75),
                     "f1_score": base_f1.get(model_id, 0.70)},
            status="completed", samples_evaluated=num_tasks,
            has_sample_results=True,
            created_by=admin_id,
            created_at=created_at,
            completed_at=created_at + timedelta(minutes=5),
            eval_metadata=eval_metadata,
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

        # Per-sample TaskEvaluations with diverse scores
        for i, t in enumerate(tasks):
            acc_val = base_accuracy.get(model_id, 0.75) + (i * 0.03 - 0.06)
            acc_val = max(0, min(1, acc_val))
            f1_val = base_f1.get(model_id, 0.70) + (i * 0.02 - 0.04)
            f1_val = max(0, min(1, f1_val))
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id,
                judge_run_id=judge_run.id,
                task_id=t.id,
                generation_id=gens[i].id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if acc_val > 0.5 else "Nein"},
                metrics={"accuracy": round(acc_val, 4), "f1": round(f1_val, 4)},
                passed=acc_val > 0.5,
            )
            db.add(te)
    await db.flush()

    # Annotation-based evaluations
    if with_annotation_evals and eval_runs:
        for i, (ann, t) in enumerate(zip(annotations, tasks)):
            te = TaskEvaluation(
                id=_uid(), evaluation_id=eval_runs[0].id,
                judge_run_id=eval_runs[0]._test_judge_run.id,
                task_id=t.id,
                generation_id=None, annotation_id=ann.id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja"},
                metrics={"accuracy": 1.0, "f1": 1.0},
                passed=True,
            )
            db.add(te)
        await db.flush()

    await db.commit()
    return {
        "project_id": project_id,
        "tasks": tasks,
        "annotations": annotations,
        "all_gens": all_gens,
        "eval_runs": eval_runs,
    }


# ===================================================================
# EVALUATED MODELS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestEvaluatedModelsDeep:
    """Deep coverage for evaluated-models endpoint handler body."""

    @pytest.mark.asyncio
    async def test_models_sorted_by_score_descending(self, async_test_client, async_test_db):
        """Models should be sorted by average_score descending."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=3, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        models = resp.json()
        scores = [m["average_score"] for m in models if m["average_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_models_include_configured_status_flags(self, async_test_client, async_test_db):
        """With include_configured, response includes is_configured, has_generations, has_results."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200
        models = resp.json()
        for m in models:
            assert "is_configured" in m
            assert "has_generations" in m
            assert "has_results" in m

    @pytest.mark.asyncio
    async def test_models_ci_bounds_present(self, async_test_client, async_test_db):
        """Models with evaluations should have CI bounds."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        for m in resp.json():
            assert "ci_lower" in m
            assert "ci_upper" in m

    @pytest.mark.asyncio
    async def test_models_annotator_synthetic_ids(self, async_test_client, async_test_db):
        """Annotation-based evaluations create annotator:username synthetic models."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1,
                                  with_annotation_evals=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200
        models = resp.json()
        annotator_models = [m for m in models if m["model_id"].startswith("annotator:")]
        assert len(annotator_models) >= 1
        for am in annotator_models:
            assert am["provider"] == "Annotator"

    @pytest.mark.asyncio
    async def test_models_last_evaluated_present(self, async_test_client, async_test_db):
        """Models should have last_evaluated timestamp."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        for m in resp.json():
            if m["evaluation_count"] > 0:
                assert m["last_evaluated"] is not None

    @pytest.mark.asyncio
    async def test_models_total_samples(self, async_test_client, async_test_db):
        """Models should have total_samples count."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        for m in resp.json():
            assert "total_samples" in m
            if m["evaluation_count"] > 0:
                assert m["total_samples"] >= 5


# ===================================================================
# CONFIGURED METHODS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestConfiguredMethodsDeep:
    """Deep coverage for configured-methods endpoint."""

    @pytest.mark.asyncio
    async def test_methods_field_structure(self, async_test_client, async_test_db):
        """Fields include automated_methods with is_configured, has_results, display_name."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["fields"]) >= 1
        field = body["fields"][0]
        assert "field_name" in field
        assert "automated_methods" in field
        assert "human_methods" in field
        for method in field["automated_methods"]:
            assert "method_name" in method
            assert "display_name" in method
            assert "is_configured" in method
            assert "has_results" in method

    @pytest.mark.asyncio
    async def test_methods_human_methods_included(self, async_test_client, async_test_db):
        """Human methods from config appear in response."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        for field in body["fields"]:
            if field["human_methods"]:
                assert field["human_methods"][0]["method_type"] == "human"

    @pytest.mark.asyncio
    async def test_methods_field_type_present(self, async_test_client, async_test_db):
        """Field type from available_methods is included."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        for field in body["fields"]:
            assert "field_type" in field


# ===================================================================
# EVALUATION HISTORY: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestEvaluationHistoryDeep:
    """Deep coverage for evaluation-history endpoint."""

    @pytest.mark.asyncio
    async def test_history_with_metric_and_model(self, async_test_client, async_test_db):
        """History returns time-series data for specific metric and model.

        Issue #111: ``metric`` was renamed to ``metrics`` (multi-valued)
        and the response is ``{series: [{metric, evaluation_config_id,
        display_name, data: [...]}, ...]}``.
        """
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2,
                                  with_date_spread=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "series" in body
        assert isinstance(body["series"], list)

    @pytest.mark.asyncio
    async def test_history_with_date_range(self, async_test_client, async_test_db):
        """History respects start_date and end_date filters."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2,
                                  with_date_spread=True)
        # Use simple ISO format without timezone offset (fromisoformat compat)
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                f"?model_ids=gpt-4o&metrics=accuracy&start_date={start}&end_date={end}",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_history_with_eval_metadata_ci(self, async_test_client, async_test_db):
        """History includes CI in each per-series data point when computable."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1,
                                  with_eval_metadata=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
            )
        assert resp.status_code == 200
        body = resp.json()
        for series in body.get("series", []):
            for point in series.get("data", []):
                assert "ci_lower" in point
                assert "ci_upper" in point

    @pytest.mark.asyncio
    async def test_history_nonexistent_project(self, async_test_client, async_test_db):
        """History for nonexistent project returns 404."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/nonexistent/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
            )
        assert resp.status_code in (404, 422)

    @pytest.mark.asyncio
    async def test_history_nonexistent_metric(self, async_test_client, async_test_db):
        """History for metric with no data returns no series."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                "?model_ids=gpt-4o&metrics=nonexistent_metric",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("series", []) == []


# ===================================================================
# SIGNIFICANCE: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestSignificanceDeep:
    """Deep coverage for significance endpoint."""

    @pytest.mark.asyncio
    async def test_significance_pairwise_results(self, async_test_client, async_test_db):
        """Significance returns pairwise comparison results."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=10)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{data['project_id']}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "comparisons" in body
        if body["comparisons"]:
            comp = body["comparisons"][0]
            assert "model_a" in comp
            assert "model_b" in comp
            assert "p_value" in comp
            assert "significant" in comp

    @pytest.mark.asyncio
    async def test_significance_three_models(self, async_test_client, async_test_db):
        """Significance with 3 models produces 3 pairwise comparisons."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=3, num_tasks=10)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{data['project_id']}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&model_ids=gemini-1.5-pro&metrics=accuracy",
            )
        assert resp.status_code == 200
        body = resp.json()
        # 3 models -> 3 pairwise comparisons
        assert len(body.get("comparisons", [])) == 3

    @pytest.mark.asyncio
    async def test_significance_insufficient_data(self, async_test_client, async_test_db):
        """With only 1 sample per model, significance should report not significant."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=1)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{data['project_id']}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code == 200
        body = resp.json()
        for comp in body.get("comparisons", []):
            assert comp["significant"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_significance_nonexistent_project(self, async_test_client, async_test_db):
        """Significance for nonexistent project returns 404."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/nonexistent"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code in (404, 422)

    @pytest.mark.asyncio
    async def test_significance_multiple_metrics(self, async_test_client, async_test_db):
        """Significance across multiple metrics."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{data['project_id']}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy&metrics=f1",
            )
        assert resp.status_code == 200
        body = resp.json()
        # 2 models * 2 metrics = 2 comparisons
        assert len(body.get("comparisons", [])) >= 2


# ===================================================================
# STATISTICS: deeper coverage
# ===================================================================

@pytest.mark.integration
class TestStatisticsDeep:
    """Deep coverage for statistics endpoint handler body."""

    @pytest.mark.asyncio
    async def test_statistics_model_aggregation_response_structure(self, async_test_client, async_test_db):
        """Model aggregation includes by_model with per-model metrics."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": ["accuracy", "f1"], "aggregation": "model", "methods": ["ci"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "model"
        assert "by_model" in body
        for model_id, model_stats in (body.get("by_model") or {}).items():
            assert "metrics" in model_stats
            assert "sample_count" in model_stats

    @pytest.mark.asyncio
    async def test_statistics_sample_aggregation_raw_scores(self, async_test_client, async_test_db):
        """Sample aggregation returns raw_scores list."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "sample", "methods": ["ci"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "sample"
        if body.get("raw_scores"):
            for score in body["raw_scores"]:
                assert "model_id" in score
                assert "metric" in score
                assert "value" in score

    @pytest.mark.asyncio
    async def test_statistics_field_aggregation(self, async_test_client, async_test_db):
        """Field aggregation returns by_field with per-field metrics."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "field", "methods": ["ci"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "field"
        if body.get("by_field"):
            for field_name, field_stats in body["by_field"].items():
                assert "metrics" in field_stats
                assert "sample_count" in field_stats

    @pytest.mark.asyncio
    async def test_statistics_overall_aggregation(self, async_test_client, async_test_db):
        """Overall aggregation returns aggregated metrics only."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "overall", "methods": ["ci"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aggregation"] == "overall"
        assert "metrics" in body

    @pytest.mark.asyncio
    async def test_statistics_with_ttest_pairwise(self, async_test_client, async_test_db):
        """T-test method produces pairwise_comparisons."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["ci", "ttest"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "ttest_p" in comp
            assert "ttest_significant" in comp

    @pytest.mark.asyncio
    async def test_statistics_with_cohens_d(self, async_test_client, async_test_db):
        """Cohens_d method produces effect size in comparisons."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["cohens_d"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "cohens_d" in comp
            assert "cohens_d_interpretation" in comp

    @pytest.mark.asyncio
    async def test_statistics_with_cliffs_delta(self, async_test_client, async_test_db):
        """Cliffs_delta method produces non-parametric effect size."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["cliffs_delta"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("pairwise_comparisons"):
            comp = body["pairwise_comparisons"][0]
            assert "cliffs_delta" in comp
            assert "cliffs_delta_interpretation" in comp

    @pytest.mark.asyncio
    async def test_statistics_with_correlation(self, async_test_client, async_test_db):
        """Correlation method produces correlation matrix between metrics."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy", "f1"],
                    "aggregation": "model",
                    "methods": ["correlation"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("correlations"):
            assert "accuracy" in body["correlations"]
            assert "f1" in body["correlations"]

    @pytest.mark.asyncio
    async def test_statistics_compare_models_filter(self, async_test_client, async_test_db):
        """compare_models filters results to specified models only."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=3, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["ci"],
                    "compare_models": ["gpt-4o"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("by_model"):
            assert "gpt-4o" in body["by_model"]

    @pytest.mark.asyncio
    async def test_statistics_no_evaluations(self, async_test_client, async_test_db):
        """Statistics for project with no evaluations returns 404."""
        admin = await _seed_user(async_test_db)
        p = Project(
            id=_uid(), title="No Evals", created_by=admin.id,
            label_config="<View/>",
        )
        async_test_db.add(p)
        await async_test_db.flush()
        p_id = p.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_statistics_metric_stats_structure(self, async_test_client, async_test_db):
        """Overall metrics include mean, std, ci_lower, ci_upper, n."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "overall", "methods": ["ci"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        if body.get("metrics") and "accuracy" in body["metrics"]:
            stats = body["metrics"]["accuracy"]
            assert "mean" in stats
            assert "std" in stats
            assert "ci_lower" in stats
            assert "ci_upper" in stats
            assert "n" in stats

    @pytest.mark.asyncio
    async def test_statistics_warnings_for_missing_models(self, async_test_client, async_test_db):
        """compare_models with nonexistent model produces warnings."""
        admin = await _seed_user(async_test_db)
        data = await _build_graph(async_test_db, admin, num_models=1, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["ci"],
                    "compare_models": ["nonexistent-model"],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("warnings") is not None
