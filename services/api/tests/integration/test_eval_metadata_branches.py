"""Behavioral integration tests for the uncovered branches of
``routers/evaluations/metadata.py`` (mounted at prefix ``/api/evaluations`` —
see ``routers/evaluations/__init__.py`` + ``main.py``).

Endpoints under test::

  GET  /api/evaluations/projects/{project_id}/evaluated-models
  GET  /api/evaluations/projects/{project_id}/configured-methods
  GET  /api/evaluations/projects/{project_id}/evaluation-history
  GET  /api/evaluations/significance/{project_id}
  POST /api/evaluations/projects/{project_id}/statistics

These handlers were migrated to the async DB lane
(``db: AsyncSession = Depends(get_async_db)`` + ``await db.execute(select(...))``).
This suite drives them over HTTP via the ``async_test_client`` fixture (wired to
``get_async_db``) and seeds the graph via the SAVEPOINT-isolated ``async_test_db``
session. Authentication is provided by overriding ``require_user`` with an
``auth_module.models.User`` built from a real seeded ``models.User`` row
(``_as_user``), so the user's ``id`` / ``is_superadmin`` drive the REAL async
access check — no access-helper patching.

Every test asserts the exact status code + concrete response JSON, and — wherever
the seeded graph drives a counted / aggregated value — re-reads the persisted rows
from ``async_test_db`` (or recomputes from the seeded Python values) to prove the
response reflects real DB state.

Access model recap (routers/projects/helpers.check_project_accessible_async):
  * superadmin -> always allowed (the non-403 happy-path tests seed a superadmin
    and auth as them; access returns True natively).
  * a PRIVATE project's creator is the only non-superadmin allowed; a private
    project created by a contributor and hit by an annotator (neither superadmin
    nor creator) with ``X-Organization-Context: private`` -> deterministic 403.
    ``_decide_project_accessible_context_mode`` short-circuits private projects to
    ``user.id == project.created_by`` -> False -> 403. The 403 tests exercise the
    REAL async access logic (no patch).

MinIO byte-streaming endpoints (export/import) are out of scope — this router
has none.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

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
from project_models import Project, Task

BASE = "/api/evaluations"


# ---------------------------------------------------------------------------
# Auth + user seeding helpers (copied from
# tests/unit/test_evaluation_metadata_extended.py — the proven async recipe)
# ---------------------------------------------------------------------------


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override ``require_user`` with an ``AuthUser`` built from a seeded DB User.

    The auth user's ``id`` / ``is_superadmin`` drive the REAL async access check,
    so this works for both the superadmin happy paths and the non-superadmin 403
    paths without patching ``check_project_accessible_async``.
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


async def _seed_user(db, *, is_superadmin=True):
    """Seed a real ``models.User`` row whose id/role drive the access check."""
    u = User(
        id=_uid(),
        username=f"meta-branch-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta Branch User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


# A binary <Choices> control (Ja/Nein) — detected as the BINARY answer type by
# the answer-type detector, name="answer", to_name="text".
BINARY_LABEL_CONFIG = (
    '<View>'
    '<Text name="text" value="$text"/>'
    '<Choices name="answer" toName="text">'
    '<Choice value="Ja"/><Choice value="Nein"/>'
    '</Choices>'
    '</View>'
)


# ---------------------------------------------------------------------------
# Seeding helpers (async)
# ---------------------------------------------------------------------------


async def _make_project(
    db,
    creator,
    *,
    label_config=BINARY_LABEL_CONFIG,
    evaluation_config=None,
    generation_config=None,
    is_private=False,
    num_tasks=0,
):
    """Create a Project (optionally private, optionally with N tasks).

    Private projects are NOT linked to any organization; for the 403 scenario the
    requester must be neither creator nor member, which holds as long as the
    project stays private and the annotator is not the creator.
    """
    project = Project(
        id=_uid(),
        title=f"meta-branch-{uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config=label_config,
        evaluation_config=evaluation_config,
        generation_config=generation_config,
        is_private=is_private,
    )
    db.add(project)
    await db.flush()
    # Capture scalar values into locals before commit (expire_on_commit=False is
    # set, but keep the discipline to avoid MissingGreenlet on lazy refresh).
    project_id = project.id
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=project_id,
            inner_id=i + 1,
            data={"text": f"text #{i}"},
            created_by=creator.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    await db.commit()
    return project, tasks


async def _seed_model_eval(
    db,
    project,
    creator,
    model_id,
    tasks,
    *,
    metric_name="accuracy",
    per_task_values,
    config_id=None,
    run_metrics=None,
    created_at=None,
    completed_at=None,
):
    """Seed a completed EvaluationRun + Generations + per-sample TaskEvaluations
    for ``model_id`` over ``tasks``. Returns (eval_run, judge_run, generations).

    Each TaskEvaluation row carries ``metrics={metric_name: value}`` so the
    sample-level aggregations (statistics / significance / history) have real
    numbers to read. ``config_id`` populates the discrete
    ``evaluation_config_id`` column used by the issue-#111 scoping filters.
    """
    ts = created_at or datetime.now(timezone.utc)
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        status="completed",
        created_by=creator.id,
        started_at=ts,
        completed_at=ts,
    )
    db.add(rg)
    await db.flush()
    rg_id = rg.id

    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(),
            generation_id=rg_id,
            task_id=t.id,
            model_id=model_id,
            run_index=i,
            case_data=json.dumps(t.data),
            response_content=f"answer from {model_id} #{i}",
            label_config_version="v1",
            status="completed",
            parse_status="success",
        )
        db.add(gen)
        gens.append(gen)
    await db.flush()

    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=[metric_name],
        metrics=run_metrics if run_metrics is not None else {metric_name: per_task_values[0]},
        status="completed",
        samples_evaluated=len(tasks),
        has_sample_results=True,
        created_by=creator.id,
        created_at=ts,
        completed_at=completed_at or ts,
    )
    db.add(er)
    await db.flush()
    er_id = er.id

    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL — use the
    # catch-all (judge_model_id=None) judge-run shape for deterministic metrics.
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er_id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()
    judge_run_id = judge_run.id

    for i, t in enumerate(tasks):
        te = TaskEvaluation(
            id=_uid(),
            evaluation_id=er_id,
            judge_run_id=judge_run_id,
            task_id=t.id,
            generation_id=gens[i].id,
            field_name="answer",
            evaluation_config_id=config_id,
            answer_type="choices",
            ground_truth={"value": "Ja"},
            prediction={"value": "Ja"},
            metrics={metric_name: per_task_values[i]},
            passed=per_task_values[i] > 0.5,
        )
        db.add(te)
    await db.flush()
    await db.commit()
    return er, judge_run, gens


# ===========================================================================
# Shared 403 access-denied path (one per endpoint)
# ===========================================================================


@pytest.mark.integration
class TestAccessDenied:
    """Every metadata endpoint runs check_project_accessible_async after the 404
    guard. A private project created by a contributor and hit by an annotator
    (neither superadmin nor creator) with the private context yields a
    deterministic 403 — the branch the deep suite never reaches. The access
    helper runs FOR REAL here (no patch)."""

    async def _private_project_and_annotator(self, db):
        # creator = contributor (non-superadmin); requester = annotator
        # (non-superadmin, neither creator nor member of any org owning it).
        contributor = await _seed_user(db, is_superadmin=False)
        annotator = await _seed_user(db, is_superadmin=False)
        project, _ = await _make_project(
            db, contributor, is_private=True, num_tasks=1
        )
        return project, annotator

    _PRIVATE_HEADERS = {"X-Organization-Context": "private"}

    @pytest.mark.asyncio
    async def test_evaluated_models_403(self, async_test_client, async_test_db):
        project, annotator = await self._private_project_and_annotator(async_test_db)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluated-models",
                headers=self._PRIVATE_HEADERS,
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_configured_methods_403(self, async_test_client, async_test_db):
        project, annotator = await self._private_project_and_annotator(async_test_db)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/configured-methods",
                headers=self._PRIVATE_HEADERS,
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_evaluation_history_403(self, async_test_client, async_test_db):
        project, annotator = await self._private_project_and_annotator(async_test_db)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
                headers=self._PRIVATE_HEADERS,
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_significance_403(self, async_test_client, async_test_db):
        project, annotator = await self._private_project_and_annotator(async_test_db)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"{BASE}/significance/{project.id}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
                headers=self._PRIVATE_HEADERS,
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_statistics_403(self, async_test_client, async_test_db):
        project, annotator = await self._private_project_and_annotator(async_test_db)
        with _as_user(annotator):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
                headers=self._PRIVATE_HEADERS,
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"


# ===========================================================================
# GET /evaluated-models — include_configured flags + empty + config-only model
# ===========================================================================


@pytest.mark.integration
class TestEvaluatedModels:
    @pytest.mark.asyncio
    async def test_empty_project_returns_empty_list(
        self, async_test_client, async_test_db
    ):
        """No generations / evaluations / annotations and no configured models
        → ``all_model_ids`` empty → early ``return []`` (line ~383)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, _ = await _make_project(async_test_db, admin, num_tasks=2)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluated-models",
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_include_configured_surfaces_config_only_model(
        self, async_test_client, async_test_db
    ):
        """include_configured=True pulls models from generation_config that have
        no results yet. The config-only model must appear with is_configured
        True, has_generations/has_results False, and a NULL average_score
        (the ``None if include_configured`` branch), and must sort AFTER the
        evaluated model (configured-with-results first)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        gen_config = {"selected_configuration": {"models": ["gpt-4o", "config-only-model"]}}
        project, tasks = await _make_project(
            async_test_db, admin,
            generation_config=gen_config, num_tasks=4,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.8, 0.82, 0.84, 0.86],
        )

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_id = {m["model_id"]: m for m in body}
        assert "gpt-4o" in by_id
        assert "config-only-model" in by_id

        evaluated = by_id["gpt-4o"]
        assert evaluated["is_configured"] is True
        assert evaluated["has_generations"] is True
        assert evaluated["has_results"] is True
        assert evaluated["evaluation_count"] >= 1
        assert evaluated["average_score"] is not None

        config_only = by_id["config-only-model"]
        assert config_only["is_configured"] is True
        assert config_only["has_generations"] is False
        assert config_only["has_results"] is False
        # include_configured + no scores → average_score is None (not 0.0).
        assert config_only["average_score"] is None
        # Configured-with-results sorts before configured-without-results.
        assert body.index(evaluated) < body.index(config_only)

    @pytest.mark.asyncio
    async def test_evaluated_model_average_matches_seeded_run_metrics(
        self, async_test_client, async_test_db
    ):
        """Without include_configured, average_score is the mean of the run's
        ``metrics`` numeric values. Seed a single run whose metrics dict has
        one value so the average is deterministic, then assert it round-trips."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, tasks = await _make_project(async_test_db, admin, num_tasks=3)
        await _seed_model_eval(
            async_test_db, project, admin, "claude-3-sonnet", tasks,
            per_task_values=[0.5, 0.5, 0.5],
            run_metrics={"accuracy": 0.7},
        )

        # DB-state: exactly one completed EvaluationRun for the model.
        runs = (
            (await async_test_db.execute(
                select(EvaluationRun).where(
                    EvaluationRun.project_id == project.id,
                    EvaluationRun.model_id == "claude-3-sonnet",
                )
            )).scalars().all()
        )
        assert len(runs) == 1
        assert runs[0].metrics == {"accuracy": 0.7}

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluated-models",
            )
        assert resp.status_code == 200, resp.text
        row = next(m for m in resp.json() if m["model_id"] == "claude-3-sonnet")
        assert row["provider"] == "Anthropic"
        assert row["average_score"] == 0.7
        assert row["total_samples"] == 3


