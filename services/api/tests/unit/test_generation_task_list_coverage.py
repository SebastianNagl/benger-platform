"""
Tests for routers/generation_task_list.py to increase branch coverage.

The router was migrated to the async DB lane (``Depends(get_async_db)``,
``await db.execute(select(...))``). Its HTTP handlers
(``get_task_generation_status``, ``start_generation``, ``get_generation_result``)
and the helpers they use (``get_project_with_permissions``,
``_bulk_latest_generations``) are now ``async def``, so the tests that drive
them seed real rows via ``async_test_db`` and either call the async helper
directly with that session or drive the HTTP surface through
``async_test_client``. ``require_user`` is overridden per-test via the
``_as_user`` context manager (the sync auth dependency can't see the async test
transaction).

The per-cell compatibility shim ``get_single_task_generation_status`` stays
SYNC (``db: Session``) — it is exercised only by ``db.query``-mocking unit
tests, which remain untouched. Sync (Mock-``db.query``) tests and async
(real-fixture) tests coexist in this one file.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation as DBGeneration
from models import Organization, OrganizationMembership
from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


def _make_user(is_superadmin=False, user_id="user-123"):
    """Build a plain auth ``User`` (used only by the sync-shim unit tests)."""
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Real-fixture helpers (shared by the converted async tests)
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override ``require_user`` to return an auth User matching a seeded DB
    user, so the async handler sees the same identity that owns the seeded
    rows. Copied from tests/integration/test_reports_branches.py."""
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


async def _seed_user(db, *, is_superadmin=False, username_prefix="gen") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Gen User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_org(db, *, name="Org") -> Organization:
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


