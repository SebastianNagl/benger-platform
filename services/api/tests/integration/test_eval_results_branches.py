"""Integration tests for uncovered branches of the evaluation results &
status routers.

Targets:
- ``services/api/routers/evaluations/results/`` (mounted at
  ``/api/evaluations`` via routers/evaluations/__init__.py) — now FULLY async
  (``get_async_db`` + ``check_project_accessible_async``).
- ``services/api/routers/evaluations/status.py`` (same prefix) — partially
  async: ``GET /evaluation/status/{id}`` and ``GET /evaluation-types/{id}`` are
  async; the ``GET /`` list and ``GET /evaluation-types`` list stay sync.

The existing suites (``test_evaluation_results_deep.py``,
``test_coverage_eval_results_deep3.py``) already cover the happy paths and
the simple 404s. This file fills in the branches those leave uncovered:

results
  * GET /{evaluation_id}/samples ........ 403 access-denied, empty-page
    (``has_next`` False), pagination tail.
  * GET /{evaluation_id}/metrics/{m}/distribution ... 403, the
    "No samples found" 404 (zero rows) vs "Metric not found" 404 (rows
    but no such key), and the >=4-values real-quantile quartile path.
  * GET /{evaluation_id}/confusion-matrix ... 403, the 400 "No valid
    ground truth/prediction pairs" guard (rows present, gt/pred NULL).
  * GET /{evaluation_id}/results/by-task-model ... 403, the
    ``include_history=True`` mean-aggregation branch, the annotation
    synthetic-``annotator:`` branch, the empty-result shape.
  * GET /projects/{project_id}/results/by-task-model ... 404 project,
    403, ``evaluation_ids`` filter, ``metric`` filter, the
    ``include_history=True`` mean branch, ``deduplication_summary`` with a
    non-zero suppressed_run_count, and the no-completed-evals
    ``_build_all_tasks_response`` shape.
  * GET /sample-result ... task 404, 403, no-results empty message,
    generation-based results, the ``annotator:`` resolution branch, the
    ``generation_id`` cohesion filter, and the ``include_history=False``
    per-field dedup.

status.py
  * GET /evaluation/status/{id} ... the 403 access-denied branch.
  * GET / (list) ... org-scoped contributor vs superadmin-sees-all, and
    the empty-accessible short-circuit.
  * GET /evaluation-types ... combined category+task_type filter, and
    GET /evaluation-types/{id} the is_active=False 404 branch.

ASYNC vs SYNC lanes
-------------------
The async-handler tests seed through ``async_test_db`` and drive
``async_test_client``, overriding ``require_user`` with a real seeded user via
``_as_user`` (superadmin for happy paths; a non-superadmin + a patched
``check_project_accessible_async`` for the deterministic 403s). The sync-handler
tests (``TestListEvaluationsBranches`` and the two ``evaluation-types`` LIST
tests) keep the legacy ``client``/``test_db``/``auth_headers`` fixtures and use
the ``*_sync`` seed helpers.

Seeding mirrors the FK-valid idioms of ``test_coverage_eval_results_deep3.py``
(ResponseGeneration parent + Generation child, EvaluationJudgeRun parent for
every TaskEvaluation, the uq_task_evaluations_cell distinct-subject rule).

MinIO byte-streaming export endpoints are deliberately out of scope — only
the Postgres-backed JSON export branch is touched (and that only lightly,
since it is already covered elsewhere).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
    LLMModel,
    Organization,
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


# ---------------------------------------------------------------------------
# Auth override (mirrors tests/unit/test_file_uploads_coverage.py)
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


async def _make_owner(db, *, name="Test Admin", is_superadmin=True):
    """Seed a project owner. Defaults to a superadmin named ``Test Admin`` so
    the synthetic ``annotator:<display>`` strings keep their literal value."""
    u = User(
        id=_uid(),
        username=f"eval-branch-{_uid()[:8]}",
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
    """Minimal Organization for the ProjectOrganization link helper."""
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


# ---------------------------------------------------------------------------
# Async seeding helpers (the default lane)
# ---------------------------------------------------------------------------


async def _setup_project(db, admin, org, *, num_tasks=3, is_private=False, link_org=True):
    """Create a project owned by ``admin`` with ``num_tasks`` tasks, optionally
    linked to ``org``. Set is_private=True + link_org=False to build the 403
    fixture (a private project a non-creator non-superadmin cannot reach)."""
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Eval Branch {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
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
            data={"text": f"Eval task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return p, tasks


async def _make_eval_run(db, project, admin_id="admin-test-id", *, status="completed",
                         metrics=None, eval_metadata=None, model_id="gpt-4"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        status=status,
        metrics=metrics or {"accuracy": 0.85, "f1": 0.82},
        samples_evaluated=10,
        eval_metadata=eval_metadata or {"type": "automated"},
        created_by=admin_id,
    )
    db.add(er)
    await db.flush()
    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL: every
    # TaskEvaluation needs a parent judge run. Catch-all shape.
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


async def _add_judge_run(db, eval_run, run_index=1):
    """Add a SECOND judge run to an existing eval run. Lets two
    TaskEvaluations share the same (generation_id, field_name) cell without
    tripping uq_task_evaluations_cell (049): the index keys on judge_run_id
    too, so distinct judge runs keep both rows alive while the endpoint's
    (generation_id, field_name) dedup still treats them as one cell."""
    jr = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_model_id=None,
        run_index=run_index,
        status="completed",
    )
    db.add(jr)
    await db.flush()
    return jr


async def _make_generation(db, task, *, model_id="gpt-4", created_at=None,
                           response_generation=None):
    """A minimal FK-valid generation (ResponseGeneration parent + Generation
    child). When ``response_generation`` is supplied the Generation hangs off
    it (lets multiple Generations share one ResponseGeneration id, which is
    what the /sample-result ``generation_id`` filter keys on)."""
    if response_generation is None:
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
    else:
        rg = response_generation
    gen_kwargs = dict(
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
    # created_at is NOT NULL with a server_default; only set it when a caller
    # needs a specific value (window-function ordering tests), otherwise let
    # the DB default fire — passing None explicitly would insert NULL.
    if created_at is not None:
        gen_kwargs["created_at"] = created_at
    gen = Generation(**gen_kwargs)
    db.add(gen)
    await db.flush()
    return gen, rg


async def _make_task_evaluation(db, eval_run, task, *, metrics=None, generation=None,
                                annotation=None, field_name="answer",
                                ground_truth=None, prediction=None, passed=True,
                                created_at=None, answer_type="choices", judge_run=None,
                                evaluation_config_id=None):
    """uq_task_evaluations_cell keys a row on its scored subject
    (generation_id / annotation_id / created_by), so a real row always has a
    generation OR an annotation. Synthesize a distinct generation when none is
    supplied, otherwise two rows in the same run+field collapse to one cell."""
    if generation is None and annotation is None:
        generation, _ = await _make_generation(db, task)
    te_kwargs = dict(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_run_id=(judge_run or eval_run._test_judge_run).id,
        task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name,
        answer_type=answer_type,
        metrics=metrics if metrics is not None else {"score": 0.9},
        passed=passed,
        ground_truth=ground_truth if ground_truth is not None else {"value": "Ja"},
        prediction=prediction if prediction is not None else {"value": "Ja"},
        evaluation_config_id=evaluation_config_id,
    )
    # created_at is NOT NULL with a server_default; only set it when a caller
    # needs a specific ordering value, else let the DB default fire.
    if created_at is not None:
        te_kwargs["created_at"] = created_at
    te = TaskEvaluation(**te_kwargs)
    db.add(te)
    await db.flush()
    return te


async def _make_annotation(db, task, project, user_id):
    ann = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id,
        completed_by=user_id,
        result=[{"from_name": "answer", "to_name": "text", "type": "choices",
                 "value": {"choices": ["Ja"]}}],
        was_cancelled=False,
    )
    db.add(ann)
    await db.flush()
    return ann


async def _make_llm_model(db, model_id, name=None):
    existing = (
        await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    ).scalars().first()
    if existing:
        return
    db.add(LLMModel(
        id=model_id, name=name or model_id, provider="openai",
        model_type="chat", capabilities=["text_generation"], is_active=True,
        is_official=True,
    ))
    await db.flush()


# ---------------------------------------------------------------------------
# Sync seeding helpers (only for the sync-handler tests below)
# ---------------------------------------------------------------------------


def _setup_project_sync(db, admin_id, org, *, num_tasks=3, is_private=False, link_org=True):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Eval Branch {pid[:6]}",
        created_by=admin_id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
    )
    db.add(p)
    db.flush()
    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin_id,
        ))
        db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Eval task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=admin_id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_eval_run_sync(db, project, admin_id="admin-test-id", *, status="completed",
                        metrics=None, eval_metadata=None, model_id="gpt-4"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        status=status,
        metrics=metrics or {"accuracy": 0.85, "f1": 0.82},
        samples_evaluated=10,
        eval_metadata=eval_metadata or {"type": "automated"},
        created_by=admin_id,
    )
    db.add(er)
    db.flush()
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    db.flush()
    return er


# ===========================================================================
# results — GET /{evaluation_id}/samples : uncovered branches
# ===========================================================================


@pytest.mark.integration
class TestSamplesBranches:
    @pytest.mark.asyncio
    async def test_samples_access_denied_403(self, async_test_client, async_test_db):
        """The evaluation exists (passes the 404 guard) but a non-creator
        non-superadmin whose access check returns False hits the 403 branch."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run(async_test_db, p)
        await _make_task_evaluation(async_test_db, er, tasks[0])
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(f"{BASE}/{er.id}/samples")
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_samples_last_page_has_next_false(self, async_test_client, async_test_db):
        """page_size that exactly drains the rows on the last page → has_next
        is False (the ``(offset + page_size) < total`` branch evaluated
        False)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=3)
        er = await _make_eval_run(async_test_db, p)
        for t in tasks:
            await _make_task_evaluation(async_test_db, er, t)
        await async_test_db.commit()

        # 3 rows, page 2 size 2 → 1 row, offset 2, (2+2)=4 !< 3 → has_next False
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/samples?page=2&page_size=2"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        assert body["page"] == 2
        assert len(body["items"]) == 1
        assert body["has_next"] is False

    @pytest.mark.asyncio
    async def test_samples_page_past_end_empty_items(self, async_test_client, async_test_db):
        """A page beyond the data returns an empty item list but still a 200
        with the correct total (offset past the end)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=2)
        er = await _make_eval_run(async_test_db, p)
        for t in tasks:
            await _make_task_evaluation(async_test_db, er, t)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/samples?page=5&page_size=10"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2
        assert body["items"] == []
        assert body["has_next"] is False


