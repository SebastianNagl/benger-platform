"""Branch-coverage integration tests for the generation router.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
these tests seed real rows via ``async_test_db`` and drive the HTTP surface
through ``async_test_client``. ``require_user`` is overridden per-test via the
``_as_user`` context manager to return an auth User matching a seeded DB user
(the sync auth dependency can't see the async test transaction).

Targets the error/edge paths in ``services/api/routers/generation.py`` that the
happy-path suites (``test_generation_endpoints_coverage.py``,
``test_remaining_router_endpoints.py``) leave uncovered:

- ``get_generation_status``: 404 unknown id, 403 when the generation's task
  belongs to an inaccessible project, 200 with the ``error_message``-as-message
  shaping.
- ``stop_generation``: owner-only 403, status-guard 400 (non pending/running),
  200 success path with persisted ``status='stopped'`` + ``completed_at`` +
  ``error_message`` (celery_app patched so the revoke side-effect is a no-op).
- ``pause_generation`` / ``resume_generation`` / ``retry_generation``: 404,
  owner-only 403, the status-transition 400 guards, AND the success paths.
  Migration 063 added ``paused_at`` / ``resumed_at`` / ``retry_count`` /
  ``dispatch_epoch`` as real columns (the retry endpoint's ``retry_count`` read
  used to 500 on a freshly-loaded row), so all the success paths now persist
  those columns and are asserted here. Progress is DERIVED from the child rows,
  so there are no ``current_progress`` / ``completed_tasks`` columns.
- ``delete_generation``: 404, owner-only 403, running-guard 400, and the 200
  success path with cascade deletion of the child ``Generation`` rows
  (asserted via ``async_test_db``).
- ``get_parse_metrics``: project-access 403, the empty-set early return,
  the populated aggregation (success/failed/validation_error counts +
  success_rate + avg_retries), the ``model_id`` filter, and the
  ``common_parse_errors`` top-N grouping.

Every test calls the endpoint through ``async_test_client``, asserts the HTTP
status + response JSON, and (where the endpoint mutates rows) verifies the
persisted DB state by re-querying ``async_test_db``. Model providers are never
invoked — the only celery touch point (``celery_app.control.revoke`` in stop)
is patched out.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation as DBLLMResponse
from models import Organization, OrganizationMembership
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


async def _seed_project(
    db,
    owner: User,
    org: Organization,
    *,
    num_tasks: int = 1,
    is_private: bool = False,
    link_org: bool = True,
) -> Project:
    """Project owned by ``owner``. Linked to ``org`` by default so member access
    checks pass; private + unlinked for the 403 paths."""
    project = Project(
        id=_uid(),
        title="gen-branches-test",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        is_private=is_private,
    )
    db.add(project)
    await db.flush()
    if link_org:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=owner.id,
            )
        )
        await db.flush()
    for i in range(num_tasks):
        db.add(
            Task(
                id=_uid(),
                project_id=project.id,
                inner_id=i + 1,
                data={"text": f"Task {i + 1}"},
                created_by=owner.id,
                updated_by=owner.id,
            )
        )
    await db.flush()
    return project


async def _seed_generation(
    db,
    project: Project,
    *,
    created_by: str,
    status_val: str = "completed",
    model_id: str = "gpt-4o",
    task_id: str = None,
    error_message: str = None,
) -> DBResponseGeneration:
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task_id,
        model_id=model_id,
        status=status_val,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        error_message=error_message,
    )
    db.add(gen)
    await db.flush()
    return gen


async def _seed_response(
    db,
    gen: DBResponseGeneration,
    task: Task,
    *,
    model_id: str,
    parse_status: str,
    parse_error: str = None,
    parse_metadata: dict = None,
    status_val: str = "completed",
    run_index: int = 0,
) -> None:
    db.add(
        DBLLMResponse(
            id=_uid(),
            generation_id=gen.id,
            task_id=task.id,
            model_id=model_id,
            case_data="input case",
            response_content="generated answer",
            status=status_val,
            parse_status=parse_status,
            parse_error=parse_error,
            parse_metadata=parse_metadata,
            run_index=run_index,
        )
    )
    await db.flush()


async def _first_task(db, project: Project) -> Task:
    return (
        await db.execute(select(Task).where(Task.project_id == project.id))
    ).scalars().first()


async def _get_generation(db, gen_id: str) -> DBResponseGeneration:
    db.expire_all()
    return (
        await db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == gen_id)
        )
    ).scalar_one_or_none()


# ===========================================================================
# get_generation_status — GET /api/generation/status/{generation_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_status_unknown_generation_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get(f"/api/generation/status/missing-{_uid()}")
    assert resp.status_code == 404, resp.text
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_inaccessible_project_returns_403(async_test_client, async_test_db):
    """The generation's task belongs to a PRIVATE project the requester did
    not create → check_project_accessible False → 403."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    annotator = await _make_user(async_test_db, username_prefix="annot")
    project = await _seed_project(
        async_test_db, owner, org, is_private=True, link_org=False
    )
    task = await _first_task(async_test_db, project)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="running", task_id=task.id,
    )
    gen_id = gen.id
    await async_test_db.commit()

    # annotator is neither superadmin nor the private project's creator.
    with _as_user(annotator):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 403, resp.text
    assert "access" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_returns_error_message_as_message(async_test_client, async_test_db):
    """A failed generation surfaces its error_message in the `message`
    field; status echoes the DB row."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    task = await _first_task(async_test_db, project)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="failed", task_id=task.id,
        error_message="boom while generating",
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == gen_id
    assert body["status"] == "failed"
    assert body["message"] == "boom while generating"
    assert body["progress"] is None


@pytest.mark.asyncio
async def test_status_default_message_when_no_error(async_test_client, async_test_db):
    """No error_message → the fallback 'Generation status' string."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Generation status"


