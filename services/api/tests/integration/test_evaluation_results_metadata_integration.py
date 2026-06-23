"""
Integration tests for evaluation results and metadata endpoints.

Tests evaluation handlers in routers/evaluations/results/ and
routers/evaluations/metadata/ using real PostgreSQL.

All endpoints exercised here were converted sync->async (``get_async_db`` +
``await db.execute(select(...))`` + ``check_project_accessible_async``), so the
tests seed through the ``async_test_db`` fixture and drive ``async_test_client``
(which overrides ``get_async_db``). Auth is supplied by overriding
``require_user`` with a real seeded user via the ``_as_user`` contextmanager
(superadmin for the happy paths — it short-circuits the access check; a
non-superadmin + a patched ``check_project_accessible_async`` for the
deterministic 403s). The seed helpers mirror the FK-valid idioms of
``test_eval_results_branches.py`` (ResponseGeneration parent + Generation child,
an EvaluationJudgeRun parent for every TaskEvaluation).
"""

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
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Project, Task

# URL prefix: main router = /api/evaluations
# results.py routes start with /evaluations/... => /api/evaluations/...
# metadata.py routes like /projects/... => /api/evaluations/projects/...
# metadata.py routes like /significance/... => /api/evaluations/significance/...
RESULTS_PREFIX = "/api/evaluations"
META_PREFIX = "/api/evaluations"


# ---------------------------------------------------------------------------
# Auth override (mirrors test_eval_results_branches.py)
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user, is_superadmin=None):
    sa = db_user.is_superadmin if is_superadmin is None else is_superadmin
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=sa,
        is_active=True,
        email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Async seeding helpers
# ---------------------------------------------------------------------------


