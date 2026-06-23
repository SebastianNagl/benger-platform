"""Behavioral integration tests for the multi-field evaluation-run router.

Target: ``services/api/routers/evaluations/multi_field.py`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``) — the lowest
covered API router. The existing cancel/idempotency coverage lives in
``tests/integration/test_evaluation_cancel_idempotency.py``; this file does NOT
re-cover those happy paths. It fills the still-uncovered branches:

  POST   /run ........................ 404 (missing project), 403 (no access),
                                       400 (no configs / no enabled configs),
                                       400 (invalid annotator_user_ids /
                                       model_ids scope filter), the all-human
                                       'ongoing' short-circuit (korrektur_*
                                       metric → singleton run, no celery), the
                                       LLM dispatch path (celery patched) →
                                       EvaluationRun persisted with the right
                                       eval_metadata.
  POST   /run/{id}/cancel ............ 403 (annotator, neither owner nor editor),
                                       already-terminal no-op, parent-project
                                       404 path is covered implicitly.
  GET    /projects/{id}/available-fields  404, 403, human/reference field
                                       extraction from label_config + task data.
  GET    /run/results/project/{id} ... 404, 403, the accepted-eval-type filter
                                       (a non-accepted type is dropped),
                                       latest_only=True vs False, the
                                       config_id|pred|ref|metric key parsing +
                                       aggregate_score, sample_results_count.
  GET    /run/results/{id} ........... 404, 403, the 'not an evaluation run'
                                       400 (wrong evaluation_type), the
                                       per-config field-combo parsing, and the
                                       judges_by_config SQL enrichment.

Every test drives the endpoint via ``client`` and asserts status + response
JSON; persistence tests re-read rows from ``test_db``. Celery dispatch is
patched to a stub (mirrors test_evaluation_cancel_idempotency) so the LLM
path lands its EvaluationRun row without a live broker.

Access model recap (routers/projects/helpers + app/core/authorization):
  * ``test_users[0]`` = admin (superadmin) — always allowed.
  * ``[1]`` = contributor (PROJECT_EDIT via org), ``[2]`` = annotator
    (PROJECT_VIEW only), ``[3]`` = org_admin.
  * A private project is reachable only by its creator / superadmin.
"""

from __future__ import annotations

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
    Organization,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task

BASE = "/api/evaluations"
CELERY_TARGET = "routers.evaluations.helpers.celery_app.send_task"


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


# --- Async lane (available-fields + results endpoints migrated to get_async_db) ---
#
# These endpoints read via ``await db.execute(select(...))`` and use the
# ``*_async`` access helpers, so the sync ``client``/``test_db`` Mock lane no
# longer reaches them. The async tests seed through ``async_test_db`` and drive
# ``async_test_client``, overriding require_user with a real seeded user via
# ``_as_user`` (superadmin owner for happy paths; a non-superadmin + a patched
# ``*_async`` access helper for the deterministic 403s). The POST /run and
# cancel handlers stay SYNC, so those tests keep the ``client``/``test_db`` lane.


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


async def _make_owner(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"mfb-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="MF Branch Owner",
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


async def _setup_project_async(db, admin, org, *, num_tasks=2, is_private=False,
                               link_org=True, label_config=None, evaluation_config=None):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"MF {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=label_config if label_config is not None else (
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
            data={"text": f"task {i}", "musterloesung": f"ml {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return p, tasks


async def _make_eval_run_async(db, project, admin_id, *, status="completed", metrics=None,
                               eval_metadata=None, model_id="gpt-4", samples=10):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy"],
        status=status,
        metrics=metrics or {},
        samples_evaluated=samples,
        eval_metadata=eval_metadata if eval_metadata is not None
        else {"evaluation_type": "evaluation"},
        created_by=admin_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=None,
        run_index=0, status="completed",
    )
    db.add(jr)
    await db.flush()
    er._test_judge_run = jr
    return er


async def _make_generation_async(db, task, *, model_id="gpt-4", parsed_annotation=None):
    rg = ResponseGeneration(
        id=_uid(), project_id=task.project_id, task_id=task.id,
        model_id=model_id, status="completed", created_by=task.created_by,
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data="{}", response_content="resp",
        status="completed", parse_status="success",
        parsed_annotation=parsed_annotation,
    )
    db.add(gen)
    await db.flush()
    return gen, rg


async def _make_task_evaluation_async(db, eval_run, task, *, generation=None, annotation=None,
                                      field_name="answer", metrics=None, judge_run=None):
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


def _setup_project(db, admin, org, *, num_tasks=2, is_private=False,
                   link_org=True, label_config=None, evaluation_config=None):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"MF {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=label_config if label_config is not None else (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    db.flush()
    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"task {i}", "musterloesung": f"ml {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_eval_run(db, project, admin_id, *, status="completed", metrics=None,
                   eval_metadata=None, model_id="gpt-4", samples=10):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy"],
        status=status,
        metrics=metrics or {},
        samples_evaluated=samples,
        eval_metadata=eval_metadata if eval_metadata is not None
        else {"evaluation_type": "evaluation"},
        created_by=admin_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=None,
        run_index=0, status="completed",
    )
    db.add(jr)
    db.flush()
    er._test_judge_run = jr
    return er


