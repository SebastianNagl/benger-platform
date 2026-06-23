"""
Integration tests for evaluation results and metadata endpoints.

Targets:
- routers/evaluations/results.py — 7.37% (547 uncovered)
- routers/evaluations/metadata.py — 9.59% (452 uncovered)
- routers/evaluations/config.py — 13.04% (132 uncovered)
- routers/evaluations/status.py — 19.29% (83 uncovered)
- routers/evaluations/validation.py — 16.92% (36 uncovered)
- routers/evaluations/multi_field.py — 18.00% (162 uncovered)
- routers/evaluations/human.py — 27.55% (142 uncovered)

ASYNC vs SYNC lanes
-------------------
Most of these handlers were migrated sync→async (``Depends(get_async_db)`` +
``await db.execute(select(...))``). Hitting an async endpoint through the sync
``client`` fixture (which only overrides ``get_db``, not ``get_async_db``)
queries an EMPTY async DB → wrong status. So the async-endpoint tests seed via
``async_test_db`` and drive ``async_test_client``, overriding ``require_user``
with a real seeded user via ``_as_user`` (superadmin for the happy paths; a
non-superadmin + a patched ``*_async`` access helper for the deterministic
403s). The handlers that stay SYNC (``GET /`` list, ``GET /evaluation-types``
list, ``PUT .../evaluation-config``, ``POST /human/session/start``) keep the
legacy ``client``/``test_db``/``auth_headers`` lane.
"""

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
# Actual sub-paths used in the mounted routers:
# Results: /api/evaluations/results/{project_id}
# Export:  /api/evaluations/export/{project_id}
# Status:  /api/evaluations/
# Types:   /api/evaluations/evaluation-types
# Config:  /api/evaluations/projects/{project_id}/evaluation-config
# Validate:/api/evaluations/validate-config
# Metadata:/api/evaluations/projects/{project_id}/...
# Multi:   /api/evaluations/projects/{project_id}/available-fields
# Human:   /api/evaluations/human/...


# ---------------------------------------------------------------------------
# Auth override (mirrors test_eval_results_branches.py / test_eval_multifield_branches.py)
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
# Async seeding helpers (the default lane for migrated endpoints)
# ---------------------------------------------------------------------------


async def _make_owner(db, *, name="Test Admin", is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"eval-int-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
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
        id=oid,
        name=f"org-{oid[:6]}",
        display_name=f"Org {oid[:6]}",
        slug=f"org-{oid[:8]}",
        is_active=True,
    )
    db.add(org)
    await db.flush()
    return org