# ===========================================================================
# stop_generation — POST /api/generation/{generation_id}/stop
# ===========================================================================


@pytest.mark.asyncio
async def test_stop_unknown_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/stop")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Generation not found"


@pytest.mark.asyncio
async def test_stop_non_owner_non_superadmin_forbidden(async_test_client, async_test_db):
    """contributor is not the generation creator (owner is) and is not a
    superadmin → 403, and the row stays 'running'."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    contributor = await _make_user(async_test_db, username_prefix="contrib")
    await _add_membership(async_test_db, contributor, org)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 403, resp.text
    assert "your own" in resp.json()["detail"].lower()

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "running"


@pytest.mark.asyncio
async def test_stop_completed_returns_400(async_test_client, async_test_db):
    """Only pending/running may be stopped → completed yields 400 and the
    status is unchanged."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 400, resp.text
    assert "completed" in resp.json()["detail"]

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
async def test_stop_running_persists_stopped_state(async_test_client, async_test_db):
    """Happy path: a running generation transitions to 'stopped', gets a
    completed_at, and an error_message naming the user. celery_app is
    patched so control.revoke is a harmless no-op."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch("routers.generation.celery_app"):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "stopped"
    assert body["generation_id"] == gen_id

    # Persisted state.
    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "stopped"
    assert refreshed.completed_at is not None
    assert "Stopped by user" in (refreshed.error_message or "")
    # (celery_app is patched only to prevent a real broker call; stop revokes
    # the deterministic fan-out ids regardless of celery_task_id — asserted
    # explicitly in test_stop_running_revokes_dispatched_celery_task.)


@pytest.mark.asyncio
async def test_stop_running_revokes_dispatched_celery_task(async_test_client, async_test_db):
    """Stop revokes the WHOLE fan-out so a stopped generation actually stops
    burning API budget. Every dispatch path fans out one job per trial with a
    deterministic id (``{gen_id}:{run_idx}:{epoch}``), reconstructed here from
    ``runs_requested`` + the current ``dispatch_epoch`` — there is no
    per-generation Celery id to track."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen.runs_requested = 2  # two trials fanned out
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch("routers.generation.celery_app") as mock_celery:
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200, resp.text
    # The deterministic fan-out ids (from runs_requested + the current
    # dispatch_epoch=0) are revoked, terminate=True.
    mock_celery.control.revoke.assert_called_once_with(
        [f"{gen_id}:0:0", f"{gen_id}:1:0"], terminate=True
    )


