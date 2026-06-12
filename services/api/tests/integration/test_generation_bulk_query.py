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
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.engine import Engine

from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project_with_tasks(
    test_db,
    admin: User,
    test_org,
    *,
    num_tasks: int,
    model_ids: List[str],
    structure_keys: List[str] | None = None,
) -> Dict:
    """Create a published project with N tasks, wired to the test org.

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
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=test_org.id,
            assigned_by=admin.id,
        )
    )
    test_db.flush()

    tasks: List[Task] = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            inner_id=i + 1,
            data={"text": f"sample {i}"},
            created_by=admin.id,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()
    test_db.commit()
    return {"project": project, "tasks": tasks}


def _seed_response_gen(
    test_db,
    *,
    project_id: str,
    task_id: str,
    model_id: str,
    structure_key: str | None,
    status: str,
    created_by: str,
    created_at: datetime | None = None,
) -> DBResponseGeneration:
    rg = DBResponseGeneration(
        id=_uid(),
        project_id=project_id,
        task_id=task_id,
        model_id=model_id,
        structure_key=structure_key,
        status=status,
        created_by=created_by,
        created_at=created_at or datetime.utcnow(),
    )
    test_db.add(rg)
    return rg


# ---------------------------------------------------------------------------
# start_generation correctness — mode="missing" decision matrix
# ---------------------------------------------------------------------------


class TestStartGenerationMissingModeDecisionMatrix:
    """For every (no row / completed / failed / pending / running / cancelled /
    older-then-newer) state, mode="missing" must queue the same cells the
    pre-fix per-cell loop would have. The bulk DISTINCT ON path must preserve
    the `latest is None or latest.status == "failed"` semantics."""

    @patch("routers.generation_task_list.celery_app")
    def test_missing_mode_queues_only_unfinished_or_failed_cells(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        mock_celery.send_task.return_value = None
        admin = test_users[0]

        model_ids = ["model-A", "model-B"]
        structure_keys = ["sk1", "sk2"]
        data = _make_project_with_tasks(
            test_db,
            admin,
            test_org,
            num_tasks=4,
            model_ids=model_ids,
            structure_keys=structure_keys,
        )
        project = data["project"]
        tasks = data["tasks"]
        # Stable handles for the matrix.
        t0, t1, t2, t3 = tasks

        # Matrix of seeded states. Anything NOT seeded → no row → should generate.
        # task / model / sk -> (status, age_offset_seconds)
        now = datetime.utcnow()
        seeds = [
            # t0: completed across the board → none should queue
            (t0, "model-A", "sk1", "completed", 0),
            (t0, "model-A", "sk2", "completed", 0),
            (t0, "model-B", "sk1", "completed", 0),
            (t0, "model-B", "sk2", "completed", 0),
            # t1: latest failed → all four should queue
            (t1, "model-A", "sk1", "failed", 0),
            (t1, "model-A", "sk2", "failed", 0),
            (t1, "model-B", "sk1", "failed", 0),
            (t1, "model-B", "sk2", "failed", 0),
            # t2: pending / running / cancelled (treated as "exists, not failed")
            #     → should NOT queue. Cancelled is the tricky one: it's not
            #     "failed" so the per-cell loop skips it. We preserve that.
            (t2, "model-A", "sk1", "pending", 0),
            (t2, "model-A", "sk2", "running", 0),
            (t2, "model-B", "sk1", "cancelled", 0),
            # (t2, "model-B", "sk2") deliberately unseeded → should queue
            # t3: older-completed-then-newer-failed → latest wins → should queue.
            #     This verifies DISTINCT ON's ORDER BY created_at DESC picks the
            #     newest row, matching the original .order_by(...).first() logic.
            (t3, "model-A", "sk1", "completed", -3600),  # 1h ago
            (t3, "model-A", "sk1", "failed", 0),  # now → latest
            # And the reverse: older-failed-then-newer-completed → should NOT queue
            (t3, "model-A", "sk2", "failed", -3600),
            (t3, "model-A", "sk2", "completed", 0),
        ]
        for task, model_id, sk, status, age_offset in seeds:
            _seed_response_gen(
                test_db,
                project_id=project.id,
                task_id=task.id,
                model_id=model_id,
                structure_key=sk,
                status=status,
                created_by=admin.id,
                created_at=now + timedelta(seconds=age_offset),
            )
        test_db.commit()

        resp = client.post(
            f"/api/generation-tasks/projects/{project.id}/generate",
            json={"mode": "missing"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Build expected set: every (task, model, sk) cell whose latest row is
        # None or "failed".
        expected = {
            (t1.id, "model-A", "sk1"),
            (t1.id, "model-A", "sk2"),
            (t1.id, "model-B", "sk1"),
            (t1.id, "model-B", "sk2"),
            (t2.id, "model-B", "sk2"),  # unseeded
            (t3.id, "model-A", "sk1"),  # latest is failed
            # t3 / model-A / sk2 has latest=completed → not queued
            # All of t3 / model-B / * unseeded → queue
            (t3.id, "model-B", "sk1"),
            (t3.id, "model-B", "sk2"),
        }
        # tasks_queued is a count; the exact cells are the rows whose IDs are
        # returned in generation_job_ids (the handler inserts one new row per
        # queued cell). Cross-check by looking those rows up.
        assert body["tasks_queued"] == len(expected)
        inserted = (
            test_db.query(
                DBResponseGeneration.task_id,
                DBResponseGeneration.model_id,
                DBResponseGeneration.structure_key,
            )
            .filter(DBResponseGeneration.id.in_(body["generation_job_ids"]))
            .all()
        )
        actual = {(r.task_id, r.model_id, r.structure_key) for r in inserted}
        assert actual == expected

    @patch("routers.generation_task_list.celery_app")
    def test_missing_mode_with_null_structure_key_legacy_projects(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        """Projects with no `prompt_structures` configured collapse to a single
        [None] structure_key. The bulk query keys by `None` and must match
        rows where structure_key IS NULL — not rows with a non-null key."""
        mock_celery.send_task.return_value = None
        admin = test_users[0]

        data = _make_project_with_tasks(
            test_db,
            admin,
            test_org,
            num_tasks=2,
            model_ids=["m-1"],
            structure_keys=[],  # → handler uses [None]
        )
        project = data["project"]
        t0, t1 = data["tasks"]

        # t0 has a NULL-keyed completed row → should NOT queue.
        # t1 has only a non-NULL-keyed completed row → that row is invisible to
        # the [None] cell, so the [None] cell is "no row" → SHOULD queue.
        _seed_response_gen(
            test_db,
            project_id=project.id,
            task_id=t0.id,
            model_id="m-1",
            structure_key=None,
            status="completed",
            created_by=admin.id,
        )
        _seed_response_gen(
            test_db,
            project_id=project.id,
            task_id=t1.id,
            model_id="m-1",
            structure_key="leftover-key",  # not in the structure_keys list
            status="completed",
            created_by=admin.id,
        )
        test_db.commit()

        resp = client.post(
            f"/api/generation-tasks/projects/{project.id}/generate",
            json={"mode": "missing"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 1

        queued = (
            test_db.query(DBResponseGeneration)
            .filter(
                DBResponseGeneration.project_id == project.id,
                DBResponseGeneration.status == "pending",
            )
            .all()
        )
        assert len(queued) == 1
        assert queued[0].task_id == t1.id
        assert queued[0].structure_key == None  # noqa: E711


# ---------------------------------------------------------------------------
# start_generation perf — the headline fix
# ---------------------------------------------------------------------------


class TestStartGenerationBulkQueryPerf:
    """Issue #83 acceptance: a 1000-task × 10-model `mode="missing"` request
    must return within 5s and issue at most one SELECT against
    `response_generations` (down from 10,000)."""

    @patch("routers.generation_task_list.celery_app")
    def test_1000_tasks_x_10_models_returns_under_5s_with_single_bulk_query(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        mock_celery.send_task.return_value = None
        admin = test_users[0]

        num_tasks = 1000
        model_ids = [f"perf-model-{i}" for i in range(10)]
        data = _make_project_with_tasks(
            test_db,
            admin,
            test_org,
            num_tasks=num_tasks,
            model_ids=model_ids,
            structure_keys=[],  # single [None] cell per (task, model)
        )
        project = data["project"]
        tasks = data["tasks"]

        # Seed one completed ResponseGeneration per cell so the missing-mode
        # check finds them all → tasks_queued == 0, no inserts, no Celery
        # dispatch. This isolates the bulk SELECT phase, which is what the
        # bug was about.
        now = datetime.utcnow()
        rg_rows = [
            {
                "id": _uid(),
                "project_id": project.id,
                "task_id": t.id,
                "model_id": m,
                "structure_key": None,
                "status": "completed",
                "created_by": admin.id,
                "created_at": now,
            }
            for t in tasks
            for m in model_ids
        ]
        test_db.bulk_insert_mappings(DBResponseGeneration, rg_rows)
        test_db.commit()

        # Count SELECTs against response_generations during the request.
        rg_select_count = 0

        def _listener(conn, cursor, statement, parameters, context, executemany):
            nonlocal rg_select_count
            stmt_lower = statement.lower()
            if "response_generations" in stmt_lower and stmt_lower.lstrip().startswith(
                "select"
            ):
                rg_select_count += 1

        event.listen(Engine, "before_cursor_execute", _listener)
        try:
            start = time.perf_counter()
            resp = client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "missing"},
                headers=auth_headers["admin"],
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
    precedence lives now."""

    def _project_with_tasks(self, test_db, admin, test_org, num_tasks):
        return _make_project_with_tasks(
            test_db,
            admin,
            test_org,
            num_tasks=num_tasks,
            model_ids=["m-cost"],
            structure_keys=["sk-x"],
        )

    def test_exact_completed_beats_null_failed(
        self, test_db, test_users, test_org
    ):
        """task has exact `sk-x` completed + NULL failed → exact wins →
        cell NOT counted (no need to regenerate)."""
        from routers.cost_estimate import _count_cells_to_generate

        admin = test_users[0]
        data = self._project_with_tasks(test_db, admin, test_org, num_tasks=1)
        t = data["tasks"][0]

        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key="sk-x",
            status="completed", created_by=admin.id,
        )
        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="failed", created_by=admin.id,
        )
        test_db.commit()

        n = _count_cells_to_generate(
            test_db, data["project"].id, "m-cost", ["sk-x"], "missing"
        )
        assert n == 0

    def test_null_fallback_used_when_no_exact_match(
        self, test_db, test_users, test_org
    ):
        """task has only NULL `completed` row (legacy) → NULL fallback wins
        for the `sk-x` query → cell NOT counted."""
        from routers.cost_estimate import _count_cells_to_generate

        admin = test_users[0]
        data = self._project_with_tasks(test_db, admin, test_org, num_tasks=1)
        t = data["tasks"][0]

        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="completed", created_by=admin.id,
        )
        test_db.commit()

        n = _count_cells_to_generate(
            test_db, data["project"].id, "m-cost", ["sk-x"], "missing"
        )
        assert n == 0

    def test_exact_failed_shadows_null_completed(
        self, test_db, test_users, test_org
    ):
        """task has exact `sk-x` failed + NULL completed → exact wins (failed)
        → cell IS counted. The NULL completed must NOT rescue the cell — the
        original case()-ordered query forbade that."""
        from routers.cost_estimate import _count_cells_to_generate

        admin = test_users[0]
        data = self._project_with_tasks(test_db, admin, test_org, num_tasks=1)
        t = data["tasks"][0]

        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key="sk-x",
            status="failed", created_by=admin.id,
        )
        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key=None,
            status="completed", created_by=admin.id,
        )
        test_db.commit()

        n = _count_cells_to_generate(
            test_db, data["project"].id, "m-cost", ["sk-x"], "missing"
        )
        assert n == 1

    def test_no_rows_at_all_cell_counted(
        self, test_db, test_users, test_org
    ):
        """No `response_generations` row for the cell → cell IS counted."""
        from routers.cost_estimate import _count_cells_to_generate

        admin = test_users[0]
        data = self._project_with_tasks(test_db, admin, test_org, num_tasks=1)

        n = _count_cells_to_generate(
            test_db, data["project"].id, "m-cost", ["sk-x"], "missing"
        )
        assert n == 1

    def test_sk_none_ignores_keyed_rows(
        self, test_db, test_users, test_org
    ):
        """Legacy projects with no structures → structure_keys=None. The
        helper must only consider NULL rows; non-null-keyed rows must NOT
        rescue the cell from counting."""
        from routers.cost_estimate import _count_cells_to_generate

        admin = test_users[0]
        data = _make_project_with_tasks(
            test_db, admin, test_org,
            num_tasks=1, model_ids=["m-cost"], structure_keys=[],
        )
        t = data["tasks"][0]

        # A non-NULL-keyed completed row exists, but the sk=None branch must
        # ignore it. Result: the [None] cell has no row → counted.
        _seed_response_gen(
            test_db, project_id=data["project"].id, task_id=t.id,
            model_id="m-cost", structure_key="leftover",
            status="completed", created_by=admin.id,
        )
        test_db.commit()

        n = _count_cells_to_generate(
            test_db, data["project"].id, "m-cost", None, "missing"
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

    @patch("routers.generation_task_list.celery_app")
    def test_fallback_above_cap_rejected_with_400(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        mock_celery.send_task.return_value = None
        admin = test_users[0]
        data = _make_project_with_tasks(
            test_db, admin, test_org, num_tasks=4, model_ids=["model-A"],
        )

        with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 3):
            resp = client.post(
                f"/api/generation-tasks/projects/{data['project'].id}/generate",
                json={"mode": "all"},
                headers=auth_headers["admin"],
            )

        assert resp.status_code == 400, resp.text
        assert "task_ids" in resp.json()["detail"]
        # Nothing was queued or dispatched.
        n_rows = (
            test_db.query(DBResponseGeneration)
            .filter(DBResponseGeneration.project_id == data["project"].id)
            .count()
        )
        assert n_rows == 0
        mock_celery.send_task.assert_not_called()

    @patch("routers.generation_task_list.celery_app")
    def test_fallback_at_cap_still_queues_all_tasks(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        mock_celery.send_task.return_value = None
        admin = test_users[0]
        data = _make_project_with_tasks(
            test_db, admin, test_org, num_tasks=4, model_ids=["model-A"],
        )

        with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 4):
            resp = client.post(
                f"/api/generation-tasks/projects/{data['project'].id}/generate",
                json={"mode": "all"},
                headers=auth_headers["admin"],
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 4

    @patch("routers.generation_task_list.celery_app")
    def test_explicit_task_ids_bypass_the_cap(
        self, mock_celery, client, test_db, test_users, test_org, auth_headers
    ):
        """The bound only guards the load-everything fallback; callers paging
        through explicit task_ids stay functional on huge projects."""
        mock_celery.send_task.return_value = None
        admin = test_users[0]
        data = _make_project_with_tasks(
            test_db, admin, test_org, num_tasks=3, model_ids=["model-A"],
        )
        picked = [t.id for t in data["tasks"][:2]]

        with patch("routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 1):
            resp = client.post(
                f"/api/generation-tasks/projects/{data['project'].id}/generate",
                json={"mode": "all", "task_ids": picked},
                headers=auth_headers["admin"],
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 2
        inserted = (
            test_db.query(DBResponseGeneration.task_id)
            .filter(DBResponseGeneration.project_id == data["project"].id)
            .all()
        )
        assert {r.task_id for r in inserted} == set(picked)
