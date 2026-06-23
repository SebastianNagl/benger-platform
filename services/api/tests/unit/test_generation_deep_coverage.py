"""
Branch-coverage tests for routers/generation.py.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so the
old direct-handler-invocation style with a Mock ``db.query(...).filter(...)``
chain no longer exercises anything — the handlers now ``await
db.execute(select(...))``. These tests therefore seed REAL rows via
``async_test_db`` and drive the HTTP surface through ``async_test_client``,
mirroring ``tests/integration/test_reports_branches.py``. ``require_user`` is
overridden per-test via the ``_as_user`` context manager (the sync auth
dependency can't see the async test transaction).

Endpoints covered (all ``/api/generation`` prefix):
  - GET    /status/{generation_id}     get_generation_status
  - POST   /{generation_id}/stop       stop_generation
  - POST   /{generation_id}/pause      pause_generation
  - POST   /{generation_id}/resume     resume_generation
  - POST   /{generation_id}/retry      retry_generation
  - DELETE /{generation_id}            delete_generation
  - GET    /parse-metrics              get_parse_metrics

Pause/resume/retry SUCCESS paths (migration 063):
  - The retry endpoint reads ``generation.retry_count or 0`` on a freshly-loaded
    row. Before migration 063 ``retry_count`` was not a mapped column, so this
    read AttributeError-ed -> the retry endpoint 500'd on real data. Migration
    063 adds ``paused_at`` / ``resumed_at`` / ``retry_count`` / ``dispatch_epoch``
    as real columns, so the SUCCESS paths now persist and are covered here
    (``test_pause_success``, ``test_resume_success_*``, ``test_retry_*``),
    asserting the persisted columns. Progress is DERIVED from the child rows, so
    there are no ``current_progress`` / ``completed_tasks`` columns.
  - resume/retry re-dispatch at a bumped ``dispatch_epoch`` so the new task ids
    are disjoint from the just-revoked prior-epoch ids (Celery would otherwise
    discard a re-dispatch reusing a revoked id) — see
    ``test_resume_redispatch_ids_disjoint_from_revoked``.
  - The stop handler revokes the deterministic fan-out task ids
    (``{gen_id}:{run_idx}:{epoch}``, reconstructed from ``runs_requested`` + the
    current ``dispatch_epoch``). The revoke runs inside a try/except, so stop
    STILL returns 200 + persists ``status='stopped'`` even if revoke raises.
    These tests assert the persisted state, not the revoke args (those are
    asserted in ``test_generation_coverage`` / ``test_generation_branches``).
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Generation as DBLLMResponse,
    ResponseGeneration as DBResponseGeneration,
    Organization,
    OrganizationMembership,
    User,
)
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


async def _make_user(db, *, is_superadmin=False, username_prefix="gen") -> User:
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


async def _make_org(db, *, name="Org") -> Organization:
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


async def _create_project(
    db,
    creator: User,
    *,
    title: str = "Gen Project",
    org: Organization = None,
    is_private: bool = False,
    assigned_by: User = None,
) -> Project:
    project_id = _uid()
    project = Project(
        id=project_id,
        title=title,
        description="Generation router test project",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()

    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project_id,
                organization_id=org.id,
                assigned_by=(assigned_by or creator).id,
            )
        )
        await db.flush()

    return project


async def _create_task(db, project: Project, creator: User, *, inner_id=1) -> Task:
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": "sample"},
        created_by=creator.id,
        inner_id=inner_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _create_generation(
    db,
    *,
    creator: User,
    project: Project = None,
    task: Task = None,
    status: str = "running",
    model_id: str = "gpt-4",
    error_message: str = None,
) -> DBResponseGeneration:
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id if project else None,
        task_id=task.id if task else None,
        model_id=model_id,
        status=status,
        responses_generated=0,
        runs_requested=1,
        runs_completed=0,
        runs_failed=0,
        error_message=error_message,
        created_by=creator.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(gen)
    await db.flush()
    return gen


async def _create_child(
    db,
    parent: DBResponseGeneration,
    *,
    run_index: int,
    model_id: str = "gpt-4",
    status: str = "completed",
    parse_status: str = "success",
    parse_error: str = None,
    parse_metadata: dict = None,
    task: Task = None,
) -> DBLLMResponse:
    child = DBLLMResponse(
        id=_uid(),
        generation_id=parent.id,
        task_id=task.id if task else None,
        model_id=model_id,
        case_data="{}",
        response_content="response",
        status=status,
        run_index=run_index,
        parse_status=parse_status,
        parse_error=parse_error,
        parse_metadata=parse_metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(child)
    await db.flush()
    return child


# ===========================================================================
# GET /api/generation/status/{generation_id}   get_generation_status
# ===========================================================================

@pytest.mark.asyncio
async def test_status_not_found(async_test_client, async_test_db):
    """Unknown generation id -> 404."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/generation/status/does-not-exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_found_with_error_message(async_test_client, async_test_db):
    """Generation found, accessible (superadmin), returns the stored
    error_message as the status message."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    gen = await _create_generation(
        async_test_db,
        creator=admin,
        project=project,
        task=task,
        status="completed",
        error_message="Done",
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == gen_id
    assert body["status"] == "completed"
    assert body["message"] == "Done"


@pytest.mark.asyncio
async def test_status_found_default_message(async_test_client, async_test_db):
    """error_message is NULL -> the default 'Generation status' message."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    gen = await _create_generation(
        async_test_db,
        creator=admin,
        project=project,
        task=task,
        status="running",
        error_message=None,
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Generation status"