async def _add_membership(db, user: User, org: Organization, *, role="CONTRIBUTOR"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _seed_project(
    db,
    creator: User,
    *,
    title: str = "Gen Project",
    org: Organization = None,
    is_private: bool = False,
    generation_config: dict = None,
) -> Project:
    project_id = _uid()
    project = Project(
        id=project_id,
        title=title,
        description="Integration test project for generation",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        is_private=is_private,
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()

    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project_id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()

    return project


async def _seed_task(db, project: Project, creator: User, *, inner_id=1, text="hello") -> Task:
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": text},
        created_by=creator.id,
        inner_id=inner_id,
        created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    db.add(task)
    await db.flush()
    return task


async def _seed_response_generation(
    db,
    project: Project,
    task: Task,
    creator: User,
    *,
    model_id="gpt-4",
    structure_key=None,
    status="completed",
    result=None,
    error_message=None,
    prompt_used=None,
    parameters=None,
    completed_at=None,
    created_at=None,
) -> DBResponseGeneration:
    rg = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id,
        model_id=model_id,
        structure_key=structure_key,
        status=status,
        result=result,
        error_message=error_message,
        prompt_used=prompt_used,
        parameters=parameters,
        runs_requested=1,
        runs_completed=1 if status == "completed" else 0,
        runs_failed=1 if status == "failed" else 0,
        created_by=creator.id,
        created_at=created_at or datetime(2025, 6, 2, tzinfo=timezone.utc),
        completed_at=completed_at,
    )
    db.add(rg)
    await db.flush()
    return rg


async def _seed_individual_generation(
    db,
    parent: DBResponseGeneration,
    *,
    run_index=0,
    response_content="Hello world",
    usage_stats=None,
    created_at=None,
) -> DBGeneration:
    g = DBGeneration(
        id=_uid(),
        generation_id=parent.id,
        task_id=parent.task_id,
        model_id=parent.model_id,
        case_data="case data text",
        response_content=response_content,
        usage_stats=usage_stats if usage_stats is not None else {"tokens": 100},
        status="completed",
        run_index=run_index,
        created_at=created_at or datetime(2025, 6, 2, tzinfo=timezone.utc),
    )
    db.add(g)
    await db.flush()
    return g


# ===========================================================================
# get_project_with_permissions (now async) — converted (C)
# ===========================================================================


class TestGetProjectWithPermissions:
    """The helper is ``async def`` and runs real access checks against the DB,
    so these direct-await the helper with the ``async_test_db`` session and
    seed real rows for each access branch."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.generation_task_list import get_project_with_permissions

        user = await _seed_user(async_test_db)
        auth = AuthUser(
            id=user.id, username=user.username, email=user.email, name=user.name,
            is_superadmin=False, is_active=True, email_verified=True,
            created_at=user.created_at,
        )
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_project_with_permissions("proj-missing", auth, async_test_db, None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_superadmin_bypasses_checks(self, async_test_db):
        from routers.generation_task_list import get_project_with_permissions

        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        pid = project.id
        auth = AuthUser(
            id=admin.id, username=admin.username, email=admin.email, name=admin.name,
            is_superadmin=True, is_active=True, email_verified=True,
            created_at=admin.created_at,
        )
        await async_test_db.commit()

        result = await get_project_with_permissions(pid, auth, async_test_db, None)
        assert result.id == pid

    @pytest.mark.asyncio
    async def test_private_project_owner_access(self, async_test_db):
        """Creator can access their own private project even as a non-superadmin."""
        from routers.generation_task_list import get_project_with_permissions

        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner, is_private=True)
        pid = project.id
        auth = AuthUser(
            id=owner.id, username=owner.username, email=owner.email, name=owner.name,
            is_superadmin=False, is_active=True, email_verified=True,
            created_at=owner.created_at,
        )
        await async_test_db.commit()

        result = await get_project_with_permissions(pid, auth, async_test_db, None)
        assert result.id == pid

    @pytest.mark.asyncio
    async def test_private_project_non_owner_denied(self, async_test_db):
        """A non-owner, non-member of a private project is denied -> 403."""
        from routers.generation_task_list import get_project_with_permissions

        owner = await _seed_user(async_test_db)
        outsider = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner, is_private=True)
        pid = project.id
        auth = AuthUser(
            id=outsider.id, username=outsider.username, email=outsider.email,
            name=outsider.name, is_superadmin=False, is_active=True,
            email_verified=True, created_at=outsider.created_at,
        )
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_project_with_permissions(pid, auth, async_test_db, None)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_org_project_member_access(self, async_test_db):
        """An org member can access a project owned by their org."""
        from routers.generation_task_list import get_project_with_permissions

        owner = await _seed_user(async_test_db)
        member = await _seed_user(async_test_db)
        org = await _seed_org(async_test_db)
        await _add_membership(async_test_db, member, org)
        project = await _seed_project(async_test_db, owner, org=org)
        pid = project.id
        auth = AuthUser(
            id=member.id, username=member.username, email=member.email,
            name=member.name, is_superadmin=False, is_active=True,
            email_verified=True, created_at=member.created_at,
        )
        await async_test_db.commit()

        result = await get_project_with_permissions(pid, auth, async_test_db, None)
        assert result.id == pid

    @pytest.mark.asyncio
    async def test_org_project_non_member_denied(self, async_test_db):
        """A user in an unrelated org cannot access a project owned by another
        org -> 403."""
        from routers.generation_task_list import get_project_with_permissions

        owner = await _seed_user(async_test_db)
        outsider = await _seed_user(async_test_db)
        org_a = await _seed_org(async_test_db, name="Org A")
        org_b = await _seed_org(async_test_db, name="Org B")
        await _add_membership(async_test_db, outsider, org_b)
        project = await _seed_project(async_test_db, owner, org=org_a)
        pid = project.id
        auth = AuthUser(
            id=outsider.id, username=outsider.username, email=outsider.email,
            name=outsider.name, is_superadmin=False, is_active=True,
            email_verified=True, created_at=outsider.created_at,
        )
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_project_with_permissions(pid, auth, async_test_db, None)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# get_single_task_generation_status (SYNC compatibility shim) — UNCHANGED (A)
# ---------------------------------------------------------------------------


class TestGetSingleTaskGenerationStatus:
    def test_no_generation_returns_none_status(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == None  # noqa: E711
        assert result.task_id == "task-1"

    def test_completed_with_dict_result(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = {"text": "a" * 200}
        gen.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = "default"
        gen.runs_requested = 1
        gen.runs_completed = 1
        gen.runs_failed = 0

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", "default", db)
        assert result.status == "completed"
        assert result.result_preview != None  # noqa: E711
        assert result.result_preview.endswith("...")

    def test_completed_with_string_result(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = "short text"
        gen.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = None
        gen.runs_requested = 1
        gen.runs_completed = 1
        gen.runs_failed = 0

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == "completed"
        assert result.result_preview == "short text"

    def test_failed_with_error_message(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "failed"
        gen.result = None
        gen.completed_at = None
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = "API timeout"
        gen.structure_key = None
        gen.runs_requested = 1
        gen.runs_completed = 0
        gen.runs_failed = 1

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == "failed"
        assert result.error_message == "API timeout"

    def test_with_structure_key_none_filter(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == None  # noqa: E711


# ===========================================================================
# GET /api/generation-tasks/projects/{project_id}/task-status — converted (D)
# ===========================================================================


class TestGetTaskGenerationStatusEndpoint:
    @pytest.mark.asyncio
    async def test_no_models_configured(self, async_test_client, async_test_db):
        """No models configured -> empty response (early return branch)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={"selected_configuration": {"models": []}},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["models"] == []

    @pytest.mark.asyncio
    async def test_with_tasks_and_models(self, async_test_client, async_test_db):
        """A configured model + one task -> total 1, one task entry."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"]},
                "prompt_structures": {},
            },
        )
        await _seed_task(async_test_db, project, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["tasks"]) == 1
        assert body["models"] == ["gpt-4"]

    @pytest.mark.asyncio
    async def test_with_prompt_structures(self, async_test_client, async_test_db):
        """prompt_structures keys surface in the response `structures` list."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"]},
                "prompt_structures": {"default": {}, "detailed": {}},
            },
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["structures"]) == {"default", "detailed"}

    @pytest.mark.asyncio
    async def test_status_filter_excludes_non_matching(self, async_test_client, async_test_db):
        """`status_filter='not_generated'` drops tasks whose every cell already
        has a status set. A completed cell means the task is NOT in the
        not_generated bucket, so it is filtered out -> 0 tasks."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"]},
                "prompt_structures": {},
            },
        )
        task = await _seed_task(async_test_db, project, admin)
        # A completed cell (structure_key None matches the [None] default) so
        # the task has a status everywhere -> excluded from "not_generated".
        await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="completed",
            result={"text": "ok"},
            completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status",
                params={"status_filter": "not_generated"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_with_search_filter(self, async_test_client, async_test_db):
        """A search term matching task data keeps the task in the results."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"]},
                "prompt_structures": {},
            },
        )
        await _seed_task(async_test_db, project, admin, text="hello")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status",
                params={"search": "hello"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1


# ===========================================================================
# POST /api/generation-tasks/projects/{project_id}/generate — converted (D)
# ===========================================================================


class TestStartGeneration:
    @pytest.mark.asyncio
    async def test_no_models_configured_error(self, async_test_client, async_test_db):
        """No models configured -> 400 'No models configured'."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={"selected_configuration": {"models": []}},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 400
        assert "No models" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_no_tasks_error(self, async_test_client, async_test_db):
        """Models configured but project has no tasks -> 400 'No tasks'."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={"selected_configuration": {"models": ["gpt-4"]}},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 400
        assert "No tasks" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_all_mode_with_cancellation_and_dispatch(
        self, async_test_client, async_test_db
    ):
        """`mode='all'` cancels pending rows, recreates cells, dispatches.
        celery_app is patched so no broker is contacted."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"], "parameters": {}}
            },
        )
        task = await _seed_task(async_test_db, project, admin)
        # A pre-existing pending row that "all" mode should cancel — supersede
        # revokes its deterministic fan-out (reconstructed from runs_requested).
        old_pending = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="pending",
        )
        old_pending.runs_requested = 2
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery, _as_user(admin):
            mock_celery.control.revoke = Mock()
            mock_celery.send_task = Mock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={
                    "mode": "all",
                    "parameters": {"temperature": 0.5, "max_tokens": 2000},
                    "model_configs": {"gpt-4": {"max_tokens": 4000}},
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "all"
        assert body["tasks_queued"] >= 1

        # Dispatch uses a deterministic task id (gen_id:run_idx) so stop/
        # supersede can revoke the fan-out without persisting every id.
        assert mock_celery.send_task.call_count >= 1
        for call in mock_celery.send_task.call_args_list:
            tid = call.kwargs["task_id"]
            # ``{generation_id}:{run_index}:{epoch}`` — initial fan-out at epoch 0.
            rest, _, epoch = tid.rpartition(":")
            gen_id, _, run_idx = rest.rpartition(":")
            assert gen_id and run_idx.isdigit() and epoch.isdigit()

        # Supersede revokes the OLD pending row's deterministic fan-out (2 ids
        # from runs_requested + dispatch_epoch=0) — not the bare generation id
        # (which matched no Celery task: a silent no-op).
        assert mock_celery.control.revoke.call_count >= 1
        revoke_args, revoke_kwargs = mock_celery.control.revoke.call_args
        revoked = revoke_args[0]
        assert isinstance(revoked, list)
        assert sum(1 for t in revoked if t.endswith(":0:0") or t.endswith(":1:0")) == 2
        assert revoke_kwargs.get("terminate") is True

    @pytest.mark.asyncio
    async def test_missing_mode_skips_completed(self, async_test_client, async_test_db):
        """`mode='missing'` only queues cells whose latest row is absent or
        failed. With one completed task and one failed task, only the failed
        one re-queues -> tasks_queued == 1."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={"selected_configuration": {"models": ["gpt-4"]}},
        )
        task1 = await _seed_task(async_test_db, project, admin, inner_id=1)
        task2 = await _seed_task(async_test_db, project, admin, inner_id=2)
        # task1: completed (skip), task2: failed (re-queue).
        await _seed_response_generation(
            async_test_db, project, task1, admin,
            model_id="gpt-4", structure_key=None, status="completed",
        )
        await _seed_response_generation(
            async_test_db, project, task2, admin,
            model_id="gpt-4", structure_key=None, status="failed",
        )
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery, _as_user(admin):
            mock_celery.send_task = Mock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "missing"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "missing"
        assert body["tasks_queued"] == 1

    @pytest.mark.asyncio
    async def test_with_specific_task_ids_and_model_ids(
        self, async_test_client, async_test_db
    ):
        """Explicit task_ids + model_ids + structure_keys -> one queued cell."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4", "claude-3"]},
                "prompt_structures": {"default": {"name": "Default"}},
            },
        )
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery, _as_user(admin):
            mock_celery.send_task = Mock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={
                    "mode": "all",
                    "model_ids": ["gpt-4"],
                    "task_ids": [tid],
                    "structure_keys": ["default"],
                },
            )
        assert resp.status_code == 200
        assert resp.json()["tasks_queued"] == 1

    @pytest.mark.asyncio
    async def test_with_structure_keys_from_config(self, async_test_client, async_test_db):
        """Structure keys default from prompt_structures (2 keys) -> 2 cells
        for one task and one model."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={
                "selected_configuration": {"models": ["gpt-4"]},
                "prompt_structures": {
                    "default": {"name": "Default"},
                    "detailed": {"name": "Detailed"},
                },
            },
        )
        await _seed_task(async_test_db, project, admin)
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery, _as_user(admin):
            mock_celery.send_task = Mock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 200
        assert resp.json()["tasks_queued"] == 2

    @pytest.mark.asyncio
    async def test_org_context_resolved_from_single_linked_org(
        self, async_test_client, async_test_db
    ):
        """When X-Organization-Context is absent/'private' and the project has
        exactly one linked org, that org_id is stamped onto the created rows."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        org = await _seed_org(async_test_db)
        project = await _seed_project(
            async_test_db, admin, org=org,
            generation_config={"selected_configuration": {"models": ["gpt-4"]}},
        )
        pid = project.id
        org_id = org.id
        await _seed_task(async_test_db, project, admin)
        await async_test_db.commit()

        with patch("routers.generation_task_list.celery_app") as mock_celery, _as_user(admin):
            mock_celery.send_task = Mock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{pid}/generate",
                json={"mode": "all"},
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 200
        assert resp.json()["tasks_queued"] == 1

        # The persisted ResponseGeneration carries the resolved org_id.
        async_test_db.expire_all()
        rows = (
            await async_test_db.execute(
                select(DBResponseGeneration).where(
                    DBResponseGeneration.project_id == pid,
                    DBResponseGeneration.status == "pending",
                )
            )
        ).scalars().all()
        assert rows
        assert all(r.organization_id == org_id for r in rows)

    @pytest.mark.asyncio
    async def test_fallback_cap_blocks_huge_project(self, async_test_client, async_test_db):
        """The no-task_ids fallback above GENERATION_FALLBACK_MAX_TASKS -> 400.
        The cap is patched low so we don't need to seed 10k tasks."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(
            async_test_db, admin,
            generation_config={"selected_configuration": {"models": ["gpt-4"]}},
        )
        await _seed_task(async_test_db, project, admin, inner_id=1)
        await _seed_task(async_test_db, project, admin, inner_id=2)
        await async_test_db.commit()

        with patch(
            "routers.generation_task_list.GENERATION_FALLBACK_MAX_TASKS", 1
        ), patch("routers.generation_task_list.celery_app"), _as_user(admin):
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project.id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 400
        assert "limit" in resp.json()["detail"].lower()