async def _make_admin(db, *, is_superadmin=True):
    u = User(
        id=f"admin-eval-{uuid.uuid4().hex[:8]}",
        username=f"evaladmin-{uuid.uuid4().hex[:8]}@test.com",
        email=f"evaladmin-{uuid.uuid4().hex[:8]}@test.com",
        name="Eval Admin",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, admin, *, is_private=False):
    p = Project(
        id=f"proj-eval-{uuid.uuid4().hex[:8]}",
        title="Evaluation Test Project",
        description="A test project for evaluation testing",
        created_by=admin.id,
        is_private=is_private,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


async def _make_tasks(db, project, admin, *, num=5):
    tasks = []
    for i in range(num):
        t = Task(
            id=f"task-eval-{uuid.uuid4().hex[:8]}",
            project_id=project.id,
            data={"text": f"Sample legal text {i}", "content": f"Content for task {i}"},
            inner_id=i + 1,
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _make_response_generation(db, project, admin):
    rg = ResponseGeneration(
        id=f"rg-eval-{uuid.uuid4().hex[:8]}",
        project_id=project.id,
        model_id="gpt-4",
        status="completed",
        created_by=admin.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    await db.flush()
    return rg


async def _make_generations(db, tasks, response_generation):
    gens = []
    for i, task in enumerate(tasks):
        gen = Generation(
            id=f"gen-eval-{uuid.uuid4().hex[:8]}",
            generation_id=response_generation.id,
            task_id=task.id,
            model_id="gpt-4",
            case_data="Sample case data",
            response_content="Generated response",
            status="completed",
            parse_status="success",
            run_index=i,
            created_at=datetime.now(timezone.utc),
        )
        db.add(gen)
        gens.append(gen)
    await db.flush()
    return gens


async def _make_eval_run(db, project, admin, *, model_id="gpt-4", status="completed",
                         metrics=None):
    er = EvaluationRun(
        id=f"eval-run-{uuid.uuid4().hex[:8]}",
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        metrics=metrics if metrics is not None else {"accuracy": 0.85, "f1_score": 0.82},
        status=status,
        samples_evaluated=5,
        has_sample_results=True,
        created_by=admin.id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; every
    # TaskEvaluation needs a parent judge run (catch-all shape).
    judge_run = EvaluationJudgeRun(
        id=f"jr-{uuid.uuid4().hex[:8]}",
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()
    er._test_judge_run = judge_run
    return er


async def _make_task_evaluations(db, eval_run, tasks, gens):
    evals = []
    for i, (task, gen) in enumerate(zip(tasks, gens)):
        score = 0.7 + (i * 0.05)
        te = TaskEvaluation(
            id=f"te-{uuid.uuid4().hex[:8]}",
            evaluation_id=eval_run.id,
            judge_run_id=eval_run._test_judge_run.id,
            task_id=task.id,
            generation_id=gen.id,
            field_name="text_answer",
            answer_type="text",
            ground_truth={"value": f"correct_answer_{i}"},
            prediction={"value": f"predicted_answer_{i}"},
            metrics={"accuracy": score, "f1_score": score - 0.03},
            passed=score >= 0.75,
            confidence_score=score,
            processing_time_ms=100 + i * 10,
            created_at=datetime.now(timezone.utc),
        )
        db.add(te)
        evals.append(te)
    await db.flush()
    return evals


async def _make_classification_evaluations(db, eval_run, tasks, gens):
    evals = []
    predictions = [
        ("positive", "positive"),
        ("negative", "negative"),
        ("neutral", "positive"),
        ("positive", "negative"),
        ("neutral", "neutral"),
    ]
    for i, (task, gen) in enumerate(zip(tasks, gens)):
        gt, pred = predictions[i]
        te = TaskEvaluation(
            id=f"te-cls-{uuid.uuid4().hex[:8]}",
            evaluation_id=eval_run.id,
            judge_run_id=eval_run._test_judge_run.id,
            task_id=task.id,
            generation_id=gen.id,
            field_name="classification",
            answer_type="classification",
            ground_truth={"value": gt},
            prediction={"value": pred},
            metrics={"accuracy": 1.0 if gt == pred else 0.0},
            passed=gt == pred,
            created_at=datetime.now(timezone.utc),
        )
        db.add(te)
        evals.append(te)
    await db.flush()
    return evals


async def _make_human_session(db, project, admin, *, session_type="likert",
                              items_evaluated=3):
    session = HumanEvaluationSession(
        id=f"hes-{uuid.uuid4().hex[:8]}",
        project_id=project.id,
        evaluator_id=admin.id,
        session_type=session_type,
        items_evaluated=items_evaluated,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session


async def _make_likert_evaluations(db, session, tasks):
    evals = []
    dimensions = ["accuracy", "clarity", "completeness"]
    for task in tasks[:3]:
        for dim in dimensions:
            le = LikertScaleEvaluation(
                id=f"le-{uuid.uuid4().hex[:8]}",
                session_id=session.id,
                task_id=task.id,
                response_id=f"resp-{uuid.uuid4().hex[:8]}",
                dimension=dim,
                rating=3 + (hash(dim) % 3),
                created_at=datetime.now(timezone.utc),
            )
            db.add(le)
            evals.append(le)
    await db.flush()
    return evals


async def _make_preference_rankings(db, session, tasks):
    rankings = []
    winners = ["a", "b", "a", "tie", "a"]
    for i, task in enumerate(tasks):
        pr = PreferenceRanking(
            id=f"pr-{uuid.uuid4().hex[:8]}",
            session_id=session.id,
            task_id=task.id,
            response_a_id=f"resp-a-{i}",
            response_b_id=f"resp-b-{i}",
            winner=winners[i],
            confidence=0.8,
            created_at=datetime.now(timezone.utc),
        )
        db.add(pr)
        rankings.append(pr)
    await db.flush()
    return rankings


# ===========================================================================
# Group 1: GET /evaluations/results/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestGetEvaluationResults:
    """Tests for GET /evaluations/results/{project_id}"""

    @pytest.mark.asyncio
    async def test_get_automated_results(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) >= 1
        assert automated[0]["results"]["metrics"]["accuracy"] == 0.85

    @pytest.mark.asyncio
    async def test_get_results_with_human_likert(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        await _make_eval_run(async_test_db, project, admin)
        session = await _make_human_session(async_test_db, project, admin)
        await _make_likert_evaluations(async_test_db, session, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        likert = [r for r in data if r["results"].get("type") == "human_likert"]
        assert len(likert) >= 1
        dims = likert[0]["results"]["dimensions"]
        assert "accuracy" in dims or "clarity" in dims or "completeness" in dims

    @pytest.mark.asyncio
    async def test_get_results_with_preference_rankings(
        self, async_test_client, async_test_db
    ):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        await _make_eval_run(async_test_db, project, admin)
        session = await _make_human_session(
            async_test_db, project, admin, session_type="preference", items_evaluated=5
        )
        await _make_preference_rankings(async_test_db, session, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        pref = [r for r in data if r["results"].get("type") == "human_preference"]
        assert len(pref) >= 1
        assert "counts" in pref[0]["results"]
        assert "percentages" in pref[0]["results"]

    @pytest.mark.asyncio
    async def test_get_results_automated_only(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        await _make_eval_run(async_test_db, project, admin)
        session = await _make_human_session(async_test_db, project, admin)
        await _make_likert_evaluations(async_test_db, session, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}?include_human=false"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        human = [r for r in data if "human" in r["results"].get("type", "")]
        assert len(human) == 0

    @pytest.mark.asyncio
    async def test_get_results_human_only(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        await _make_eval_run(async_test_db, project, admin)
        session = await _make_human_session(async_test_db, project, admin)
        await _make_likert_evaluations(async_test_db, session, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}?include_automated=false"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) == 0

    @pytest.mark.asyncio
    async def test_get_results_limit(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}?limit=1"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) <= 1

    @pytest.mark.asyncio
    async def test_get_results_no_auth(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await async_test_db.commit()
        resp = await async_test_client.get(f"{RESULTS_PREFIX}/results/{project.id}")
        assert resp.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_results_nonexistent_project(self, async_test_client, async_test_db):
        """Superadmin can access any project; nonexistent returns empty results."""
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/nonexistent-project-id"
            )
        # Superadmin passes access check; endpoint returns 200 with empty list
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_results_empty_project(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)


# ===========================================================================
# POST /evaluations/export/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestExportEvaluationResults:
    """Tests for POST /evaluations/export/{project_id}"""

    @pytest.mark.asyncio
    async def test_export_json(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{RESULTS_PREFIX}/export/{project.id}?format=json"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["project_id"] == project.id
        assert "results" in data

    @pytest.mark.asyncio
    async def test_export_csv(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{RESULTS_PREFIX}/export/{project.id}?format=csv"
            )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_no_auth(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await async_test_db.commit()
        resp = await async_test_client.post(
            f"{RESULTS_PREFIX}/export/{project.id}?format=json"
        )
        assert resp.status_code in [401, 403]


# ===========================================================================
# GET /evaluations/{evaluation_id}/samples
# ===========================================================================


@pytest.mark.integration
class TestGetEvaluationSamples:
    """Tests for GET /evaluations/{evaluation_id}/samples"""

    async def _seed_samples(self, db):
        admin = await _make_admin(db)
        project = await _make_project(db, admin)
        tasks = await _make_tasks(db, project, admin)
        rg = await _make_response_generation(db, project, admin)
        gens = await _make_generations(db, tasks, rg)
        er = await _make_eval_run(db, project, admin)
        await _make_task_evaluations(db, er, tasks, gens)
        await db.commit()
        return admin, project, er

    @pytest.mark.asyncio
    async def test_get_samples(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_get_samples_filter_by_field(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples?field_name=text_answer"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_get_samples_filter_passed_true(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples?passed=true"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for item in data["items"]:
            assert item["passed"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_filter_passed_false(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples?passed=false"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for item in data["items"]:
            assert item["passed"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_pagination(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples?page=1&page_size=2"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["has_next"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_samples_page_2(self, async_test_client, async_test_db):
        admin, project, er = await self._seed_samples(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/samples?page=2&page_size=2"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["page"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_samples_nonexistent_evaluation(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/nonexistent-eval-id/samples"
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_get_samples_no_auth(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        er = await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        resp = await async_test_client.get(f"{RESULTS_PREFIX}/{er.id}/samples")
        assert resp.status_code in [401, 403]


# ===========================================================================
# GET /evaluations/{evaluation_id}/metrics/{metric_name}/distribution
# ===========================================================================


@pytest.mark.integration
class TestMetricDistribution:
    """Tests for GET /evaluations/{evaluation_id}/metrics/{metric_name}/distribution"""

    async def _seed(self, db):
        admin = await _make_admin(db)
        project = await _make_project(db, admin)
        tasks = await _make_tasks(db, project, admin)
        rg = await _make_response_generation(db, project, admin)
        gens = await _make_generations(db, tasks, rg)
        er = await _make_eval_run(db, project, admin)
        await _make_task_evaluations(db, er, tasks, gens)
        await db.commit()
        return admin, er

    @pytest.mark.asyncio
    async def test_get_distribution(self, async_test_client, async_test_db):
        admin, er = await self._seed(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/metrics/accuracy/distribution"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["metric_name"] == "accuracy"
        assert "mean" in data
        assert "median" in data
        assert "std" in data
        assert "min" in data
        assert "max" in data
        assert "quartiles" in data
        assert "histogram" in data

    @pytest.mark.asyncio
    async def test_distribution_stats_correct(self, async_test_client, async_test_db):
        admin, er = await self._seed(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/metrics/accuracy/distribution"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["min"] <= data["mean"] <= data["max"]
        assert data["min"] <= data["median"] <= data["max"]
        assert data["std"] >= 0

    @pytest.mark.asyncio
    async def test_distribution_with_field_filter(self, async_test_client, async_test_db):
        admin, er = await self._seed(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/metrics/accuracy/distribution?field_name=text_answer"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["metric_name"] == "accuracy"

    @pytest.mark.asyncio
    async def test_distribution_nonexistent_metric(self, async_test_client, async_test_db):
        admin, er = await self._seed(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/metrics/nonexistent_metric/distribution"
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_distribution_nonexistent_evaluation(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/nonexistent-eval/metrics/accuracy/distribution"
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_distribution_no_auth(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        er = await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        resp = await async_test_client.get(
            f"{RESULTS_PREFIX}/{er.id}/metrics/accuracy/distribution"
        )
        assert resp.status_code in [401, 403]


# ===========================================================================
# GET /evaluations/{evaluation_id}/confusion-matrix
# ===========================================================================


@pytest.mark.integration
class TestConfusionMatrix:
    """Tests for GET /evaluations/{evaluation_id}/confusion-matrix"""

    async def _seed_classification(self, db):
        admin = await _make_admin(db)
        project = await _make_project(db, admin)
        tasks = await _make_tasks(db, project, admin)
        rg = await _make_response_generation(db, project, admin)
        gens = await _make_generations(db, tasks, rg)
        er = await _make_eval_run(db, project, admin)
        await _make_classification_evaluations(db, er, tasks, gens)
        await db.commit()
        return admin, er

    @pytest.mark.asyncio
    async def test_get_confusion_matrix(self, async_test_client, async_test_db):
        admin, er = await self._seed_classification(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix?field_name=classification"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["field_name"] == "classification"
        assert "labels" in data
        assert "matrix" in data
        assert "accuracy" in data
        assert "precision_per_class" in data
        assert "recall_per_class" in data
        assert "f1_per_class" in data

    @pytest.mark.asyncio
    async def test_confusion_matrix_labels(self, async_test_client, async_test_db):
        admin, er = await self._seed_classification(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix?field_name=classification"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        labels = data["labels"]
        assert len(labels) >= 2
        assert labels == sorted(labels)

    @pytest.mark.asyncio
    async def test_confusion_matrix_dimensions(self, async_test_client, async_test_db):
        admin, er = await self._seed_classification(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix?field_name=classification"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        n = len(data["labels"])
        assert len(data["matrix"]) == n
        for row in data["matrix"]:
            assert len(row) == n

    @pytest.mark.asyncio
    async def test_confusion_matrix_accuracy_range(self, async_test_client, async_test_db):
        admin, er = await self._seed_classification(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix?field_name=classification"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert 0.0 <= data["accuracy"] <= 1.0

    @pytest.mark.asyncio
    async def test_confusion_matrix_no_field(self, async_test_client, async_test_db):
        admin, er = await self._seed_classification(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix"
            )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_confusion_matrix_nonexistent_field(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, admin)
        gens = await _make_generations(async_test_db, tasks, rg)
        er = await _make_eval_run(async_test_db, project, admin)
        await _make_task_evaluations(async_test_db, er, tasks, gens)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/{er.id}/confusion-matrix?field_name=nonexistent_field"
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_confusion_matrix_nonexistent_evaluation(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/nonexistent/confusion-matrix?field_name=classification"
            )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# metadata endpoints (routers/evaluations/metadata/)
# ===========================================================================


@pytest.mark.integration
class TestEvaluationMetadataEndpoints:
    """Tests for metadata endpoints in routers/evaluations/metadata/"""

    @pytest.mark.asyncio
    async def test_get_evaluated_models(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, admin)
        await _make_generations(async_test_db, tasks, rg)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_evaluated_models_includes_model_info(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, admin)
        await _make_generations(async_test_db, tasks, rg)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data:
            model = data[0]
            assert "model_id" in model
            assert "model_name" in model

    @pytest.mark.asyncio
    async def test_evaluated_models_with_configured(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, admin)
        await _make_generations(async_test_db, tasks, rg)
        await _make_eval_run(async_test_db, project, admin)
        project.generation_config = {
            "selected_configuration": {
                "models": ["gpt-4", "claude-3-sonnet"],
            }
        }
        async_test_db.add(project)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluated-models?include_configured=true"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_evaluated_models_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/nonexistent-project/evaluated-models"
            )
        assert resp.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_evaluated_models_no_auth(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await async_test_db.commit()
        resp = await async_test_client.get(
            f"{META_PREFIX}/projects/{project.id}/evaluated-models"
        )
        assert resp.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_configured_methods_no_config(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/configured-methods"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["project_id"] == project.id
        assert data["fields"] == []

    @pytest.mark.asyncio
    async def test_configured_methods_with_config(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        project.evaluation_config = {
            "selected_methods": {
                "text_answer": {
                    "automated": ["accuracy", "f1"],
                    "human": ["likert"],
                }
            },
            "available_methods": {
                "text_answer": {
                    "type": "text",
                    "to_name": "text",
                }
            },
        }
        async_test_db.add(project)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/configured-methods"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["fields"]) >= 1
        field = data["fields"][0]
        assert field["field_name"] == "text_answer"
        assert len(field["automated_methods"]) >= 1
        assert len(field["human_methods"]) >= 1


# ===========================================================================
# GET /projects/{project_id}/evaluation-history
# ===========================================================================


@pytest.mark.integration
class TestEvaluationHistory:
    """Tests for GET /projects/{project_id}/evaluation-history"""

    @pytest.mark.asyncio
    async def test_evaluation_history(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        # Issue #111: ``metric`` was renamed to ``metrics`` and the
        # response is now ``{series: [...]}``.
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4&metrics=accuracy"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert isinstance(data["series"], list)

    @pytest.mark.asyncio
    async def test_evaluation_history_data_points(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4&metrics=accuracy"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Issue #111: data points live under each series rather than a
        # top-level "data" array.
        for series in data["series"]:
            assert "metric" in series
            assert "evaluation_config_id" in series
            assert "display_name" in series
            for point in series.get("data", []):
                assert "date" in point
                assert "model_id" in point
                assert "value" in point
                assert "sample_count" in point

    @pytest.mark.asyncio
    async def test_evaluation_history_date_filter(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        await _make_eval_run(async_test_db, project, admin)
        await async_test_db.commit()
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
        tomorrow = (datetime.utcnow() + timedelta(days=1)).isoformat()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/{project.id}/evaluation-history"
                f"?model_ids=gpt-4&metrics=accuracy&start_date={yesterday}&end_date={tomorrow}"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_evaluation_history_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/projects/nonexistent/evaluation-history?model_ids=gpt-4&metrics=accuracy"
            )
        assert resp.status_code in [403, 404]


# ===========================================================================
# GET /significance/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestSignificanceTests:
    """Tests for GET /significance/{project_id}"""

    @pytest.mark.asyncio
    async def test_significance_endpoint(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        tasks = await _make_tasks(async_test_db, project, admin)
        rg = await _make_response_generation(async_test_db, project, admin)
        gens = await _make_generations(async_test_db, tasks, rg)
        er = await _make_eval_run(async_test_db, project, admin)
        await _make_task_evaluations(async_test_db, er, tasks, gens)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/significance/{project.id}"
                "?model_ids=gpt-4&metrics=accuracy"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "comparisons" in data or "message" in data

    @pytest.mark.asyncio
    async def test_significance_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{META_PREFIX}/significance/nonexistent?model_ids=gpt-4&metrics=accuracy"
            )
        assert resp.status_code in [403, 404]


# ===========================================================================
# Model comparison via results endpoints
# ===========================================================================


@pytest.mark.integration
class TestModelComparison:
    """Tests for model comparison via results endpoints."""

    @pytest.mark.asyncio
    async def test_multiple_eval_runs(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        for i in range(3):
            er = EvaluationRun(
                id=f"er-multi-{uuid.uuid4().hex[:8]}",
                project_id=project.id,
                model_id=f"model-{i}",
                evaluation_type_ids=["accuracy"],
                metrics={"accuracy": 0.7 + (i * 0.1)},
                status="completed",
                samples_evaluated=10,
                created_by=admin.id,
                created_at=datetime.now(timezone.utc),
            )
            async_test_db.add(er)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}?limit=100"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        assert len(automated) >= 3

    @pytest.mark.asyncio
    async def test_result_ordering(self, async_test_client, async_test_db):
        admin = await _make_admin(async_test_db)
        project = await _make_project(async_test_db, admin)
        for i in range(3):
            er = EvaluationRun(
                id=f"er-order-{uuid.uuid4().hex[:8]}",
                project_id=project.id,
                model_id="gpt-4",
                evaluation_type_ids=["accuracy"],
                metrics={"accuracy": 0.5 + (i * 0.1)},
                status="completed",
                samples_evaluated=10,
                created_by=admin.id,
                created_at=datetime.now(timezone.utc) - timedelta(hours=3 - i),
            )
            async_test_db.add(er)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{RESULTS_PREFIX}/results/{project.id}?limit=100"
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        automated = [r for r in data if r["results"].get("type") == "automated"]
        if len(automated) >= 2:
            for i in range(len(automated) - 1):
                t1 = automated[i]["created_at"]
                t2 = automated[i + 1]["created_at"]
                assert t1 >= t2