@pytest.mark.asyncio
async def test_status_task_none_skips_access_check(async_test_client, async_test_db):
    """generation.task_id resolves to no Task -> the access check is skipped
    (the ``if task and ...`` short-circuits) and the status is returned even
    for a non-superadmin who could not otherwise see the project."""
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner, is_private=True)
    # No Task seeded -> generation.task_id points at nothing.
    gen = await _create_generation(
        async_test_db,
        creator=owner,
        project=project,
        task=None,
        status="completed",
        error_message="ok",
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_status_access_denied(async_test_client, async_test_db):
    """Generation belongs to a private project the caller can't see (task
    present so the access check runs) -> 403."""
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner, is_private=True)
    task = await _create_task(async_test_db, project, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, task=task, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 403
    assert "access" in resp.json()["detail"].lower()


# ===========================================================================
# POST /api/generation/{generation_id}/stop   stop_generation
# ===========================================================================

@pytest.mark.asyncio
async def test_stop_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post("/api/generation/missing/stop")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stop_forbidden_non_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 403
    assert "only stop your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stop_invalid_status(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 400
    assert "cannot stop" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stop_owner_success_persists_stopped(async_test_client, async_test_db):
    """Owner stops a running generation. Stop revokes the deterministic fan-out
    ids (``{gen_id}:{run_idx}:{epoch}`` from runs_requested + dispatch_epoch),
    wrapped in a try/except so stop STILL returns 200 and persists
    status='stopped' even if revoke raises. This test asserts the persisted
    state, not the revoke args."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    owner_username = owner.username
    await async_test_db.commit()

    with _as_user(owner), patch("routers.generation.celery_app"):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "stopped"
    assert refreshed.completed_at is not None
    assert refreshed.error_message == f"Stopped by user {owner_username}"


@pytest.mark.asyncio
async def test_stop_superadmin_can_stop_others(async_test_client, async_test_db):
    """A superadmin may stop someone else's generation (owner-check bypassed)."""
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="pending"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin), patch("routers.generation.celery_app"):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "stopped"


# ===========================================================================
# POST /api/generation/{generation_id}/pause   pause_generation
# (guards + success path; migration 063 mapped the lifecycle columns)
# ===========================================================================

