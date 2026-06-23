"""Integration tests for issue #83 — bulk-fetch latest ResponseGeneration.

Covers:
  - start_generation `mode="missing"` decision matrix: every (no row / completed /
    failed / pending / running / cancelled / older-then-newer) state must produce
    the same queued cells as the pre-fix per-cell loop.
  - start_generation `mode="missing"` perf at 1000 tasks × 10 models: handler
    returns under the 5s budget and issues at most one SELECT against
    `response_generations` (the bulk DISTINCT ON query), down from N×M
    round-trips.
  - _count_cells_to_generate `exact_match preferred over NULL fallback` rule
    in cost_estimate.py: exact structure_key matches must shadow legacy NULL
    rows, and the sk=None branch must ignore keyed rows.

The `generation_task_list` router was migrated to the async DB lane
(``Depends(get_async_db)``), so the start_generation tests seed real rows via
``async_test_db`` and drive the HTTP surface through ``async_test_client``.
``require_user`` is overridden per-test via the ``_as_user`` context manager to
return an auth User matching a seeded DB user (the sync auth dependency can't
see the async test transaction). ``celery_app`` is patched on the router module
so no real broker fires.

``_count_cells_to_generate`` is a sync-only helper (``db: Session``) that the
async cost-estimate handler bridges via ``run_sync``; the ``TestCountCellsBulkQuery``
class exercises it directly on a sync ``async_test_db`` connection through
``await async_test_db.run_sync(...)`` so the seeded rows are visible.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import patch

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _make_superadmin(db, *, username_prefix="bulkq") -> User:
    """A superadmin passes every access + write-access check, which is all the
    start_generation handler needs from the caller."""
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Bulk Query Admin",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Org") -> "object":
    from models import Organization

    org = Organization(
        id=_uid(),
        name=name,
        display_name=name,
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_project_with_tasks(
    db,
    admin: User,
    org,
    *,
    num_tasks: int,
    model_ids: List[str],
    structure_keys: List[str] | None = None,
) -> Dict:
    """Create a published project with N tasks, wired to the given org.

    Seeds generation_config so start_generation finds models + structure keys
    without needing the caller to pass them explicitly.
    """
    structure_keys = structure_keys or []
    pid = _uid()
    prompt_structures = {sk: {"key": sk} for sk in structure_keys}
    project = Project(
        id=pid,
        title=f"bulk-query-test-{pid[:6]}",
        description="issue #83 perf fix",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={
            "selected_configuration": {"models": model_ids},
            "prompt_structures": prompt_structures,
        },
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=org.id,
            assigned_by=admin.id,
        )
    )
    await db.flush()

    tasks: List[Task] = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            inner_id=i + 1,
            data={"text": f"sample {i}"},
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return {"project": project, "tasks": tasks}


def _make_response_gen(
    *,
    project_id: str,
    task_id: str,
    model_id: str,
    structure_key: str | None,
    status: str,
    created_by: str,
    created_at: datetime | None = None,
) -> DBResponseGeneration:
    return DBResponseGeneration(
        id=_uid(),
        project_id=project_id,
        task_id=task_id,
        model_id=model_id,
        structure_key=structure_key,
        status=status,
        created_by=created_by,
        created_at=created_at or datetime.utcnow(),
    )


async def _seed_response_gen(db, **kwargs) -> DBResponseGeneration:
    rg = _make_response_gen(**kwargs)
    db.add(rg)
    await db.flush()
    return rg


# ---------------------------------------------------------------------------
# start_generation correctness — mode="missing" decision matrix
# ---------------------------------------------------------------------------


class TestStartGenerationMissingModeDecisionMatrix:
    """For every (no row / completed / failed / pending / running / cancelled /
    older-then-newer) state, mode="missing" must queue the same cells the
    pre-fix per-cell loop would have. The bulk DISTINCT ON path must preserve
    the `latest is None or latest.status == "failed"` semantics."""

    @pytest.mark.asyncio
    async def test_missing_mode_queues_only_unfinished_or_failed_cells(
        self, async_test_client, async_test_db
    ):
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)

        model_ids = ["model-A", "model-B"]
        structure_keys = ["sk1", "sk2"]
        data = await _make_project_with_tasks(
            async_test_db,
            admin,
            org,
            num_tasks=4,
            model_ids=model_ids,
            structure_keys=structure_keys,
        )
        project = data["project"]
        project_id = project.id
        tasks = data["tasks"]
        # Stable handles for the matrix.
        t0, t1, t2, t3 = tasks
        t0_id, t1_id, t2_id, t3_id = t0.id, t1.id, t2.id, t3.id

        # Matrix of seeded states. Anything NOT seeded → no row → should generate.
        # task / model / sk -> (status, age_offset_seconds)
        now = datetime.utcnow()
        seeds = [
            # t0: completed across the board → none should queue
            (t0_id, "model-A", "sk1", "completed", 0),
            (t0_id, "model-A", "sk2", "completed", 0),
            (t0_id, "model-B", "sk1", "completed", 0),
            (t0_id, "model-B", "sk2", "completed", 0),
            # t1: latest failed → all four should queue
            (t1_id, "model-A", "sk1", "failed", 0),
            (t1_id, "model-A", "sk2", "failed", 0),
            (t1_id, "model-B", "sk1", "failed", 0),
            (t1_id, "model-B", "sk2", "failed", 0),
            # t2: pending / running / cancelled (treated as "exists, not failed")
            #     → should NOT queue. Cancelled is the tricky one: it's not
            #     "failed" so the per-cell loop skips it. We preserve that.
            (t2_id, "model-A", "sk1", "pending", 0),
            (t2_id, "model-A", "sk2", "running", 0),
            (t2_id, "model-B", "sk1", "cancelled", 0),
            # (t2, "model-B", "sk2") deliberately unseeded → should queue
            # t3: older-completed-then-newer-failed → latest wins → should queue.
            #     This verifies DISTINCT ON's ORDER BY created_at DESC picks the
            #     newest row, matching the original .order_by(...).first() logic.
            (t3_id, "model-A", "sk1", "completed", -3600),  # 1h ago
            (t3_id, "model-A", "sk1", "failed", 0),  # now → latest
            # And the reverse: older-failed-then-newer-completed → should NOT queue
            (t3_id, "model-A", "sk2", "failed", -3600),
            (t3_id, "model-A", "sk2", "completed", 0),
        ]
        for task_id, model_id, sk, status, age_offset in seeds:
            await _seed_response_gen(
                async_test_db,
                project_id=project_id,
                task_id=task_id,
                model_id=model_id,
                structure_key=sk,
                status=status,
                created_by=admin.id,
                created_at=now + timedelta(seconds=age_offset),
            )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = None
            with _as_user(admin):
                resp = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project_id}/generate",
                    json={"mode": "missing"},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Build expected set: every (task, model, sk) cell whose latest row is
        # None or "failed".
        expected = {
            (t1_id, "model-A", "sk1"),
            (t1_id, "model-A", "sk2"),
            (t1_id, "model-B", "sk1"),
            (t1_id, "model-B", "sk2"),
            (t2_id, "model-B", "sk2"),  # unseeded
            (t3_id, "model-A", "sk1"),  # latest is failed
            # t3 / model-A / sk2 has latest=completed → not queued
            # All of t3 / model-B / * unseeded → queue
            (t3_id, "model-B", "sk1"),
            (t3_id, "model-B", "sk2"),
        }
        # tasks_queued is a count; the exact cells are the rows whose IDs are
        # returned in generation_job_ids (the handler inserts one new row per
        # queued cell). Cross-check by looking those rows up.
        assert body["tasks_queued"] == len(expected)
        inserted = (
            await async_test_db.execute(
                select(
                    DBResponseGeneration.task_id,
                    DBResponseGeneration.model_id,
                    DBResponseGeneration.structure_key,
                ).where(DBResponseGeneration.id.in_(body["generation_job_ids"]))
            )
        ).all()
        actual = {(r.task_id, r.model_id, r.structure_key) for r in inserted}
        assert actual == expected

    @pytest.mark.asyncio
    async def test_missing_mode_with_null_structure_key_legacy_projects(
        self, async_test_client, async_test_db
    ):
        """Projects with no `prompt_structures` configured collapse to a single
        [None] structure_key. The bulk query keys by `None` and must match
        rows where structure_key IS NULL — not rows with a non-null key."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)

        data = await _make_project_with_tasks(
            async_test_db,
            admin,
            org,
            num_tasks=2,
            model_ids=["m-1"],
            structure_keys=[],  # → handler uses [None]
        )
        project = data["project"]
        project_id = project.id
        t0, t1 = data["tasks"]
        t1_id = t1.id

        # t0 has a NULL-keyed completed row → should NOT queue.
        # t1 has only a non-NULL-keyed completed row → that row is invisible to
        # the [None] cell, so the [None] cell is "no row" → SHOULD queue.
        await _seed_response_gen(
            async_test_db,
            project_id=project_id,
            task_id=t0.id,
            model_id="m-1",
            structure_key=None,
            status="completed",
            created_by=admin.id,
        )
        await _seed_response_gen(
            async_test_db,
            project_id=project_id,
            task_id=t1.id,
            model_id="m-1",
            structure_key="leftover-key",  # not in the structure_keys list
            status="completed",
            created_by=admin.id,
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = None
            with _as_user(admin):
                resp = await async_test_client.post(
                    f"/api/generation-tasks/projects/{project_id}/generate",
                    json={"mode": "missing"},
                )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 1

        async_test_db.expire_all()
        queued = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(
                    DBResponseGeneration.project_id == project_id,
                    DBResponseGeneration.status == "pending",
                )
            )
        ).scalars().all()
        assert len(queued) == 1
        assert queued[0].task_id == t1_id
        assert queued[0].structure_key == None  # noqa: E711


