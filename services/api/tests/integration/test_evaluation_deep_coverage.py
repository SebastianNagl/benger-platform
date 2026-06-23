"""
Deep integration tests for evaluation endpoints.

Targets: routers/evaluations/results/, metadata/, config.py, status.py,
         validation.py, multi_field/, human.py

ASYNC vs SYNC lanes
-------------------
Many evaluation read handlers were converted sync→async (``get_async_db`` +
``check_project_accessible_async`` / ``auth_service.check_project_access_async``).
Those tests seed through ``async_test_db`` and drive ``async_test_client``,
overriding ``require_user`` with a real seeded user via ``_as_user`` (a
superadmin owner short-circuits access for happy paths; a non-superadmin +
patched ``*_async`` access helper gives the deterministic 403s).

The handlers that are still SYNC (``GET /`` list, ``GET /evaluation-types``
list, ``POST /human/session/start``, ``PUT .../evaluation-config``) keep the
legacy ``client``/``test_db``/``auth_headers`` lane untouched.
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
    EvaluationType,
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


# ---------------------------------------------------------------------------
# Auth override (mirrors test_eval_multifield_branches / test_eval_results_branches)
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


# ---------------------------------------------------------------------------
# Async seeding helpers (the default lane)
# ---------------------------------------------------------------------------


async def _make_owner(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"deep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Deep Eval Owner",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db):
    oid = _uid()
    org = Organization(
        id=oid, name=f"org-{oid[:6]}", display_name=f"Org {oid[:6]}",
        slug=f"org-{oid[:8]}", is_active=True,
    )
    db.add(org)
    await db.flush()
    return org


async def _make_eval_project_async(db, admin, org, *, num_tasks=3, num_models=2,
                                   with_task_evals=True, with_generations=True,
                                   with_human=False, evaluation_config=None,
                                   is_private=False, link_org=True):
    """Create a rich evaluation project via the async session."""
    project = Project(
        id=_uid(),
        title="Deep Eval Test",
        created_by=admin.id,
        is_private=is_private,
        evaluation_config=evaluation_config,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    await db.flush()

    if link_org:
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
            data={"text": f"Eval text #{i}", "answer_field": f"A{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    # Add annotations
    for t in tasks:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=admin.id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
    await db.flush()

    models = ["gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"][:num_models]
    eval_runs = []
    for model_id in models:
        er = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            evaluation_type_ids=["accuracy", "f1"],
            metrics={"accuracy": 0.85 + (0.05 if model_id == "gpt-4o" else 0),
                     "f1_score": 0.82},
            status="completed",
            samples_evaluated=num_tasks,
            eval_metadata={"evaluation_type": "evaluation"},
            created_by=admin.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(er)
        eval_runs.append(er)
    await db.flush()
    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; every
    # EvaluationRun needs a parent judge run.
    for er in eval_runs:
        jr = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        db.add(jr)
        er._test_judge_run = jr
    await db.flush()

    generations = []
    if with_generations:
        for model_id in models:
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
                    case_data=json.dumps({"text": f"case for {t.id}"}),
                    response_content=f"Answer from {model_id}",
                    status="completed",
                )
                db.add(gen)
                generations.append(gen)
        await db.flush()

    task_evals = []
    if with_task_evals and generations:
        for er in eval_runs:
            model_gens = [g for g in generations if g.model_id == er.model_id]
            for gen in model_gens:
                te = TaskEvaluation(
                    id=_uid(),
                    evaluation_id=er.id,
                    judge_run_id=er._test_judge_run.id,
                    task_id=gen.task_id,
                    generation_id=gen.id,
                    field_name="answer",
                    answer_type="choices",
                    ground_truth="Ja",
                    prediction="Ja",
                    metrics={"accuracy": 1.0, "f1": 0.9},
                    passed=True,
                )
                db.add(te)
                task_evals.append(te)
        await db.flush()

    human_sessions = []
    if with_human and generations:
        hs = HumanEvaluationSession(
            id=_uid(),
            project_id=project.id,
            evaluator_id=admin.id,
            session_type="likert",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(hs)
        await db.flush()

        # LikertScaleEvaluation requires response_id (NOT NULL)
        first_gen = generations[0] if generations else None
        if first_gen:
            for dim in ["fluency", "accuracy", "relevance"]:
                le = LikertScaleEvaluation(
                    id=_uid(), session_id=hs.id,
                    task_id=tasks[0].id, response_id=first_gen.id,
                    dimension=dim, rating=4,
                )
                db.add(le)

            pr = PreferenceRanking(
                id=_uid(), session_id=hs.id,
                task_id=tasks[0].id, winner="gpt-4o",
            )
            db.add(pr)
        human_sessions.append(hs)
        await db.flush()

    await db.commit()
    return {
        "project": project, "tasks": tasks, "eval_runs": eval_runs,
        "generations": generations, "task_evals": task_evals,
        "human_sessions": human_sessions,
    }


# ===================================================================
# RESULTS ENDPOINT — GET /results/{project_id}  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestEvalResults:
    """GET /api/evaluations/results/{project_id}"""

    @pytest.mark.asyncio
    async def test_results_with_task_evals(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org, with_task_evals=True,
        )
        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/{data['project'].id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    @pytest.mark.asyncio
    async def test_results_filter_by_model(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?model_id=gpt-4o"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_results_include_human_flag(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org, with_human=False)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?include_human=true"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_results_with_limit_offset(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{data['project'].id}?limit=2"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_results_empty_project(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org,
            with_task_evals=False, with_generations=False, num_models=0,
        )
        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/{data['project'].id}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_results_access_denied_403(self, async_test_client, async_test_db):
        from unittest.mock import patch
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org, is_private=True, link_org=False,
            with_task_evals=False, with_generations=False, num_models=0,
        )
        with _as_user(outsider), patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(f"{BASE}/results/{data['project'].id}")
        assert resp.status_code == 403, resp.text


# ===================================================================
# EXPORT — POST /export/{project_id}  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestEvalExport:
    """POST /api/evaluations/export/{project_id}"""

    @pytest.mark.asyncio
    async def test_export_json_with_data(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=json"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "project_id" in body
        assert "results" in body

    @pytest.mark.asyncio
    async def test_export_csv_with_data(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=csv"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_export_empty_project(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org,
            with_task_evals=False, with_generations=False, num_models=0,
        )
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{data['project'].id}?format=json"
            )
        assert resp.status_code == 200, resp.text


# ===================================================================
# METADATA — evaluated models, configured methods, statistics  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestEvalMetadata:
    """Evaluation metadata endpoints."""

    @pytest.mark.asyncio
    async def test_evaluated_models(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project'].id}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        # Should have 2 models
        assert len(body) >= 2

    @pytest.mark.asyncio
    async def test_evaluated_models_empty(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org,
            num_models=0, with_task_evals=False, with_generations=False,
        )
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project'].id}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_configured_methods(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project'].id}/configured-methods"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_statistics_basic(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project'].id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
            )
        assert resp.status_code in (200, 400, 422), resp.text

    @pytest.mark.asyncio
    async def test_statistics_sample_aggregation(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/projects/{data['project'].id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "sample"},
            )
        assert resp.status_code in (200, 400, 422), resp.text


# ===================================================================
# CONFIG — evaluation configuration
# ===================================================================

@pytest.mark.integration
class TestEvalConfig:
    """Evaluation configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_config_with_existing(self, async_test_client, async_test_db):
        """GET /projects/{id}/evaluation-config is ASYNC."""
        eval_config = {"metrics": ["accuracy", "f1"], "evaluation_mode": "automated"}
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(
            async_test_db, owner, org, evaluation_config=eval_config,
        )
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project'].id}/evaluation-config"
            )
        assert resp.status_code in (200, 403), resp.text

    def test_update_config_basic(self, client, test_db, test_users, auth_headers, test_org):
        """PUT /projects/{id}/evaluation-config is still SYNC."""
        # Seed a minimal project on the sync lane.
        project = Project(
            id=_uid(),
            title="Sync Config Project",
            created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        ))
        test_db.commit()
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"metrics": ["accuracy"], "evaluation_mode": "automated"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422), resp.text