@pytest.mark.asyncio
async def test_pause_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post("/api/generation/missing/pause")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pause_forbidden_non_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 403
    assert "only pause your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_invalid_status(async_test_client, async_test_db):
    """Status != 'running' -> 400, returned BEFORE the missing-column write."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 400
    assert "cannot pause" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_success(async_test_client, async_test_db):
    """Owner pauses a running generation. Migration 063 added paused_at, so the
    write now PERSISTS instead of AttributeError-ing. Redis is mocked to None so
    the redis-store branch is skipped; the column write + status transition +
    the Celery revoke (pause must actually stop the work) are what we assert."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen.runs_requested = 2
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch(
        "routers.generation.get_redis_client", return_value=None
    ), patch("routers.generation.celery_app") as mock_celery:
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"

    # Pause revokes the fan-out (from runs_requested + the current
    # dispatch_epoch=0) with terminate=True so the worker stops — otherwise pause
    # is a no-op the finalizer overwrites.
    mock_celery.control.revoke.assert_called_once_with(
        [f"{gen_id}:0:0", f"{gen_id}:1:0"], terminate=True
    )

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "paused"
    # The NOW-PERSISTED column (migration 063): paused_at is stamped.
    assert refreshed.paused_at is not None


@pytest.mark.asyncio
async def test_pause_redis_none(async_test_client, async_test_db):
    """Pause persists status='paused' + paused_at and revokes (no Redis snapshot
    — resume recomputes what's left from the child rows)."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch(
        "routers.generation.get_redis_client", return_value=None
    ), patch("routers.generation.celery_app"):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "paused"
    assert refreshed.paused_at is not None


@pytest.mark.asyncio
async def test_superadmin_can_pause_others(async_test_client, async_test_db):
    """A superadmin may pause someone else's running generation (owner-check
    bypassed); paused_at is persisted."""
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin), patch(
        "routers.generation.get_redis_client", return_value=None
    ):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "paused"
    assert refreshed.paused_at is not None


# ===========================================================================
# POST /api/generation/{generation_id}/resume   resume_generation
# ===========================================================================

@pytest.mark.asyncio
async def test_resume_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post("/api/generation/missing/resume")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resume_forbidden_non_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 403
    assert "only resume your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_invalid_status(async_test_client, async_test_db):
    """Status != 'paused' -> 400, returned BEFORE the missing-column write."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 400
    assert "cannot resume" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_success_redispatches_missing_trial(async_test_client, async_test_db):
    """Owner resumes a paused single-run generation with no completed child:
    the one missing trial (run_index 0) is re-dispatched via the deterministic
    fan-out (tasks.generate_response, task_id {gen}:0), status->running, and
    resumed_at persists. There is no per-generation Celery id — the fan-out ids
    are reconstructed from runs_requested by the revoke paths."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen.runs_requested = 1
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    # Exactly one fan-out trial dispatched (run_index 0) with the deterministic
    # id at the bumped dispatch_epoch=1 (resume increments 0 -> 1).
    mock_celery.send_task.assert_called_once()
    call = mock_celery.send_task.call_args
    assert call.args[0] == "tasks.generate_response"
    assert call.kwargs["task_id"] == f"{gen_id}:0:1"
    assert call.kwargs["queue"] == "generation"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    # The NOW-PERSISTED column (migration 063): resumed_at is stamped.
    assert refreshed.resumed_at is not None


@pytest.mark.asyncio
async def test_resume_redispatch_ids_disjoint_from_revoked(
    async_test_client, async_test_db
):
    """C2 regression: resume must re-dispatch at a NEW dispatch_epoch so the
    re-dispatched task ids are DISJOINT from the ids it revokes. If they reused
    the prior epoch's ids, Celery's in-memory revoked set (every worker remembers
    a revoked id ~3h) would discard the re-dispatch and resume would regenerate
    nothing. Assert: the prior-epoch (0) ids are revoked, the new-epoch (1) ids
    are dispatched, the two sets don't intersect, and dispatch_epoch persists 1."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen.runs_requested = 2
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 200, resp.text

    # Prior epoch (0) revoked; new epoch (1) dispatched — disjoint sets.
    mock_celery.control.revoke.assert_called_once()
    revoked = set(mock_celery.control.revoke.call_args.args[0])
    dispatched = {c.kwargs["task_id"] for c in mock_celery.send_task.call_args_list}
    assert revoked == {f"{gen_id}:0:0", f"{gen_id}:1:0"}
    assert dispatched == {f"{gen_id}:0:1", f"{gen_id}:1:1"}
    assert revoked.isdisjoint(dispatched), (
        "re-dispatch must NOT reuse a just-revoked id (Celery would discard it)"
    )

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.dispatch_epoch == 1