# ===========================================================================
# results — GET /{evaluation_id}/metrics/{metric}/distribution
# ===========================================================================


@pytest.mark.integration
class TestDistributionBranches:
    @pytest.mark.asyncio
    async def test_distribution_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run(async_test_db, p)
        await _make_task_evaluation(async_test_db, er, tasks[0], metrics={"score": 0.5})
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/metrics/score/distribution"
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_distribution_no_samples_at_all_404(self, async_test_client, async_test_db):
        """An eval run with zero TaskEvaluation rows hits the 'No samples found
        for this evaluation' 404 — a DIFFERENT branch from the metric-missing
        404 (which requires rows to exist)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        er = await _make_eval_run(async_test_db, p)
        await async_test_db.commit()

        # DB-state: no task_evaluations for this run.
        count = (
            await async_test_db.execute(
                select(TaskEvaluation).where(TaskEvaluation.evaluation_id == er.id)
            )
        ).scalars().all()
        assert len(count) == 0

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/metrics/score/distribution"
            )
        assert resp.status_code == 404, resp.text
        assert "No samples found for this evaluation" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_distribution_metric_missing_from_present_samples_404(
        self, async_test_client, async_test_db
    ):
        """Rows exist (so the no-samples guard passes) but none carry the
        requested metric key → the 'Metric ... not found in samples' 404."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=2)
        er = await _make_eval_run(async_test_db, p)
        for t in tasks:
            await _make_task_evaluation(async_test_db, er, t, metrics={"accuracy": 0.7})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/metrics/bleu/distribution"
            )
        assert resp.status_code == 404, resp.text
        assert "bleu" in resp.json()["detail"]
        assert "not found in samples" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_distribution_quartiles_with_four_plus_values(
        self, async_test_client, async_test_db
    ):
        """With >=4 distinct values the q1/q3 take the real
        ``statistics.quantiles`` branch (not the len<4 fallback to
        min/max), and q1 <= median <= q3 holds. Also pins mean/min/max."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=5)
        er = await _make_eval_run(async_test_db, p)
        vals = [0.1, 0.3, 0.5, 0.7, 0.9]
        for t, v in zip(tasks, vals):
            await _make_task_evaluation(async_test_db, er, t, metrics={"score": v})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/metrics/score/distribution"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metric_name"] == "score"
        assert body["min"] == pytest.approx(0.1)
        assert body["max"] == pytest.approx(0.9)
        assert body["mean"] == pytest.approx(0.5)
        assert body["median"] == pytest.approx(0.5)
        q = body["quartiles"]
        # >=4 values → real quantiles, monotone and strictly inside (min,max).
        assert q["q1"] < q["q2"] < q["q3"]
        assert q["q1"] > body["min"]
        assert q["q3"] < body["max"]
        assert len(body["histogram"]) == 10


# ===========================================================================
# results — GET /{evaluation_id}/confusion-matrix
# ===========================================================================


@pytest.mark.integration
class TestConfusionMatrixBranches:
    @pytest.mark.asyncio
    async def test_confusion_matrix_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run(async_test_db, p)
        await _make_task_evaluation(
            async_test_db, er, tasks[0], field_name="answer",
            ground_truth={"value": "ja"}, prediction={"value": "ja"},
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/confusion-matrix?field_name=answer"
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_confusion_matrix_no_valid_pairs_400(self, async_test_client, async_test_db):
        """Samples exist for the field (so the no-samples 404 passes) but their
        ground_truth/prediction values are NULL → the
        'No valid ground truth/prediction pairs found' 400 guard. We supply a
        JSON object WITHOUT a 'value' key so ``.get('value')`` is None."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=2)
        er = await _make_eval_run(async_test_db, p)
        for t in tasks:
            await _make_task_evaluation(
                async_test_db, er, t, field_name="answer",
                ground_truth={"other": "x"}, prediction={"other": "y"},
            )
        await async_test_db.commit()

        # DB-state: rows exist for the field, but no value subkey.
        rows = (
            await async_test_db.execute(
                select(TaskEvaluation).where(
                    TaskEvaluation.evaluation_id == er.id,
                    TaskEvaluation.field_name == "answer",
                )
            )
        ).scalars().all()
        assert len(rows) == 2
        assert all("value" not in (r.ground_truth or {}) for r in rows)

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/confusion-matrix?field_name=answer"
            )
        assert resp.status_code == 400, resp.text
        assert "No valid ground truth/prediction pairs" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_confusion_matrix_perfect_diagonal_accuracy_one(
        self, async_test_client, async_test_db
    ):
        """All predictions correct → accuracy 1.0 and per-class precision/recall
        of 1.0 for every label (exercises the TP/FP/FN arithmetic loop)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=4)
        er = await _make_eval_run(async_test_db, p)
        pairs = [("ja", "ja"), ("ja", "ja"), ("nein", "nein"), ("nein", "nein")]
        for t, (gt, pred) in zip(tasks, pairs):
            await _make_task_evaluation(
                async_test_db, er, t, field_name="answer",
                ground_truth={"value": gt}, prediction={"value": pred},
            )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/confusion-matrix?field_name=answer"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accuracy"] == pytest.approx(1.0)
        assert sorted(body["labels"]) == ["ja", "nein"]
        for label in body["labels"]:
            assert body["precision_per_class"][label] == pytest.approx(1.0)
            assert body["recall_per_class"][label] == pytest.approx(1.0)
            assert body["f1_per_class"][label] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_confusion_matrix_missing_field_name_422(self, async_test_client, async_test_db):
        """field_name is a required query param (``Query(...)``) — omitting it
        is a 422 before any DB access."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        er = await _make_eval_run(async_test_db, p)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/{er.id}/confusion-matrix")
        assert resp.status_code == 422, resp.text


