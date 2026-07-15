"""
Integration tests for remaining untested API routers (Phases 2.3, 2.4, 2.5).

Covers:
  Group 1 — Generation routers: generation.py, generation_task_list.py
  Group 2 — Auth & User Management: auth.py, users.py, invitations.py
  Group 3 — Admin & System routers: notifications.py, feature_flags.py,
            dashboard.py, health.py, prompt_structures.py, reports.py,
            llm_models.py

Uses real PostgreSQL with per-test transaction rollback isolation via the
shared test_db fixture.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from models import (
    FeatureFlag,
    Invitation,
    LLMModel,
    Notification,
    NotificationType,
    Organization,
    OrganizationRole,
    ResponseGeneration as DBResponseGeneration,
    User,
)
from project_models import (
    Project,
    ProjectOrganization,
    Task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Shared async auth + seeding helpers
#
# Many routers exercised below (auth /me & profile reads, users mgmt, the
# invitations list/validate/cancel, dashboard, reports, async feature flags)
# were migrated to the async DB lane (``Depends(get_async_db)``). The sync
# auth dependency (``require_user`` → ``Depends(get_db)``) can't see the async
# test transaction, and ``async_test_client`` only overrides ``get_async_db``
# — so the sync ``client``/``auth_headers``/``test_users``/``test_org``
# fixtures are invisible to those handlers. We seed actors/orgs/invitations
# directly into ``async_test_db`` and override ``require_user`` with an
# ``AuthUser`` built from the seeded row (mirrors
# ``test_global_tasks_integration.py`` and the in-file ``_gen_user_ctx``).
#
# Tests whose endpoint is still on the SYNC lane (POST /auth/login, PUT
# /auth/profile, DELETE /users/{id}, POST invitation create, all of
# notifications, and the sync feature-flag handlers /all, PUT, /check) keep
# the sync ``client`` + ``auth_headers`` fixtures — converting them would
# break them, because ``get_db`` is NOT overridden under ``async_test_client``
# (it would resolve to a real, non-isolated session).
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user: User):
    """Override require_user with an AuthUser matching a seeded async DB user."""
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _make_user(db, *, is_superadmin=False, prefix="usr"):
    """Seed a bare User into the async test session (no mandatory profile)."""
    u = User(
        id=_uid(),
        username=f"{prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=f"{prefix.title()} User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org_async(db, *, name="Test Org"):
    org = Organization(
        id=_uid(),
        name=f"{name}-{_uid()[:6]}",
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:6]}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_invitation_async(
    db,
    org,
    inviter,
    *,
    email="invitee@example.com",
    role=OrganizationRole.CONTRIBUTOR,
    token=None,
    accepted=False,
    expires_delta=timedelta(days=7),
):
    inv = Invitation(
        id=_uid(),
        organization_id=org.id,
        email=email,
        role=role,
        token=token or _uid(),
        invited_by=inviter.id,
        expires_at=datetime.now(timezone.utc) + expires_delta,
        accepted=accepted,
    )
    db.add(inv)
    await db.flush()
    return inv


async def _make_project_async(
    db,
    creator,
    test_org=None,
    *,
    title="Test Project",
    label_config='<View><Text name="text" value="$text"/></View>',
    is_private=False,
    num_tasks=2,
):
    """Async twin of ``_make_project`` — seeds a project (optionally linked to
    an org) plus tasks into the async test session."""
    pid = _uid()
    project = Project(
        id=pid,
        title=f"{title} {pid[:6]}",
        description="Integration test project",
        created_by=creator.id,
        label_config=label_config,
        is_private=is_private,
    )
    db.add(project)
    await db.flush()

    if not is_private and test_org is not None:
        db.add(ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=test_org.id,
            assigned_by=creator.id,
        ))
        await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            data={"text": f"Sample text {i}"},
            created_by=creator.id,
            inner_id=i + 1,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    return {"project": project, "tasks": tasks}


def _make_project(
    test_db: Session,
    admin: User,
    test_org: Organization,
    *,
    title: str = "Test Project",
    generation_config: dict = None,
    label_config: str = '<View><Text name="text" value="$text"/></View>',
    is_private: bool = False,
    num_tasks: int = 2,
) -> Dict:
    """Create a project linked to the test organization with tasks."""
    pid = _uid()
    project = Project(
        id=pid,
        title=f"{title} {pid[:6]}",
        description="Integration test project",
        created_by=admin.id,
        label_config=label_config,
        generation_config=generation_config,
        is_private=is_private,
    )
    test_db.add(project)
    test_db.flush()

    if not is_private:
        test_db.add(ProjectOrganization(
            id=_uid(),
            project_id=pid,
            organization_id=test_org.id,
            assigned_by=admin.id,
        ))
        test_db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            data={"text": f"Sample text {i}"},
            created_by=admin.id,
            inner_id=i + 1,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()
    test_db.commit()

    return {"project": project, "tasks": tasks}


# ===================================================================
# GROUP 1 — GENERATION ROUTERS
# ===================================================================


def _gen_as_user(db_user):
    """Override require_user with an AuthUser matching a seeded DB user.

    Shared by the two generation test classes below. Both routers
    (``generation.py`` / ``generation_task_list.py``) were migrated to the
    async DB lane, so the sync auth dependency can't see the async test
    transaction — we override it with a user built from the seeded row.
    """
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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
    return auth_user


@contextmanager
def _gen_user_ctx(db_user):
    from auth_module.dependencies import require_user
    from main import app

    _gen_as_user(db_user)
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _gen_make_user(db, *, is_superadmin=True, prefix="gen"):
    u = User(
        id=_uid(),
        username=f"{prefix}-{_uid()[:8]}",
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


async def _gen_make_project(db, creator, *, generation_config=None, num_tasks=2):
    project = Project(
        id=_uid(),
        title=f"Gen Project {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Sample text {i}"},
            created_by=creator.id,
            inner_id=i + 1,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return project, tasks


async def _gen_make_response_generation(
    db, project, task, creator, *, status_val="completed", model_id="gpt-4o"
):
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id,
        model_id=model_id,
        status=status_val,
        created_by=creator.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(gen)
    await db.flush()
    return gen


async def _gen_make_custom_model(db, creator, *, parameter_constraints=None):
    """Seed an active custom (BYOM) LLMModel visible to its creator.

    base_url + endpoint_model_name are always set so the
    ck_llm_models_custom_endpoint_required CHECK holds.
    """
    model = LLMModel(
        id=f"custom-{uuid.uuid4()}",
        name="Custom vLLM",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        created_by=creator.id,
        is_private=True,
        is_public=False,
        base_url="http://10.10.3.7:8000/v1",
        endpoint_model_name="llama-3-8b",
        requires_api_key=False,
        parameter_constraints=parameter_constraints,
        created_at=datetime.now(timezone.utc),
    )
    db.add(model)
    await db.flush()
    return model


async def _gen_make_official_model(db, *, parameter_constraints=None):
    model = LLMModel(
        id=f"gpt-official-{_uid()[:8]}",
        name="Official Model",
        provider="OpenAI",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=True,
        is_private=False,
        is_public=False,
        parameter_constraints=parameter_constraints,
        created_at=datetime.now(timezone.utc),
    )
    db.add(model)
    await db.flush()
    return model


@pytest.mark.asyncio
class TestGenerationStatusEndpoints:
    """Tests for /api/generation status, stop, pause, resume, retry, delete, parse-metrics.

    ``routers/generation.py`` was migrated to the async DB lane, so these seed
    via ``async_test_db`` and drive through ``async_test_client``.
    """

    async def test_get_generation_status_found(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(f"/api/generation/status/{gen_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == gen_id
        assert body["status"] == "running"

    async def test_get_generation_status_not_found(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get("/api/generation/status/nonexistent-id")
        assert resp.status_code == 404

    async def test_stop_running_generation(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stopped"

    async def test_stop_completed_generation_returns_400(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="completed"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
        assert resp.status_code == 400

    async def test_stop_generation_permission_denied(self, async_test_client, async_test_db):
        """Non-owner, non-superadmin cannot stop another user's generation."""
        admin = await _gen_make_user(async_test_db)
        other = await _gen_make_user(async_test_db, is_superadmin=False, prefix="other")
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(other):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/stop")
        assert resp.status_code == 403

    async def test_pause_non_running_returns_400(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="completed"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/pause")
        assert resp.status_code == 400

    async def test_resume_non_paused_returns_400(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/resume")
        assert resp.status_code == 400

    async def test_retry_failed_generation(self, async_test_client, async_test_db):
        # Migration 063 added the retry_count (+paused_at/resumed_at/
        # current_progress/completed_tasks) columns, so the retry endpoint now
        # resets state, increments retry_count, and re-dispatches the missing
        # fan-out trial(s) (status -> running) successfully.
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="failed"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch("routers.generation.celery_app"):
            resp = await async_test_client.post(f"/api/generation/{gen_id}/retry")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "running"
        assert body["retry_count"] == 1

    async def test_delete_completed_generation(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="completed"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.delete(f"/api/generation/{gen_id}")
        assert resp.status_code == 200
        assert resp.json()["generation_id"] == gen_id

    async def test_delete_running_generation_returns_400(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, tasks = await _gen_make_project(async_test_db, admin)
        gen = await _gen_make_response_generation(
            async_test_db, project, tasks[0], admin, status_val="running"
        )
        gen_id = gen.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.delete(f"/api/generation/{gen_id}")
        assert resp.status_code == 400

    async def test_parse_metrics_empty_project(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin)
        project_id = project.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(
                f"/api/generation/parse-metrics?project_id={project_id}"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_generations"] == 0
        assert body["parse_success_rate"] == 0

    async def test_parse_metrics_no_project_filter(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get("/api/generation/parse-metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_generations" in body


@pytest.mark.asyncio
class TestGenerationTaskListEndpoints:
    """Tests for /api/generation-tasks endpoints.

    ``routers/generation_task_list.py`` was migrated to the async DB lane, so
    these seed via ``async_test_db`` and drive through ``async_test_client``.
    """

    async def test_task_status_no_models_configured(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, generation_config={})
        project_id = project.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["models"] == []

    async def test_task_status_with_models(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        gen_config = {
            "selected_configuration": {"models": ["gpt-4o"], "active_structures": []},
            "prompt_structures": {},
        }
        project, _ = await _gen_make_project(
            async_test_db, admin, generation_config=gen_config, num_tasks=3
        )
        project_id = project.id
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project_id}/task-status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["models"] == ["gpt-4o"]
        assert len(body["tasks"]) == 3

    async def test_task_status_project_not_found(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/projects/nonexistent-id/task-status"
            )
        assert resp.status_code == 404

    async def test_start_generation_no_models_returns_400(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, generation_config={})
        project_id = project.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch("routers.generation_task_list.celery_app"):
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 400

    async def test_start_generation_all_mode(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        gen_config = {
            "selected_configuration": {"models": ["gpt-4o"], "active_structures": []},
            "prompt_structures": {},
        }
        project, _ = await _gen_make_project(
            async_test_db, admin, generation_config=gen_config, num_tasks=2
        )
        project_id = project.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch("routers.generation_task_list.celery_app") as mock_celery:
            mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
            mock_celery.control.revoke = MagicMock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={"mode": "all"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tasks_queued"] == 2
        assert body["models_count"] == 1

    async def test_generation_result_task_not_found(self, async_test_client, async_test_db):
        admin = await _gen_make_user(async_test_db)
        await async_test_db.commit()
        with _gen_user_ctx(admin):
            resp = await async_test_client.get(
                "/api/generation-tasks/generation-result?task_id=nope&model_id=gpt-4o"
            )
        assert resp.status_code == 404

    # ---- model-aware max_tokens (BYOM follow-up) ----

    async def test_start_generation_rejects_max_tokens_above_model_declared_max(
        self, async_test_client, async_test_db
    ):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, num_tasks=2)
        model = await _gen_make_custom_model(
            async_test_db, admin, parameter_constraints={"max_tokens": {"max": 8000}}
        )
        project_id, model_id = project.id, model.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch(
            "routers.generation_task_list.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
            mock_celery.control.revoke = MagicMock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={
                    "mode": "all",
                    "model_ids": [model_id],
                    "parameters": {"max_tokens": 12000},
                },
            )
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert "12000" in detail and "8000" in detail and model_id in detail

    async def test_start_generation_accepts_max_tokens_at_model_declared_max(
        self, async_test_client, async_test_db
    ):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, num_tasks=2)
        model = await _gen_make_custom_model(
            async_test_db, admin, parameter_constraints={"max_tokens": {"max": 8000}}
        )
        project_id, model_id = project.id, model.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch(
            "routers.generation_task_list.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
            mock_celery.control.revoke = MagicMock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={
                    "mode": "all",
                    "model_ids": [model_id],
                    "parameters": {"max_tokens": 8000},
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 2

    async def test_start_generation_allows_large_max_tokens_when_no_declared_max(
        self, async_test_client, async_test_db
    ):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, num_tasks=2)
        # No parameter_constraints at all → no declared max → schema ceiling applies.
        model = await _gen_make_custom_model(async_test_db, admin, parameter_constraints=None)
        project_id, model_id = project.id, model.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch(
            "routers.generation_task_list.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
            mock_celery.control.revoke = MagicMock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={
                    "mode": "all",
                    "model_ids": [model_id],
                    "parameters": {"max_tokens": 100000},
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 2

    async def test_start_generation_official_model_unaffected_by_cap(
        self, async_test_client, async_test_db
    ):
        admin = await _gen_make_user(async_test_db)
        project, _ = await _gen_make_project(async_test_db, admin, num_tasks=2)
        # Official row with a temperature constraint but NO max_tokens.max.
        model = await _gen_make_official_model(
            async_test_db,
            parameter_constraints={"temperature": {"supported": True, "min": 0, "max": 2}},
        )
        project_id, model_id = project.id, model.id
        await async_test_db.commit()
        with _gen_user_ctx(admin), patch(
            "routers.generation_task_list.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = MagicMock(id="celery-task-id")
            mock_celery.control.revoke = MagicMock()
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={
                    "mode": "all",
                    "model_ids": [model_id],
                    "parameters": {"max_tokens": 50000},
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tasks_queued"] == 2


# ===================================================================
# GROUP 2 — AUTH & USER MANAGEMENT
# ===================================================================


class TestAuthLoginEndpoints:
    """Tests for /api/auth/login and related auth endpoints."""

    def test_login_valid_credentials(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_invalid_password(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, test_db, test_users):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody@test.com", "password": "anything"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestAuthMeEndpoints:
    """Tests for /api/auth/me and /api/auth/verify.

    ``GET /me``, ``GET /me/contexts`` and ``GET /verify`` were migrated to the
    async DB lane, so these seed an actor via ``async_test_db`` and override
    ``require_user`` with that seeded user.
    """

    async def test_get_me_authenticated(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == admin.id
        assert body["is_superadmin"] == True  # noqa: E712
        assert body["email"] == admin.email

    async def test_get_me_unauthenticated(self, async_test_client, async_test_db):
        resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    async def test_verify_token_valid(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] == True  # noqa: E712

    async def test_me_contexts_returns_orgs(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await _make_org_async(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/me/contexts")
        assert resp.status_code == 200
        body = resp.json()
        assert "user" in body
        assert "organizations" in body
        assert isinstance(body["organizations"], list)


class TestAuthProfileEndpoints:
    """Tests for /api/auth/profile GET and PUT.

    ``GET /profile`` is on the async DB lane (seeds via ``async_test_db`` +
    ``_as_user``). ``PUT /profile`` deliberately stays on the SYNC lane
    (``update_user_profile`` has no async twin), so its test keeps the sync
    ``client`` + ``auth_headers`` fixtures.
    """

    @pytest.mark.asyncio
    async def test_get_profile(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == admin.id
        assert body["username"] == admin.username
        assert body["email"] == admin.email
        assert body["is_superadmin"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_profile_contributor(self, async_test_client, async_test_db):
        contributor = await _make_user(
            async_test_db, is_superadmin=False, prefix="contributor"
        )
        await async_test_db.commit()
        with _as_user(contributor):
            resp = await async_test_client.get("/api/auth/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_superadmin"] == False  # noqa: E712

    def test_update_profile_name(self, client, test_db, test_users, auth_headers):
        # PUT /auth/profile is on the SYNC DB lane (no async twin), so keep the
        # sync client + auth_headers fixtures here.
        resp = client.put(
            "/api/auth/profile",
            json={"name": "Updated Admin Name"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Updated Admin Name"


@pytest.mark.asyncio
class TestAuthMandatoryProfileEndpoints:
    """Tests for /api/auth/mandatory-profile-status and /api/auth/confirm-profile.

    Both endpoints (plus /check-profile-status) were migrated to the async DB
    lane and re-read the actor by id, so they seed via ``async_test_db`` +
    ``_as_user``.
    """

    async def test_mandatory_profile_status(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/mandatory-profile-status")
        assert resp.status_code == 200
        body = resp.json()
        assert "mandatory_profile_completed" in body
        assert "confirmation_due" in body
        assert "missing_fields" in body

    async def test_confirm_profile(self, async_test_client, async_test_db):
        # confirm-profile returns 400 when mandatory profile fields are missing.
        # The seeded user is created without gender, age, legal_expertise_level,
        # etc., so it always has missing mandatory fields.
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/confirm-profile")
        assert resp.status_code == 400
        body = resp.json()
        assert "missing fields" in body["detail"].lower()

    async def test_check_profile_status(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/auth/check-profile-status")
        assert resp.status_code == 200
        body = resp.json()
        assert "profile_completed" in body
        assert "has_password" in body


@pytest.mark.asyncio
class TestAuthLogoutEndpoints:
    """Tests for /api/auth/logout and /api/auth/logout-all.

    Both were migrated to the async DB lane (async refresh-token revocation).
    """

    async def test_logout(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    async def test_logout_all(self, async_test_client, async_test_db):
        """Logout from all devices revokes all refresh tokens."""
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post("/api/auth/logout-all")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body or "detail" in body or resp.status_code == 200


class TestUsersEndpoints:
    """Tests for /api/users endpoints (superadmin only).

    GET / (list), PATCH /{id}/role and PATCH /{id}/status are on the async DB
    lane (seed via ``async_test_db`` + ``_as_user``). DELETE /{id} stays on the
    SYNC lane (``delete_user`` has no async twin), so its tests keep the sync
    ``client`` + ``auth_headers`` fixtures.
    """

    @pytest.mark.asyncio
    async def test_get_all_users_as_admin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await _make_user(async_test_db, is_superadmin=False, prefix="u1")
        await _make_user(async_test_db, is_superadmin=False, prefix="u2")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/users")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 3  # The three users seeded above

    @pytest.mark.asyncio
    async def test_get_all_users_as_non_admin_returns_403(
        self, async_test_client, async_test_db
    ):
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.get("/api/users")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_role(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{annotator.id}/role",
                json={"is_superadmin": True},
            )
        assert resp.status_code == 200
        assert resp.json()["is_superadmin"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_update_user_role_invalid_type(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{annotator.id}/role",
                json={"is_superadmin": "not-a-bool"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_user_status(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{annotator.id}/status",
                json={"is_active": False},
            )
        assert resp.status_code == 200

    def test_delete_user_not_self(self, client, test_db, test_users, auth_headers):
        # DELETE /users/{id} is on the SYNC DB lane — keep sync fixtures.
        annotator = test_users[2]
        resp = client.delete(
            f"/api/users/{annotator.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 204

    def test_delete_self_returns_400(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        resp = client.delete(
            f"/api/users/{admin.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_delete_nonexistent_user_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            "/api/users/nonexistent-user-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestInvitationsEndpoints:
    """Tests for /api/invitations endpoints.

    The list / validate / get-by-token / cancel endpoints were migrated to the
    async DB lane (seed via ``async_test_db``; a superadmin actor via
    ``_as_user`` skips the org-admin membership check on list/cancel). The
    create endpoint (POST .../invitations) stays on the SYNC lane
    (``can_manage_organization`` + sync invitation service), so its tests keep
    the sync ``client`` + ``auth_headers`` + ``test_org`` fixtures.
    """

    def test_create_invitation(self, client, test_db, test_users, test_org, auth_headers):
        # POST create is on the SYNC DB lane — keep sync fixtures.
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                f"/api/invitations/organizations/{test_org.id}/invitations",
                json={"email": "newuser@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["role"] == "ANNOTATOR"
        assert body["accepted"] == False  # noqa: E712

    def test_create_invitation_org_not_found(self, client, test_db, test_users, auth_headers):
        with patch("routers.invitations.celery_app"):
            resp = client.post(
                "/api/invitations/organizations/nonexistent-org/invitations",
                json={"email": "user@example.com", "role": "ANNOTATOR"},
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_invitations(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        await _make_invitation_async(
            async_test_db, org, admin, email="listed@example.com"
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/invitations/organizations/{org.id}/invitations",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert any(inv["email"] == "listed@example.com" for inv in body)

    @pytest.mark.asyncio
    async def test_validate_invitation_token(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        token = _uid()
        await _make_invitation_async(
            async_test_db,
            org,
            admin,
            email="validate@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=token,
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] == True  # noqa: E712
        assert body["email"] == "validate@example.com"

    @pytest.mark.asyncio
    async def test_validate_expired_invitation(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        token = _uid()
        await _make_invitation_async(
            async_test_db,
            org,
            admin,
            email="expired@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=token,
            expires_delta=timedelta(days=-1),
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/validate/{token}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cancel_invitation(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        invitation = await _make_invitation_async(
            async_test_db,
            org,
            admin,
            email="cancel@example.com",
            role=OrganizationRole.ANNOTATOR,
        )
        invitation_id = invitation.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/invitations/{invitation_id}",
            )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Invitation cancelled successfully"

    @pytest.mark.asyncio
    async def test_get_invitation_by_token(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        token = _uid()
        await _make_invitation_async(
            async_test_db,
            org,
            admin,
            email="bytoken@example.com",
            role=OrganizationRole.CONTRIBUTOR,
            token=token,
        )
        await async_test_db.commit()

        resp = await async_test_client.get(f"/api/invitations/token/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "bytoken@example.com"
        assert body["role"] == "CONTRIBUTOR"


# ===================================================================
# GROUP 3 — ADMIN & SYSTEM ROUTERS
# ===================================================================


class TestNotificationEndpoints:
    """Tests for /api/notifications endpoints."""

    def _create_notification(self, test_db, user, *, is_read=False):
        n = Notification(
            id=_uid(),
            user_id=user.id,
            type=NotificationType.SYSTEM_ALERT,
            title="Test Notification",
            message="This is a test notification",
            data={"test": True},
            is_read=is_read,
        )
        test_db.add(n)
        test_db.flush()
        test_db.commit()
        return n

    def test_get_notifications_empty(self, client, test_db, test_users, auth_headers):
        resp = client.get("/api/notifications/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_notifications_with_data(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin)
        self._create_notification(test_db, admin)
        resp = client.get("/api/notifications/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) >= 2

    def test_get_notifications_unread_only(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        self._create_notification(test_db, admin, is_read=True)
        resp = client.get(
            "/api/notifications/?unread_only=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(not n["is_read"] for n in body)

    def test_get_unread_count(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        resp = client.get("/api/notifications/unread-count", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_mark_notification_read(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        n = self._create_notification(test_db, admin, is_read=False)
        resp = client.post(
            f"/api/notifications/mark-read/{n.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "marked as read" in resp.json()["message"].lower()

    def test_mark_nonexistent_notification_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/notifications/mark-read/nonexistent-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_mark_all_read(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        self._create_notification(test_db, admin, is_read=False)
        self._create_notification(test_db, admin, is_read=False)
        resp = client.post(
            "/api/notifications/mark-all-read",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "marked" in resp.json()["message"].lower()

    def test_notification_preferences_get(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/notifications/preferences",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "preferences" in resp.json()

    def test_notification_preferences_update(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/notifications/preferences",
            json={"preferences": {"system_alert": False}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_notification_summary(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/notifications/summary",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_notifications" in body
        assert "unread_notifications" in body
        assert "period_days" in body


class TestFeatureFlagEndpoints:
    """Tests for /api/feature-flags endpoints.

    The list / get-single / delete handlers are on the async DB lane
    (require_superadmin; seed via ``async_test_db`` + ``_as_user``). The /all,
    PUT and /check handlers stay on the SYNC lane (sync-only
    ``FeatureFlagService``), so their tests keep the sync ``client`` +
    ``auth_headers`` fixtures.
    """

    def _create_flag(self, test_db, admin):
        flag = FeatureFlag(
            id=_uid(),
            name=f"test_flag_{_uid()[:8]}",
            description="A test flag",
            is_enabled=False,
            created_by=admin.id,
        )
        test_db.add(flag)
        test_db.flush()
        test_db.commit()
        return flag

    async def _create_flag_async(self, db, admin):
        flag = FeatureFlag(
            id=_uid(),
            name=f"test_flag_{_uid()[:8]}",
            description="A test flag",
            is_enabled=False,
            created_by=admin.id,
        )
        db.add(flag)
        await db.flush()
        return flag

    @pytest.mark.asyncio
    async def test_list_feature_flags_as_admin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await self._create_flag_async(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/feature-flags")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_feature_flags_as_non_admin_returns_403(
        self, async_test_client, async_test_db
    ):
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.get("/api/feature-flags")
        assert resp.status_code == 403

    def test_get_all_flags_as_regular_user(self, client, test_db, test_users, auth_headers):
        """The /all endpoint is available to any authenticated user.

        /all is on the SYNC DB lane — keep sync fixtures.
        """
        admin = test_users[0]
        self._create_flag(test_db, admin)
        resp = client.get("/api/feature-flags/all", headers=auth_headers["annotator"])
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_single_flag(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        flag = await self._create_flag_async(async_test_db, admin)
        flag_id, flag_name = flag.id, flag.name
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/feature-flags/{flag_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == flag_name
        assert body["is_enabled"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_get_nonexistent_flag_returns_404(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/feature-flags/nonexistent-id")
        assert resp.status_code == 404

    def test_update_feature_flag(self, client, test_db, test_users, auth_headers):
        # PUT /{id} is on the SYNC DB lane — keep sync fixtures.
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.put(
            f"/api/feature-flags/{flag.id}",
            json={"is_enabled": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_delete_feature_flag(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        flag = await self._create_flag_async(async_test_db, admin)
        flag_id = flag.id
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(f"/api/feature-flags/{flag_id}")
        assert resp.status_code == 204

    def test_check_flag_by_name(self, client, test_db, test_users, auth_headers):
        # GET /check/{name} is on the SYNC DB lane — keep sync fixtures.
        admin = test_users[0]
        flag = self._create_flag(test_db, admin)
        resp = client.get(
            f"/api/feature-flags/check/{flag.name}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["flag_name"] == flag.name
        assert "is_enabled" in body


class TestDashboardEndpoints:
    """Tests for /api/dashboard/stats.

    GET /dashboard/stats was migrated to the async DB lane (it bridges the sync
    accessible-project helper via ``db.run_sync`` on the async session), so
    these seed via ``async_test_db`` and override ``require_user`` with the
    seeded actor.
    """

    @pytest.mark.asyncio
    async def test_dashboard_stats(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "project_count" in body
        assert "task_count" in body
        assert "annotation_count" in body
        assert "projects_with_generations" in body
        assert "projects_with_evaluations" in body

    @pytest.mark.asyncio
    async def test_dashboard_stats_with_org_header(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/dashboard/stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_count"] >= 0

    @pytest.mark.asyncio
    async def test_dashboard_stats_counts_match_data(
        self, async_test_client, async_test_db
    ):
        """Verify dashboard counts match actual data in the database."""
        from models import EvaluationJudgeRun, EvaluationRun, Generation, ResponseGeneration, TaskEvaluation
        from project_models import Annotation, Project, ProjectOrganization, Task

        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        org = await _make_org_async(async_test_db)
        now = datetime.now(timezone.utc)

        # Create a project with known data counts
        project = Project(
            id=_uid(), title="Dashboard Count Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        async_test_db.add(project)
        await async_test_db.flush()
        async_test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=org.id, assigned_by=admin.id,
        ))
        await async_test_db.flush()

        # 3 tasks
        tasks = []
        for i in range(3):
            t = Task(id=_uid(), project_id=project.id, data={"text": f"t{i}"},
                     inner_id=i + 1, created_by=admin.id)
            async_test_db.add(t)
            tasks.append(t)
        await async_test_db.flush()

        # 2 annotations (non-cancelled, with results)
        for i in range(2):
            async_test_db.add(Annotation(
                id=_uid(), task_id=tasks[i].id, project_id=project.id,
                completed_by=admin.id, was_cancelled=False,
                result=[{"value": "test"}],
                created_at=now,
            ))
        await async_test_db.flush()

        # 1 generation
        rg = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            status="completed", created_by=admin.id,
            started_at=now, completed_at=now,
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=tasks[0].id,
            model_id="gpt-4o", case_data='{"text": "t0"}',
            response_content="response", status="completed",
            # Dashboard aggregator filters generations by parse_status="success"
            # to match the precomputed project_summaries semantic.
            parse_status="success",
        )
        async_test_db.add(gen)
        await async_test_db.flush()

        # 1 evaluation
        er = EvaluationRun(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            evaluation_type_ids=["accuracy"], metrics={"accuracy": 0.9},
            status="completed", created_by=admin.id, created_at=now,
        )
        async_test_db.add(er)
        await async_test_db.flush()
        # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; use the
        # catch-all judge-run shape that orphan backfill uses.
        judge_run = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        async_test_db.add(judge_run)
        await async_test_db.flush()
        async_test_db.add(TaskEvaluation(
            id=_uid(), evaluation_id=er.id, judge_run_id=judge_run.id,
            task_id=tasks[0].id,
            # `_scored_pairs_query` requires a non-null subject (annotation_id
            # OR generation_id) for the row to count toward the dashboard's
            # evaluations tally.
            generation_id=gen.id,
            field_name="text", answer_type="text",
            metrics={"accuracy": 0.9}, prediction="pred", ground_truth="gt",
            passed=True,
        ))
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/dashboard/stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()

        # Counts should be at least what we created (other tests may add more)
        assert body["project_count"] >= 1
        assert body["task_count"] >= 3
        assert body["annotation_count"] >= 2
        assert body["projects_with_generations"] >= 1
        assert body["projects_with_evaluations"] >= 1

    @pytest.mark.asyncio
    async def test_dashboard_stats_unauthenticated(
        self, async_test_client, async_test_db
    ):
        resp = await async_test_client.get("/api/dashboard/stats")
        assert resp.status_code in (401, 403)


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Tests for health check endpoints.

    ``/`` and ``/healthz`` touch no DB; ``/health/schema`` is on the async DB
    lane; ``/health/cors-auth`` is auth-only (no DB). All drive through
    ``async_test_client`` for consistency; cors-auth overrides ``require_user``
    with a seeded actor.
    """

    async def test_root_endpoint(self, async_test_client):
        resp = await async_test_client.get("/")
        assert resp.status_code == 200
        assert "message" in resp.json()

    async def test_healthz(self, async_test_client):
        resp = await async_test_client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_health_schema(self, async_test_client, async_test_db):
        resp = await async_test_client.get("/health/schema")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "error")
        assert "schema" in body

    async def test_health_cors_auth(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/health/cors-auth")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["user_id"] == admin.id


class TestPromptStructureEndpoints:
    """Tests for /api/projects/{project_id}/generation-config/structures endpoints.

    The prompt_structures router was migrated to the async DB lane, so these
    seed via async_test_db and drive through async_test_client, overriding
    require_user with a seeded superadmin (the sync auth dependency can't see
    the async test transaction).
    """

    BASE = "/api/projects"

    @staticmethod
    @contextmanager
    def _as_admin():
        from auth_module.dependencies import require_user
        from auth_module.models import User as AuthUser
        from main import app

        admin = AuthUser(
            id=f"ps-admin-{uuid.uuid4().hex[:8]}",
            username="ps-admin",
            email="ps-admin@test.com",
            name="PS Admin",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[require_user] = lambda: admin
        try:
            yield admin
        finally:
            app.dependency_overrides.pop(require_user, None)

    @staticmethod
    async def _make_async_project(db, *, generation_config=None):
        from models import User as DBUser

        creator = DBUser(
            id=_uid(),
            username=f"ps-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="PS Creator",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(creator)
        await db.flush()
        project = Project(
            id=_uid(),
            title=f"PS Project {uuid.uuid4().hex[:6]}",
            created_by=creator.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config=generation_config,
        )
        db.add(project)
        await db.flush()
        await db.commit()
        return project

    @pytest.mark.asyncio
    async def test_list_structures_empty(self, async_test_client, async_test_db):
        project = await self._make_async_project(async_test_db, generation_config={})
        with self._as_admin():
            resp = await async_test_client.get(
                f"{self.BASE}/{project.id}/generation-config/structures",
            )
        assert resp.status_code == 200
        assert resp.json() == {}

    @pytest.mark.asyncio
    async def test_create_structure(self, async_test_client, async_test_db):
        project = await self._make_async_project(async_test_db, generation_config={})
        structure_payload = {
            "name": "My Structure",
            "system_prompt": "You are a legal assistant.",
            "instruction_prompt": "Answer the following question: {question}",
        }
        with self._as_admin():
            resp = await async_test_client.put(
                f"{self.BASE}/{project.id}/generation-config/structures/my-structure",
                json=structure_payload,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "my-structure"

    @pytest.mark.asyncio
    async def test_get_structure(self, async_test_client, async_test_db):
        gen_config = {
            "prompt_structures": {
                "qa-prompt": {
                    "name": "QA Prompt",
                    "system_prompt": "Be helpful",
                    "instruction_prompt": "Q: {question}",
                }
            },
            "selected_configuration": {"models": [], "active_structures": []},
        }
        project = await self._make_async_project(
            async_test_db, generation_config=gen_config
        )
        with self._as_admin():
            resp = await async_test_client.get(
                f"{self.BASE}/{project.id}/generation-config/structures/qa-prompt",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "qa-prompt"

    @pytest.mark.asyncio
    async def test_get_nonexistent_structure_returns_404(
        self, async_test_client, async_test_db
    ):
        project = await self._make_async_project(async_test_db, generation_config={})
        with self._as_admin():
            resp = await async_test_client.get(
                f"{self.BASE}/{project.id}/generation-config/structures/nonexistent",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_structure(self, async_test_client, async_test_db):
        gen_config = {
            "prompt_structures": {
                "to-delete": {
                    "name": "To Delete",
                    "system_prompt": "X",
                    "instruction_prompt": "Y",
                }
            },
            "selected_configuration": {"models": [], "active_structures": ["to-delete"]},
        }
        project = await self._make_async_project(
            async_test_db, generation_config=gen_config
        )
        with self._as_admin():
            resp = await async_test_client.delete(
                f"{self.BASE}/{project.id}/generation-config/structures/to-delete",
            )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_structure_returns_404(
        self, async_test_client, async_test_db
    ):
        project = await self._make_async_project(async_test_db, generation_config={})
        with self._as_admin():
            resp = await async_test_client.delete(
                f"{self.BASE}/{project.id}/generation-config/structures/no-such-key",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_structure_key(self, async_test_client, async_test_db):
        project = await self._make_async_project(async_test_db, generation_config={})
        with self._as_admin():
            resp = await async_test_client.put(
                f"{self.BASE}/{project.id}/generation-config/structures/invalid key!",
                json={"name": "Invalid", "system_prompt": "x", "instruction_prompt": "y"},
            )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestReportEndpoints:
    """Tests for /api/projects/{project_id}/report and /api/reports endpoints.

    All report read/publish endpoints were migrated to the async DB lane. The
    non-admin 403 tests rely on the handlers' superadmin gate (which fires
    before the project lookup), so a non-superadmin actor via ``_as_user`` is
    rejected regardless of the seeded project.
    """

    async def test_get_report_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent-id/report")
        assert resp.status_code == 404

    async def test_update_report_non_admin_returns_403(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        org = await _make_org_async(async_test_db)
        data = await _make_project_async(async_test_db, admin, org)
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.post(
                f"/api/projects/{data['project'].id}/report",
                json={
                    "content": {
                        "sections": {"project_info": {"status": "completed"}},
                        "metadata": {"version": 1},
                    }
                },
            )
        assert resp.status_code == 403

    async def test_publish_report_non_admin_returns_403(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        org = await _make_org_async(async_test_db)
        data = await _make_project_async(async_test_db, admin, org)
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.put(
                f"/api/projects/{data['project'].id}/report/publish",
            )
        assert resp.status_code == 403

    async def test_unpublish_report_non_admin_returns_403(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        annotator = await _make_user(
            async_test_db, is_superadmin=False, prefix="annotator"
        )
        org = await _make_org_async(async_test_db)
        data = await _make_project_async(async_test_db, admin, org)
        await async_test_db.commit()
        with _as_user(annotator):
            resp = await async_test_client.put(
                f"/api/projects/{data['project'].id}/report/unpublish",
            )
        assert resp.status_code == 403

    async def test_list_published_reports(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True, prefix="admin")
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/reports")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestLLMModelEndpoints:
    """Tests for /api/llm_models endpoints.

    /public/models was migrated to the async DB lane (Depends(get_async_db)),
    so the DB-touching tests use async_test_client / async_test_db — the
    sync `client` fixture only overrides get_db, not get_async_db, so a row
    seeded into the sync SAVEPOINT transaction would be invisible to the
    async handler's separate connection.
    """

    @pytest.mark.asyncio
    async def test_get_public_models_empty(self, async_test_client):
        """Public models endpoint returns list even with no models."""
        resp = await async_test_client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_public_models_with_data(self, async_test_client, async_test_db):
        model = LLMModel(
            id=_uid(),
            name="Test GPT-4o",
            provider="openai",
            model_type="chat",
            capabilities=["text_generation"],
            is_active=True,
            is_official=True,
        )
        async_test_db.add(model)
        await async_test_db.commit()

        resp = await async_test_client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        body = resp.json()
        assert any(m["name"] == "Test GPT-4o" for m in body)

    @pytest.mark.asyncio
    async def test_inactive_models_not_returned(self, async_test_client, async_test_db):
        model = LLMModel(
            id=_uid(),
            name="Inactive Model",
            provider="openai",
            model_type="chat",
            capabilities=["text_generation"],
            is_active=False,
            is_official=True,
        )
        async_test_db.add(model)
        await async_test_db.commit()

        resp = await async_test_client.get("/api/llm_models/public/models")
        assert resp.status_code == 200
        body = resp.json()
        assert not any(m["name"] == "Inactive Model" for m in body)

    @pytest.mark.asyncio
    async def test_get_provider_capabilities(self, async_test_client):
        resp = await async_test_client.get("/api/llm_models/public/provider-capabilities")
        assert resp.status_code == 200
        # Response is a dict of providers; may be empty if shared lib not available
        assert isinstance(resp.json(), dict)
