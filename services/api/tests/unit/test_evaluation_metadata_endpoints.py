"""
Unit tests for routers/evaluations/metadata.py to increase branch coverage.
Covers evaluated-models, configured-methods, evaluation-history, significance,
and statistics endpoints.

The metadata handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``), so the old
``get_db``-override + ``db.query``-Mock pattern no longer reaches them. These
tests now seed real rows via the SAVEPOINT-isolated ``async_test_db``
AsyncSession and drive the surface through ``async_test_client`` (wired to
``get_async_db``). Authentication overrides ``require_user`` with an
``auth_module.models.User`` built from the seeded DB user; the access branch is
exercised either by seeding a superadmin user (``check_project_accessible_async``
short-circuits True) or by patching ``check_project_accessible_async`` on the
submodule where each handler lives.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

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
)
from models import User
from project_models import Project, Task


def _uid() -> str:
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


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"meta-ep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta EP User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, evaluation_config=None, generation_config=None):
    proj = Project(
        id=_uid(),
        title=f"Meta EP {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(proj)
    await db.commit()
    return proj


# ---------------------------------------------------------------------------
# Evaluated Models
# ---------------------------------------------------------------------------


class TestEvaluatedModels:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluated-models"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user, generation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluated-models"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_models_returns_empty(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, generation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluated-models"
            )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Configured Methods
# ---------------------------------------------------------------------------


class TestConfiguredMethods:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/configured-methods"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_eval_config(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 200
        assert resp.json()["fields"] == []

    @pytest.mark.asyncio
    async def test_with_selected_methods(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db,
            user,
            evaluation_config={
                "selected_methods": {
                    "answer": {
                        "automated": [
                            "rouge_l",
                            {"name": "llm_judge_custom", "parameters": {"criteria": "accuracy"}},
                        ],
                        "human": ["likert_scale"],
                        "field_mapping": {"prediction_field": "answer", "reference_field": "answer"},
                    }
                },
                "available_methods": {
                    "answer": {"type": "text", "to_name": "answer"}
                },
            },
        )
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fields"]) == 1
        assert data["fields"][0]["field_name"] == "answer"

    @pytest.mark.asyncio
    async def test_empty_selected_methods(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db, user, evaluation_config={"selected_methods": {}}
        )
        with _as_user(user), patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/configured-methods"
            )
        assert resp.status_code == 200
        assert resp.json()["fields"] == []


# ---------------------------------------------------------------------------
# Evaluation History
# ---------------------------------------------------------------------------


class TestEvaluationHistory:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/evaluation-history",
                params={"model_ids": "m1", "metrics": "accuracy"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={"model_ids": "m1", "metrics": "accuracy"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_with_empty_results_returns_empty_series(
        self, async_test_client, async_test_db
    ):
        """Issue #111: /evaluation-history now returns ``{series: [...]}``.

        A real project with no seeded TaskEvaluation rows returns an empty
        series. Real per-row aggregation is covered by
        ``TestEvaluationHistoryPerConfig`` below.
        """
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={"model_ids": "gpt-4", "metrics": "accuracy"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "series" in data
        assert data["series"] == []

    @pytest.mark.asyncio
    async def test_with_date_filters(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={
                    "model_ids": "gpt-4",
                    "metrics": "accuracy",
                    "start_date": "2025-01-01T00:00:00",
                    "end_date": "2025-12-31T23:59:59",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"series": []}

    @pytest.mark.asyncio
    async def test_with_evaluation_config_ids_filter(
        self, async_test_client, async_test_db
    ):
        """Issue #111: ``evaluation_config_ids`` is accepted as a Query param."""
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        with _as_user(user), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{proj.id}/evaluation-history",
                params={
                    "model_ids": "gpt-4",
                    "metrics": "accuracy",
                    "evaluation_config_ids": ["cfgA", "cfgB"],
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"series": []}


# ---------------------------------------------------------------------------
# Significance Tests
# ---------------------------------------------------------------------------