# ===========================================================================
# results — GET /{evaluation_id}/results/by-task-model (eval-level)
# ===========================================================================


@pytest.mark.integration
class TestEvalByTaskModelBranches:
    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run(async_test_db, p)
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/results/by-task-model"
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_include_history_means_multiple_generations(
        self, async_test_client, async_test_db
    ):
        """include_history=True averages every historical generation row for a
        (task, model) cell. Two generations for one task/model with scores 0.4
        and 0.8 → the cell mean is 0.6 (the aggregate_mean branch)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-hist", "GPT Hist")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        er = await _make_eval_run(async_test_db, p, model_id="gpt-hist")
        task = tasks[0]
        gen1, _ = await _make_generation(async_test_db, task, model_id="gpt-hist")
        gen2, _ = await _make_generation(async_test_db, task, model_id="gpt-hist")
        await _make_task_evaluation(async_test_db, er, task, generation=gen1, metrics={"score": 0.4})
        await _make_task_evaluation(async_test_db, er, task, generation=gen2, metrics={"score": 0.8})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/results/by-task-model?include_history=true"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "gpt-hist" in body["models"]
        # Cell shows the mean of 0.4 and 0.8.
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"]["gpt-hist"] == pytest.approx(0.6)
        assert body["summary"]["gpt-hist"]["avg"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_annotation_results_synthetic_annotator_model(
        self, async_test_client, async_test_db
    ):
        """Annotation-based TaskEvaluations (generation_id NULL, annotation_id
        set) surface as a synthetic ``annotator:<display>`` model. The display
        falls back to the user's ``name`` (Test Admin)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        er = await _make_eval_run(async_test_db, p)
        ann = await _make_annotation(async_test_db, tasks[0], p, owner.id)
        await _make_task_evaluation(async_test_db, er, tasks[0], annotation=ann, metrics={"score": 0.75})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/results/by-task-model"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        annot_models = [m for m in body["models"] if m.startswith("annotator:")]
        assert len(annot_models) == 1
        synth = annot_models[0]
        # Display resolves through name ("Test Admin") since use_pseudonym is off.
        assert synth == "annotator:Test Admin"
        assert body["model_names"][synth] == "Annotator: Test Admin"
        assert body["summary"][synth]["avg"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_empty_result_shape(self, async_test_client, async_test_db):
        """An eval run with no task_evaluations and no annotations returns the
        documented empty envelope (early-return branch)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        er = await _make_eval_run(async_test_db, p)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/{er.id}/results/by-task-model"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "evaluation_id": er.id,
            "models": [],
            "model_names": {},
            "tasks": [],
            "summary": {},
        }


# ===========================================================================
# results — GET /projects/{project_id}/results/by-task-model
# ===========================================================================


@pytest.mark.integration
class TestProjectByTaskModelBranches:
    @pytest.mark.asyncio
    async def test_project_not_found_404(self, async_test_client, async_test_db):
        """An unknown project_id hits the first guard (the project lookup) for a
        superadmin too — 404 'Project ... not found'."""
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/does-not-exist-{uuid.uuid4().hex}/results/by-task-model"
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_no_completed_evals_builds_all_tasks(self, async_test_client, async_test_db):
        """A project whose only eval run is ``failed`` (excluded by the
        status filter) yields no completed_eval_ids → the early return that
        still lists every project task via _build_all_tasks_response, with
        empty scores and the data-availability fields present."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=3)
        await _make_eval_run(async_test_db, p, status="failed")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["models"] == []
        assert body["summary"] == {}
        assert {t["task_id"] for t in body["tasks"]} == {t.id for t in tasks}
        for t in body["tasks"]:
            assert t["scores"] == {}
            assert "has_annotation" in t
            assert "generation_models" in t
            assert "annotator_columns" in t

    @pytest.mark.asyncio
    async def test_evaluation_ids_filter_scopes_results(self, async_test_client, async_test_db):
        """The ``evaluation_ids`` query restricts which runs feed the matrix.
        Two completed runs on the same task/model with different scores; asking
        for only run A surfaces A's score, not B's."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-filter", "GPT Filter")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        # Run A: score 0.2 on an older generation.
        er_a = await _make_eval_run(async_test_db, p, model_id="gpt-filter")
        gen_a, _ = await _make_generation(
            async_test_db, task, model_id="gpt-filter",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        await _make_task_evaluation(async_test_db, er_a, task, generation=gen_a, metrics={"score": 0.2})
        # Run B: score 0.9 on a newer generation.
        er_b = await _make_eval_run(async_test_db, p, model_id="gpt-filter")
        gen_b, _ = await _make_generation(
            async_test_db, task, model_id="gpt-filter",
            created_at=datetime.now(timezone.utc),
        )
        await _make_task_evaluation(async_test_db, er_b, task, generation=gen_b, metrics={"score": 0.9})
        await async_test_db.commit()

        # include_history=true so we average ALL rows of the filtered run
        # rather than latest-gen-only (which would dedup to one gen).
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
                f"?evaluation_ids={er_a.id}&include_history=true"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        # Only run A is in scope → 0.2, run B's 0.9 is excluded.
        assert cell["scores"].get("gpt-filter") == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_metric_filter_selects_key(self, async_test_client, async_test_db):
        """When a run bundles two metrics in one row, ``metric=`` keeps only
        rows carrying that key. A row with both 'bleu' and 'rouge' is returned
        for metric=bleu and the score is the bleu value (primary-score
        extraction over the lite-projected metrics)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-metric", "GPT Metric")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-metric")
        gen, _ = await _make_generation(async_test_db, task, model_id="gpt-metric")
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen,
            metrics={"bleu": 0.42},
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model?metric=bleu"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-metric") == pytest.approx(0.42)

        # A metric absent from every row → no score for that cell.
        with _as_user(owner):
            resp2 = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model?metric=does_not_exist"
            )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        cell2 = next(t for t in body2["tasks"] if t["task_id"] == task.id)
        assert cell2["scores"] == {}

    @pytest.mark.asyncio
    async def test_evaluation_config_id_unions_gen_and_annotation(
        self, async_test_client, async_test_db
    ):
        """`evaluation_config_id` scopes to ONE method and scans ALL runs,
        unioning a generation-side cell (model column) with an annotation-side
        cell (annotator column) even when they live on DIFFERENT runs (a model
        run + an immediate KI-Votum run). This is the "one page per method,
        all runs, no n/a" contract."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-union", "GPT Union")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        CFG = "llm_judge_falloesung-cfgunion"
        # Run 1: an LLM generation graded under CFG.
        er_gen = await _make_eval_run(async_test_db, p, model_id="gpt-union")
        gen, _ = await _make_generation(async_test_db, task, model_id="gpt-union")
        await _make_task_evaluation(
            async_test_db, er_gen, task, generation=gen,
            metrics={"llm_judge_falloesung": {"value": 0.70}},
            evaluation_config_id=CFG,
        )
        # Run 2: a human annotation graded under the SAME CFG, on another run.
        er_ann = await _make_eval_run(async_test_db, p, model_id="immediate")
        ann = await _make_annotation(async_test_db, task, p, owner.id)
        await _make_task_evaluation(
            async_test_db, er_ann, task, annotation=ann,
            metrics={"llm_judge_falloesung": {"value": 0.55}},
            evaluation_config_id=CFG,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
                f"?metric=llm_judge_falloesung&evaluation_config_id={CFG}"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        # Both the model column and the annotator column are populated, from
        # two different runs, under the one config id.
        assert cell["scores"].get("gpt-union") == pytest.approx(0.70)
        assert cell["scores"].get("annotator:Test Admin") == pytest.approx(0.55)

    @pytest.mark.asyncio
    async def test_evaluation_config_id_isolates_same_metric_configs(
        self, async_test_client, async_test_db
    ):
        """Two configs sharing a metric key (issue #111) stay isolated: filtering
        by one config's id returns only that config's rows, never the sibling's."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-iso", "GPT Iso")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=2)
        t1, t2 = tasks[0], tasks[1]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-iso")
        g1, _ = await _make_generation(async_test_db, t1, model_id="gpt-iso")
        g2, _ = await _make_generation(async_test_db, t2, model_id="gpt-iso")
        await _make_task_evaluation(
            async_test_db, er, t1, generation=g1,
            metrics={"bleu": 0.2}, evaluation_config_id="cfg-a",
        )
        await _make_task_evaluation(
            async_test_db, er, t2, generation=g2,
            metrics={"bleu": 0.9}, evaluation_config_id="cfg-b",
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp_a = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
                f"?metric=bleu&evaluation_config_id=cfg-a"
            )
            resp_b = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
                f"?metric=bleu&evaluation_config_id=cfg-b"
            )
        assert resp_a.status_code == 200, resp_a.text
        assert resp_b.status_code == 200, resp_b.text
        a, b = resp_a.json(), resp_b.json()
        a1 = next(t for t in a["tasks"] if t["task_id"] == t1.id)
        assert a1["scores"].get("gpt-iso") == pytest.approx(0.2)
        # cfg-a never surfaces t2's cfg-b row.
        a2 = next((t for t in a["tasks"] if t["task_id"] == t2.id), None)
        assert a2 is None or a2["scores"].get("gpt-iso") is None
        b2 = next(t for t in b["tasks"] if t["task_id"] == t2.id)
        assert b2["scores"].get("gpt-iso") == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_evaluation_config_id_excludes_null_legacy_rows(
        self, async_test_client, async_test_db
    ):
        """Legacy rows with a NULL evaluation_config_id are excluded by the
        config-id filter (documented; scripts/backfill_immediate_eval_config_id
        remediates). Without the filter the same row IS returned."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-null", "GPT Null")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-null")
        gen, _ = await _make_generation(async_test_db, task, model_id="gpt-null")
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen,
            metrics={"bleu": 0.5}, evaluation_config_id=None,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
                f"?metric=bleu&evaluation_config_id=cfg-a"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next((t for t in body["tasks"] if t["task_id"] == task.id), None)
        assert cell is None or cell["scores"].get("gpt-null") is None

        # Sanity: metric-only (no config filter) still returns the legacy row.
        with _as_user(owner):
            resp2 = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model?metric=bleu"
            )
        body2 = resp2.json()
        cell2 = next(t for t in body2["tasks"] if t["task_id"] == task.id)
        assert cell2["scores"].get("gpt-null") == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_deduplication_summary_counts_suppressed(
        self, async_test_client, async_test_db
    ):
        """Two TaskEvaluation rows for the SAME (generation_id, field_name)
        differing only by created_at → the latest wins and the older is
        suppressed; deduplication_summary.suppressed_run_count reflects it."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-dedup", "GPT Dedup")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-dedup")
        gen, _ = await _make_generation(async_test_db, task, model_id="gpt-dedup")
        # Same gen + same field, two evals → one is suppressed by latest-wins.
        # They sit under two different judge runs so uq_task_evaluations_cell
        # (049, which keys on judge_run_id) lets both rows persist; the
        # endpoint's (generation_id, field_name) partition still collapses
        # them to one cell, suppressing the older.
        jr2 = await _add_judge_run(async_test_db, er)
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.3},
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.7}, judge_run=jr2,
            created_at=datetime.now(timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        dedup = body["deduplication_summary"]
        assert dedup["scope"] == "(generation_id, field_name)"
        assert dedup["policy"] == "latest_wins_by_created_at_desc"
        assert dedup["suppressed_run_count"] == 1
        # Cell shows the latest (0.7), not the suppressed 0.3.
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-dedup") == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_include_history_means_project_level(
        self, async_test_client, async_test_db
    ):
        """include_history=True at the project level averages the per-cell
        rows. Two generations for one (task, model), scores 0.2 and 0.6 →
        cell mean 0.4."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        await _make_llm_model(async_test_db, "gpt-phist", "GPT PHist")
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-phist")
        gen1, _ = await _make_generation(async_test_db, task, model_id="gpt-phist")
        gen2, _ = await _make_generation(async_test_db, task, model_id="gpt-phist")
        await _make_task_evaluation(async_test_db, er, task, generation=gen1, metrics={"score": 0.2})
        await _make_task_evaluation(async_test_db, er, task, generation=gen2, metrics={"score": 0.6})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/results/by-task-model?include_history=true"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-phist") == pytest.approx(0.4)


# ===========================================================================
# results — GET /sample-result  (entirely uncovered)
# ===========================================================================


@pytest.mark.integration
class TestSampleResultBranches:
    @pytest.mark.asyncio
    async def test_task_not_found_404(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id=nonexistent-{uuid.uuid4().hex}&model_id=gpt-4"
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={tasks[0].id}&model_id=gpt-4"
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_no_results_returns_empty_message(self, async_test_client, async_test_db):
        """Task is accessible but has no evaluations for the model → the
        empty-results envelope with the explanatory message."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={tasks[0].id}&model_id=gpt-4"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_id"] == tasks[0].id
        assert body["model_id"] == "gpt-4"
        assert body["results"] == []
        assert "No evaluation results" in body["message"]

    @pytest.mark.asyncio
    async def test_generation_based_results(self, async_test_client, async_test_db):
        """A generation-based TaskEvaluation for the task+model is returned with
        full detail (metrics, ground_truth, prediction, evaluation_context)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-4",
                                  eval_metadata={"evaluation_type": "llm_judge"})
        gen, _ = await _make_generation(async_test_db, task, model_id="gpt-4")
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.66}, passed=True,
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        row = body["results"][0]
        assert row["field_name"] == "answer"
        assert row["metrics"] == {"score": 0.66}
        assert row["passed"] is True
        assert row["evaluation_context"]["status"] == "completed"
        assert row["evaluation_context"]["evaluation_type"] == "llm_judge"

    @pytest.mark.asyncio
    async def test_generation_id_filter_cohesion(self, async_test_client, async_test_db):
        """The ``generation_id`` param filters on Generation.generation_id (the
        FK back to ResponseGeneration), not TaskEvaluation.generation_id. Two
        ResponseGeneration parents for the same task/model; filtering by one
        parent id returns only its evaluation."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-4")
        # Two distinct ResponseGeneration parents, each with one child Generation.
        gen_a, rg_a = await _make_generation(async_test_db, task, model_id="gpt-4")
        gen_b, rg_b = await _make_generation(async_test_db, task, model_id="gpt-4")
        await _make_task_evaluation(async_test_db, er, task, generation=gen_a,
                                    field_name="answer", metrics={"score": 0.11})
        await _make_task_evaluation(async_test_db, er, task, generation=gen_b,
                                    field_name="comment", metrics={"score": 0.99})
        await async_test_db.commit()

        # Filter to parent rg_a → only gen_a's eval (score 0.11) comes back.
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4"
                f"&generation_id={rg_a.id}"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        assert body["results"][0]["metrics"] == {"score": 0.11}

    @pytest.mark.asyncio
    async def test_include_history_false_dedups_per_field(
        self, async_test_client, async_test_db
    ):
        """include_history=false keeps only the latest row per field_name.
        Two evals on the same field (different generations) collapse to one;
        a second field survives → 2 rows total, latest per field."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p, model_id="gpt-4")
        gen1, _ = await _make_generation(async_test_db, task, model_id="gpt-4")
        gen2, _ = await _make_generation(async_test_db, task, model_id="gpt-4")
        gen3, _ = await _make_generation(async_test_db, task, model_id="gpt-4")
        # Two rows on field "answer" (older + newer) + one row on "comment".
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen1, field_name="answer",
            metrics={"score": 0.1},
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen2, field_name="answer",
            metrics={"score": 0.5},
            created_at=datetime.now(timezone.utc),
        )
        await _make_task_evaluation(
            async_test_db, er, task, generation=gen3, field_name="comment",
            metrics={"score": 0.9},
        )
        await async_test_db.commit()

        # history on → all 3 rows.
        with _as_user(owner):
            resp_all = await async_test_client.get(
                f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4&include_history=true"
            )
        assert resp_all.status_code == 200, resp_all.text
        assert resp_all.json()["total_count"] == 3

        # history off → one per field (2 fields). The "answer" survivor is the
        # latest (0.5), not 0.1.
        with _as_user(owner):
            resp_dedup = await async_test_client.get(
                f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4&include_history=false"
            )
        assert resp_dedup.status_code == 200, resp_dedup.text
        body = resp_dedup.json()
        assert body["total_count"] == 2
        by_field = {r["field_name"]: r["metrics"]["score"] for r in body["results"]}
        assert by_field == {"answer": 0.5, "comment": 0.9}

    @pytest.mark.asyncio
    async def test_annotator_model_resolution(self, async_test_client, async_test_db):
        """A ``model_id`` of ``annotator:<display>`` resolves the user back
        through the pseudonym→name→username precedence and returns the
        annotation-based evaluation rows for that user."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        task = tasks[0]
        er = await _make_eval_run(async_test_db, p)
        ann = await _make_annotation(async_test_db, task, p, owner.id)
        await _make_task_evaluation(
            async_test_db, er, task, annotation=ann, field_name="answer",
            metrics={"score": 0.55},
        )
        await async_test_db.commit()

        # owner's display name is "Test Admin" (use_pseudonym off → name wins).
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={task.id}&model_id=annotator:Test Admin"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        assert body["results"][0]["metrics"] == {"score": 0.55}

    @pytest.mark.asyncio
    async def test_annotator_unknown_display_empty(self, async_test_client, async_test_db):
        """An ``annotator:<display>`` that matches no user resolves to no rows
        → the empty envelope (the ``user is None`` → sample_results = []
        branch)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org, num_tasks=1)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={tasks[0].id}"
                f"&model_id=annotator:Nobody {uuid.uuid4().hex}"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"] == []

    @pytest.mark.asyncio
    async def test_missing_required_query_params_422(self, async_test_client, async_test_db):
        """task_id and model_id are required (``Query(...)``) — omitting model_id
        is a 422."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/sample-result?task_id={tasks[0].id}"
            )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# status.py — GET /evaluation/status/{id} : 403 branch (async)
