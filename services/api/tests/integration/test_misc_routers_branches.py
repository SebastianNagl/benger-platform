"""Behavioral integration tests for several smaller platform API routers.

Seeds real rows via ``test_db`` and asserts HTTP status + response JSON +
persisted DB state against Postgres. Existing unit suites cover these
routers with Mock sessions; this module exercises the real query/commit
paths the mocks cannot.

Routers / endpoints covered:

- ``services/api/routers/prompt_structures.py``
  (``/api/projects/{pid}/generation-config/structures``):
    * ``PUT /{key}`` create → persisted into ``generation_config.prompt_structures``.
    * key-validation 400 (bad chars / too long).
    * 404 project, 403 outsider-org-context.
    * ``GET ""`` list + ``GET /{key}`` get + ``GET /{key}`` 404 missing.
    * ``PUT ""`` set-active validation (unknown key 400) + persisted active list.
    * ``DELETE /{key}`` 404 missing, and delete that also drops the key from
      ``active_structures``.

- ``services/api/routers/dashboard.py`` (``/api/dashboard/stats``):
    * the empty-``project_summaries`` live-fallback path: seeded tasks /
      annotations / generations are counted by ``_live_dashboard_counts``.
    * the no-accessible-projects all-zeros short-circuit.

- ``services/api/routers/file_uploads.py`` (``/api/files``):
    * ``GET /`` empty + ``task_id`` filter + ownership scoping.
    * ``GET /{id}/download`` 404 for an unknown / not-owned file (reached
      before any object-storage call).
    * ``DELETE /{id}`` 404 unknown, persisted delete for an owned record
      with no storage_key (no MinIO call).

- ``services/api/routers/evaluations/status.py`` (``/api/evaluations``):
    * ``GET /evaluation/status/{id}`` 404 + 403 + happy path.
    * ``GET /`` org-scoped list (superadmin sees all; the empty-accessible
      short-circuit).
    * ``GET /evaluation-types`` combined category filter, and
      ``GET /evaluation-types/{id}`` is_active=False 404.

MinIO byte-streaming (upload + presigned download success) is out of scope.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationRun,
    EvaluationType,
    Generation,
    ResponseGeneration,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, is_superadmin=None):
    """Override ``require_user`` with a real seeded user for async-handler tests
    driven through ``async_test_client`` (mirrors test_eval_results_branches.py)."""
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


async def _make_owner(db, *, name="Test Admin", is_superadmin=True):
    """Seed a user via the async session for the async-handler tests."""
    u = User(
        id=_uid(),
        username=f"misc-branch-{_uid()[:8]}",
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


async def _make_project_async(db, creator):
    """Seed a minimal project via the async session."""
    p = Project(
        id=_uid(),
        title=f"Misc Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=False,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _make_eval_run_async(db, project, creator, *, status="completed"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4",
        evaluation_type_ids=["accuracy"],
        metrics={"accuracy": 0.9},
        status=status,
        samples_evaluated=7,
        eval_metadata={"type": "automated"},
        created_by=creator.id,
    )
    db.add(er)
    await db.flush()
    return er


def _make_project(db, creator, org=None, *, is_private=False):
    p = Project(
        id=_uid(),
        title=f"Misc Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    return p


def _ctx(auth_headers, role, org):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# NOTE: The prompt_structures.py and file_uploads.py routers were migrated to
# the async DB lane (Depends(get_async_db)). Their behavioral coverage moved to
# the async-fixture suites that can see the AsyncSession transaction:
#   - tests/unit/test_prompt_structures_router.py
#   - tests/integration/test_file_uploads_coverage.py
# This module keeps the still-sync dashboard.py + evaluations/status.py routers.


# ===========================================================================
# dashboard.py
# ===========================================================================


@pytest.mark.integration
class TestDashboardStats:
    @pytest.mark.asyncio
    async def test_live_fallback_counts_real_rows(
        self, async_test_client, async_test_db
    ):
        """With an empty project_summaries table, /stats falls back to the
        live counters. Seed a task + a real annotation + a parsed generation
        and assert each surfaces."""
        owner = await _make_owner(async_test_db)
        project = await _make_project_async(async_test_db, owner)
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={"text": "dash task"},
            created_by=owner.id,
        )
        async_test_db.add(task)
        await async_test_db.flush()

        # Real (non-cancelled, non-empty result) annotation.
        async_test_db.add(
            Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=owner.id,
                result=[{"value": "x"}],
                was_cancelled=False,
            )
        )
        # Parsed generation (parse_status == "success") under a parent.
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            task_id=task.id,
            model_id="gpt-4",
            status="completed",
            created_by=owner.id,
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        async_test_db.add(
            Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=task.id,
                model_id="gpt-4",
                case_data="{}",
                response_content="answer",
                status="completed",
                parse_status="success",
            )
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_count"] >= 1
        assert stats["task_count"] >= 1
        assert stats["annotation_count"] >= 1
        assert stats["projects_with_generations"] >= 1

    @pytest.mark.asyncio
    async def test_no_accessible_projects_all_zero(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin in private context with no own private projects
        has an empty accessible set → the all-zeros short-circuit."""
        annotator = await _make_owner(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get(
                "/api/dashboard/stats",
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_count"] == 0
        assert stats["task_count"] == 0
        assert stats["annotation_count"] == 0
        assert stats["projects_with_generations"] == 0
        assert stats["projects_with_evaluations"] == 0


# ===========================================================================
# evaluations/status.py
# ===========================================================================

_EVAL_BASE = "/api/evaluations"


def _make_eval_run(db, project, creator, *, status="completed", model_id="gpt-4", metrics=None):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy"],
        metrics=metrics if metrics is not None else {"accuracy": 0.9},
        status=status,
        samples_evaluated=7,
        eval_metadata={"type": "automated"},
        created_by=creator.id,
    )
    db.add(er)
    db.flush()
    return er


@pytest.mark.integration
class TestEvaluationStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_not_found_404(self, async_test_client, async_test_db):
        owner = await _make_owner(async_test_db)
        await async_test_db.commit()
        missing = _uid()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"{_EVAL_BASE}/evaluation/status/{missing}",
            )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_status_inaccessible_project_403(
        self, async_test_client, async_test_db
    ):
        """The eval run exists (passes the 404 guard) but a non-superadmin
        whose access check returns False hits the 403 branch."""
        owner = await _make_owner(async_test_db)
        outsider = await _make_owner(
            async_test_db, name="Outsider", is_superadmin=False
        )
        project = await _make_project_async(async_test_db, owner)
        er = await _make_eval_run_async(async_test_db, project, owner)
        await async_test_db.commit()

        with _as_user(outsider), patch(
            "routers.evaluations.status.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            resp = await async_test_client.get(
                f"{_EVAL_BASE}/evaluation/status/{er.id}",
            )
        assert resp.status_code == 403
        assert "access" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_status_happy_path(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        project = await _make_project_async(async_test_db, owner)
        er = await _make_eval_run_async(
            async_test_db, project, owner, status="failed",
        )
        er.error_message = "boom"
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{_EVAL_BASE}/evaluation/status/{er.id}",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == er.id
        assert body["status"] == "failed"
        assert body["message"] == "boom"


@pytest.mark.integration
class TestEvaluationListEndpoint:
    def test_superadmin_sees_run(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, project, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert er.id in ids
        match = next(r for r in resp.json() if r["id"] == er.id)
        assert match["project_id"] == project.id
        assert match["samples_evaluated"] == 7

    def test_empty_accessible_returns_empty_list(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A non-superadmin in private context with no own private projects
        gets the empty-accessible short-circuit (empty list)."""
        # Seed a run in an org project so something exists but is out of scope.
        project = _make_project(test_db, test_users[0], test_org)
        _make_eval_run(test_db, project, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.integration
class TestEvaluationTypesEndpoint:
    def test_filter_by_category(
        self, client, auth_headers, test_db, test_users
    ):
        # Two active types in different categories.
        test_db.add(
            EvaluationType(
                id=f"cat-a-{uuid.uuid4().hex[:6]}",
                name="Cat A Metric",
                category="classification",
                higher_is_better=True,
                is_active=True,
                applicable_project_types=["text_classification"],
            )
        )
        target_id = f"cat-b-{uuid.uuid4().hex[:6]}"
        test_db.add(
            EvaluationType(
                id=target_id,
                name="Cat B Metric",
                category="qa_branch_unique",
                higher_is_better=True,
                is_active=True,
                applicable_project_types=["qa_reasoning"],
            )
        )
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation-types?category=qa_branch_unique",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert ids == {target_id}

    @pytest.mark.asyncio
    async def test_get_inactive_type_404(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        inactive_id = f"inactive-{uuid.uuid4().hex[:6]}"
        async_test_db.add(
            EvaluationType(
                id=inactive_id,
                name="Inactive Metric",
                category="classification",
                higher_is_better=True,
                is_active=False,
                applicable_project_types=[],
            )
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{_EVAL_BASE}/evaluation-types/{inactive_id}",
            )
        assert resp.status_code == 404
        assert inactive_id in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_active_type_happy_path(
        self, async_test_client, async_test_db
    ):
        owner = await _make_owner(async_test_db)
        active_id = f"active-{uuid.uuid4().hex[:6]}"
        async_test_db.add(
            EvaluationType(
                id=active_id,
                name="Active Metric",
                category="classification",
                higher_is_better=False,
                is_active=True,
                value_range={"min": 0, "max": 1},
                applicable_project_types=["text_classification"],
            )
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{_EVAL_BASE}/evaluation-types/{active_id}",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == active_id
        assert body["higher_is_better"] is False
        assert body["value_range"] == {"min": 0, "max": 1}
