"""
Coverage push tests for evaluation results endpoints.

Targets specific branches in routers/evaluations/results.py:
- get_evaluation_results with automated and human evaluation data
- export_evaluation_results in JSON and CSV formats
- get_evaluation_samples with filtering and pagination
- get_metric_distribution with statistics computation
- get_confusion_matrix with per-class metrics
- get_results_by_task_model with generation-based and annotation-based results
- get_project_results_by_task_model aggregated results
- get_sample_result_by_task_model for both model and annotator
- _extract_primary_score priority chain

The results router package (``routers/evaluations/results/``) was migrated to
the async DB lane: every endpoint is ``async def`` with
``db: AsyncSession = Depends(get_async_db)`` and calls
``check_project_accessible_async``. These tests therefore drive the surface
through ``async_test_client`` and seed via ``async_test_db`` (the sync
``client``/``test_db`` only override ``get_db``, which the async handlers no
longer use). Auth is provided by overriding ``require_user`` with a superadmin,
so ``check_project_accessible_async`` short-circuits to True without org-context
headers.
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
    HumanEvaluationSession,
    LikertScaleEvaluation,
    Organization,
    OrganizationMembership,
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


def _make_superadmin(*, name="Eval Owner") -> User:
    uid = str(uuid.uuid4())
    return User(
        id=uid,
        username=f"eval-owner-{uid[:8]}",
        email=f"{uid[:8]}@example.com",
        name=name,
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_annotator() -> User:
    uid = str(uuid.uuid4())
    return User(
        id=uid,
        username=f"eval-annot-{uid[:8]}",
        email=f"{uid[:8]}@example.com",
        name=f"Annotator {uid[:6]}",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


async def _setup_eval_project(db, *, add_human_evals=False, add_automated=True,
                              add_generations=True, num_tasks=3):  # noqa: E127
    """Create project with evaluation data for testing results endpoints.

    Seeds its own superadmin ``owner`` (the project creator) plus a plain
    ``annotator`` user used for annotations / human-eval evaluator references.
    Returns both in the result dict. Async: flushes throughout with a single
    commit at the end.
    """
    owner = _make_superadmin()
    annotator = _make_annotator()
    db.add(owner)
    db.add(annotator)
    await db.flush()

    org = Organization(
        id=str(uuid.uuid4()),
        name="Eval Test Org",
        slug=f"eval-org-{uuid.uuid4().hex[:8]}",
        display_name="Eval Test Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    await db.flush()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Eval Test Project",
        description="For testing evaluation results",
        created_by=owner.id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
    )
    db.add(p)
    await db.flush()

    for i, user in enumerate([owner, annotator]):
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i == 0 else "CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=owner.id,
    ))
    await db.flush()

    tasks = []
    annotations = []
    generations = []
    eval_runs = []
    judge_runs = []
    task_evals = []

    for i in range(num_tasks):
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            project_id=pid,
            data={"text": f"Eval sample text {i}", "input": f"Question {i}"},
            meta={"index": i},
            inner_id=i + 1,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()

    # Create annotations
    for i, task in enumerate(tasks):
        ann_id = str(uuid.uuid4())
        ann = Annotation(
            id=ann_id,
            task_id=task.id,
            project_id=pid,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": [f"answer {i}"]}}],
            completed_by=annotator.id,
            was_cancelled=False,
        )
        db.add(ann)
        annotations.append(ann)
    await db.flush()

    if add_generations:
        for task in tasks:
            rg_id = str(uuid.uuid4())
            rg = ResponseGeneration(
                id=rg_id,
                task_id=task.id,
                project_id=pid,
                model_id="gpt-4o",
                config_id="default",
                status="completed",
                responses_generated=1,
                created_by=owner.id,
                completed_at=datetime.utcnow(),
            )
            db.add(rg)
            await db.flush()

            gen_id = str(uuid.uuid4())
            gen = Generation(
                id=gen_id,
                generation_id=rg_id,
                task_id=task.id,
                model_id="gpt-4o",
                run_index=0,
                case_data=json.dumps(task.data),
                response_content=f"Generated for task {task.inner_id}",
                status="completed",
            )
            db.add(gen)
            generations.append(gen)
        await db.flush()

    if add_automated:
        er_id = str(uuid.uuid4())
        er = EvaluationRun(
            id=er_id,
            project_id=pid,
            model_id="gpt-4o",
            evaluation_type_ids=["exact_match", "bleu"],
            metrics={"accuracy": 0.85, "f1": 0.90},
            eval_metadata={"evaluation_type": "automated"},
            status="completed",
            samples_evaluated=num_tasks,
            has_sample_results=True,
            created_by=owner.id,
        )
        db.add(er)
        eval_runs.append(er)
        await db.flush()

        # Migration 043: TaskEvaluation.judge_run_id is NOT NULL.
        jr_id = str(uuid.uuid4())
        jr = EvaluationJudgeRun(
            id=jr_id, evaluation_id=er_id, judge_model_id=None,
            run_index=0, status="completed",
        )
        db.add(jr)
        judge_runs.append(jr)
        await db.flush()

        for j, task in enumerate(tasks):
            te_id = str(uuid.uuid4())
            gen_id = generations[j].id if generations else None
            te = TaskEvaluation(
                id=te_id,
                evaluation_id=er_id,
                judge_run_id=jr_id,
                task_id=task.id,
                generation_id=gen_id,
                field_name="answer",
                answer_type="text",
                ground_truth={"value": f"answer {j}"},
                prediction={"value": f"predicted {j}"},
                metrics={
                    "exact_match": 1.0 if j == 0 else 0.0,
                    "bleu": 0.3 + j * 0.2,
                    "llm_judge_custom": 0.75,
                },
                passed=(j == 0),
                confidence_score=0.95 - j * 0.1,
                processing_time_ms=100 + j * 50,
            )
            db.add(te)
            task_evals.append(te)
        await db.flush()

    if add_human_evals:
        session_id = str(uuid.uuid4())
        session = HumanEvaluationSession(
            id=session_id,
            project_id=pid,
            evaluator_id=annotator.id,
            session_type="likert",
            items_evaluated=num_tasks,
            status="completed",
        )
        db.add(session)
        await db.flush()

        for i, task in enumerate(tasks):
            for dim in ["accuracy", "clarity", "completeness"]:
                likert = LikertScaleEvaluation(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    task_id=task.id,
                    response_id=str(uuid.uuid4()),
                    dimension=dim,
                    rating=3 + (i % 3),
                )
                db.add(likert)
        await db.flush()

        pref_session_id = str(uuid.uuid4())
        pref_session = HumanEvaluationSession(
            id=pref_session_id,
            project_id=pid,
            evaluator_id=annotator.id,
            session_type="preference",
            items_evaluated=num_tasks,
            status="completed",
        )
        db.add(pref_session)
        await db.flush()

        for i, task in enumerate(tasks):
            pref = PreferenceRanking(
                id=str(uuid.uuid4()),
                session_id=pref_session_id,
                task_id=task.id,
                response_a_id=str(uuid.uuid4()),
                response_b_id=str(uuid.uuid4()),
                winner="a" if i % 2 == 0 else "b",
            )
            db.add(pref)
        await db.flush()

    await db.commit()

    return {
        "owner": owner,
        "annotator": annotator,
        "project": p,
        "tasks": tasks,
        "annotations": annotations,
        "generations": generations,
        "eval_runs": eval_runs,
        "judge_runs": judge_runs,
        "task_evals": task_evals,
        "org": org,
    }


class TestGetEvaluationResults:
    """Test GET /api/evaluations/results/{project_id}"""

    @pytest.mark.asyncio
    async def test_automated_results(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=False)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(f"/api/evaluations/results/{pid}")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert results[0]["results"]["type"] == "automated"

    @pytest.mark.asyncio
    async def test_human_likert_results(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=False, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(f"/api/evaluations/results/{pid}")
        assert resp.status_code == 200
        results = resp.json()
        found_likert = False
        found_preference = False
        for r in results:
            if r["results"]["type"] == "human_likert":
                found_likert = True
                assert "dimensions" in r["results"]
            if r["results"]["type"] == "human_preference":
                found_preference = True
                assert "percentages" in r["results"]
        assert found_likert
        assert found_preference

    @pytest.mark.asyncio
    async def test_both_automated_and_human(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(f"/api/evaluations/results/{pid}")
        assert resp.status_code == 200
        results = resp.json()
        types = {r["results"]["type"] for r in results}
        assert "automated" in types
        assert "human_likert" in types

    @pytest.mark.asyncio
    async def test_include_automated_only(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/results/{pid}?include_human=false"
            )
        assert resp.status_code == 200
        results = resp.json()
        for r in results:
            assert r["results"]["type"] == "automated"

    @pytest.mark.asyncio
    async def test_include_human_only(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/results/{pid}?include_automated=false"
            )
        assert resp.status_code == 200
        results = resp.json()
        for r in results:
            assert r["results"]["type"] != "automated"

    @pytest.mark.asyncio
    async def test_empty_results(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=False, add_human_evals=False)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(f"/api/evaluations/results/{pid}")
        assert resp.status_code == 200
        assert resp.json() == []


class TestExportEvaluationResults:
    """Test POST /api/evaluations/export/{project_id}"""

    @pytest.mark.asyncio
    async def test_export_json(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.post(f"/api/evaluations/export/{pid}?format=json")
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "exported_at" in body

    @pytest.mark.asyncio
    async def test_export_csv_with_metrics(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=True, add_human_evals=False)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.post(f"/api/evaluations/export/{pid}?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_csv_with_human(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=False, add_human_evals=True)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.post(f"/api/evaluations/export/{pid}?format=csv")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_csv_empty(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=False, add_human_evals=False)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.post(f"/api/evaluations/export/{pid}?format=csv")
        assert resp.status_code == 200


class TestGetEvaluationSamples:
    """Test GET /api/evaluations/{evaluation_id}/samples"""

    @pytest.mark.asyncio
    async def test_get_samples(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(f"/api/evaluations/{er_id}/samples")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    @pytest.mark.asyncio
    async def test_get_samples_with_field_filter(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/samples?field_name=answer"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    @pytest.mark.asyncio
    async def test_get_samples_with_passed_filter(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/samples?passed=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1  # Only first task passed

    @pytest.mark.asyncio
    async def test_get_samples_pagination(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/samples?page=1&page_size=2"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert body["has_next"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get("/api/evaluations/nonexistent-id/samples")
        assert resp.status_code == 404


class TestGetMetricDistribution:
    """Test GET /api/evaluations/{evaluation_id}/metrics/{metric_name}/distribution"""

    @pytest.mark.asyncio
    async def test_bleu_distribution(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/metrics/bleu/distribution"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric_name"] == "bleu"
        assert "mean" in body
        assert "median" in body
        assert "std" in body
        assert "quartiles" in body
        assert "histogram" in body

    @pytest.mark.asyncio
    async def test_distribution_with_field_filter(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/metrics/bleu/distribution?field_name=answer"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_distribution_metric_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/metrics/nonexistent_metric/distribution"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_distribution_eval_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/nonexistent/metrics/bleu/distribution"
            )
        assert resp.status_code == 404


class TestGetConfusionMatrix:
    """Test GET /api/evaluations/{evaluation_id}/confusion-matrix"""

    @pytest.mark.asyncio
    async def test_confusion_matrix(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, num_tasks=4)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        # Update task evaluations with classification data
        for i, te in enumerate(data["task_evals"]):
            te.ground_truth = {"value": "positive" if i % 2 == 0 else "negative"}
            te.prediction = {"value": "positive" if i < 2 else "negative"}
            async_test_db.add(te)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/confusion-matrix?field_name=answer"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "labels" in body
        assert "matrix" in body
        assert "accuracy" in body
        assert "precision_per_class" in body
        assert "recall_per_class" in body
        assert "f1_per_class" in body

    @pytest.mark.asyncio
    async def test_confusion_matrix_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/nonexistent/confusion-matrix?field_name=test"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_confusion_matrix_no_samples(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/confusion-matrix?field_name=nonexistent_field"
            )
        assert resp.status_code == 404


class TestGetResultsByTaskModel:
    """Test GET /api/evaluations/{evaluation_id}/results/by-task-model"""

    @pytest.mark.asyncio
    async def test_results_by_task_model(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        er_id = data["eval_runs"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/results/by-task-model"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "models" in body
        assert "tasks" in body
        assert "summary" in body

    @pytest.mark.asyncio
    async def test_results_by_task_model_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/nonexistent/results/by-task-model"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_results_by_task_model_no_results(self, async_test_client, async_test_db):
        """Eval run exists but no task evaluations with generation_id."""
        data = await _setup_eval_project(
            async_test_db, add_generations=False, add_automated=False
        )
        owner = data["owner"]
        pid = data["project"].id

        er_id = str(uuid.uuid4())
        er = EvaluationRun(
            id=er_id,
            project_id=pid,
            model_id="gpt-4o",
            evaluation_type_ids=["test"],
            metrics={},
            status="completed",
            has_sample_results=False,
            created_by=owner.id,
        )
        async_test_db.add(er)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/{er_id}/results/by-task-model"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["models"] == []


class TestGetProjectResultsByTaskModel:
    """Test GET /api/evaluations/projects/{project_id}/results/by-task-model"""

    @pytest.mark.asyncio
    async def test_project_results(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/results/by-task-model"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == pid
        assert "models" in body
        assert "tasks" in body
        assert "summary" in body

    @pytest.mark.asyncio
    async def test_project_results_no_completed_evals(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db, add_automated=False, add_human_evals=False)
        owner = data["owner"]
        pid = data["project"].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/results/by-task-model"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["models"] == []
        assert len(body["tasks"]) == 3  # All tasks returned even without evaluations

    @pytest.mark.asyncio
    async def test_project_results_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/results/by-task-model"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_results_with_annotation_evals(self, async_test_client, async_test_db):
        """Test annotation-based evaluations appear as synthetic annotator models."""
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        pid = data["project"].id
        er_id = data["eval_runs"][0].id

        # Add annotation-based evaluation (no generation_id, with annotation_id)
        te_id = str(uuid.uuid4())
        te = TaskEvaluation(
            id=te_id,
            evaluation_id=er_id,
            judge_run_id=data["judge_runs"][0].id,
            task_id=data["tasks"][0].id,
            generation_id=None,
            annotation_id=data["annotations"][0].id,
            field_name="answer",
            answer_type="text",
            ground_truth={"value": "gt"},
            prediction={"value": "pred"},
            metrics={"score": 0.8},
            passed=True,
        )
        async_test_db.add(te)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{pid}/results/by-task-model"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Should have annotator model in the list
        annotator_models = [m for m in body["models"] if m.startswith("annotator:")]
        assert len(annotator_models) >= 1


class TestGetSampleResultByTaskModel:
    """Test GET /api/evaluations/sample-result"""

    @pytest.mark.asyncio
    async def test_sample_result_by_generation(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        task_id = data["tasks"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/sample-result?task_id={task_id}&model_id=gpt-4o"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == task_id
        assert len(body["results"]) >= 1

    @pytest.mark.asyncio
    async def test_sample_result_no_results(self, async_test_client, async_test_db):
        data = await _setup_eval_project(
            async_test_db, add_automated=False, add_generations=False
        )
        owner = data["owner"]
        task_id = data["tasks"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/sample-result?task_id={task_id}&model_id=nonexistent"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []

    @pytest.mark.asyncio
    async def test_sample_result_task_not_found(self, async_test_client, async_test_db):
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]

        with _as_user(owner):
            resp = await async_test_client.get(
                "/api/evaluations/sample-result?task_id=nonexistent&model_id=gpt-4o"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_sample_result_by_annotator(self, async_test_client, async_test_db):
        """Test annotator: prefix for annotation-based sample results."""
        data = await _setup_eval_project(async_test_db)
        owner = data["owner"]
        annotator = data["annotator"]
        task_id = data["tasks"][0].id
        er_id = data["eval_runs"][0].id

        # Add annotation-based evaluation
        te_id = str(uuid.uuid4())
        te = TaskEvaluation(
            id=te_id,
            evaluation_id=er_id,
            judge_run_id=data["judge_runs"][0].id,
            task_id=task_id,
            generation_id=None,
            annotation_id=data["annotations"][0].id,
            field_name="answer",
            answer_type="text",
            ground_truth={"value": "gt"},
            prediction={"value": "pred"},
            metrics={"score": 0.8},
            passed=True,
        )
        async_test_db.add(te)
        await async_test_db.commit()

        # Use annotator:username format — the handler resolves the suffix
        # against name/username, and the seeded annotation's completed_by is
        # this user.
        username = annotator.username
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/sample-result?task_id={task_id}&model_id=annotator:{username}"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_sample_result_by_annotator_not_found(self, async_test_client, async_test_db):
        """Test annotator: prefix with unknown username."""
        data = await _setup_eval_project(async_test_db, add_automated=False)
        owner = data["owner"]
        task_id = data["tasks"][0].id

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/sample-result?task_id={task_id}&model_id=annotator:nonexistent_user"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []


class TestExtractPrimaryScore:
    """Test _extract_primary_score helper with priority chain."""

    def test_priority_grade_points(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 15, "score": 0.5}
        assert _extract_primary_score(metrics) == 15

    def test_priority_custom(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 0.9, "score": 0.5}
        assert _extract_primary_score(metrics) == 0.9

    def test_priority_generic_llm_judge(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_coherence": 0.8, "score": 0.5}
        assert _extract_primary_score(metrics) == 0.8

    def test_skip_non_numeric_llm_judge(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_response": "text", "score": 0.5}
        assert _extract_primary_score(metrics) == 0.5

    def test_skip_llm_judge_suffixes(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_test_response": 0.5, "llm_judge_test_passed": True, "score": 0.3}
        assert _extract_primary_score(metrics) == 0.3

    def test_fallback_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0.65}
        assert _extract_primary_score(metrics) == 0.65

    def test_fallback_overall_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"overall_score": 0.72}
        assert _extract_primary_score(metrics) == 0.72

    def test_none_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score({}) is None

    def test_no_matching_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"some_text": "value", "not_a_number": [1, 2]}
        assert _extract_primary_score(metrics) is None