# ===================================================================
# STATUS — evaluation listing and status
# ===================================================================

@pytest.mark.integration
class TestEvalStatus:
    """Evaluation status and listing endpoints."""

    def test_list_evaluations_with_data(self, client, test_db, test_users, auth_headers, test_org):
        """GET / (list) is still SYNC."""
        project = Project(
            id=_uid(),
            title="Sync List Project",
            created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        ))
        test_db.flush()
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            evaluation_type_ids=["accuracy"], status="completed",
            metrics={"accuracy": 0.9}, samples_evaluated=1,
            eval_metadata={"evaluation_type": "evaluation"},
            created_by=test_users[0].id,
        )
        test_db.add(er)
        test_db.commit()
        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text

    def test_evaluation_types(self, client, test_db, test_users, auth_headers):
        """GET /evaluation-types (LIST) is still SYNC. Self-seed a unique-id
        EvaluationType rather than the shared ``test_evaluation_types`` fixture,
        whose fixed ids (e.g. 'accuracy') collide with rows already committed to
        the long-lived test DB (UniqueViolation)."""
        et_id = f"deep-list-{uuid.uuid4().hex[:8]}"
        test_db.add(EvaluationType(
            id=et_id, name="Deep List Metric",
            description="self-seeded for the list test",
            category="classification", higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"], is_active=True,
        ))
        test_db.commit()
        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        assert et_id in {d["id"] for d in body}

    @pytest.mark.asyncio
    async def test_evaluation_status_by_id(self, async_test_client, async_test_db):
        """GET /evaluation/status/{id} is ASYNC."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        if data["eval_runs"]:
            er_id = data["eval_runs"][0].id
            with _as_user(owner):
                resp = await async_test_client.get(
                    f"{BASE}/evaluation/status/{er_id}"
                )
            assert resp.status_code in (200, 404), resp.text


# ===================================================================
# MULTI-FIELD  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestMultiField:
    """Multi-field evaluation endpoints."""

    @pytest.mark.asyncio
    async def test_available_fields(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{data['project'].id}/available-fields"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_field_results(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{data['project'].id}"
            )
        assert resp.status_code == 200, resp.text


# ===================================================================
# HUMAN EVALUATION — sessions (ASYNC), session/start (SYNC)
# ===================================================================

@pytest.mark.integration
class TestHumanEval:
    """Human evaluation endpoints."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, async_test_client, async_test_db):
        """GET /human/sessions/{project_id} is ASYNC."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org, with_human=False)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/sessions/{data['project'].id}"
            )
        assert resp.status_code in (200, 403), resp.text

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, async_test_client, async_test_db):
        """GET /human/sessions/{project_id} on a project with no sessions."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_eval_project_async(async_test_db, owner, org, with_human=False)
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/sessions/{data['project'].id}"
            )
        assert resp.status_code in (200, 403), resp.text

    def test_start_session(self, client, test_db, test_users, auth_headers, test_org):
        """POST /human/session/start is still SYNC."""
        project = Project(
            id=_uid(),
            title="Sync Human Project",
            created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        ))
        test_db.commit()
        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": project.id, "evaluation_type": "likert"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 400, 403, 422), resp.text