def _make_generation(db, task, *, model_id="gpt-4", parsed_annotation=None):
    rg = ResponseGeneration(
        id=_uid(), project_id=task.project_id, task_id=task.id,
        model_id=model_id, status="completed", created_by=task.created_by,
    )
    db.add(rg)
    db.flush()
    gen = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data="{}", response_content="resp",
        status="completed", parse_status="success",
        parsed_annotation=parsed_annotation,
    )
    db.add(gen)
    db.flush()
    return gen, rg


def _make_task_evaluation(db, eval_run, task, *, generation=None, annotation=None,
                          field_name="answer", metrics=None, judge_run=None):
    if generation is None and annotation is None:
        generation, _ = _make_generation(db, task)
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
    db.flush()
    return te


def _h(auth_headers, org, role="admin"):
    return {**auth_headers[role], "X-Organization-Context": org.id}


def _config(metric="bleu", cfg_id="c1", enabled=True):
    return {
        "id": cfg_id,
        "metric": metric,
        "prediction_fields": ["__response__"],
        "reference_fields": ["musterloesung"],
        "enabled": enabled,
    }


# ===========================================================================
# POST /run
# ===========================================================================


@pytest.mark.integration
class TestRunEvaluation:
    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            f"{BASE}/run",
            json={"project_id": f"missing-{uuid.uuid4().hex}",
                  "evaluation_configs": [_config()]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, _ = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={"project_id": p.id, "evaluation_configs": [_config()]},
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    def test_empty_configs_400(self, client, test_db, test_users, auth_headers, test_org):
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={"project_id": p.id, "evaluation_configs": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "No evaluation configurations" in resp.json()["detail"]

    def test_no_enabled_configs_400(self, client, test_db, test_users, auth_headers, test_org):
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={"project_id": p.id,
                  "evaluation_configs": [_config(enabled=False)]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "No enabled evaluation configurations" in resp.json()["detail"]

    def test_invalid_annotator_ids_400(self, client, test_db, test_users, auth_headers, test_org):
        """annotator_user_ids that have no annotations on the project → 400."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={
                "project_id": p.id,
                "evaluation_configs": [_config()],
                "annotator_user_ids": ["ghost-annotator"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "annotator_user_ids" in resp.json()["detail"]
        assert "ghost-annotator" in resp.json()["detail"]

    def test_invalid_model_ids_400(self, client, test_db, test_users, auth_headers, test_org):
        """model_ids that have no generations on the project → 400."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={
                "project_id": p.id,
                "evaluation_configs": [_config()],
                "model_ids": ["ghost-model"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "model_ids" in resp.json()["detail"]
        assert "ghost-model" in resp.json()["detail"]

    def test_all_human_metric_returns_ongoing(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A request whose only enabled config is a human-graded metric
        (korrektur_falloesung) creates the singleton ongoing run and returns
        status='ongoing' WITHOUT dispatching to celery."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/run",
            json={
                "project_id": p.id,
                "evaluation_configs": [
                    {
                        "id": "k1",
                        "metric": "korrektur_falloesung",
                        "prediction_fields": ["loesung"],
                        "reference_fields": ["musterloesung"],
                        "enabled": True,
                    }
                ],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ongoing"
        assert len(body["human_eval_run_ids"]) == 1

        # DB state: the singleton human run exists with model_id 'human'.
        run = test_db.query(EvaluationRun).filter_by(id=body["evaluation_id"]).one()
        assert run.model_id == "human"
        assert run.project_id == p.id
        assert run.eval_metadata.get("evaluation_type") == "korrektur_falloesung"

    def test_llm_dispatch_persists_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An LLM metric config dispatches: the EvaluationRun lands as 'pending'
        with the config snapshot + dispatch_hash in eval_metadata, and celery
        send_task is invoked once (stubbed)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        stub_task = type("T", (), {"id": "celery-task-stub"})()
        with patch(CELERY_TARGET, return_value=stub_task) as send_task:
            resp = client.post(
                f"{BASE}/run",
                json={
                    "project_id": p.id,
                    "evaluation_configs": [_config(metric="bleu")],
                    "force_rerun": True,
                },
                headers=_h(auth_headers, test_org),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "started"
        assert body["task_id"] == "celery-task-stub"
        send_task.assert_called_once()

        run = test_db.query(EvaluationRun).filter_by(id=body["evaluation_id"]).one()
        assert run.status == "pending"
        assert run.eval_metadata["evaluation_type"] == "evaluation"
        assert "dispatch_hash" in run.eval_metadata
        assert run.eval_metadata["force_rerun"] is True
        assert run.eval_metadata["evaluation_configs"][0]["metric"] == "bleu"


# ===========================================================================
# POST /run/{evaluation_id}/cancel  (auth branches not in the idempotency suite)
# ===========================================================================


@pytest.mark.integration
class TestCancelAuthBranches:
    def test_annotator_cannot_cancel_others_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An annotator (PROJECT_VIEW only) who didn't trigger the run cannot
        cancel it: not owner AND not PROJECT_EDIT → 403."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p, test_users[0].id, status="running")
        test_db.commit()

        resp = client.post(
            f"{BASE}/run/{er.id}/cancel",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert "permission to cancel" in resp.json()["detail"]

        # DB state: run was NOT cancelled.
        test_db.expire_all()
        assert test_db.query(EvaluationRun).filter_by(id=er.id).one().status == "running"

    def test_cancel_already_completed_is_noop(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Cancelling an already-completed run returns the terminal no-op
        envelope (the ``status in (...)`` early return)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p, test_users[0].id, status="completed")
        test_db.commit()

        resp = client.post(
            f"{BASE}/run/{er.id}/cancel",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cancelled_run_ids"] == []
        assert "already terminal" in body["message"]

    def test_owner_can_cancel_own_running_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The user who triggered a run can cancel it even without editor rights
        (the ``is_owner`` arm of the disjunction). Here the contributor owns the
        run and cancels it."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p, test_users[1].id, status="running")
        test_db.commit()

        resp = client.post(
            f"{BASE}/run/{er.id}/cancel",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled_run_ids"] == [er.id]
        test_db.expire_all()
        assert test_db.query(EvaluationRun).filter_by(id=er.id).one().status == "cancelled"


# ===========================================================================
# GET /projects/{project_id}/available-fields
# ===========================================================================


@pytest.mark.integration
class TestAvailableFields:
    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/missing-{uuid.uuid4().hex}/available-fields",
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.multi_field.fields.auth_service.check_project_access_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/available-fields",
            )
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_extracts_human_and_reference_fields(
        self, async_test_client, async_test_db
    ):
        """Human fields come from label_config (Choices name='answer');
        reference fields come from non-underscore task.data keys (text,
        musterloesung). Model fields come from parsed_annotation from_name."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project_async(async_test_db, owner, org, num_tasks=1)
        # A successful generation whose parsed_annotation carries a from_name.
        await _make_generation_async(
            async_test_db, tasks[0], model_id="gpt-4",
            parsed_annotation=[{"from_name": "answer", "to_name": "text",
                                "type": "choices", "value": {"choices": ["Ja"]}}],
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/projects/{p.id}/available-fields",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # human field "answer" from the Choices control.
        assert "answer" in body["human_annotation_fields"]
        # reference fields from task.data (non-underscore string/list values).
        assert "text" in body["reference_fields"]
        assert "musterloesung" in body["reference_fields"]
        # model field from parsed_annotation from_name.
        assert "answer" in body["model_response_fields"]
        # all_fields is the union.
        assert set(body["all_fields"]) >= {"answer", "text", "musterloesung"}


# ===========================================================================
# GET /run/results/project/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestProjectResults:
    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/missing-{uuid.uuid4().hex}",
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.multi_field.results.auth_service.check_project_access_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}",
            )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_accepted_eval_type_filtered_out(
        self, async_test_client, async_test_db
    ):
        """A run whose eval_metadata.evaluation_type is not in the accepted set
        (e.g. 'generation') is dropped from the results list."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(async_test_db, owner, org)
        await _make_eval_run_async(
            async_test_db, p, owner.id,
            eval_metadata={"evaluation_type": "generation"},
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 0
        assert body["evaluations"] == []

    @pytest.mark.asyncio
    async def test_parses_metric_keys_and_aggregate(
        self, async_test_client, async_test_db
    ):
        """The config_id|pred|ref|metric key format parses into field_results;
        the aggregate_score averages numeric scores. Also pins
        sample_results_count from the seeded TaskEvaluation rows."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project_async(async_test_db, owner, org, num_tasks=1)
        er = await _make_eval_run_async(
            async_test_db, p, owner.id,
            metrics={
                "cfgA|__response__|musterloesung|bleu": 0.4,
                "cfgA|__response__|musterloesung|rouge": 0.6,
            },
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgA", "metric": "bleu"}],
            },
        )
        await _make_task_evaluation_async(async_test_db, er, tasks[0], metrics={"bleu": 0.4})
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        result = body["evaluations"][0]
        assert result["evaluation_id"] == er.id
        assert result["sample_results_count"] == 1
        cfg = result["results_by_config"]["cfgA"]
        combo = cfg["field_results"][0]
        assert combo["prediction_field"] == "__response__"
        assert combo["reference_field"] == "musterloesung"
        assert combo["scores"] == {"bleu": 0.4, "rouge": 0.6}
        # aggregate = mean(0.4, 0.6) = 0.5
        assert cfg["aggregate_score"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_latest_only_returns_single_run(
        self, async_test_client, async_test_db
    ):
        """latest_only=True (default) returns only the most recent run; passing
        latest_only=false returns all runs."""
        from datetime import timedelta

        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(async_test_db, owner, org)
        er_old = await _make_eval_run_async(async_test_db, p, owner.id)
        er_old.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        er_new = await _make_eval_run_async(async_test_db, p, owner.id)
        er_new.created_at = datetime.now(timezone.utc)
        await async_test_db.commit()

        with _as_user(owner):
            # Default latest_only=True → 1 run (the newest).
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}",
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total_count"] == 1
            assert body["evaluations"][0]["evaluation_id"] == er_new.id

            # latest_only=false → both runs.
            resp_all = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}?latest_only=false",
            )
        assert resp_all.status_code == 200, resp_all.text
        ids = {r["evaluation_id"] for r in resp_all.json()["evaluations"]}
        assert ids == {er_old.id, er_new.id}

    @pytest.mark.asyncio
    async def test_human_ongoing_badge_and_samples_fallback(
        self, async_test_client, async_test_db
    ):
        """A korrektur_falloesung singleton (model_id='human') is marked
        is_human_ongoing and its samples_evaluated falls back to the live
        TaskEvaluation count rather than the (unmaintained) column."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project_async(async_test_db, owner, org, num_tasks=1)
        er = await _make_eval_run_async(
            async_test_db, p, owner.id, model_id="human", samples=0,
            eval_metadata={"evaluation_type": "korrektur_falloesung"},
        )
        # Two grade rows under the human singleton.
        ann = Annotation(
            id=_uid(), task_id=tasks[0].id, project_id=p.id,
            completed_by=owner.id, result=[], was_cancelled=False,
        )
        async_test_db.add(ann)
        await async_test_db.flush()
        await _make_task_evaluation_async(async_test_db, er, tasks[0], annotation=ann,
                                          field_name="grade1", metrics={"grade_points": 12})
        # Second grade needs a distinct cell — use a second judge run.
        jr2 = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=1, status="completed",
        )
        async_test_db.add(jr2)
        await async_test_db.flush()
        await _make_task_evaluation_async(async_test_db, er, tasks[0], annotation=ann,
                                          field_name="grade2", metrics={"grade_points": 15},
                                          judge_run=jr2)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/project/{p.id}",
            )
        assert resp.status_code == 200, resp.text
        result = resp.json()["evaluations"][0]
        assert result["is_human_ongoing"] is True
        # samples_evaluated falls back to the live count (2), not the 0 column.
        assert result["samples_evaluated"] == 2
        assert result["sample_results_count"] == 2


# ===========================================================================
# GET /run/results/{evaluation_id}
# ===========================================================================


@pytest.mark.integration
class TestRunResults:
    @pytest.mark.asyncio
    async def test_missing_run_404(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/missing-{uuid.uuid4().hex}",
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(
            async_test_db, owner, org, is_private=True, link_org=False,
        )
        er = await _make_eval_run_async(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.multi_field.results.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"{BASE}/run/results/{er.id}",
            )
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_not_an_evaluation_run_400(
        self, async_test_client, async_test_db
    ):
        """A run whose eval_metadata.evaluation_type isn't 'multi_field' or
        'evaluation' (e.g. 'immediate') hits the 'not an evaluation run' 400."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(async_test_db, owner, org)
        er = await _make_eval_run_async(
            async_test_db, p, owner.id,
            eval_metadata={"evaluation_type": "immediate"},
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/{er.id}",
            )
        assert resp.status_code == 400, resp.text
        assert "not an evaluation run" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_parses_results_by_config(
        self, async_test_client, async_test_db
    ):
        """The metrics key format parses into results_by_config[config][combo]
        and the raw metrics are echoed under aggregated_metrics."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, _ = await _setup_project_async(async_test_db, owner, org)
        er = await _make_eval_run_async(
            async_test_db, p, owner.id,
            metrics={"cfgZ|__response__|musterloesung|bleu": 0.42},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgZ", "metric": "bleu"}],
            },
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/{er.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["evaluation_id"] == er.id
        combo = body["results_by_config"]["cfgZ"]["__response___vs_musterloesung"]
        assert combo["bleu"] == pytest.approx(0.42)
        assert body["aggregated_metrics"]["cfgZ|__response__|musterloesung|bleu"] == pytest.approx(0.42)
        # No scope filters → scope is null.
        assert body["scope"] is None

    @pytest.mark.asyncio
    async def test_judges_by_config_sql_enrichment(
        self, async_test_client, async_test_db
    ):
        """When eval_metadata.judges_by_config has an entry whose
        samples_evaluated is 0/None, the endpoint enriches it with the SQL
        COUNT of TaskEvaluation rows under that judge_run."""
        owner = await _make_owner(async_test_db)
        org = await _make_org(async_test_db)
        p, tasks = await _setup_project_async(async_test_db, owner, org, num_tasks=1)
        er = await _make_eval_run_async(
            async_test_db, p, owner.id,
            metrics={"cfgJ|__response__|musterloesung|llm_judge_classic": 0.7},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgJ", "metric": "llm_judge_classic"}],
            },
        )
        jr = er._test_judge_run
        # Two TaskEvaluations under the judge run (distinct cells).
        await _make_task_evaluation_async(async_test_db, er, tasks[0], field_name="answer",
                                          metrics={"llm_judge_classic": 0.7})
        jr2 = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=1, status="completed",
        )
        async_test_db.add(jr2)
        await async_test_db.flush()
        await _make_task_evaluation_async(async_test_db, er, tasks[0], field_name="answer2",
                                          metrics={"llm_judge_classic": 0.8}, judge_run=jr2)
        # judges_by_config references the FIRST judge run with a zero count.
        er.eval_metadata = {
            **er.eval_metadata,
            "judges_by_config": {
                "cfgJ": [{"judge_run_id": jr.id, "samples_evaluated": 0}],
            },
        }
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(er, "eval_metadata")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/run/results/{er.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        enriched = body["eval_metadata"]["judges_by_config"]["cfgJ"][0]
        # jr had exactly one TaskEvaluation → the 0 is replaced by the SQL count 1.
        assert enriched["samples_evaluated"] == 1