@pytest.mark.asyncio
async def test_stop_pending_persists_stopped_state(async_test_client, async_test_db):
    """'pending' is the other stoppable status."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="pending"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner), patch("routers.generation.celery_app"):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
    assert resp.status_code == 200, resp.text

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "stopped"


# ===========================================================================
# pause_generation — POST /api/generation/{generation_id}/pause
# ===========================================================================


@pytest.mark.asyncio
async def test_pause_unknown_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/pause")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Generation not found"


@pytest.mark.asyncio
async def test_pause_non_owner_forbidden(async_test_client, async_test_db):
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    contributor = await _make_user(async_test_db, username_prefix="contrib")
    await _add_membership(async_test_db, contributor, org)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 403, resp.text
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_non_running_returns_400(async_test_client, async_test_db):
    """Only running generations may be paused → completed yields 400 (the
    status guard returns before any state is written)."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
    assert resp.status_code == 400, resp.text
    assert "completed" in resp.json()["detail"]

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
async def test_pause_running_persists_paused_state(async_test_client, async_test_db):
    """Happy path (migration 063): a running generation transitions to 'paused'
    and the new paused_at column is stamped. Redis is mocked to None so the
    optional Redis-store block is skipped here. celery_app is patched so the
    pause revoke (pause must actually stop the work) doesn't hit a real broker."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
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
    # Pause revokes the fan-out (current dispatch_epoch=0) so the worker stops.
    mock_celery.control.revoke.assert_called_once_with(
        [f"{gen_id}:0:0", f"{gen_id}:1:0"], terminate=True
    )

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "paused"
    assert refreshed.paused_at is not None


# ===========================================================================
# resume_generation — POST /api/generation/{generation_id}/resume
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_unknown_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/resume")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Generation not found"


@pytest.mark.asyncio
async def test_resume_non_owner_forbidden(async_test_client, async_test_db):
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    contributor = await _make_user(async_test_db, username_prefix="contrib")
    await _add_membership(async_test_db, contributor, org)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="paused"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 403, resp.text
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_non_paused_returns_400(async_test_client, async_test_db):
    """Only paused generations may be resumed → running yields 400 (the
    guard returns before the model's missing resumed_at column is touched)."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 400, resp.text
    assert "running" in resp.json()["detail"]

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "running"


@pytest.mark.asyncio
async def test_resume_paused_persists_running_and_redispatches(
    async_test_client, async_test_db
):
    """Happy path (migration 063): a paused 2-run generation transitions to
    'running', the new resumed_at column is stamped, and BOTH missing trials
    re-dispatch via the deterministic fan-out (celery patched so the enqueue is
    a no-op)."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="paused"
    )
    gen.runs_requested = 2
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    # Both missing run_indices re-dispatch (multi-run: not just run 0), at the
    # bumped dispatch_epoch=1 so the prior epoch's revoke can't discard them.
    assert mock_celery.send_task.call_count == 2
    assert {c.kwargs["task_id"] for c in mock_celery.send_task.call_args_list} == {
        f"{gen_id}:0:1", f"{gen_id}:1:1"
    }

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "running"
    assert refreshed.resumed_at is not None


# ===========================================================================
# retry_generation — POST /api/generation/{generation_id}/retry
# ===========================================================================


@pytest.mark.asyncio
async def test_retry_unknown_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/retry")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Generation not found"


@pytest.mark.asyncio
async def test_retry_non_owner_forbidden(async_test_client, async_test_db):
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    contributor = await _make_user(async_test_db, username_prefix="contrib")
    await _add_membership(async_test_db, contributor, org)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="failed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 403, resp.text
    assert "your own" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retry_completed_returns_400(async_test_client, async_test_db):
    """Only failed/stopped generations may be retried → completed yields 400.
    The status guard returns before any retry state is written."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 400, resp.text
    assert "completed" in resp.json()["detail"]

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
async def test_retry_failed_resets_state_and_increments_count(
    async_test_client, async_test_db
):
    """THE prod bug fixed by migration 063: retry reads
    ``generation.retry_count or 0`` on a freshly-loaded row. Before 063 that
    read AttributeError-ed -> 500. Now retry_count is a real column: the failed
    generation clears error/completed_at, increments retry_count, reconciles the
    multi-run counters to the (zero) completed children, and re-dispatches all 3
    missing trials via the deterministic fan-out (status -> running)."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="failed", error_message="boom",
    )
    # A multi-run attempt with stale counters but no completed children.
    gen.runs_requested = 3
    gen.runs_completed = 1
    gen.runs_failed = 2
    gen.retry_count = 2
    await async_test_db.flush()
    gen_id = gen.id
    await async_test_db.commit()

    mock_celery = MagicMock()

    with _as_user(owner), patch("routers.generation.celery_app", mock_celery):
        resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["retry_count"] == 3
    # All 3 run_indices re-dispatch (none have a child) at the bumped epoch=1.
    assert mock_celery.send_task.call_count == 3
    assert {c.kwargs["task_id"] for c in mock_celery.send_task.call_args_list} == {
        f"{gen_id}:0:1", f"{gen_id}:1:1", f"{gen_id}:2:1"
    }

    refreshed = await _get_generation(async_test_db, gen_id)
    assert refreshed.status == "running"
    assert refreshed.error_message is None
    assert refreshed.completed_at is None
    # Multi-run counters reconciled to the (zero) completed children.
    assert refreshed.runs_completed == 0
    assert refreshed.runs_failed == 0
    assert refreshed.runs_requested == 3
    # The NOW-PERSISTED column (migration 063): retry_count incremented 2 -> 3.
    assert refreshed.retry_count == 3


# ===========================================================================
# delete_generation — DELETE /api/generation/{generation_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_unknown_returns_404(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.delete(f"/api/generation/missing-{_uid()}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Generation not found"


@pytest.mark.asyncio
async def test_delete_non_owner_forbidden(async_test_client, async_test_db):
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    contributor = await _make_user(async_test_db, username_prefix="contrib")
    await _add_membership(async_test_db, contributor, org)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="completed"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 403, resp.text
    assert "your own" in resp.json()["detail"].lower()

    # Still present.
    assert await _get_generation(async_test_db, gen_id) is not None


@pytest.mark.asyncio
async def test_delete_running_returns_400(async_test_client, async_test_db):
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id, status_val="running"
    )
    gen_id = gen.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 400, resp.text
    assert "running" in resp.json()["detail"].lower()

    assert await _get_generation(async_test_db, gen_id) is not None


@pytest.mark.asyncio
async def test_delete_completed_cascades_child_responses(async_test_client, async_test_db):
    """Deleting a completed generation removes the ResponseGeneration row
    AND its child Generation rows; the response reports the deleted count."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    task = await _first_task(async_test_db, project)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="completed", task_id=task.id,
    )
    gen_id = gen.id
    # Two child Generation rows (different run_index so the unique index
    # on (generation_id, run_index) is satisfied).
    for run_index in (0, 1):
        async_test_db.add(
            DBLLMResponse(
                id=_uid(),
                generation_id=gen_id,
                task_id=task.id,
                model_id=gen.model_id,
                case_data="input case",
                response_content="generated answer",
                status="completed",
                run_index=run_index,
            )
        )
    await async_test_db.commit()

    # Sanity: 2 child rows exist before deletion.
    pre_count = (
        await async_test_db.execute(
            select(DBLLMResponse).where(DBLLMResponse.generation_id == gen_id)
        )
    ).scalars().all()
    assert len(pre_count) == 2

    with _as_user(owner):
        resp = await async_test_client.delete(f"/api/generation/{gen_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["generation_id"] == gen_id
    assert body["deleted_responses"] == 2

    # Parent + children gone.
    async_test_db.expire_all()
    assert await _get_generation(async_test_db, gen_id) is None
    post_children = (
        await async_test_db.execute(
            select(DBLLMResponse).where(DBLLMResponse.generation_id == gen_id)
        )
    ).scalars().all()
    assert len(post_children) == 0


# ===========================================================================
# get_parse_metrics — GET /api/generation/parse-metrics
# ===========================================================================


@pytest.mark.asyncio
async def test_parse_metrics_inaccessible_project_returns_403(
    async_test_client, async_test_db
):
    """project_id of a PRIVATE project the requester did not create → 403."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    annotator = await _make_user(async_test_db, username_prefix="annot")
    project = await _seed_project(
        async_test_db, owner, org, is_private=True, link_org=False
    )
    project_id = project.id
    await async_test_db.commit()

    with _as_user(annotator):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 403, resp.text
    assert "access" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_parse_metrics_empty_project_returns_zeroed_metrics(
    async_test_client, async_test_db
):
    """Accessible project with no responses → the total==0 early return."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    project_id = project.id
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_generations"] == 0
    assert body["parse_success_rate"] == 0
    assert body["avg_retries_until_success"] == 0
    assert body["common_parse_errors"] == []


@pytest.mark.asyncio
async def test_parse_metrics_populated_aggregate_and_avg_retries(
    async_test_client, async_test_db
):
    """Mixed parse_status rows aggregate into success/failed/validation_error
    counts; success_rate and avg_retries are computed; the top failure
    error is grouped into common_parse_errors."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    project_id = project.id
    task = await _first_task(async_test_db, project)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="completed", task_id=task.id,
    )
    # 2 success (retry_count 1 and 3 → avg 2), 1 failed, 1 validation_error.
    await _seed_response(
        async_test_db, gen, task, model_id="gpt-4o",
        parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
    )
    await _seed_response(
        async_test_db, gen, task, model_id="gpt-4o",
        parse_status="success", parse_metadata={"retry_count": 3}, run_index=1,
    )
    await _seed_response(
        async_test_db, gen, task, model_id="gpt-4o",
        parse_status="failed", parse_error="JSON decode error", run_index=2,
    )
    await _seed_response(
        async_test_db, gen, task, model_id="gpt-4o",
        parse_status="validation_error", parse_error="schema mismatch",
        run_index=3,
    )
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_generations"] == 4
    assert body["parse_success"] == 2
    assert body["parse_failed"] == 1
    assert body["parse_validation_error"] == 1
    assert body["parse_success_rate"] == 0.5
    # (1 + 3) / 2 == 2.0
    assert body["avg_retries_until_success"] == 2.0
    # Both failure rows grouped; two distinct error strings, each count 1.
    errors = {e["error"]: e["count"] for e in body["common_parse_errors"]}
    assert errors.get("JSON decode error") == 1
    assert errors.get("schema mismatch") == 1


@pytest.mark.asyncio
async def test_parse_metrics_model_id_filter_narrows_aggregation(
    async_test_client, async_test_db
):
    """The model_id query param restricts the aggregation to one model's
    rows."""
    owner = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _seed_project(async_test_db, owner, org)
    project_id = project.id
    task = await _first_task(async_test_db, project)
    gen = await _seed_generation(
        async_test_db, project, created_by=owner.id,
        status_val="completed", task_id=task.id,
    )
    await _seed_response(
        async_test_db, gen, task, model_id="gpt-4o",
        parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
    )
    await _seed_response(
        async_test_db, gen, task, model_id="claude-3",
        parse_status="failed", parse_error="boom", run_index=1,
    )
    await async_test_db.commit()

    with _as_user(owner):
        resp = await async_test_client.get(
            f"/api/generation/parse-metrics?project_id={project_id}&model_id=gpt-4o"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Only the gpt-4o success row is counted.
    assert body["total_generations"] == 1
    assert body["parse_success"] == 1
    assert body["parse_failed"] == 0
    assert body["common_parse_errors"] == []