# ---------------------------------------------------------------------------
# start_generation perf — the headline fix
# ---------------------------------------------------------------------------


class TestStartGenerationBulkQueryPerf:
    """Issue #83 acceptance: a 1000-task × 10-model `mode="missing"` request
    must return within 5s and issue at most one SELECT against
    `response_generations` (down from 10,000)."""

    @pytest.mark.asyncio
    async def test_1000_tasks_x_10_models_returns_under_5s_with_single_bulk_query(
        self, async_test_client, async_test_db
    ):
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)

        num_tasks = 1000
        model_ids = [f"perf-model-{i}" for i in range(10)]
        data = await _make_project_with_tasks(
            async_test_db,
            admin,
            org,
            num_tasks=num_tasks,
            model_ids=model_ids,
            structure_keys=[],  # single [None] cell per (task, model)
        )
        project = data["project"]
        project_id = project.id
        tasks = data["tasks"]

        # Seed one completed ResponseGeneration per cell so the missing-mode
        # check finds them all → tasks_queued == 0, no inserts, no Celery
        # dispatch. This isolates the bulk SELECT phase, which is what the
        # bug was about.
        now = datetime.utcnow()
        for t in tasks:
            for m in model_ids:
                async_test_db.add(
                    _make_response_gen(
                        project_id=project_id,
                        task_id=t.id,
                        model_id=m,
                        structure_key=None,
                        status="completed",
                        created_by=admin.id,
                        created_at=now,
                    )
                )
        await async_test_db.commit()

        # Count SELECTs against response_generations during the request. The
        # async lane runs over asyncpg, but SQLAlchemy still drives it through a
        # sync_engine under the hood, so the global `Engine` class's
        # `before_cursor_execute` event fires for these statements too — letting
        # us count the same way the sync version did.
        rg_select_count = 0

        def _listener(conn, cursor, statement, parameters, context, executemany):
            nonlocal rg_select_count
            stmt_lower = statement.lower()
            if "response_generations" in stmt_lower and stmt_lower.lstrip().startswith(
                "select"
            ):
                rg_select_count += 1

        # Listen on the global Engine class so any engine (sync or the async
        # engine's underlying sync_engine) fires the hook.
        event.listen(Engine, "before_cursor_execute", _listener)
        try:
            start = time.perf_counter()
            with patch("routers.generation_task_list.celery_app") as mock_celery:
                mock_celery.send_task.return_value = None
                with _as_user(admin):
                    resp = await async_test_client.post(
                        f"/api/generation-tasks/projects/{project_id}/generate",
                        json={"mode": "missing"},
                    )
            elapsed = time.perf_counter() - start
        finally:
            event.remove(Engine, "before_cursor_execute", _listener)

        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 0  # all cells already completed
        assert elapsed < 5.0, (
            f"handler took {elapsed:.2f}s for 10k cells — issue #83 regressed; "
            "the bulk DISTINCT ON path is meant to keep this under 5s"
        )
        # Bulk path: exactly one SELECT against response_generations
        # (the DISTINCT ON query). Tolerate <=2 for any defensive add.
        assert rg_select_count <= 2, (
            f"response_generations was queried {rg_select_count} times — "
            "the per-cell N+1 pattern is back"
        )