# ===========================================================================
# GET /configured-methods — fields shape, has_results, suffix-noise, human
# ===========================================================================


@pytest.mark.integration
class TestConfiguredMethods:
    @pytest.mark.asyncio
    async def test_no_evaluation_config_returns_empty_fields(
        self, async_test_client, async_test_db
    ):
        """Project with evaluation_config=None → ``{project_id, fields: []}``."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, _ = await _make_project(async_test_db, admin)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"project_id": project.id, "fields": []}

    @pytest.mark.asyncio
    async def test_no_selected_methods_returns_empty_fields(
        self, async_test_client, async_test_db
    ):
        """evaluation_config present but no ``selected_methods`` → empty fields."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, _ = await _make_project(
            async_test_db, admin,
            evaluation_config={"available_methods": {"answer": {"type": "binary"}}},
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["fields"] == []

    @pytest.mark.asyncio
    async def test_has_results_counts_scored_taskevaluations(
        self, async_test_client, async_test_db
    ):
        """The result map counts scored TaskEvaluation rows per metric key
        (jsonb_object_keys over TaskEvaluation.metrics). We seed 3 rows whose
        metrics carry an ``accuracy`` key plus a ``_details`` sidekey that must
        be filtered out of the dropdown. ``accuracy`` should show
        result_count=3 / has_results True; the configured-but-unscored ``f1``
        shows result_count=0 / has_results False."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        eval_config = {
            "selected_methods": {
                "answer": {"automated": ["accuracy", "f1"], "human": []}
            },
            "available_methods": {"answer": {"type": "binary", "to_name": "text"}},
        }
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=3,
        )
        # Seed an eval whose per-sample metrics carry accuracy + a noise sidekey.
        er, judge_run, gens = await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.9, 0.9, 0.9],
        )
        er_id = er.id
        # Overwrite metrics so each row also has the _details suffix-noise key.
        rows_to_patch = (
            (await async_test_db.execute(
                select(TaskEvaluation).where(TaskEvaluation.evaluation_id == er_id)
            )).scalars().all()
        )
        for te in rows_to_patch:
            te.metrics = {"accuracy": 0.9, "accuracy_details": {"raw": 1}}
        await async_test_db.commit()

        # DB-state: 3 scored rows, all carrying the accuracy key.
        rows = (
            (await async_test_db.execute(
                select(TaskEvaluation).where(TaskEvaluation.evaluation_id == er_id)
            )).scalars().all()
        )
        assert len(rows) == 3
        assert all("accuracy" in r.metrics for r in rows)

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == project.id
        field = next(f for f in body["fields"] if f["field_name"] == "answer")
        methods = {m["method_name"]: m for m in field["automated_methods"]}

        assert methods["accuracy"]["has_results"] is True
        assert methods["accuracy"]["result_count"] == 3
        assert methods["accuracy"]["last_run"] is not None
        assert methods["accuracy"]["is_configured"] is True

        assert methods["f1"]["has_results"] is False
        assert methods["f1"]["result_count"] == 0
        assert methods["f1"]["last_run"] is None

        # The _details suffix-noise key must NOT surface as its own method.
        assert "accuracy_details" not in methods

    @pytest.mark.asyncio
    async def test_llm_judge_method_type_and_human_method(
        self, async_test_client, async_test_db
    ):
        """An ``llm_judge_*`` automated method is typed 'llm-judge'; a human
        method surfaces under human_methods with method_type 'human'. Neither
        has scored rows → has_results False / result_count 0."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        eval_config = {
            "selected_methods": {
                "answer": {
                    "automated": [{"name": "llm_judge_classic", "parameters": {"x": 1}}],
                    "human": ["likert"],
                }
            },
            "available_methods": {"answer": {"type": "binary", "to_name": "text"}},
        }
        project, _ = await _make_project(
            async_test_db, admin, evaluation_config=eval_config,
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/configured-methods",
            )
        assert resp.status_code == 200, resp.text
        field = next(
            f for f in resp.json()["fields"] if f["field_name"] == "answer"
        )
        auto = field["automated_methods"][0]
        assert auto["method_name"] == "llm_judge_classic"
        assert auto["method_type"] == "llm-judge"
        assert auto["parameters"] == {"x": 1}
        assert auto["has_results"] is False
        assert auto["result_count"] == 0

        human = field["human_methods"][0]
        assert human["method_name"] == "likert"
        assert human["method_type"] == "human"
        assert human["has_results"] is False