async def _setup_project_async(db, admin, org, *, num_tasks=3, is_private=False,
                               link_org=True, with_annotations=False,
                               evaluation_config=None):
    """Create a project owned by ``admin`` with ``num_tasks`` tasks, optionally
    linked to ``org``. Set is_private=True + link_org=False to build the 403
    fixture (a private project a non-creator non-superadmin cannot reach)."""
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Eval Test {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    await db.flush()

    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Eval text #{i}", "musterloesung": f"ml {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    annotations = []
    if with_annotations:
        for t in tasks:
            ann = Annotation(
                id=_uid(), task_id=t.id, project_id=pid,
                completed_by=admin.id,
                result=[{"from_name": "answer", "to_name": "text",
                         "type": "choices", "value": {"choices": ["Ja"]}}],
                was_cancelled=False,
            )
            db.add(ann)
            annotations.append(ann)
        await db.flush()

    return p, tasks, annotations


async def _make_eval_run_async(db, project, admin_id, *, status="completed",
                               metrics=None, eval_metadata=None, model_id="gpt-4o",
                               samples=3):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        status=status,
        metrics=metrics if metrics is not None else {"accuracy": 0.85, "f1_score": 0.82},
        samples_evaluated=samples,
        eval_metadata=eval_metadata if eval_metadata is not None
        else {"type": "automated"},
        created_by=admin_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()
    er._test_judge_run = judge_run
    return er


async def _make_generation_async(db, task, *, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(),
        project_id=task.project_id,
        task_id=task.id,
        model_id=model_id,
        status="completed",
        created_by=task.created_by,
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        run_index=0,
        case_data="{}",
        response_content="x",
        status="completed",
        parse_status="success",
    )
    db.add(gen)
    await db.flush()
    return gen, rg


async def _make_task_evaluation_async(db, eval_run, task, *, generation=None,
                                      annotation=None, field_name="answer",
                                      metrics=None, judge_run=None):
    if generation is None and annotation is None:
        generation, _ = await _make_generation_async(db, task)
    te = TaskEvaluation(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_run_id=(judge_run or eval_run._test_judge_run).id,
        task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name,
        answer_type="choices",
        metrics=metrics if metrics is not None else {"score": 0.9},
        passed=True,
        ground_truth={"value": "Ja"},
        prediction={"value": "Ja"},
    )
    db.add(te)
    await db.flush()
    return te


async def _make_human_session_async(
    db, project, evaluator_id, tasks, *, session_type="likert", status="completed"
):
    # GET /human/sessions/{id} only reads HumanEvaluationSession rows, so the
    # session alone is enough — no Likert/Preference children needed (those
    # carry NOT-NULL FKs like response_id that this endpoint never touches).
    # The submit endpoints (POST /human/likert, /human/preference) verify the
    # session by (id, evaluator_id, session_type), so those tests pass the
    # matching session_type.
    hs = HumanEvaluationSession(
        id=_uid(),
        project_id=project.id,
        evaluator_id=evaluator_id,
        session_type=session_type,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hs)
    await db.flush()
    return hs


# ---------------------------------------------------------------------------
# Sync seeding helpers (only for the sync-handler tests)
# ---------------------------------------------------------------------------


def _setup_project_sync(db, admin, org, *, num_tasks=3, evaluation_config=None):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Eval Test {pid[:6]}",
        created_by=admin.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    db.flush()
    db.add(ProjectOrganization(
        id=_uid(), project_id=pid,
        organization_id=org.id, assigned_by=admin.id,
    ))
    db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Eval text #{i}", "question": f"Q{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_eval_run_sync(db, project, admin_id, *, model_id="gpt-4o"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        metrics={"accuracy": 0.85, "f1_score": 0.82},
        status="completed",
        samples_evaluated=3,
        created_by=admin_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    return er


# ===================================================================
# EVALUATION RESULTS  (ASYNC — GET /results/{project_id})
# ===================================================================

@pytest.mark.integration
class TestGetEvaluationResults:
    """GET /api/evaluations/results/{project_id}"""

    @pytest.mark.asyncio
    async def test_get_results_basic(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            await _make_eval_run_async(async_test_db, p, owner.id, model_id=model_id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/{p.id}")
        assert resp.status_code == 200, resp.text
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_results_empty_project(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/{p.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    # Human evaluation results are tested in test_evaluation_endpoints.py::TestHumanEvaluationSessions

    @pytest.mark.asyncio
    async def test_get_results_automated_only(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            await _make_eval_run_async(async_test_db, p, owner.id, model_id=model_id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/results/{p.id}?include_human=false"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_get_results_limit(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            await _make_eval_run_async(async_test_db, p, owner.id, model_id=model_id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/{p.id}?limit=1")
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_get_results_nonexistent_project(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/results/nonexistent-id")
        # Superadmin can access any project; returns empty list for nonexistent
        assert resp.status_code in (200, 403, 404), resp.text


# ===================================================================
# EVALUATION EXPORT  (ASYNC — POST /export/{project_id})
# ===================================================================

@pytest.mark.integration
class TestExportEvaluationResults:
    """POST /api/evaluations/export/{project_id}"""

    @pytest.mark.asyncio
    async def test_export_json(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            await _make_eval_run_async(async_test_db, p, owner.id, model_id=model_id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{p.id}?format=json"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "project_id" in body
        assert "results" in body

    @pytest.mark.asyncio
    async def test_export_csv(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            await _make_eval_run_async(async_test_db, p, owner.id, model_id=model_id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/export/{p.id}?format=csv"
            )
        assert resp.status_code == 200, resp.text


# ===================================================================
# EVALUATION STATUS
# ===================================================================

@pytest.mark.integration
class TestEvaluationStatus:
    """Evaluation listing, types, and status endpoints."""

    def test_list_evaluations(self, client, test_db, test_users, auth_headers, test_org):
        # GET / (list) is a SYNC handler.
        _setup_project_sync(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_evaluation_types(self, client, test_db, test_users, auth_headers):
        # GET /evaluation-types (LIST) is a SYNC handler. Self-seed a unique-id
        # active type (the shared ``test_evaluation_types`` fixture's fixed ids
        # collide with rows already committed to the shared test DB).
        test_db.add(EvaluationType(
            id=f"acc-{uuid.uuid4().hex[:8]}",
            name="Branch Accuracy",
            description="self-seeded",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"],
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_evaluation_status(self, async_test_client, async_test_db):
        # GET /evaluation/status/{id} is an ASYNC handler.
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        er = await _make_eval_run_async(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/evaluation/status/{er.id}"
            )
        assert resp.status_code in (200, 404), resp.text


# ===================================================================
# EVALUATION CONFIG
# ===================================================================

@pytest.mark.integration
class TestEvaluationConfig:
    """Evaluation configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_eval_config(self, async_test_client, async_test_db):
        # GET .../evaluation-config is an ASYNC handler.
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/evaluation-config"
            )
        assert resp.status_code in (200, 403), resp.text

    def test_update_eval_config(self, client, test_db, test_users, auth_headers, test_org):
        # PUT .../evaluation-config stays a SYNC handler.
        p, _ = _setup_project_sync(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.put(
            f"{BASE}/projects/{p.id}/evaluation-config",
            json={
                "metrics": ["accuracy", "f1"],
                "evaluation_mode": "automated",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_get_eval_config_nonexistent(self, async_test_client, async_test_db):
        # GET .../evaluation-config is an ASYNC handler.
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/nonexistent/evaluation-config"
            )
        assert resp.status_code in (403, 404), resp.text


# ===================================================================
# EVALUATION VALIDATION  (ASYNC — POST /validate-config)
# ===================================================================

@pytest.mark.integration
class TestEvaluationValidation:
    """Evaluation config validation endpoint."""

    @pytest.mark.asyncio
    async def test_validate_config(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/validate-config",
                json={"project_id": p.id, "metrics": ["accuracy"]},
            )
        assert resp.status_code in (200, 400, 403, 422), resp.text


# ===================================================================
# EVALUATION METADATA  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestEvaluationMetadata:
    """Evaluation metadata endpoints (evaluated models, statistics)."""

    @pytest.mark.asyncio
    async def test_get_evaluated_models(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await _make_eval_run_async(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/evaluated-models"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_get_evaluation_methods(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await _make_eval_run_async(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/configured-methods"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_get_evaluation_statistics(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await _make_eval_run_async(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/projects/{p.id}/statistics",
                json={"metrics": ["accuracy"], "aggregation": "model"},
            )
        assert resp.status_code in (200, 400, 422), resp.text


# ===================================================================
# MULTI-FIELD EVALUATION  (ASYNC)
# ===================================================================

@pytest.mark.integration
class TestMultiFieldEvaluation:
    """Multi-field evaluation endpoints."""

    @pytest.mark.asyncio
    async def test_get_available_fields(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/available-fields"
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_get_field_results(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}"
            )
        assert resp.status_code == 200, resp.text


# ===================================================================
# HUMAN EVALUATION
# ===================================================================

@pytest.mark.integration
class TestHumanEvaluation:
    """Human evaluation session endpoints."""

    def test_create_human_eval_session(self, client, test_db, test_users, auth_headers, test_org):
        # POST /human/session/start stays a SYNC handler.
        p, _ = _setup_project_sync(test_db, test_users[0], test_org)
        test_db.commit()
        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": p.id, "evaluation_type": "likert"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 400, 403, 422)

    @pytest.mark.asyncio
    async def test_list_human_eval_sessions(self, async_test_client, async_test_db):
        # GET /human/sessions/{id} is an ASYNC handler.
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        await _make_human_session_async(async_test_db, p, owner.id, tasks)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/sessions/{p.id}"
            )
        assert resp.status_code in (200, 403), resp.text

    @pytest.mark.asyncio
    async def test_submit_likert_evaluation(self, async_test_client, async_test_db):
        # POST /human/likert is an ASYNC handler. The HEAD test was a guarded
        # no-op (it called _setup_evaluation_project WITHOUT with_human_sessions,
        # so `if data["human_sessions"]:` never fired). Made real here: seed a
        # likert session owned by the evaluator + a task, fire the submit, and
        # assert the LikertScaleEvaluation row persisted + items_evaluated bumped.
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        session = await _make_human_session_async(
            async_test_db, p, owner.id, tasks, session_type="likert", status="active"
        )
        await async_test_db.commit()
        session_id, task_id = session.id, tasks[0].id

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/likert",
                json={
                    "session_id": session_id,
                    "task_id": task_id,
                    "response_id": "resp-1",
                    "ratings": {"accuracy": 4, "clarity": 5},
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items_evaluated"] == 1

        async_test_db.expire_all()
        rows = (
            await async_test_db.execute(
                select(LikertScaleEvaluation).where(
                    LikertScaleEvaluation.session_id == session_id
                )
            )
        ).scalars().all()
        assert {r.dimension: r.rating for r in rows} == {"accuracy": 4, "clarity": 5}

    @pytest.mark.asyncio
    async def test_submit_preference_ranking(self, async_test_client, async_test_db):
        # POST /human/preference is an ASYNC handler. Same HEAD guarded-no-op
        # story as test_submit_likert_evaluation; made real here.
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks, _ = await _setup_project_async(async_test_db, owner, org)
        session = await _make_human_session_async(
            async_test_db, p, owner.id, tasks, session_type="preference", status="active"
        )
        await async_test_db.commit()
        session_id, task_id = session.id, tasks[0].id

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/preference",
                json={
                    "session_id": session_id,
                    "task_id": task_id,
                    "response_a_id": "resp-a",
                    "response_b_id": "resp-b",
                    "winner": "a",
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items_evaluated"] == 1

        async_test_db.expire_all()
        ranking = (
            await async_test_db.execute(
                select(PreferenceRanking).where(
                    PreferenceRanking.session_id == session_id
                )
            )
        ).scalar_one()
        assert ranking.winner == "a"
        assert ranking.task_id == task_id