@pytest.mark.asyncio
async def test_stop_after_resume_revokes_the_bumped_epoch(
    async_test_client, async_test_db
):
    """After a resume bumps dispatch_epoch 0→1, a subsequent stop must revoke the
    CURRENT (bumped) epoch's ids `{gen}:N:1` — NOT the original epoch 0. This
    guards that stop/pause read the LIVE dispatch_epoch off the row rather than
    assuming 0 (the `:N:0` stop/pause tests on fresh gens can't catch a regression
    here because the default epoch is already 0)."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen.runs_requested = 2
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        # Resume re-dispatches at epoch 1 and persists dispatch_epoch=1.
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
        assert resp.status_code == 200, resp.text
        # Now stop the (running) gen — it must revoke the BUMPED epoch.
        mock_celery.reset_mock()
        resp2 = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp2.status_code == 200, resp2.text

    mock_celery.control.revoke.assert_called_once()
    revoked = set(mock_celery.control.revoke.call_args.args[0])
    assert revoked == {f"{gen_id}:0:1", f"{gen_id}:1:1"}, (
        "stop must revoke the current (bumped) epoch, not epoch 0"
    )


@pytest.mark.asyncio
async def test_resume_success_no_redis(async_test_client, async_test_db):
    """Resume with no Redis client -> saved_progress stays None, but the resume
    still succeeds, persists resumed_at, and re-dispatches."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    mock_celery.send_task.return_value = MagicMock(id="new-celery-id")

    with _as_user(owner), patch(
        "routers.generation.get_redis_client", return_value=None
    ), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    mock_celery.send_task.assert_called_once()

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    assert refreshed.resumed_at is not None


@pytest.mark.asyncio
async def test_superadmin_can_resume_others(async_test_client, async_test_db):
    """A superadmin may resume someone else's paused generation; resumed_at is
    persisted."""
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="paused"
    )
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    mock_celery.send_task.return_value = MagicMock(id="new-celery-id")

    with _as_user(admin), patch(
        "routers.generation.get_redis_client", return_value=None
    ), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    assert refreshed.resumed_at is not None


# ===========================================================================
# POST /api/generation/{generation_id}/retry   retry_generation
# ===========================================================================

@pytest.mark.asyncio
async def test_retry_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post("/api/generation/missing/retry")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_forbidden_non_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 403
    assert "only retry your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_invalid_status(async_test_client, async_test_db):
    """Status not in {failed, stopped} -> 400, before any column write."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 400
    assert "cannot retry" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_success(async_test_client, async_test_db):
    """Owner retries a FAILED generation. This is THE bug fixed by migration
    063: retry reads ``generation.retry_count or 0`` on a freshly-loaded row,
    which used to AttributeError -> 500. With retry_count now a real column it
    increments and persists. celery_app is patched so re-dispatch is a no-op."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    # Seed a prior retry_count so we can assert the increment (2 -> 3).
    gen.retry_count = 2
    await async_test_db.flush()
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Single-run failed gen with no completed child -> the one missing trial
    # (run_index 0) re-dispatches via the deterministic fan-out; status running.
    assert body["status"] == "running"
    assert body["retry_count"] == 3
    mock_celery.send_task.assert_called_once()
    call = mock_celery.send_task.call_args
    assert call.args[0] == "tasks.generate_response"
    # Re-dispatch at the bumped dispatch_epoch=1 (retry increments 0 -> 1).
    assert call.kwargs["task_id"] == f"{gen_id}:0:1"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    assert refreshed.error_message is None
    assert refreshed.completed_at is None
    # The NOW-PERSISTED column (migration 063): retry_count incremented to 3.
    assert refreshed.retry_count == 3


