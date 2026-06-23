"""Tests for post-annotation questionnaire endpoints (Issue #1208).

The questionnaire router was migrated to the async DB lane
(``Depends(get_async_db)``) and the access preamble now flows through the
``require_project_access`` dependency, which resolves the *async* helpers
(``check_project_accessible_async`` / ``check_user_can_edit_project_async``)
on ``routers.projects.deps``. The task-assignment gate inside the handler is
likewise the async helper (``check_task_assigned_to_user_async``).

These tests therefore seed real ``Project`` / ``Task`` / ``Annotation`` rows via
``async_test_db`` and drive the surface through ``async_test_client`` with
``require_user`` overridden per-test. Access-control helpers (not under test
here) are patched as ``AsyncMock`` so each test isolates the questionnaire
logic — the assertions (200 success, 400 duplicate, 400 disabled, 404
nonexistent annotation, 200 creator/superadmin list, 403 denied) are unchanged.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, PostAnnotationResponse, Project, Task


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


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"q-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Questionnaire User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, *, created_by, questionnaire_enabled=True):
    p = Project(
        id=_uid(),
        title="Questionnaire Project",
        created_by=created_by,
        questionnaire_enabled=questionnaire_enabled,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, *, project_id, inner_id=1):
    t = Task(
        id=_uid(),
        project_id=project_id,
        data={"text": "sample"},
        inner_id=inner_id,
    )
    db.add(t)
    await db.flush()
    return t


async def _make_annotation(db, *, task_id, project_id, completed_by):
    a = Annotation(
        id=_uid(),
        task_id=task_id,
        project_id=project_id,
        completed_by=completed_by,
        result=[{"from_name": "q1", "to_name": "q1", "type": "choices",
                 "value": {"choices": ["yes"]}}],
    )
    db.add(a)
    await db.flush()
    return a


# Access-control helpers (not under test here) — patched permissive by default.
def _patch_access(*, accessible=True, can_edit=True, assigned=True):
    return [
        patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=accessible),
        ),
        patch(
            "routers.projects.deps.check_user_can_edit_project_async",
            new=AsyncMock(return_value=can_edit),
        ),
        patch(
            "routers.projects.questionnaire.check_task_assigned_to_user_async",
            new=AsyncMock(return_value=assigned),
        ),
    ]


@pytest.mark.asyncio
class TestQuestionnaireEndpoints:
    """Test questionnaire endpoints at /api/projects/{pid}/tasks/{tid}/questionnaire-response"""

    async def test_submit_questionnaire_success(self, async_test_client, async_test_db):
        """Submit succeeds with valid data."""
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        task = await _make_task(async_test_db, project_id=project.id)
        annotation = await _make_annotation(
            async_test_db, task_id=task.id, project_id=project.id, completed_by=user.id
        )
        await async_test_db.commit()

        patches = _patch_access()
        with _as_user(user), patches[0], patches[1], patches[2]:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": annotation.id,
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices",
                                "value": {"choices": ["yes"]}}],
                },
            )
        assert response.status_code == 200
        # A real row was persisted.
        from sqlalchemy import select
        row = (
            await async_test_db.execute(
                select(PostAnnotationResponse).where(
                    PostAnnotationResponse.annotation_id == annotation.id
                )
            )
        ).scalar_one_or_none()
        assert row is not None

    async def test_submit_duplicate_rejected(self, async_test_client, async_test_db):
        """Duplicate responses rejected (400)."""
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        task = await _make_task(async_test_db, project_id=project.id)
        annotation = await _make_annotation(
            async_test_db, task_id=task.id, project_id=project.id, completed_by=user.id
        )
        async_test_db.add(
            PostAnnotationResponse(
                id=_uid(),
                annotation_id=annotation.id,
                task_id=task.id,
                project_id=project.id,
                user_id=user.id,
                result=[{"answer": "prior"}],
            )
        )
        await async_test_db.commit()

        patches = _patch_access()
        with _as_user(user), patches[0], patches[1], patches[2]:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": annotation.id,
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices",
                                "value": {"choices": ["yes"]}}],
                },
            )
        assert response.status_code == 400
        assert "already submitted" in response.json()["detail"]

    async def test_submit_disabled_questionnaire_rejected(self, async_test_client, async_test_db):
        """Disabled questionnaire rejected (400)."""
        user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=user.id, questionnaire_enabled=False
        )
        task = await _make_task(async_test_db, project_id=project.id)
        await async_test_db.commit()

        patches = _patch_access()
        with _as_user(user), patches[0], patches[1], patches[2]:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": _uid(),
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices",
                                "value": {"choices": ["yes"]}}],
                },
            )
        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    async def test_submit_nonexistent_annotation_rejected(self, async_test_client, async_test_db):
        """Non-existent annotation rejected (404)."""
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        task = await _make_task(async_test_db, project_id=project.id)
        await async_test_db.commit()

        patches = _patch_access()
        with _as_user(user), patches[0], patches[1], patches[2]:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/questionnaire-response",
                json={
                    "annotation_id": "nonexistent",
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices",
                                "value": {"choices": ["yes"]}}],
                },
            )
        assert response.status_code == 404

    async def test_list_responses_permission_creator(self, async_test_client, async_test_db):
        """Project creator can list questionnaire responses."""
        creator = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=creator.id)
        await async_test_db.commit()

        # creator passes the edit gate
        patches = _patch_access(can_edit=True)
        with _as_user(creator), patches[0], patches[1], patches[2]:
            response = await async_test_client.get(
                f"/api/projects/{project.id}/questionnaire-responses"
            )
        assert response.status_code == 200

    async def test_list_responses_permission_superadmin(self, async_test_client, async_test_db):
        """Superadmin can list questionnaire responses."""
        creator = await _make_user(async_test_db)
        superadmin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=creator.id)
        await async_test_db.commit()

        patches = _patch_access(can_edit=True)
        with _as_user(superadmin), patches[0], patches[1], patches[2]:
            response = await async_test_client.get(
                f"/api/projects/{project.id}/questionnaire-responses"
            )
        assert response.status_code == 200

    async def test_list_responses_permission_denied(self, async_test_client, async_test_db):
        """Non-creator, non-superadmin, non-contributor gets 403."""
        creator = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=creator.id)
        await async_test_db.commit()

        # accessible but no edit permission → 403 from the require_project_access dep
        patches = _patch_access(accessible=True, can_edit=False)
        with _as_user(outsider), patches[0], patches[1], patches[2]:
            response = await async_test_client.get(
                f"/api/projects/{project.id}/questionnaire-responses"
            )
        assert response.status_code == 403