# ===========================================================================
# GET /evaluation-history — required metrics, series content, config scoping
# ===========================================================================


@pytest.mark.integration
class TestEvaluationHistory:
    @pytest.mark.asyncio
    async def test_missing_metrics_param_returns_422(
        self, async_test_client, async_test_db
    ):
        """``metrics`` is a required query param → omitting it is a 422."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, _ = await _make_project(async_test_db, admin)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history?model_ids=gpt-4o",
            )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_series_buckets_per_day_and_resolves_display_name(
        self, async_test_client, async_test_db
    ):
        """One model, one config id, two days of samples → one series whose
        display_name resolves from the project's evaluation_configs lookup and
        whose data has one point per day, each carrying the per-day mean and a
        sample_count matching the seeded rows."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        cfg_id = "cfg-bleu-3"
        eval_config = {
            "evaluation_configs": [
                {"id": cfg_id, "metric": "accuracy", "display_name": "BLEU (3-gram)"}
            ]
        }
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=2,
        )
        day1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.80, 0.90], config_id=cfg_id,
            created_at=day1,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.60, 0.60], config_id=cfg_id,
            created_at=day2,
        )

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
            )
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 1
        s = series[0]
        assert s["metric"] == "accuracy"
        assert s["evaluation_config_id"] == cfg_id
        assert s["display_name"] == "BLEU (3-gram)"

        points = {p["date"]: p for p in s["data"]}
        assert set(points) == {"2026-05-01", "2026-05-03"}
        # day1 mean of [0.80, 0.90] = 0.85; day2 mean of [0.60, 0.60] = 0.60.
        assert points["2026-05-01"]["value"] == 0.85
        assert points["2026-05-01"]["sample_count"] == 2
        assert points["2026-05-03"]["value"] == 0.60
        # Data points are sorted ascending by date.
        assert [p["date"] for p in s["data"]] == ["2026-05-01", "2026-05-03"]

    @pytest.mark.asyncio
    async def test_evaluation_config_ids_filter_scopes_series(
        self, async_test_client, async_test_db
    ):
        """Two configs of the same metric produce two series; passing
        ``evaluation_config_ids`` for only one scopes the response to that
        config's series."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        eval_config = {
            "evaluation_configs": [
                {"id": "cfg-a", "metric": "accuracy", "display_name": "Config A"},
                {"id": "cfg-b", "metric": "accuracy", "display_name": "Config B"},
            ]
        }
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=2,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.7, 0.7], config_id="cfg-a",
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.4, 0.4], config_id="cfg-b",
        )

        with _as_user(admin):
            # Unscoped: both configs' series present.
            resp_all = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy",
            )
            assert resp_all.status_code == 200, resp_all.text
            all_cfg_ids = {s["evaluation_config_id"] for s in resp_all.json()["series"]}
            assert all_cfg_ids == {"cfg-a", "cfg-b"}

            # Scoped to cfg-a only.
            resp_scoped = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy&evaluation_config_ids=cfg-a",
            )
        assert resp_scoped.status_code == 200, resp_scoped.text
        scoped = resp_scoped.json()["series"]
        assert len(scoped) == 1
        assert scoped[0]["evaluation_config_id"] == "cfg-a"
        assert scoped[0]["display_name"] == "Config A"

    @pytest.mark.asyncio
    async def test_end_date_filter_excludes_later_runs(
        self, async_test_client, async_test_db
    ):
        """An ``end_date`` earlier than a run's created_at excludes it. Seed two
        days; cap end_date at day1 → only day1 survives."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, tasks = await _make_project(async_test_db, admin, num_tasks=2)
        day1 = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.5, 0.5], created_at=day1,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.9, 0.9], created_at=day2,
        )

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{project.id}/evaluation-history"
                "?model_ids=gpt-4o&metrics=accuracy&end_date=2026-05-15T00:00:00",
            )
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 1
        dates = {p["date"] for p in series[0]["data"]}
        assert dates == {"2026-05-01"}


