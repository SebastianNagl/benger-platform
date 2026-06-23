"""
Deep integration tests for evaluation metadata, statistics, and significance.

Covers routers/evaluations/metadata/*:
- GET  /projects/{project_id}/evaluated-models — model listing with CI
- GET  /projects/{project_id}/configured-methods — method result status
- POST /projects/{project_id}/statistics — comprehensive statistics computation
- GET  /projects/{project_id}/evaluation-history — evaluation timeline
- GET  /significance/{project_id} — pairwise statistical tests

These handlers were migrated to the async DB lane (``Depends(get_async_db)`` +
``await db.execute(select(...))``). The sync ``client`` fixture only overrides
``get_db`` — the async handlers run against a separate ``get_async_db`` session,
so rows seeded inside the sync ``test_db`` transaction are invisible to them.
The suite therefore seeds its data graph via ``async_test_db`` and drives the
surface through ``async_test_client``, authenticating as a seeded superadmin
``User`` via ``_as_user`` (overriding ``require_user``). A superadmin always
passes ``check_project_accessible_async``, so no access-helper patch is needed.

The assertions are intentionally lenient (many accept
``status_code in (200, 400, 422)``); that leniency is preserved exactly.
"""

import json
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
        username=f"meta-deep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta Deep User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _build(db, admin, *, num_tasks=5, num_models=3,
                 with_eval_config=False, with_annotation_evals=False):
    """Build a rich evaluation data graph with multiple models."""
    project = Project(
        id=_uid(),
        title=f"Meta {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config={
            "selected_methods": {
                "answer": {
                    "automated": ["accuracy", "f1"],
                    "human": [],
                }
            },
            "available_methods": {
                "answer": {"type": "choices", "options": ["Ja", "Nein"]},
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
    # Capture the id before commit so it remains usable post-commit.
    project_id = project.id

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project_id,
            data={"text": f"Meta text #{i}"}, inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    # Annotations
    annotations = []
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project_id,
            completed_by=admin.id,
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
    task_evals = []

    for model_id in models:
        rg = ResponseGeneration(
            id=_uid(), project_id=project_id, model_id=model_id,
            status="completed", created_by=admin.id,
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
                response_content=f"Answer from {model_id}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            db.add(gen)
            gens.append(gen)
        await db.flush()
        all_gens[model_id] = gens

        # Evaluation run
        base_accuracy = {"gpt-4o": 0.85, "claude-3-sonnet": 0.78, "gemini-1.5-pro": 0.90}
        er = EvaluationRun(
            id=_uid(), project_id=project_id, model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": base_accuracy.get(model_id, 0.75), "f1_score": 0.80},
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
        for i, t in enumerate(tasks):
            accuracy_val = base_accuracy.get(model_id, 0.75) + (i * 0.02 - 0.04)
            accuracy_val = max(0, min(1, accuracy_val))
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id,
                judge_run_id=judge_run.id,
                task_id=t.id,
                generation_id=gens[i].id,
                field_name="answer", answer_type="choices",
                ground_truth={"value": "Ja"},
                prediction={"value": "Ja" if accuracy_val > 0.5 else "Nein"},
                metrics={"accuracy": accuracy_val, "f1": 0.75 + (i * 0.01)},
                passed=accuracy_val > 0.5,
            )
            db.add(te)
            task_evals.append(te)
    await db.flush()

    # Annotation evaluations (if requested)
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
        "project": project,
        "project_id": project_id,
        "tasks": tasks,
        "annotations": annotations,
        "all_gens": all_gens,
        "eval_runs": eval_runs,
        "task_evals": task_evals,
    }


# ===================================================================
# EVALUATED MODELS
# ===================================================================

@pytest.mark.integration
class TestGetEvaluatedModels:
    """GET /api/evaluations/projects/{project_id}/evaluated-models"""

    @pytest.mark.asyncio
    async def test_evaluated_models_basic(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)
        assert len(models) >= 2
        model_ids = {m["model_id"] for m in models}
        assert "gpt-4o" in model_ids
        assert "claude-3-sonnet" in model_ids

    @pytest.mark.asyncio
    async def test_evaluated_models_include_configured(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200
        models = resp.json()
        # Should include the 3rd configured model even if not evaluated
        for m in models:
            if m.get("is_configured"):
                assert "has_results" in m
                assert "has_generations" in m

    @pytest.mark.asyncio
    async def test_evaluated_models_has_provider(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        for m in resp.json():
            assert "provider" in m
            assert m["provider"] != ""

    @pytest.mark.asyncio
    async def test_evaluated_models_has_scores(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        for m in resp.json():
            if m["evaluation_count"] > 0:
                assert m["average_score"] is not None
                assert isinstance(m["average_score"], (int, float))

    @pytest.mark.asyncio
    async def test_evaluated_models_empty_project(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        project = Project(
            id=_uid(), title="Empty Meta", created_by=admin.id,
            label_config="<View/>",
        )
        async_test_db.add(project)
        await async_test_db.flush()
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project_id}/evaluated-models",
            )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_evaluated_models_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/nonexistent-id/evaluated-models",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluated_models_with_annotation_evals(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=1, with_annotation_evals=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200
        models = resp.json()
        # Should include annotator synthetic models
        annotator_models = [m for m in models if m["model_id"].startswith("annotator:")]
        assert len(annotator_models) >= 1


# ===================================================================
# CONFIGURED METHODS
# ===================================================================

@pytest.mark.integration
class TestGetConfiguredMethods:
    """GET /api/evaluations/projects/{project_id}/configured-methods"""

    @pytest.mark.asyncio
    async def test_configured_methods_with_config(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == data["project_id"]
        assert "fields" in body

    @pytest.mark.asyncio
    async def test_configured_methods_no_config(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=1, with_eval_config=False)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fields"] == []

    @pytest.mark.asyncio
    async def test_configured_methods_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/nonexistent/configured-methods",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_configured_methods_has_result_status(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        for field in body.get("fields", []):
            for method in field.get("automated_methods", []):
                assert "is_configured" in method
                assert "has_results" in method
                assert "result_count" in method


# ===================================================================
# STATISTICS
# ===================================================================

@pytest.mark.integration
class TestStatistics:
    """POST /api/evaluations/projects/{project_id}/statistics"""

    @pytest.mark.asyncio
    async def test_statistics_by_model(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=3, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy", "f1"],
                    "aggregation": "model",
                    "methods": ["ci"],
                },
            )
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            body = resp.json()
            assert body["aggregation"] == "model"

    @pytest.mark.asyncio
    async def test_statistics_by_sample(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "sample",
                    "methods": ["ci"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_by_field(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "field",
                    "methods": ["ci"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_overall(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "overall",
                    "methods": ["ci"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_with_ttest(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["ci", "ttest"],
                    "compare_models": ["gpt-4o", "claude-3-sonnet"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_with_bootstrap(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["bootstrap"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/nonexistent/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
            )
        assert resp.status_code in (400, 403, 404, 422)

    @pytest.mark.asyncio
    async def test_statistics_empty_metrics(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=1)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={"metrics": [], "aggregation": "model"},
            )
        assert resp.status_code in (200, 400, 422)


# ===================================================================
# EVALUATION HISTORY
# ===================================================================

@pytest.mark.integration
class TestEvaluationHistory:
    """GET /api/evaluations/projects/{project_id}/evaluation-history"""

    @pytest.mark.asyncio
    async def test_evaluation_history(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        # Issue #111: ``metrics`` is required, response shape is ``{series: []}``.
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code in (200, 404, 422)
        if resp.status_code == 200:
            assert "series" in resp.json()

    @pytest.mark.asyncio
    async def test_evaluation_history_with_model_filter(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
            )
        assert resp.status_code in (200, 404, 422)
        if resp.status_code == 200:
            assert isinstance(resp.json().get("series"), list)


# ===================================================================
# SIGNIFICANCE TESTS
# ===================================================================

@pytest.mark.integration
class TestSignificance:
    """GET /api/evaluations/significance/{project_id}"""

    @pytest.mark.asyncio
    async def test_significance_two_models(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=10)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{data['project_id']}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code in (200, 400, 404, 422)

    @pytest.mark.asyncio
    async def test_significance_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/nonexistent"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            )
        assert resp.status_code in (400, 403, 404, 422)


# ===================================================================
# ADDITIONAL METADATA EDGE CASES
# ===================================================================

@pytest.mark.integration
class TestMetadataEdgeCases:
    """Additional edge cases for metadata endpoints."""

    @pytest.mark.asyncio
    async def test_evaluated_models_sorts_by_score(self, async_test_client, async_test_db):
        """Models should be sorted by average_score descending."""
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=3, num_tasks=5)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        models = resp.json()
        scores = [m["average_score"] for m in models if m["average_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_configured_methods_field_mapping(self, async_test_client, async_test_db):
        """Configured methods should include field_mapping if set."""
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=1, with_eval_config=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/configured-methods",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "project_id" in body

    @pytest.mark.asyncio
    async def test_evaluated_models_ci_values(self, async_test_client, async_test_db):
        """Models with enough data should have CI values."""
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=1, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models",
            )
        assert resp.status_code == 200
        models = resp.json()
        for m in models:
            assert "ci_lower" in m
            assert "ci_upper" in m

    @pytest.mark.asyncio
    async def test_statistics_with_cohens_d(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["cohens_d"],
                    "compare_models": ["gpt-4o", "claude-3-sonnet"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_statistics_with_correlation(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2, num_tasks=8)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["accuracy", "f1"],
                    "aggregation": "model",
                    "methods": ["correlation"],
                },
            )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_evaluated_models_filters_unknown(self, async_test_client, async_test_db):
        """The 'unknown' model_id should be filtered out."""
        admin = await _seed_user(async_test_db)
        data = await _build(async_test_db, admin, num_models=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project_id']}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200
        models = resp.json()
        model_ids = {m["model_id"] for m in models}
        assert "unknown" not in model_ids