@pytest.mark.asyncio
async def test_retry_stopped_generation(async_test_client, async_test_db):
    """'stopped' is the other retryable status; retry_count goes 0 -> 1."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="stopped"
    )
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    mock_celery.send_task.return_value = MagicMock(id="new-celery-id")

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    # server_default 0 + one retry == 1.
    assert refreshed.retry_count == 1


@pytest.mark.asyncio
async def test_retry_resets_multi_run_counters(async_test_client, async_test_db):
    """Multi-run regression: retry reconciles runs_completed/runs_failed to the
    actual completed children (here: none seeded -> 0/0) so the worker's status
    fan-in computes against reality instead of inheriting last run's numbers.
    runs_requested (the original trigger snapshot) must be left untouched, and
    retry_count increments. With 0 completed and runs_requested=3, all three
    trials re-dispatch."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    # Last attempt's stale counters (1 done, 2 failed) but no completed children.
    gen.runs_requested = 3
    gen.runs_completed = 1
    gen.runs_failed = 2
    await async_test_db.flush()
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text

    # All 3 run_indices re-dispatch (none have a child) at the bumped epoch=1.
    assert mock_celery.send_task.call_count == 3
    redispatched_task_ids = {
        c.kwargs["task_id"] for c in mock_celery.send_task.call_args_list
    }
    assert redispatched_task_ids == {f"{gen_id}:0:1", f"{gen_id}:1:1", f"{gen_id}:2:1"}

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    # Counters reconciled to the (zero) completed children.
    assert refreshed.runs_completed == 0
    assert refreshed.runs_failed == 0
    # runs_requested is the snapshot of the original trigger — NOT touched.
    assert refreshed.runs_requested == 3
    assert refreshed.status == "running"
    assert refreshed.retry_count == 1


@pytest.mark.asyncio
async def test_retry_multirun_redispatches_only_missing_trials(
    async_test_client, async_test_db
):
    """THE multi-run rework: a 4-run generation with trials 0 & 2 completed and
    trial 1 parse-failed re-dispatches ONLY the truly-missing run_index (3) at the
    bumped epoch — not just run_index 0 (the old single-umbrella bug), and not any
    run_index that already produced a child.

    "Missing" == NO child row. A parse-failed trial DID produce a child, so it is
    present — exactly how the worker's ``COUNT(DISTINCT run_index)`` counts it. The
    two sides agree (no completed/parse_failed state-machine split), the child is
    NOT deleted, and its parse-failure provenance + any TaskEvaluation link
    survive the retry."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    task = await _create_task(async_test_db, project, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, task=task, status="failed"
    )
    gen.runs_requested = 4
    gen.runs_completed = 2
    gen.runs_failed = 1
    await async_test_db.flush()
    # Trials 0 & 2 succeeded; trial 1 left a parse-failed child; trial 3 never ran.
    await _create_child(async_test_db, gen, run_index=0, status="completed", task=task)
    await _create_child(async_test_db, gen, run_index=2, status="completed", task=task)
    parse_failed_child = await _create_child(
        async_test_db, gen, run_index=1, status="parse_failed", task=task
    )
    parse_failed_child_id = parse_failed_child.id
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text

    # Only the truly-missing run_index (3, no child) re-dispatches at epoch=1 —
    # not 0/2 (completed) and NOT 1 (parse-failed counts as present).
    dispatched_ids = {
        c.kwargs["task_id"] for c in mock_celery.send_task.call_args_list
    }
    assert dispatched_ids == {f"{gen_id}:3:1"}
    for c in mock_celery.send_task.call_args_list:
        assert c.args[0] == "tasks.generate_response"
        assert c.kwargs["args"][5] is True  # force_rerun (known-missing)
        assert c.kwargs["queue"] == "generation"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    # Counters reconciled to the 3 present children (0, 1, 2) — matching the
    # worker's COUNT(DISTINCT run_index). Only run_index 3 is missing.
    assert refreshed.runs_completed == 3
    assert refreshed.runs_failed == 0
    assert refreshed.runs_requested == 4
    assert refreshed.status == "running"

    # NO child is deleted — the parse-failed child (and its provenance / eval
    # links) survives the retry. The re-dispatched run_index 3 has no prior child
    # to collide with on uq(generation_id, run_index).
    remaining = (
        await async_test_db.execute(
            select(DBLLMResponse.run_index, DBLLMResponse.status).where(
                DBLLMResponse.generation_id == gen_id
            )
        )
    ).all()
    statuses = {ri: st for ri, st in remaining}
    assert statuses == {0: "completed", 1: "parse_failed", 2: "completed"}
    assert parse_failed_child_id in {  # the parse-failed child row is preserved
        r.id
        for r in (
            await async_test_db.execute(
                select(DBLLMResponse).where(DBLLMResponse.generation_id == gen_id)
            )
        ).scalars().all()
    }


@pytest.mark.asyncio
async def test_superadmin_can_retry_others(async_test_client, async_test_db):
    """A superadmin may retry someone else's failed generation; retry_count is
    persisted."""
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    mock_celery.send_task.return_value = MagicMock(id="new-celery-id")

    with _as_user(admin), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "running"
    assert refreshed.retry_count == 1


@pytest.mark.asyncio
async def test_retry_all_present_completes_without_dispatch(
    async_test_client, async_test_db
):
    """When every run_index already has a child, retry has nothing to
    re-dispatch: _prepare_missing_trials returns [], so the endpoint flips the
    gen to 'completed' and never calls send_task (guards generation.py:594-597)."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    task = await _create_task(async_test_db, project, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, task=task, status="failed"
    )
    gen.runs_requested = 2
    await async_test_db.flush()
    # Both run_indices already produced a child.
    await _create_child(async_test_db, gen, run_index=0, status="completed", task=task)
    await _create_child(async_test_db, gen, run_index=1, status="completed", task=task)
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    mock_celery.send_task.assert_not_called()

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "completed"
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_retry_dispatch_failure_marks_failed(
    async_test_client, async_test_db
):
    """If send_task raises mid-dispatch, _commit_and_dispatch flips the gen back
    to 'failed' (retry-eligible) and re-raises → a partial dispatch must not
    strand it in 'running' with no recovery path (guards generation.py:452-462)."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()
    mock_celery.send_task.side_effect = RuntimeError("broker down")

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 500

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    # Flipped back to failed (not stranded in running), completed_at stamped,
    # error_message records the dispatch failure.
    assert refreshed.status == "failed"
    assert refreshed.completed_at is not None
    assert "Dispatch failed" in (refreshed.error_message or "")


# ===========================================================================
# DELETE /api/generation/{generation_id}   delete_generation
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete("/api/generation/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_forbidden_non_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 403
    assert "only delete your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_running_generation_blocked(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 400
    assert "cannot delete running" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_success_removes_children(async_test_client, async_test_db):
    """Owner deletes a completed generation; its child Generation rows are
    bulk-deleted and the parent row is removed. ``deleted_responses`` reflects
    the child row count."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    task = await _create_task(async_test_db, project, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, task=task, status="completed"
    )
    await _create_child(async_test_db, gen, run_index=0, task=task)
    await _create_child(async_test_db, gen, run_index=1, task=task)
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch("routers.generation.celery_app"):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_responses"] == 2

    async_test_db.expire_all()
    parent = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert parent is None
    children = (
        await async_test_db.execute(
            select(DBLLMResponse).where(DBLLMResponse.generation_id == gen_id)
        )
    ).scalars().all()
    assert children == []