# ===========================================================================


@pytest.mark.integration
class TestStatusBranches:
    @pytest.mark.asyncio
    async def test_status_access_denied_403(self, async_test_client, async_test_db):
        """The run exists (passes 404) but its private project is not the
        requester's → 403 with the status-specific message."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, name="Outsider", is_superadmin=False)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run(async_test_db, p, status="running")
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.status.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(f"{BASE}/evaluation/status/{er.id}")
        assert resp.status_code == 403, resp.text
        assert "don't have access" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_status_message_from_error_message(self, async_test_client, async_test_db):
        """A failed run surfaces its error_message as the status message
        (the ``error_message or 'Evaluation status'`` branch, error side)."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        er = await _make_eval_run(async_test_db, p, status="failed")
        er.error_message = "boom: judge timed out"
        async_test_db.add(er)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/evaluation/status/{er.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "failed"
        assert body["message"] == "boom: judge timed out"

    @pytest.mark.asyncio
    async def test_status_default_message_when_no_error(self, async_test_client, async_test_db):
        """A run without an error_message uses the literal fallback string."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, org)
        er = await _make_eval_run(async_test_db, p, status="completed")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/evaluation/status/{er.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "Evaluation status"


# ===========================================================================
# status.py — GET /  (list) : org-scoping branches (SYNC handler)
# ===========================================================================


@pytest.mark.integration
class TestListEvaluationsBranches:
    def test_superadmin_sees_all(self, client, test_db, test_users, auth_headers, test_org):
        """A superadmin's accessible_ids is None (see-everything) so the
        project-id filter is skipped — the run is present without any org
        header."""
        p, tasks = _setup_project_sync(test_db, test_users[0].id, test_org)
        er = _make_eval_run_sync(test_db, p)
        test_db.commit()

        resp = client.get(f"{BASE}/", headers=auth_headers["admin"])
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er.id in ids

    def test_contributor_scoped_to_org_projects(self, client, test_db, test_users, auth_headers, test_org):
        """A non-superadmin sees runs for projects in their accessible set. The
        contributor is an org member, the project is linked to the org → the
        run appears under the org context."""
        p, tasks = _setup_project_sync(test_db, test_users[0].id, test_org)
        er = _make_eval_run_sync(test_db, p)
        test_db.commit()

        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er.id in ids

    def test_contributor_excluded_from_inaccessible_private(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A run on a private project the contributor cannot access is filtered
        OUT of their list (the accessible_ids restriction in action)."""
        # Private project owned by admin, not linked to any org → contributor
        # has no path to it.
        p_priv, _ = _setup_project_sync(
            test_db, test_users[0].id, test_org, is_private=True, link_org=False,
        )
        er_priv = _make_eval_run_sync(test_db, p_priv)
        test_db.commit()

        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er_priv.id not in ids


# ===========================================================================
# status.py — GET /evaluation-types  &  /evaluation-types/{id}
# ===========================================================================


@pytest.mark.integration
class TestEvaluationTypesBranches:
    def test_combined_category_and_task_type_filter(
        self, client, test_db, test_users, auth_headers
    ):
        """Both filters applied together: category=classification AND
        task_type_id=text_classification. The result is the intersection — only
        classification types applicable to text_classification. SYNC list.

        Self-seeds unique-id rows (rather than the shared ``test_evaluation_types``
        fixture, whose fixed ids collide with rows already committed to the
        shared test DB): a classification row applicable to ``text_classification``
        and a qa row applicable to ``qa_reasoning``. The classification one must
        appear, the qa one must be filtered out, and every returned row must be
        classification."""
        cls_id = f"cls-{uuid.uuid4().hex[:8]}"
        qa_id = f"qa-{uuid.uuid4().hex[:8]}"
        test_db.add(EvaluationType(
            id=cls_id, name="Branch Classification",
            description="classification + text_classification",
            category="classification", higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"], is_active=True,
        ))
        test_db.add(EvaluationType(
            id=qa_id, name="Branch QA",
            description="qa + qa_reasoning",
            category="qa", higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["qa_reasoning"], is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation-types"
            "?category=classification&task_type_id=text_classification",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        returned = {d["id"] for d in data}
        # The classification row applies to text_classification → present.
        assert cls_id in returned
        # The qa row is excluded by BOTH the category and task_type filters.
        assert qa_id not in returned
        # Intersection semantics: every returned row is classification.
        for d in data:
            assert d["category"] == "classification"

    @pytest.mark.asyncio
    async def test_inactive_type_returns_404(self, async_test_client, async_test_db):
        """GET /evaluation-types/{id} (ASYNC) filters on is_active — an inactive
        type is a 404 even though the row exists."""
        owner = await _make_owner(async_test_db)
        et = EvaluationType(
            id=f"inactive-{uuid.uuid4().hex[:8]}",
            name="Inactive Metric",
            description="deactivated",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"],
            is_active=False,
        )
        async_test_db.add(et)
        await async_test_db.commit()

        # DB-state: the row exists but is inactive.
        row = (
            await async_test_db.execute(
                select(EvaluationType).where(EvaluationType.id == et.id)
            )
        ).scalars().first()
        assert row is not None
        assert row.is_active is False

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/evaluation-types/{et.id}")
        assert resp.status_code == 404, resp.text
        assert et.id in resp.json()["detail"]

    def test_active_type_excludes_inactive_from_list(
        self, client, test_db, test_users, auth_headers
    ):
        """The list endpoint (SYNC) filters is_active=True — an inactive row
        never appears. Self-seeds its own inactive row (no shared fixture —
        see note on the combined-filter test about the colliding fixture ids)."""
        et = EvaluationType(
            id=f"hidden-{uuid.uuid4().hex[:8]}",
            name="Hidden Metric",
            category="qa",
            higher_is_better=True,
            applicable_project_types=["qa_reasoning"],
            is_active=False,
        )
        test_db.add(et)
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {d["id"] for d in resp.json()}
        assert et.id not in ids
