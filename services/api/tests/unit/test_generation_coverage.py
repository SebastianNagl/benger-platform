"""
Async-DB tests for routers/generation.py (status / stop / pause / resume /
retry / delete / parse-metrics).

The router was migrated to the async DB lane (``Depends(get_async_db)`` +
``await db.execute(select(...))``), so the old ``app.dependency_overrides[get_db]
= <Mock with .query>`` style no longer touches the handler at all. These tests
seed REAL rows via ``async_test_db`` and drive the HTTP surface through
``async_test_client`` (pattern copied from
``tests/integration/test_reports_branches.py``). ``require_user`` is overridden
per-test via the ``_as_user`` context manager to return an auth User matching a
seeded DB user (the sync auth dependency can't see the async test transaction).

Branch coverage preserved per endpoint:
  - GET    /api/generation/status/{id}      404 / 200-success / 403-access-denied
  - POST   /api/generation/{id}/stop        404 / 403-owner / 400-status /
                                            200-persisted-stopped /
                                            200-pending / celery-revoke-failure
  - POST   /api/generation/{id}/pause       404 / 403-owner / 400-status (guards)
  - POST   /api/generation/{id}/resume      404 / 403-owner / 400-status (guards)
  - POST   /api/generation/{id}/retry       404 / 403-owner / 400-status (guards)
  - DELETE /api/generation/{id}             404 / 403-owner / 400-running /
                                            200-success-with-children /
                                            200-superadmin-deletes-others
  - GET    /api/generation/parse-metrics    403-access / empty-aggregation /
                                            no-project-empty-accessible /
                                            populated-aggregation /
                                            model_id-filter / top-N errors /
                                            avg_retries

The pause/resume/retry SUCCESS paths are exercised elsewhere
(``test_generation_deep_coverage`` / ``test_generation_branches``); here only the
guard branches (404 / owner-403 / status-400) and the stop path are tested.
Celery is patched out on the stop tests so no broker control call fires.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Generation as DBLLMResponse,
    Organization,
    OrganizationMembership,
    ResponseGeneration as DBResponseGeneration,
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
    assigned_by: User = None,
) -> Project:
    project_id = _uid()
    project = Project(
        id=project_id,
        title=title,
        description="Generation test project",
        created_by=creator.id,
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


async def _create_task(db, project: Project, creator: User, *, inner_id: int = 1) -> Task:
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
    status_val: str = "running",
    model_id: str = "gpt-4",
    runs_requested: int = 1,
) -> DBResponseGeneration:
    # Every dispatch path fans out N ``tasks.generate_response`` jobs with
    # deterministic ids ``{gen_id}:{run_idx}`` that stop/pause/supersede
    # reconstruct from ``runs_requested`` — there is no per-generation Celery id.
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=(project.id if project else None),
        task_id=(task.id if task else None),
        model_id=model_id,
        status=status_val,
        created_by=creator.id,
        runs_requested=runs_requested,
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
    parse_status: str = "success",
    status_val: str = "completed",
    parse_error: str = None,
    parse_metadata: dict = None,
    task_id: str = None,
) -> DBLLMResponse:
    """Seed one child Generation row. parse-metrics aggregates over these
    joined to the parent ResponseGeneration.project_id."""
    child = DBLLMResponse(
        id=_uid(),
        generation_id=parent.id,
        task_id=task_id,
        model_id=model_id,
        case_data="case",
        response_content="response",
        status=status_val,
        run_index=run_index,
        parse_status=parse_status,
        parse_error=parse_error,
        parse_metadata=parse_metadata,
    )
    db.add(child)
    await db.flush()
    return child


# ===========================================================================
# GET /api/generation/status/{generation_id}
# ===========================================================================

@pytest.mark.asyncio
async def test_status_not_found(async_test_client, async_test_db):
    """Unknown generation id -> 404."""
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        resp = await async_test_client.get("/api/generation/status/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_success(async_test_client, async_test_db):
    """Superadmin (always project-accessible) gets the status payload."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    task = await _create_task(async_test_db, project, admin)
    gen = await _create_generation(
        async_test_db, creator=admin, project=project, task=task, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == gen_id
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_status_access_denied(async_test_client, async_test_db):
    """A non-superadmin with no access to the generation's project -> 403."""
    owner = await _make_user(async_test_db)
    outsider = await _make_user(async_test_db)
    # Owner's private project; outsider is in no org and is not the creator.
    project = await _create_project(async_test_db, owner)
    task = await _create_task(async_test_db, project, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, task=task, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(outsider):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 403


# ===========================================================================
# POST /api/generation/{generation_id}/stop
# ===========================================================================

@pytest.mark.asyncio
async def test_stop_not_found(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post("/api/generation/missing/stop")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stop_not_owner(async_test_client, async_test_db):
    """A non-superadmin who does not own the generation -> 403 'your own'."""
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stop_wrong_status(async_test_client, async_test_db):
    """Stopping a completed generation -> 400 status guard."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="completed")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stop_success_persists_state(async_test_client, async_test_db):
    """Stopping a running generation persists status='stopped' + completed_at +
    error_message, and revokes the deterministic fan-out task ids (so a
    never-resumed generation actually stops burning API budget)."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(
        async_test_db, creator=owner, status_val="running", runs_requested=3
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app") as mock_celery:
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    # The fix: stop reconstructs the fan-out ids from runs_requested + the
    # current dispatch_epoch (0 here) and revokes them with terminate=True — NOT
    # a no-op revoke(None).
    mock_celery.control.revoke.assert_called_once()
    revoked_ids, kwargs = mock_celery.control.revoke.call_args
    assert revoked_ids[0] == [f"{gen_id}:0:0", f"{gen_id}:1:0", f"{gen_id}:2:0"]
    assert kwargs.get("terminate") is True

    # Persisted state on a fresh read.
    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "stopped"
    assert refreshed.completed_at is not None
    assert refreshed.error_message is not None
    assert "stopped by user" in refreshed.error_message.lower()


@pytest.mark.asyncio
async def test_stop_success_pending(async_test_client, async_test_db):
    """Pending generations are stoppable too (the other branch of the status
    guard)."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="pending")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_stop_celery_revoke_fails_gracefully(async_test_client, async_test_db):
    """A failing Celery revoke is swallowed; the stop still succeeds (200) and
    the DB state is persisted."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app") as mock_celery:
            mock_celery.control.revoke.side_effect = Exception("celery down")
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed.status == "stopped"


# ===========================================================================
# POST /api/generation/{generation_id}/pause  (guard branches only)
# ===========================================================================

@pytest.mark.asyncio
async def test_pause_not_found(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        resp = await async_test_client.post("/api/generation/missing/pause")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pause_not_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_wrong_status(async_test_client, async_test_db):
    """Only running generations can be paused; a pending one -> 400."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="pending")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 400


# ===========================================================================
# POST /api/generation/{generation_id}/resume  (guard branches only)
# ===========================================================================

@pytest.mark.asyncio
async def test_resume_not_found(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post("/api/generation/missing/resume")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resume_not_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="paused")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_wrong_status(async_test_client, async_test_db):
    """Only paused generations can be resumed; a running one -> 400."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 400


# ===========================================================================
# POST /api/generation/{generation_id}/retry  (guard branches only)
# ===========================================================================

@pytest.mark.asyncio
async def test_retry_not_found(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post("/api/generation/missing/retry")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_not_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="failed")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_wrong_status(async_test_client, async_test_db):
    """Only failed/stopped generations can be retried; a running one -> 400."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        with patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 400


# ===========================================================================
# DELETE /api/generation/{generation_id}
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_not_found(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    await async_test_db.commit()
    with _as_user(user):
        resp = await async_test_client.delete("/api/generation/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_owner(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    other = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="completed")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(other):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_cannot_delete_running(async_test_client, async_test_db):
    """Running generations cannot be deleted -> 400."""
    owner = await _make_user(async_test_db)
    gen = await _create_generation(async_test_db, creator=owner, status_val="running")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_success_with_children(async_test_client, async_test_db):
    """Deleting a completed generation removes its child Generation rows and
    reports the deleted count, and the parent row is gone."""
    owner = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    gen = await _create_generation(
        async_test_db, creator=owner, project=project, status_val="completed"
    )
    gen_id = gen.id
    # Two child rows (distinct run_index per generation_id).
    await _create_child(async_test_db, gen, run_index=0)
    await _create_child(async_test_db, gen, run_index=1)
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_responses"] == 2

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed is None
    remaining_children = (
        await async_test_db.execute(
            select(DBLLMResponse).where(DBLLMResponse.generation_id == gen_id)
        )
    ).scalars().all()
    assert remaining_children == []


@pytest.mark.asyncio
async def test_delete_superadmin_can_delete_others(async_test_client, async_test_db):
    """A superadmin can delete a generation owned by someone else."""
    owner = await _make_user(async_test_db)
    admin = await _make_user(async_test_db, is_superadmin=True)
    gen = await _create_generation(async_test_db, creator=owner, status_val="failed")
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_responses"] == 0

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()
    assert refreshed is None


# ===========================================================================
# GET /api/generation/parse-metrics
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_metrics_project_access_denied(async_test_client, async_test_db):
    """A non-superadmin with no access to project_id -> 403."""
    owner = await _make_user(async_test_db)
    outsider = await _make_user(async_test_db)
    project = await _create_project(async_test_db, owner)
    project_id = project.id
    await async_test_db.commit()

    with _as_user(outsider):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_parse_metrics_empty_results(async_test_client, async_test_db):
    """Superadmin + a project_id with no child Generation rows -> all-zero
    aggregation shape (total==0 early return)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    project_id = project.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 0
    assert body["parse_success_rate"] == 0
    assert body["common_parse_errors"] == []


@pytest.mark.asyncio
async def test_parse_metrics_no_project_empty_accessible(async_test_client, async_test_db):
    """No project_id + a non-superadmin whose accessible-project set is empty ->
    the empty early-return branch (200, all zeros)."""
    user = await _make_user(async_test_db)  # not superadmin, no projects, no orgs
    await async_test_db.commit()

    with _as_user(user):
        resp = await async_test_client.get("/api/generation/parse-metrics")
    assert resp.status_code == 200
    assert resp.json()["total_generations"] == 0


@pytest.mark.asyncio
async def test_parse_metrics_aggregation_counts(async_test_client, async_test_db):
    """Populated aggregation: success/failed/validation_error/max_retries counts,
    success rate, avg_retries (from parse_metadata.retry_count), and top-N
    common_parse_errors ordering."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    project_id = project.id
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, status_val="completed"
    )

    # 3 successes (retry_counts 1, 3, 5 -> avg 3.0), 2 failed (same error
    # "boom" x2), 1 validation_error ("schema"), 1 parse_failed_max_retries
    # (status column, parse_status success so it doesn't double-count as failed).
    await _create_child(
        async_test_db, parent, run_index=0, parse_status="success",
        parse_metadata={"retry_count": 1},
    )
    await _create_child(
        async_test_db, parent, run_index=1, parse_status="success",
        parse_metadata={"retry_count": 3},
    )
    await _create_child(
        async_test_db, parent, run_index=2, parse_status="success",
        parse_metadata={"retry_count": 5},
    )
    await _create_child(
        async_test_db, parent, run_index=3, parse_status="failed", parse_error="boom",
    )
    await _create_child(
        async_test_db, parent, run_index=4, parse_status="failed", parse_error="boom",
    )
    await _create_child(
        async_test_db, parent, run_index=5, parse_status="validation_error",
        parse_error="schema",
    )
    await _create_child(
        async_test_db, parent, run_index=6, parse_status="success",
        status_val="parse_failed_max_retries", parse_metadata={"retry_count": 1},
    )
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 7
    assert body["parse_success"] == 4
    assert body["parse_failed"] == 2
    assert body["parse_validation_error"] == 1
    assert body["parse_failed_max_retries"] == 1
    assert body["parse_success_rate"] == pytest.approx(4 / 7)
    # avg over the 4 success rows' retry_count (1, 3, 5, 1) = 10 / 4 = 2.5
    assert body["avg_retries_until_success"] == pytest.approx(2.5)
    # Top error is "boom" (count 2), then "schema" (count 1).
    errors = body["common_parse_errors"]
    assert errors[0] == {"error": "boom", "count": 2}
    error_map = {e["error"]: e["count"] for e in errors}
    assert error_map.get("schema") == 1


@pytest.mark.asyncio
async def test_parse_metrics_model_id_filter(async_test_client, async_test_db):
    """The model_id filter narrows the aggregation to that model's child rows."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    project_id = project.id
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, status_val="completed"
    )
    # 2 rows for gpt-4, 1 row for claude — filtering on gpt-4 returns 2.
    await _create_child(
        async_test_db, parent, run_index=0, model_id="gpt-4", parse_status="success",
        parse_metadata={"retry_count": 1},
    )
    await _create_child(
        async_test_db, parent, run_index=1, model_id="gpt-4", parse_status="failed",
        parse_error="boom",
    )
    await _create_child(
        async_test_db, parent, run_index=2, model_id="claude", parse_status="success",
        parse_metadata={"retry_count": 1},
    )
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}&model_id=gpt-4"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_generations"] == 2
    assert body["parse_success"] == 1
    assert body["parse_failed"] == 1


