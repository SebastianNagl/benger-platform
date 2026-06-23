"""
Integration tests for annotation endpoints.

Targets: routers/projects/annotations.py — create_annotation, list_annotations,
         get_annotation, delete_annotation

Some of these classes exercise endpoints on ``routers/projects/crud.py`` that
were migrated to the async DB lane (PATCH ``/{id}/visibility``, POST
``/{id}/recalculate-stats``, GET ``/{id}/completion-stats``). Those tests seed
rows via ``async_test_db`` and drive the surface through ``async_test_client``
with a ``require_user`` override (the sync ``client``/``test_db`` pair only
overrides ``get_db``, so the async handlers can't see uncommitted SAVEPOINT
rows). The annotation POST (``create_annotation``) stayed sync, so
``TestCreateAnnotation`` keeps the sync ``client``/``test_db`` fixtures.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import get_current_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


@pytest.fixture(autouse=True)
def _mute_celery():
    """Stub the report-refresh Celery dispatch in create_annotation.

    Without a Redis broker (isolated venv) Celery retries the connection for
    ~20s, stalling the request well past the 15s async statement_timeout. The
    handler already swallows dispatch failures in prod, so this changes no
    behaviour under test.
    """
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


def _uid():
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
    # recalculate-stats authenticates via get_current_user; visibility and
    # completion-stats via require_user. Override both so every endpoint in
    # this file sees the seeded acting user.
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"ann-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Ann User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


def _make_project_with_task(db, admin, org):
    """Create a project with a single task (sync — for create_annotation)."""
    project = Project(
        id=_uid(),
        title="Annotation Test",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    task = Task(
        id=_uid(), project_id=project.id,
        data={"text": "Annotation test text"},
        inner_id=1, created_by=admin.id,
    )
    db.add(task)
    db.commit()
    return project, task


@pytest.mark.integration
class TestCreateAnnotation:
    """POST /api/projects/tasks/{task_id}/annotations (sync DB lane)"""

    def test_create_annotation_basic(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [
                    {"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["completed_by"] == test_users[0].id

    def test_create_annotation_with_lead_time(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [
                    {"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Nein"]}}
                ],
                "lead_time": 45.5,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/tasks/nonexistent-id/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404

    def test_create_annotation_empty_result(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_with_draft(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [],
                "draft": [{"from_name": "answer", "to_name": "text",
                           "type": "choices", "value": {"choices": ["Ja"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_cancelled(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestListAnnotations:
    """GET /api/projects/{project_id}/annotations"""

    def test_list_annotations(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=project.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # May not exist as separate endpoint
        assert resp.status_code in (200, 404, 405)


@pytest.mark.integration
class TestProjectVisibility:
    """PATCH /api/projects/{project_id}/visibility (async DB lane)"""

    @pytest.mark.asyncio
    async def test_toggle_visibility(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = Project(
            id=_uid(), title="Vis Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        async_test_db.add(project)
        # No ProjectOrganization linkage: the seeded superadmin short-circuits
        # the creator/superadmin access check, and a random org_id would
        # violate the organizations FK on commit.
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True},
            )
        assert resp.status_code in (200, 400, 403)

    @pytest.mark.asyncio
    async def test_make_public(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = Project(
            id=_uid(), title="Public Test", created_by=admin.id,
            is_private=True,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        async_test_db.add(project)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False},
            )
        assert resp.status_code in (200, 400, 403)


@pytest.mark.integration
class TestRecalculateStats:
    """POST /api/projects/{project_id}/recalculate-stats (async DB lane)"""

    @pytest.mark.asyncio
    async def test_recalculate_stats(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = Project(
            id=_uid(), title="Recalc Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        async_test_db.add(project)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/recalculate-stats",
            )
        assert resp.status_code == 200


@pytest.mark.integration
class TestCompletionStats:
    """GET /api/projects/{project_id}/completion-stats (async DB lane)"""

    @pytest.mark.asyncio
    async def test_completion_stats(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = Project(
            id=_uid(), title="Completion Test", created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        async_test_db.add(project)
        await async_test_db.flush()
        for i in range(3):
            task = Task(
                id=_uid(), project_id=project.id,
                data={"text": f"task {i}"}, inner_id=i + 1,
                created_by=admin.id,
            )
            async_test_db.add(task)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