class TestSignificanceTests:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/significance/nonexistent",
                params={"model_ids": ["m1", "m2"], "metrics": "accuracy"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_scipy_not_available(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            return_value=True,
        ), patch("routers.leaderboards.STATS_AVAILABLE", False):
            resp = await async_test_client.get(
                f"/api/evaluations/significance/{proj.id}",
                params={"model_ids": ["m1", "m2"], "metrics": "accuracy"},
            )
        assert resp.status_code == 200
        assert "not available" in resp.json().get("message", "")

    @pytest.mark.asyncio
    async def test_insufficient_data(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        # Seed one sample per model → each model has <2 scores → handler emits
        # the default (non-significant) comparison.
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"m1": [0.85], "m2": [0.70]},
            metric="accuracy",
            eval_metrics={},
        )
        with _as_user(user), patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            return_value=True,
        ), patch("routers.leaderboards.STATS_AVAILABLE", True):
            resp = await async_test_client.get(
                f"/api/evaluations/significance/{proj.id}",
                params={"model_ids": ["m1", "m2"], "metrics": "accuracy"},
            )
        assert resp.status_code == 200
        comps = resp.json()["comparisons"]
        assert len(comps) == 1
        assert comps[0]["significant"] == False  # noqa: E712


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/evaluations/projects/nonexistent/statistics",
                json={"metrics": ["accuracy"]},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_evaluations(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{proj.id}/statistics",
                json={"metrics": ["accuracy"]},
            )
        assert resp.status_code == 404
        assert "No completed evaluations" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        with _as_user(user), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{proj.id}/statistics",
                json={"metrics": ["accuracy"]},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Shared eval-graph seeding helper (single-config)
# ---------------------------------------------------------------------------


async def _seed_eval_graph(
    db,
    owner,
    project,
    *,
    model_scores,
    metric="bleu",
    field_name="answer",
    eval_metrics=None,
):
    """Seed a full evaluation data graph for ``project``.

    ``model_scores`` maps ``model_id -> [score, score, ...]``. For each model
    we create a ResponseGeneration + one Generation/TaskEvaluation per score,
    all hanging off a shared EvaluationRun + EvaluationJudgeRun.
    """
    now = datetime.now(timezone.utc)
    for model_id, scores in model_scores.items():
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            status="completed",
            created_by=owner.id,
            started_at=now,
            completed_at=now,
        )
        db.add(rg)
        await db.flush()

        er = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            evaluation_type_ids=[metric],
            metrics=(eval_metrics if eval_metrics is not None else {metric: 0.7}),
            status="completed",
            samples_evaluated=len(scores),
            has_sample_results=True,
            created_by=owner.id,
            created_at=now,
            completed_at=now,
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

        for i, score in enumerate(scores):
            task = Task(
                id=_uid(),
                project_id=project.id,
                data={"text": f"Task {model_id}-{i}"},
                inner_id=i + 1,
                created_by=owner.id,
            )
            db.add(task)
            await db.flush()

            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=task.id,
                model_id=model_id,
                run_index=i,
                case_data=json.dumps(task.data),
                response_content=f"r-{i}",
                label_config_version="v1",
                status="completed",
                parse_status="success",
            )
            db.add(gen)
            await db.flush()

            te = TaskEvaluation(
                id=_uid(),
                evaluation_id=er.id,
                judge_run_id=jr.id,
                task_id=task.id,
                generation_id=gen.id,
                field_name=field_name,
                evaluation_config_id=None,
                answer_type="text",
                ground_truth={"value": "ref"},
                prediction={"value": f"hyp-{i}"},
                metrics={metric: score},
                passed=True,
                created_at=now,
            )
            db.add(te)
    await db.commit()


# ---------------------------------------------------------------------------
# Issue #111 — per-config integration tests (real DB)
# ---------------------------------------------------------------------------

# These tests seed real ``TaskEvaluation`` rows with distinct
# ``evaluation_config_id`` values so the new ``/statistics``,
# ``/significance``, and ``/evaluation-history`` per-config plumbing is
# exercised end-to-end. They seed a superadmin user (so
# ``check_project_accessible_async`` short-circuits True, also patched
# explicitly) and drive the async surface through ``async_test_client``.