@pytest.mark.asyncio
async def test_delete_superadmin_can_delete_others(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status="failed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin), patch("routers.generation.celery_app"):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_responses"] == 0


# ===========================================================================
# GET /api/generation/parse-metrics   get_parse_metrics
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_metrics_project_access_denied(async_test_client, async_test_db):
    """project_id given but the caller can't access that private project -> 403."""
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner, is_private=True)
    project_id = project.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            params={"project_id": project_id},
        )
    assert resp.status_code == 403
    assert "access to this project" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_parse_metrics_project_scoped_empty(async_test_client, async_test_db):
    """Accessible project but no child Generation rows -> total 0 early-return
    shape (all zero metrics, empty errors)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    project_id = project.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            params={"project_id": project_id},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 0
    assert body["parse_success_rate"] == 0
    assert body["common_parse_errors"] == []


@pytest.mark.asyncio
async def test_parse_metrics_with_data_aggregation(async_test_client, async_test_db):
    """Populated child rows: success/failed counts, success rate, avg retries
    until success, and the grouped common_parse_errors all compute."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, task=task, status="completed"
    )
    # 2 successes (retry_count 2 and 1->default), 1 failed, 1 validation_error.
    await _create_child(
        async_test_db, parent, run_index=0, parse_status="success",
        parse_metadata={"retry_count": 2}, task=task,
    )
    await _create_child(
        async_test_db, parent, run_index=1, parse_status="success",
        parse_metadata=None, task=task,
    )
    await _create_child(
        async_test_db, parent, run_index=2, parse_status="failed",
        parse_error="JSON decode error", task=task,
    )
    await _create_child(
        async_test_db, parent, run_index=3, parse_status="validation_error",
        parse_error="Schema mismatch", status="parse_failed_max_retries", task=task,
    )
    project_id = project.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            params={"project_id": project_id},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 4
    assert body["parse_success"] == 2
    assert body["parse_failed"] == 1
    assert body["parse_validation_error"] == 1
    assert body["parse_failed_max_retries"] == 1
    assert body["parse_success_rate"] == 0.5
    # retry_count 2 + default(1 for the None metadata) = 3 over 2 success rows.
    assert body["avg_retries_until_success"] == 1.5
    errors = {e["error"]: e["count"] for e in body["common_parse_errors"]}
    assert errors["JSON decode error"] == 1
    assert errors["Schema mismatch"] == 1