# ===========================================================================
# GET /significance/{project_id} — default branch, real comparison, config scope
# ===========================================================================


@pytest.mark.integration
class TestSignificance:
    @pytest.mark.asyncio
    async def test_insufficient_samples_default_comparison(
        self, async_test_client, async_test_db
    ):
        """When a model has <2 scored samples the comparison short-circuits to
        the default {p_value: 1.0, significant: False, effect_size: 0.0,
        stars: ""} entry — no t-test is run."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, tasks = await _make_project(async_test_db, admin, num_tasks=1)
        # gpt-4o: 1 sample; claude: 1 sample → both <2.
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.8], run_metrics={"accuracy": 0.8},
        )
        await _seed_model_eval(
            async_test_db, project, admin, "claude-3-sonnet", tasks,
            per_task_values=[0.6], run_metrics={"accuracy": 0.6},
        )

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{project.id}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy"
                # Scope to a non-matching config so the run-level direct fallback
                # is skipped — guarantees each model keeps <2 samples and hits
                # the short-circuit default rather than the t-test branch.
                "&evaluation_config_ids=no-such-config",
            )
        assert resp.status_code == 200, resp.text
        comparisons = resp.json()["comparisons"]
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c["model_a"] == "gpt-4o"
        assert c["model_b"] == "claude-3-sonnet"
        assert c["metric"] == "accuracy"
        assert c["p_value"] == 1.0
        assert c["significant"] is False
        assert c["effect_size"] == 0.0
        assert c["stars"] == ""

    @pytest.mark.asyncio
    async def test_two_models_real_ttest_comparison(
        self, async_test_client, async_test_db
    ):
        """With ≥2 samples per model, the real Welch t-test runs: a clearly
        separated pair (all-high vs all-low) is flagged significant with a
        p_value < 0.05 and a non-empty star string. Scoping to the seeded config
        keeps the comparison config-local (no run-level fallback)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        cfg_id = "cfg-acc"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=5,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.95, 0.96, 0.97, 0.94, 0.95], config_id=cfg_id,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "claude-3-sonnet", tasks,
            per_task_values=[0.10, 0.12, 0.09, 0.11, 0.08], config_id=cfg_id,
        )

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{project.id}"
                "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy"
                f"&evaluation_config_ids={cfg_id}",
            )
        assert resp.status_code == 200, resp.text
        comparisons = resp.json()["comparisons"]
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c["p_value"] < 0.05
        assert c["significant"] is True
        assert c["stars"] != ""
        # Large separation → non-trivial effect size.
        assert abs(c["effect_size"]) > 0.0