# ===========================================================================
# GET /api/generation-tasks/generation-result — converted (D)
# ===========================================================================


class TestGetGenerationResult:
    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": "no-such-task", "model_id": "gpt-4"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_generations_found(self, async_test_client, async_test_db):
        """Task exists but no generation rows -> empty results list."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tid
        assert body["model_id"] == "gpt-4"
        assert body["results"] == []

    @pytest.mark.asyncio
    async def test_completed_with_single_individual_generation(
        self, async_test_client, async_test_db
    ):
        """One completed parent with one individual generation -> generated_text."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        parent = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="completed",
            prompt_used="Translate the following text",
            parameters={"temperature": 0.0},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        )
        await _seed_individual_generation(
            async_test_db, parent, run_index=0, response_content="Hello world",
            usage_stats={"tokens": 100},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tid
        assert len(body["results"]) == 1
        assert body["results"][0]["status"] == "completed"
        assert body["results"][0]["result"]["generated_text"] == "Hello world"
        assert body["results"][0]["generation_time_seconds"] is not None

    @pytest.mark.asyncio
    async def test_completed_with_multiple_individual_generations(
        self, async_test_client, async_test_db
    ):
        """One completed parent with two individual generations -> `generations`
        list with two entries."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        parent = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="completed",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        )
        await _seed_individual_generation(
            async_test_db, parent, run_index=0, response_content="First response",
            usage_stats={"tokens": 50},
            created_at=datetime(2025, 6, 2, 0, 0, 0, tzinfo=timezone.utc),
        )
        await _seed_individual_generation(
            async_test_db, parent, run_index=1, response_content="Second response",
            usage_stats={"tokens": 60},
            created_at=datetime(2025, 6, 2, 1, 0, 0, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "generations" in body["results"][0]["result"]
        assert len(body["results"][0]["result"]["generations"]) == 2

    @pytest.mark.asyncio
    async def test_failed_generation(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="failed",
            error_message="API rate limit exceeded",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["status"] == "failed"
        assert body["results"][0]["error_message"] == "API rate limit exceeded"

    @pytest.mark.asyncio
    async def test_with_structure_key_filter(self, async_test_client, async_test_db):
        """structure_key query narrows to that structure's rows."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            result={"text": "test"},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4", "structure_key": "default"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["structure_key"] == "default"

    # ---- Issue #1372: Generation history tests ----

    @pytest.mark.asyncio
    async def test_default_deduplication_unchanged(self, async_test_client, async_test_db):
        """Two generations for the same structure_key: default mode returns only
        the most recent."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        # Older row first, then newer — handler dedups newest-first per structure.
        await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        )
        newer = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 7, 2, tzinfo=timezone.utc),
        )
        newer_id = newer.id
        await _seed_individual_generation(
            async_test_db, newer, run_index=0, response_content="New response",
            created_at=datetime(2025, 7, 2, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4", "include_history": "false"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["generation_id"] == newer_id

    @pytest.mark.asyncio
    async def test_include_history_returns_all(self, async_test_client, async_test_db):
        """include_history=True returns all generations across structures."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id

        g1 = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 7, 1, 1, tzinfo=timezone.utc),
        )
        g2 = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 6, 1, 1, tzinfo=timezone.utc),
        )
        g3 = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="custom", status="completed",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 7, 1, 1, tzinfo=timezone.utc),
        )
        id1, id2, id3 = g1.id, g2.id, g3.id
        await _seed_individual_generation(async_test_db, g1, run_index=0, response_content="Resp 1", usage_stats={})
        await _seed_individual_generation(async_test_db, g2, run_index=0, response_content="Resp 2", usage_stats={})
        await _seed_individual_generation(async_test_db, g3, run_index=0, response_content="Resp 3", usage_stats={})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4", "include_history": "true"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 3
        gen_ids = [r["generation_id"] for r in body["results"]]
        assert id1 in gen_ids
        assert id2 in gen_ids
        assert id3 in gen_ids

    @pytest.mark.asyncio
    async def test_include_history_with_structure_filter(self, async_test_client, async_test_db):
        """include_history=True combined with a structure_key filter returns all
        rows for that structure (completed + failed), newest first."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id

        g1 = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="completed",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 7, 1, 1, tzinfo=timezone.utc),
        )
        g2 = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key="default", status="failed",
            error_message="Rate limit",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        id1, id2 = g1.id, g2.id
        await _seed_individual_generation(async_test_db, g1, run_index=0, response_content="Result", usage_stats={})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={
                    "task_id": tid, "model_id": "gpt-4",
                    "structure_key": "default", "include_history": "true",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 2
        # Ordered newest-first within the structure.
        assert body["results"][0]["generation_id"] == id1
        assert body["results"][1]["generation_id"] == id2
        assert body["results"][1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_created_by_name_populated(self, async_test_client, async_test_db):
        """created_by and created_by_name are populated when the user exists."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        creator = await _seed_user(async_test_db, username_prefix="alice")
        creator.name = "Alice Smith"
        await async_test_db.flush()
        creator_id = creator.id
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        await _seed_response_generation(
            async_test_db, project, task, creator,
            model_id="gpt-4", structure_key=None, status="failed",
            error_message="Error",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4", "include_history": "false"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["created_by"] == creator_id
        assert body["results"][0]["created_by_name"] == "Alice Smith"

    @pytest.mark.asyncio
    async def test_created_by_name_missing_user(self, async_test_client, async_test_db):
        """created_by_name is None when the created_by id has no matching user
        row (e.g. a user that was deleted). created_by itself keeps the dangling
        id; only the name resolution comes back empty."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, admin)
        task = await _seed_task(async_test_db, project, admin)
        tid = task.id
        rg = await _seed_response_generation(
            async_test_db, project, task, admin,
            model_id="gpt-4", structure_key=None, status="failed",
            error_message="Error",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        # Point created_by at an id with no matching users row (no FK on this
        # column) so the batch name lookup finds nothing.
        rg.created_by = "deleted-user-99"
        await async_test_db.flush()
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result",
                params={"task_id": tid, "model_id": "gpt-4", "include_history": "false"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["created_by"] == "deleted-user-99"
        assert body["results"][0]["created_by_name"] is None