@pytest.mark.asyncio
async def test_parse_metrics_model_id_filter(async_test_client, async_test_db):
    """The model_id filter restricts aggregation to matching child rows only."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, task=task, status="completed"
    )
    await _create_child(
        async_test_db, parent, run_index=0, model_id="gpt-4",
        parse_status="success", parse_metadata={"retry_count": 1}, task=task,
    )
    await _create_child(
        async_test_db, parent, run_index=1, model_id="claude-3",
        parse_status="failed", parse_error="other-model error", task=task,
    )
    project_id = project.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            params={"project_id": project_id, "model_id": "gpt-4"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # Only the gpt-4 success row is counted; the claude-3 failure is filtered out.
    assert body["total_generations"] == 1
    assert body["parse_success"] == 1
    assert body["parse_failed"] == 0
    assert body["common_parse_errors"] == []


@pytest.mark.asyncio
async def test_parse_metrics_no_project_superadmin_unscoped(async_test_client, async_test_db):
    """No project_id + superadmin: get_accessible_project_ids_async returns None
    (the include_all_private branch), so the query is unscoped and aggregates
    across all child rows. We seed one success row and read it back."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, task=task, status="completed"
    )
    await _create_child(
        async_test_db, parent, run_index=0, parse_status="success",
        parse_metadata={"retry_count": 1}, task=task,
    )
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get("/api/generation/parse-metrics")
    assert resp.status_code == 200
    body = resp.json()
    # Unscoped superadmin view counts at least our seeded success row.
    assert body["total_generations"] >= 1
    assert body["parse_success"] >= 1


@pytest.mark.asyncio
async def test_parse_metrics_no_project_org_scoped(async_test_client, async_test_db):
    """No project_id + non-superadmin org member with an org context:
    get_accessible_project_ids_async returns the org's project ids (non-empty),
    so the aggregation is scoped to that id set via the IN(...) branch."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    member = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, member, org)
    project = await _create_project(async_test_db, admin, org=org)
    task = await _create_task(async_test_db, project, admin)
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, task=task, status="completed"
    )
    await _create_child(
        async_test_db, parent, run_index=0, parse_status="success",
        parse_metadata={"retry_count": 1}, task=task,
    )
    org_id = org.id
    await async_test_db.commit()

    with _as_user(member):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            headers={"X-Organization-Context": org_id},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 1
    assert body["parse_success"] == 1


@pytest.mark.asyncio
async def test_parse_metrics_no_project_empty_accessible(async_test_client, async_test_db):
    """No project_id + a non-superadmin with NO accessible projects in the
    'private' context (created none) -> accessible_ids is empty -> the early
    zero-metrics return."""
    loner = await _make_user(async_test_db)
    await async_test_db.commit()

    with _as_user(loner):
        resp = await async_test_client.get(
            "/api/generation/parse-metrics",
            headers={"X-Organization-Context": "private"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 0
    assert body["parse_success_rate"] == 0
    assert body["common_parse_errors"] == []


# ===========================================================================
# Auth gate
# ===========================================================================

@pytest.mark.asyncio
async def test_generation_endpoints_require_auth(async_test_client):
    """No credentials -> 401 on a representative endpoint (require_user gate)."""
    resp = await async_test_client.get("/api/generation/parse-metrics")
    assert resp.status_code == 401