async def _seed_two_config_project(db, admin):
    """Build a project with two evaluation_configs sharing ``metric=bleu``.

    Seeds two ``EvaluationRun`` + ``EvaluationJudgeRun`` + per-task
    ``TaskEvaluation`` rows per model (cfgA + cfgB), so the per-config
    filter has data on both sides. Returns the project, both config ids,
    and the seeded model ids.
    """
    import uuid as _uuid
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    cfg_a_id = f"cfgA-{_uuid.uuid4().hex[:6]}"
    cfg_b_id = f"cfgB-{_uuid.uuid4().hex[:6]}"
    project = Project(
        id=str(_uuid.uuid4()),
        title=f"Issue111 {_uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config={
            "evaluation_configs": [
                {"id": cfg_a_id, "metric": "bleu", "display_name": "BLEU strict"},
                {"id": cfg_b_id, "metric": "bleu", "display_name": "BLEU relaxed"},
            ],
        },
        generation_config={
            "selected_configuration": {"models": ["gpt-4o", "claude-3-sonnet"]},
        },
    )
    db.add(project)
    await db.flush()
    project_id = project.id

    tasks = []
    for i in range(4):
        t = Task(
            id=str(_uuid.uuid4()), project_id=project_id,
            data={"text": f"Task {i}"}, inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    models = ["gpt-4o", "claude-3-sonnet"]
    for model_id in models:
        rg = ResponseGeneration(
            id=str(_uuid.uuid4()), project_id=project_id,
            model_id=model_id, status="completed", created_by=admin.id,
            started_at=_dt.now(_tz.utc), completed_at=_dt.now(_tz.utc),
        )
        db.add(rg)
        await db.flush()
        gens = []
        for i, t in enumerate(tasks):
            g = Generation(
                id=str(_uuid.uuid4()), generation_id=rg.id, task_id=t.id,
                model_id=model_id, run_index=i,
                case_data=_json.dumps(t.data), response_content=f"r-{i}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            db.add(g)
            gens.append(g)
        await db.flush()

        # One EvaluationRun + JudgeRun pair per model — both configs land
        # under the same run so the multi-run aggregator has to bucket on
        # ``evaluation_config_id`` itself rather than relying on run_id.
        er = EvaluationRun(
            id=str(_uuid.uuid4()), project_id=project_id, model_id=model_id,
            evaluation_type_ids=["bleu"],
            metrics={"bleu": 0.7},
            status="completed", samples_evaluated=len(tasks) * 2,
            has_sample_results=True, created_by=admin.id,
            created_at=_dt.now(_tz.utc), completed_at=_dt.now(_tz.utc),
        )
        db.add(er)
        await db.flush()
        jr = EvaluationJudgeRun(
            id=str(_uuid.uuid4()), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        db.add(jr)
        await db.flush()
        # Two TaskEvaluation rows per task — one per config — so the
        # per-config filter excludes exactly half the data on each side.
        # cfgA scores deliberately higher than cfgB so model-level means
        # split cleanly when filtered.
        for cfg_id, base in ((cfg_a_id, 0.8), (cfg_b_id, 0.4)):
            for i, t in enumerate(tasks):
                te = TaskEvaluation(
                    id=str(_uuid.uuid4()), evaluation_id=er.id,
                    judge_run_id=jr.id, task_id=t.id,
                    generation_id=gens[i].id,
                    field_name=f"{cfg_id}|answer|answer",
                    evaluation_config_id=cfg_id,
                    answer_type="text",
                    ground_truth={"value": "ref"},
                    prediction={"value": f"hyp-{i}"},
                    metrics={"bleu": round(base + i * 0.01, 4)},
                    passed=True,
                )
                db.add(te)
    await db.commit()
    return {
        "project": project,
        "project_id": project_id,
        "cfg_a_id": cfg_a_id,
        "cfg_b_id": cfg_b_id,
        "model_ids": models,
    }


class TestComputeStatisticsPerConfig:
    """Issue #111: per-config plumbing in POST /statistics."""

    @pytest.mark.asyncio
    async def test_raw_scores_carry_evaluation_config_id(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        with _as_user(admin), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{data['project_id']}/statistics",
                json={"metrics": ["bleu"], "aggregation": "sample"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        raw = body.get("raw_scores") or []
        # We seeded 2 models × 4 tasks × 2 configs = 16 rows.
        assert len(raw) == 16
        cfg_ids = {r.get("evaluation_config_id") for r in raw}
        assert cfg_ids == {data["cfg_a_id"], data["cfg_b_id"]}

    @pytest.mark.asyncio
    async def test_evaluation_config_ids_filter_excludes_other(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        with _as_user(admin), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{data['project_id']}/statistics",
                json={
                    "metrics": ["bleu"],
                    "aggregation": "sample",
                    "evaluation_config_ids": [data["cfg_a_id"]],
                },
            )
        assert resp.status_code == 200, resp.text
        raw = resp.json().get("raw_scores") or []
        assert len(raw) == 8  # 2 models × 4 tasks × 1 config
        assert {r["evaluation_config_id"] for r in raw} == {data["cfg_a_id"]}

    @pytest.mark.asyncio
    async def test_by_field_carries_structured_fields(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        with _as_user(admin), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{data['project_id']}/statistics",
                json={"metrics": ["bleu"], "aggregation": "field"},
            )
        assert resp.status_code == 200, resp.text
        by_field = resp.json().get("by_field") or {}
        # Outer key remains the raw field_name. Two distinct field_names
        # for two configs.
        assert len(by_field) == 2
        for field_name, fs in by_field.items():
            assert fs["evaluation_config_id"] in (data["cfg_a_id"], data["cfg_b_id"])
            assert fs["prediction_field"] == "answer"
            assert fs["reference_field"] == "answer"
            assert fs["display_name"] in ("BLEU strict", "BLEU relaxed")

    @pytest.mark.asyncio
    async def test_runs_by_model_metric_keyed_with_config_id(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        with _as_user(admin), patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.post(
                f"/api/evaluations/projects/{data['project_id']}/statistics",
                json={"metrics": ["bleu"], "aggregation": "model"},
            )
        assert resp.status_code == 200, resp.text
        runs = resp.json().get("runs_by_model_metric") or {}
        # Re-keyed to "model|config|metric" — two distinct buckets per
        # model so the same metric type with different configs surfaces
        # separately for RQ5 / inter-judge analysis.
        expected = {
            f"{m}|{cfg}|bleu"
            for m in data["model_ids"]
            for cfg in (data["cfg_a_id"], data["cfg_b_id"])
        }
        assert expected.issubset(set(runs.keys()))


class TestSignificanceTestsPerConfig:
    """Issue #111: ``evaluation_config_ids`` Query param on /significance."""

    @pytest.mark.asyncio
    async def test_evaluation_config_filter_excludes_other(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        # cfgA score base 0.8, cfgB score base 0.4 — so filtering to cfgB
        # should compare the two models on the lower-band scores only.
        with _as_user(admin), patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/significance/{data['project_id']}",
                params={
                    "model_ids": [data["model_ids"][0], data["model_ids"][1]],
                    "metrics": "bleu",
                    "evaluation_config_ids": data["cfg_b_id"],
                },
            )
        assert resp.status_code == 200, resp.text
        comps = resp.json().get("comparisons") or []
        # The two models share the same scores per cfg in this seed
        # (deterministic, model-agnostic). Just assert we got the one
        # pair × one metric row back, scoped by cfgB. Detailed numeric
        # assertions live in the existing significance tests.
        assert len(comps) == 1
        assert comps[0]["metric"] == "bleu"


class TestEvaluationHistoryPerConfig:
    """Issue #111: ``/evaluation-history`` returns one series per
    (metric, evaluation_config_id) pair."""

    @pytest.mark.asyncio
    async def test_series_split_per_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        data = await _seed_two_config_project(async_test_db, admin)
        with _as_user(admin), patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{data['project_id']}/evaluation-history",
                params={
                    "model_ids": [data["model_ids"][0], data["model_ids"][1]],
                    "metrics": "bleu",
                },
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        series = body.get("series") or []
        # One series per (metric, evaluation_config_id) — bleu × {cfgA, cfgB}.
        assert len(series) == 2
        cfg_ids = {s["evaluation_config_id"] for s in series}
        assert cfg_ids == {data["cfg_a_id"], data["cfg_b_id"]}
        display_names = {s["display_name"] for s in series}
        assert display_names == {"BLEU strict", "BLEU relaxed"}
        for s in series:
            assert s["metric"] == "bleu"
            assert isinstance(s["data"], list)
            for point in s["data"]:
                assert "date" in point
                assert "model_id" in point
                assert "value" in point
                assert "sample_count" in point