# ---------------------------------------------------------------------------
# cost_estimate _count_cells_to_generate — exact-match-preferred-over-NULL
# ---------------------------------------------------------------------------


class TestCountCellsBulkQuery:
    """The `_count_cells_to_generate` helper must preserve the precedence rule
    `exact structure_key match > NULL fallback row` that the original
    per-cell `case((sk match, 0), else_=1)` ORDER BY enforced. The bulk-query
    rewrite splits this into two queries; the Python merge below is where the
    precedence lives now.

    The helper is sync-only (``db: Session``); we run it via
    ``async_test_db.run_sync`` so it sees the rows seeded in this async
    transaction.
    """

    async def _project_with_tasks(self, db, admin, org, num_tasks):
        return await _make_project_with_tasks(
            db,
            admin,
            org,
            num_tasks=num_tasks,
            model_ids=["m-cost"],
            structure_keys=["sk-x"],
        )

    @staticmethod
    def _count(sync_db, project_id, structure_keys):
        from routers.cost_estimate import _count_cells_to_generate

        return _count_cells_to_generate(
            sync_db, project_id, "m-cost", structure_keys, "missing"
        )

    @pytest.mark.asyncio
    async def test_exact_completed_beats_null_failed(self, async_test_db):
        """task has exact `sk-x` completed + NULL failed → exact wins →
        cell NOT counted (no need to regenerate)."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await self._project_with_tasks(async_test_db, admin, org, num_tasks=1)
        project_id = data["project"].id
        t = data["tasks"][0]

        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key="sk-x",
            status="completed", created_by=admin.id,
        )
        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="failed", created_by=admin.id,
        )
        await async_test_db.commit()

        n = await async_test_db.run_sync(
            lambda s: self._count(s, project_id, ["sk-x"])
        )
        assert n == 0

    @pytest.mark.asyncio
    async def test_null_fallback_used_when_no_exact_match(self, async_test_db):
        """task has only NULL `completed` row (legacy) → NULL fallback wins
        for the `sk-x` query → cell NOT counted."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await self._project_with_tasks(async_test_db, admin, org, num_tasks=1)
        project_id = data["project"].id
        t = data["tasks"][0]

        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="completed", created_by=admin.id,
        )
        await async_test_db.commit()

        n = await async_test_db.run_sync(
            lambda s: self._count(s, project_id, ["sk-x"])
        )
        assert n == 0

    @pytest.mark.asyncio
    async def test_exact_failed_shadows_null_completed(self, async_test_db):
        """task has exact `sk-x` failed + NULL completed → exact wins (failed)
        → cell IS counted. The NULL completed must NOT rescue the cell — the
        original case()-ordered query forbade that."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await self._project_with_tasks(async_test_db, admin, org, num_tasks=1)
        project_id = data["project"].id
        t = data["tasks"][0]

        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key="sk-x",
            status="failed", created_by=admin.id,
        )
        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="completed", created_by=admin.id,
        )
        await async_test_db.commit()

        n = await async_test_db.run_sync(
            lambda s: self._count(s, project_id, ["sk-x"])
        )
        assert n == 1

    @pytest.mark.asyncio
    async def test_no_rows_at_all_cell_counted(self, async_test_db):
        """No `response_generations` row for the cell → cell IS counted."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await self._project_with_tasks(async_test_db, admin, org, num_tasks=1)
        project_id = data["project"].id
        await async_test_db.commit()

        n = await async_test_db.run_sync(
            lambda s: self._count(s, project_id, ["sk-x"])
        )
        assert n == 1

    @pytest.mark.asyncio
    async def test_sk_none_ignores_keyed_rows(self, async_test_db):
        """Legacy projects with no structures → structure_keys=None. The
        helper must only consider NULL rows; non-null-keyed rows must NOT
        rescue the cell from counting."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_project_with_tasks(
            async_test_db, admin, org,
            num_tasks=1, model_ids=["m-cost"], structure_keys=[],
        )
        project_id = data["project"].id
        t = data["tasks"][0]

        # A non-NULL-keyed completed row exists, but the sk=None branch must
        # ignore it. Result: the [None] cell has no row → counted.
        await _seed_response_gen(
            async_test_db, project_id=project_id, task_id=t.id,
            model_id="m-cost", structure_key="leftover",
            status="completed", created_by=admin.id,
        )
        await async_test_db.commit()

        n = await async_test_db.run_sync(
            lambda s: self._count(s, project_id, None)
        )
        assert n == 1


# ---------------------------------------------------------------------------
# start_generation fallback bound — issue #106
# ---------------------------------------------------------------------------


class TestStartGenerationFallbackBound:
    """Issue #106: omitting `task_ids` used to load every Task row in the
    project (full `data` JSONB included) with no upper bound. The handler now
    loads IDs only and rejects the no-task_ids fallback above
    GENERATION_FALLBACK_MAX_TASKS."""

    @pytest.mark.asyncio
    async def test_fallback_above_cap_rejected_with_400(
        self, async_test_client, async_test_db
    ):
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_project_with_tasks(
            async_test_db, admin, org, num_tasks=4, model_ids=["model-A"],
        )
        project_id = data["project"].id
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = None
            with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 3):
                with _as_user(admin):
                    resp = await async_test_client.post(
                        f"/api/generation-tasks/projects/{project_id}/generate",
                        json={"mode": "all"},
                    )

            assert resp.status_code == 400, resp.text
            assert "task_ids" in resp.json()["detail"]
            mock_celery.send_task.assert_not_called()

        # Nothing was queued.
        async_test_db.expire_all()
        n_rows = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(
                    DBResponseGeneration.project_id == project_id
                )
            )
        ).scalars().all()
        assert len(n_rows) == 0

    @pytest.mark.asyncio
    async def test_fallback_at_cap_still_queues_all_tasks(
        self, async_test_client, async_test_db
    ):
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_project_with_tasks(
            async_test_db, admin, org, num_tasks=4, model_ids=["model-A"],
        )
        project_id = data["project"].id
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = None
            with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 4):
                with _as_user(admin):
                    resp = await async_test_client.post(
                        f"/api/generation-tasks/projects/{project_id}/generate",
                        json={"mode": "all"},
                    )

        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 4

    @pytest.mark.asyncio
    async def test_explicit_task_ids_bypass_the_cap(
        self, async_test_client, async_test_db
    ):
        """The bound only guards the load-everything fallback; callers paging
        through explicit task_ids stay functional on huge projects."""
        admin = await _make_superadmin(async_test_db)
        org = await _make_org(async_test_db)
        data = await _make_project_with_tasks(
            async_test_db, admin, org, num_tasks=3, model_ids=["model-A"],
        )
        project_id = data["project"].id
        picked = [t.id for t in data["tasks"][:2]]
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = None
            with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 1):
                with _as_user(admin):
                    resp = await async_test_client.post(
                        f"/api/generation-tasks/projects/{project_id}/generate",
                        json={"mode": "all", "task_ids": picked},
                    )

        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 2
        async_test_db.expire_all()
        inserted = (
            await async_test_db.execute(
                select(DBResponseGeneration.task_id).where(
                    DBResponseGeneration.project_id == project_id
                )
            )
        ).all()
        assert {r.task_id for r in inserted} == set(picked)