@pytest.mark.asyncio
async def test_parse_metrics_common_errors_top_n(async_test_client, async_test_db):
    """common_parse_errors caps at the top 5 by count, ordered descending; a
    NULL parse_error coalesces to 'Unknown error'."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = await _create_project(async_test_db, admin)
    project_id = project.id
    parent = await _create_generation(
        async_test_db, creator=admin, project=project, status_val="completed"
    )
    # 6 distinct error strings (e0..e5) with decreasing counts so only the top
    # 5 survive the LIMIT; e0 has the highest count.
    run = 0
    for label, count in [("e0", 6), ("e1", 5), ("e2", 4), ("e3", 3), ("e4", 2), ("e5", 1)]:
        for _ in range(count):
            await _create_child(
                async_test_db, parent, run_index=run, parse_status="failed",
                parse_error=label,
            )
            run += 1
    # One failed row with NULL parse_error -> coalesces to "Unknown error".
    await _create_child(
        async_test_db, parent, run_index=run, parse_status="failed", parse_error=None,
    )
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 200
    errors = resp.json()["common_parse_errors"]
    assert len(errors) == 5  # capped at top-5
    # Descending by count, e0 first.
    counts = [e["count"] for e in errors]
    assert counts == sorted(counts, reverse=True)
    assert errors[0] == {"error": "e0", "count": 6}
    # The single-count "e5" and the "Unknown error" row are below the cut.
    surfaced = {e["error"] for e in errors}
    assert "e5" not in surfaced
    assert "Unknown error" not in surfaced
