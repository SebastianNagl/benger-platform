"""Complement behavioral tests for the evaluation metadata router.

Target: ``services/api/routers/evaluations/metadata/*`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``). All handlers were
migrated to the ASYNC DB lane (``db: AsyncSession = Depends(get_async_db)`` +
``await db.execute(select(...))``), so this file drives them through the
``async_test_client`` + ``async_test_db`` fixtures. A real superadmin
``models.User`` is seeded per test and bound via ``_as_user`` (overrides
``require_user``); superadmin means ``check_project_accessible_async`` returns
True natively, so no access patch is needed.

This file is the COMPLEMENT of the happy-path metadata coverage tests. It fills
the still-uncovered arms:

  GET  /projects/{id}/evaluated-models ... the 404 missing-project guard; the
                                           include_configured config-only model
                                           with NO results (average_score None,
                                           has_results False).
  GET  /projects/{id}/configured-methods . the 404 missing-project guard.
  GET  /significance/{id} ................ the evaluation_config_ids scope filter
                                           branch (direct-evaluations fallback is
                                           skipped when set).
  POST /projects/{id}/statistics ......... the evaluation_config_ids scope filter
                                           (per-config sample subset, fallback
                                           skipped); the FIELD aggregation with
                                           an encoded "cfg|pred|ref" field_name
                                           parsed into structured fields +
                                           display_name; the multi-run aggregate
                                           block (>=2 judge runs → variance +
                                           per_run_means; >=2 distinct
                                           judge_model_ids → inter-judge
                                           agreement); the correlation
                                           insufficient-data warning; the
                                           bootstrap permutation method; the
                                           annotation-based result merge.
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
from project_models import Annotation, Project, Task

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
        name="Meta Coverage User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _project(db, admin, *, evaluation_config=None, generation_config=None):
    p = Project(
        id=_uid(),
        title=f"MetaC {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(p)
    await db.flush()
    return p


async def _task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": f"t{inner_id}"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    await db.flush()
    return t


async def _eval_run(db, project, admin_id, *, model_id="gpt-4o", metrics=None,
                    eval_types=None):
    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=eval_types or ["accuracy"],
        metrics=metrics or {}, status="completed", samples_evaluated=0,
        has_sample_results=True, created_by=admin_id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    return er


async def _judge_run(db, er, *, judge_model_id=None, run_index=0):
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=judge_model_id,
        run_index=run_index, status="completed",
    )
    db.add(jr)
    await db.flush()
    return jr


async def _generation(db, project, task, admin_id, *, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by=admin_id,
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data=json.dumps(task.data), response_content="r",
        status="completed", parse_status="success",
    )
    db.add(gen)
    await db.flush()
    return gen


async def _task_eval(db, er, jr, task, *, generation=None, annotation=None,
                     field_name="answer", metrics=None, cfg_id=None):
    te = TaskEvaluation(
        id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name, evaluation_config_id=cfg_id,
        answer_type="choices", ground_truth={"value": "Ja"},
        prediction={"value": "Ja"},
        metrics=metrics if metrics is not None else {"accuracy": 0.9},
        passed=True,
    )
    db.add(te)
    await db.flush()
    return te


# ===================================================================
# GET /projects/{id}/evaluated-models — 404 + config-only no-result model
# ===================================================================


@pytest.mark.integration
class TestEvaluatedModelsComplement:
    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/missing-{uuid.uuid4().hex}/evaluated-models",
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_include_configured_surfaces_unevaluated_model_with_null_score(
        self, async_test_client, async_test_db
    ):
        """include_configured=true surfaces a model listed in
        generation_config.selected_configuration.models that has NO generations
        and NO evaluations: average_score None, has_results False,
        is_configured True."""
        admin = await _seed_user(async_test_db)
        p = await _project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["config-only-model"]}
            },
        )
        p_id = p.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p_id}/evaluated-models?include_configured=true",
            )
        assert resp.status_code == 200, resp.text
        models = {m["model_id"]: m for m in resp.json()}
        assert "config-only-model" in models
        co = models["config-only-model"]
        assert co["is_configured"] is True
        assert co["has_generations"] is False
        assert co["has_results"] is False
        assert co["average_score"] is None


# ===================================================================
# GET /projects/{id}/configured-methods — 404
# ===================================================================


@pytest.mark.integration
class TestConfiguredMethodsComplement:
    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/projects/missing-{uuid.uuid4().hex}/configured-methods",
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]


# ===================================================================
# GET /significance/{id} — evaluation_config_ids scope branch
# ===================================================================


@pytest.mark.integration
class TestSignificanceConfigScope:
    @pytest.mark.asyncio
    async def test_config_scoped_significance_skips_direct_fallback(
        self, async_test_client, async_test_db
    ):
        """With evaluation_config_ids set, only TaskEvaluation rows tagged with
        that config are scored, and the run-level direct-evaluations fallback is
        skipped (run metrics can't be re-scoped per config). The matching config
        has >=2 samples per model so a real comparison is produced."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        # Direct run-level metrics that WOULD be picked up by the fallback —
        # must be ignored when the config filter is set.
        er = await _eval_run(
            async_test_db, p, admin.id, model_id="gpt-4o",
            metrics={"accuracy": 0.99},
        )
        jr = await _judge_run(async_test_db, er)
        # Two tasks per model, tagged with cfg-A; a second model too.
        _inner = 0
        for model_id, vals in (("gpt-4o", [0.8, 0.82]), ("claude-3", [0.6, 0.62])):
            for v in vals:
                _inner += 1
                t = await _task(async_test_db, p, admin.id, inner_id=_inner)
                gen = await _generation(async_test_db, p, t, admin.id, model_id=model_id)
                await _task_eval(async_test_db, er, jr, t, generation=gen,
                                 metrics={"accuracy": v}, cfg_id="cfg-A")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE}/significance/{p_id}"
                "?model_ids=gpt-4o&model_ids=claude-3&metrics=accuracy"
                "&evaluation_config_ids=cfg-A",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["comparisons"]) == 1
        comp = body["comparisons"][0]
        assert comp["metric"] == "accuracy"
        # A real comparison (not the insufficient-data 1.0/False stub) — both
        # models had 2 samples in cfg-A.
        assert {comp["model_a"], comp["model_b"]} == {"gpt-4o", "claude-3"}