# ===========================================================================
# POST /statistics — 404 no-evals, compare_models warning, field display, sample
# ===========================================================================


@pytest.mark.integration
class TestStatistics:
    @pytest.mark.asyncio
    async def test_no_completed_evaluations_returns_404(
        self, async_test_client, async_test_db
    ):
        """A project that exists + is accessible but has zero completed
        EvaluationRuns → 404 'No completed evaluations found for this project'."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, _ = await _make_project(async_test_db, admin, num_tasks=2)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
            )
        assert resp.status_code == 404, resp.text
        assert "No completed evaluations" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_model_aggregation_stats_round_trip(
        self, async_test_client, async_test_db
    ):
        """Model aggregation surfaces per-model MetricStatistics whose ``n``
        equals the number of seeded samples and whose ``mean`` matches the
        seeded values. Two models → no single-model warning."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, tasks = await _make_project(async_test_db, admin, num_tasks=4)
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.6, 0.6, 0.6, 0.6],
        )
        await _seed_model_eval(
            async_test_db, project, admin, "claude-3-sonnet", tasks,
            per_task_values=[0.2, 0.2, 0.2, 0.2],
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model", "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["aggregation"] == "model"
        by_model = body["by_model"]
        assert set(by_model) == {"gpt-4o", "claude-3-sonnet"}
        gpt = by_model["gpt-4o"]["metrics"]["accuracy"]
        assert gpt["n"] == 4
        assert gpt["mean"] == 0.6
        assert by_model["gpt-4o"]["sample_count"] == 4
        # Two models present → the single-model warning is absent.
        warnings = body.get("warnings") or []
        assert "Only one model has data; pairwise comparisons not possible" not in warnings

    @pytest.mark.asyncio
    async def test_compare_models_missing_emits_warning(
        self, async_test_client, async_test_db
    ):
        """compare_models naming only absent models → all sample rows filter
        out → the 'No data found for specified models' warning fires."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project, tasks = await _make_project(async_test_db, admin, num_tasks=3)
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.5, 0.5, 0.5],
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "compare_models": ["nonexistent-model"],
                },
            )
        assert resp.status_code == 200, resp.text
        warnings = resp.json().get("warnings") or []
        assert any(
            "No data found for specified models" in w for w in warnings
        ), warnings

    @pytest.mark.asyncio
    async def test_field_aggregation_resolves_display_name(
        self, async_test_client, async_test_db
    ):
        """field aggregation builds by_field keyed on the raw field_name and
        resolves display_name from the project's evaluation_configs lookup via
        the discrete evaluation_config_id column. Carries the parsed cfg id and
        sample_count from the seeded rows."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        cfg_id = "cfg-field-1"
        eval_config = {
            "evaluation_configs": [
                {"id": cfg_id, "metric": "accuracy", "display_name": "Antwort-Feld"}
            ]
        }
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=3,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.7, 0.8, 0.9], config_id=cfg_id,
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "field", "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        by_field = resp.json()["by_field"]
        assert "answer" in by_field
        field = by_field["answer"]
        assert field["evaluation_config_id"] == cfg_id
        assert field["display_name"] == "Antwort-Feld"
        assert field["sample_count"] == 3
        assert field["metrics"]["accuracy"]["n"] == 3

    @pytest.mark.asyncio
    async def test_sample_aggregation_returns_raw_scores(
        self, async_test_client, async_test_db
    ):
        """sample aggregation returns one RawScore per (sample, metric) carrying
        the model_id, evaluation_config_id and value. Count equals the number
        of seeded TaskEvaluation rows."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        cfg_id = "cfg-sample"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=3,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.3, 0.6, 0.9], config_id=cfg_id,
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "sample", "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        raw = resp.json()["raw_scores"]
        assert raw is not None
        accuracy_scores = [r for r in raw if r["metric"] == "accuracy"]
        assert len(accuracy_scores) == 3
        for r in accuracy_scores:
            assert r["model_id"] == "gpt-4o"
            assert r["evaluation_config_id"] == cfg_id
        assert sorted(round(r["value"], 1) for r in accuracy_scores) == [0.3, 0.6, 0.9]

    @pytest.mark.asyncio
    async def test_multi_run_aggregate_present_for_single_run(
        self, async_test_client, async_test_db
    ):
        """The multi-run block emits one ``runs_by_model_metric`` entry keyed
        ``model|config|metric`` even for a single judge-run, with n_runs=1 and
        a mean_of_means matching the seeded per-sample mean. config_id is the
        seeded value (not the 'unknown' sentinel) since rows carry it."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        cfg_id = "cfg-multirun"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=4,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.4, 0.5, 0.6, 0.5], config_id=cfg_id,
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model", "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        runs = body.get("runs_by_model_metric")
        assert runs is not None
        key = f"gpt-4o|{cfg_id}|accuracy"
        assert key in runs, runs
        agg = runs[key]
        assert agg["n_runs"] == 1
        # mean of [0.4,0.5,0.6,0.5] = 0.5; single run → CI bounds collapse.
        assert agg["mean_of_means"] == 0.5
        assert agg["ci_lower"] is None
        assert agg["ci_upper"] is None

    @pytest.mark.asyncio
    async def test_evaluation_config_ids_filter_scopes_statistics(
        self, async_test_client, async_test_db
    ):
        """Passing evaluation_config_ids restricts the sample query to that
        config; a model evaluated only under a different config drops out of
        by_model entirely."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        eval_config = {
            "evaluation_configs": [
                {"id": "cfg-x", "metric": "accuracy"},
                {"id": "cfg-y", "metric": "accuracy"},
            ]
        }
        project, tasks = await _make_project(
            async_test_db, admin,
            evaluation_config=eval_config, num_tasks=3,
        )
        await _seed_model_eval(
            async_test_db, project, admin, "gpt-4o", tasks,
            per_task_values=[0.8, 0.8, 0.8], config_id="cfg-x",
        )
        await _seed_model_eval(
            async_test_db, project, admin, "claude-3-sonnet", tasks,
            per_task_values=[0.2, 0.2, 0.2], config_id="cfg-y",
        )

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{project.id}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "model",
                    "methods": ["ci"],
                    "evaluation_config_ids": ["cfg-x"],
                },
            )
        assert resp.status_code == 200, resp.text
        by_model = resp.json()["by_model"]
        # Only the cfg-x model survives the scope filter.
        assert "gpt-4o" in by_model
        assert "claude-3-sonnet" not in by_model
        assert by_model["gpt-4o"]["metrics"]["accuracy"]["mean"] == 0.8