# ===================================================================
# POST /projects/{id}/statistics — uncovered arms
# ===================================================================


@pytest.mark.integration
class TestStatisticsComplement:
    @pytest.mark.asyncio
    async def test_config_scoped_statistics_subsets_samples(
        self, async_test_client, async_test_db
    ):
        """evaluation_config_ids restricts sample-level rows to the matching
        config. Rows tagged cfg-B are excluded when only cfg-A is requested."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr = await _judge_run(async_test_db, er)
        # cfg-A rows (accuracy ~0.9), cfg-B rows (accuracy ~0.1).
        for i in range(4):
            t = await _task(async_test_db, p, admin.id, inner_id=i + 1)
            gen = await _generation(async_test_db, p, t, admin.id)
            await _task_eval(async_test_db, er, jr, t, generation=gen,
                             metrics={"accuracy": 0.9}, cfg_id="cfg-A")
        for i in range(4):
            t = await _task(async_test_db, p, admin.id, inner_id=100 + i)
            gen = await _generation(async_test_db, p, t, admin.id)
            await _task_eval(async_test_db, er, jr, t, generation=gen,
                             metrics={"accuracy": 0.1}, cfg_id="cfg-B")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={
                    "metrics": ["accuracy"],
                    "aggregation": "overall",
                    "methods": ["ci"],
                    "evaluation_config_ids": ["cfg-A"],
                },
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        stats = body["metrics"]["accuracy"]
        # Only the 4 cfg-A rows (all 0.9) counted → mean ~0.9, n == 4.
        assert stats["n"] == 4
        assert stats["mean"] == pytest.approx(0.9, abs=1e-6)

    @pytest.mark.asyncio
    async def test_field_aggregation_parses_encoded_field_name(
        self, async_test_client, async_test_db
    ):
        """Field aggregation parses the worker's encoded
        ``"{cfg_id}|{pred}|{ref}"`` field_name into discrete prediction/
        reference fields and resolves display_name from the project's
        evaluation_configs."""
        encoded = "cfg-xyz|__response__|musterloesung"
        admin = await _seed_user(async_test_db)
        p = await _project(
            async_test_db, admin,
            evaluation_config={
                "evaluation_configs": [
                    {"id": "cfg-xyz", "display_name": "BLEU vs Musterlösung"}
                ]
            },
        )
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr = await _judge_run(async_test_db, er)
        for i in range(3):
            t = await _task(async_test_db, p, admin.id, inner_id=i + 1)
            gen = await _generation(async_test_db, p, t, admin.id)
            await _task_eval(async_test_db, er, jr, t, generation=gen,
                             field_name=encoded, metrics={"bleu": 0.5 + i * 0.1},
                             cfg_id="cfg-xyz")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["bleu"], "aggregation": "field", "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert encoded in body["by_field"]
        fs = body["by_field"][encoded]
        assert fs["evaluation_config_id"] == "cfg-xyz"
        assert fs["prediction_field"] == "__response__"
        assert fs["reference_field"] == "musterloesung"
        assert fs["display_name"] == "BLEU vs Musterlösung"
        assert "bleu" in fs["metrics"]

    @pytest.mark.asyncio
    async def test_multirun_variance_and_per_run_means(
        self, async_test_client, async_test_db
    ):
        """Two judge runs over the same task/model produce a runs_by_model_metric
        entry (n_runs=2, std_of_means) and a per_run_means_by_model_metric entry
        with one PerRunMean per run."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr1 = await _judge_run(async_test_db, er, judge_model_id="judge-x", run_index=0)
        jr2 = await _judge_run(async_test_db, er, judge_model_id="judge-x", run_index=1)
        # Same task graded across two runs with different scores → cross-run
        # variance is defined.
        t = await _task(async_test_db, p, admin.id, inner_id=1)
        gen = await _generation(async_test_db, p, t, admin.id)
        await _task_eval(async_test_db, er, jr1, t, generation=gen,
                         metrics={"llm_judge_grade": 10.0}, cfg_id="cfg-run")
        await _task_eval(async_test_db, er, jr2, t, generation=gen,
                         metrics={"llm_judge_grade": 14.0}, cfg_id="cfg-run")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["llm_judge_grade"], "aggregation": "model",
                      "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        runs = body.get("runs_by_model_metric") or {}
        key = "gpt-4o|cfg-run|llm_judge_grade"
        assert key in runs, runs
        assert runs[key]["n_runs"] == 2
        per_run = body.get("per_run_means_by_model_metric") or {}
        assert key in per_run
        assert len(per_run[key]) == 2
        run_indices = sorted(e["run_index"] for e in per_run[key])
        assert run_indices == [0, 1]

    @pytest.mark.asyncio
    async def test_multirun_inter_judge_agreement(
        self, async_test_client, async_test_db
    ):
        """Two distinct judge_model_ids grading the same items produce a
        judge_agreement_by_model_metric entry with n_judges=2."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr_a = await _judge_run(async_test_db, er, judge_model_id="judge-a", run_index=0)
        jr_b = await _judge_run(async_test_db, er, judge_model_id="judge-b", run_index=0)
        # Two tasks, each scored by both judges.
        for i in range(2):
            t = await _task(async_test_db, p, admin.id, inner_id=i + 1)
            gen = await _generation(async_test_db, p, t, admin.id)
            await _task_eval(async_test_db, er, jr_a, t, generation=gen,
                             metrics={"llm_judge_grade": 8.0 + i}, cfg_id="cfg-ag")
            await _task_eval(async_test_db, er, jr_b, t, generation=gen,
                             metrics={"llm_judge_grade": 9.0 + i}, cfg_id="cfg-ag")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["llm_judge_grade"], "aggregation": "model",
                      "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        agreement = body.get("judge_agreement_by_model_metric") or {}
        key = "gpt-4o|cfg-ag|llm_judge_grade"
        assert key in agreement, agreement
        assert agreement[key]["n_judges"] == 2
        assert agreement[key]["n_items"] >= 1

    @pytest.mark.asyncio
    async def test_correlation_insufficient_data_warning(
        self, async_test_client, async_test_db
    ):
        """With only 2 samples for the requested metrics (<3 needed), the
        correlation method emits the insufficient-data warning rather than a
        matrix."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr = await _judge_run(async_test_db, er)
        for i in range(2):
            t = await _task(async_test_db, p, admin.id, inner_id=i + 1)
            gen = await _generation(async_test_db, p, t, admin.id)
            await _task_eval(async_test_db, er, jr, t, generation=gen,
                             metrics={"accuracy": 0.8, "f1": 0.7})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["accuracy", "f1"], "aggregation": "overall",
                      "methods": ["correlation"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("correlations") is None
        warnings = body.get("warnings") or []
        assert any("correlation" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_bootstrap_permutation_method(
        self, async_test_client, async_test_db
    ):
        """The bootstrap method runs the permutation test and populates
        bootstrap_p / bootstrap_significant on each pairwise comparison."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id)
        jr = await _judge_run(async_test_db, er)
        # Two clearly-separated models with several samples each.
        _inner = 0
        for model_id, base in (("gpt-4o", 0.9), ("claude-3", 0.2)):
            for i in range(5):
                _inner += 1
                t = await _task(async_test_db, p, admin.id, inner_id=_inner)
                gen = await _generation(async_test_db, p, t, admin.id, model_id=model_id)
                await _task_eval(async_test_db, er, jr, t, generation=gen,
                                 metrics={"accuracy": base + i * 0.01})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model",
                      "methods": ["bootstrap"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        comps = body.get("pairwise_comparisons") or []
        assert len(comps) >= 1
        comp = comps[0]
        assert comp["bootstrap_p"] is not None
        assert comp["bootstrap_significant"] is not None

    @pytest.mark.asyncio
    async def test_annotation_based_results_merge_into_statistics(
        self, async_test_client, async_test_db
    ):
        """Annotation-side TaskEvaluations (generation_id NULL, annotation_id
        set) merge into the per-model stats under an ``annotator:<name>`` model
        id."""
        admin = await _seed_user(async_test_db)
        p = await _project(async_test_db, admin)
        p_id = p.id
        er = await _eval_run(async_test_db, p, admin.id, model_id="human")
        jr = await _judge_run(async_test_db, er)
        for i in range(3):
            t = await _task(async_test_db, p, admin.id, inner_id=i + 1)
            ann = Annotation(
                id=_uid(), task_id=t.id, project_id=p.id,
                completed_by=admin.id,
                result=[{"from_name": "answer", "to_name": "text",
                         "type": "choices", "value": {"choices": ["Ja"]}}],
                was_cancelled=False,
            )
            async_test_db.add(ann)
            await async_test_db.flush()
            await _task_eval(async_test_db, er, jr, t, annotation=ann,
                             metrics={"accuracy": 1.0})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p_id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model",
                      "methods": ["ci"]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_model = body.get("by_model") or {}
        annotator_keys = [k for k in by_model if k.startswith("annotator:")]
        assert annotator_keys, by_model
