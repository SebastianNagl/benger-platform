"""
Integration tests for annotation management endpoints.

Targets: routers/projects/annotations.py — 8.91% coverage (118 uncovered lines)
Uses real PostgreSQL with per-test transaction rollback.

The GET ``list_task_annotations`` and PATCH ``update_annotation`` handlers were
migrated to the async DB lane (``Depends(get_async_db)``). Tests exercising
those endpoints seed rows via ``async_test_db`` and drive the HTTP surface
through ``async_test_client`` with a ``require_user`` override — the sync
``client``/``test_db`` pair only overrides ``get_db``, so an async handler can't
see uncommitted SAVEPOINT rows. The POST ``create_annotation`` handler STAYED on
the sync DB lane (it calls sync-only extension hooks), so ``TestCreateAnnotation``
keeps the sync ``client``/``test_db`` fixtures.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
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
    """Stub the report-refresh Celery dispatch in create/update_annotation.

    The handlers call ``get_celery_app().send_task(...)`` for the async report
    update. With no Redis broker (as in the isolated venv) Celery retries the
    connection for ~20s, which on the async lane outlives the 15s
    statement_timeout and cancels the in-flight transaction. Stubbing the
    dispatch keeps the request fast and deterministic; the handler already
    swallows dispatch failures in prod, so behaviour under test is unchanged.
    """
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


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


def _setup(db, admin, org, *, num_tasks=2, assignment_mode="open", max_annotations=10,
           min_annotations_per_task=1, conditional_instructions=None):
    """Create project with tasks linked to org (sync — for create_annotation)."""
    project = Project(
        id=_uid(),
        title=f"Ann Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode=assignment_mode,
        maximum_annotations=max_annotations,
        min_annotations_per_task=min_annotations_per_task,
        conditional_instructions=conditional_instructions,
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Annotate me #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)
    db.commit()
    return project, tasks


async def _setup_async(db, admin, *, num_tasks=2, assignment_mode="open",
                       max_annotations=10, min_annotations_per_task=1):
    """Async twin of ``_setup`` — for the migrated list/update endpoints.

    The acting user is seeded as a superadmin, which short-circuits every
    access check, so no org/ProjectOrganization linkage is required.
    """
    project = Project(
        id=_uid(),
        title=f"Ann Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode=assignment_mode,
        maximum_annotations=max_annotations,
        min_annotations_per_task=min_annotations_per_task,
    )
    db.add(project)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Annotate me #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()
    return project, tasks


async def _seed_annotation(db, task, project, completed_by, *, result=None,
                           was_cancelled=False):
    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=completed_by,
        result=result if result is not None else [
            {"from_name": "text", "to_name": "text", "type": "textarea",
             "value": {"text": ["x"]}}
        ],
        was_cancelled=was_cancelled,
    )
    db.add(ann)
    await db.flush()
    return ann


@pytest.mark.integration
class TestCreateAnnotation:
    """POST /api/projects/tasks/{task_id}/annotations (sync DB lane)"""

    def test_create_annotation_success(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [
                    {"from_name": "text", "to_name": "text", "type": "textarea",
                     "value": {"text": ["Test annotation"]}}
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == tasks[0].id
        assert data["result"] is not None

    def test_strict_timer_duplicate_submit_updates_in_place(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """On a strict-timer project, a second submit for the same (task, user)
        — the client/worker auto-submit race or an auto-then-manual submit —
        UPDATES the one annotation (latest content wins) instead of inserting a
        duplicate row."""
        project = Project(
            id=_uid(), title="Timer Dup", created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
            assignment_mode="open", maximum_annotations=10, min_annotations_per_task=1,
            strict_timer_enabled=True,
        )
        test_db.add(project)
        test_db.flush()
        test_db.add(ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=test_org.id,
            assigned_by=test_users[0].id,
        ))
        task = Task(id=_uid(), project_id=project.id, data={"text": "sv"},
                    inner_id=1, created_by=test_users[0].id)
        test_db.add(task)
        test_db.commit()

        hdr = {**auth_headers["admin"], "X-Organization-Context": test_org.id}
        url = f"/api/projects/tasks/{task.id}/annotations"
        r1 = client.post(url, json={
            "result": [{"from_name": "text", "to_name": "text", "type": "textarea",
                        "value": {"text": ["short auto"]}}],
            "auto_submitted": True,
        }, headers=hdr)
        r2 = client.post(url, json={
            "result": [{"from_name": "text", "to_name": "text", "type": "textarea",
                        "value": {"text": ["full manual answer"]}}],
            "auto_submitted": False,
        }, headers=hdr)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text

        test_db.expire_all()
        anns = (
            test_db.query(Annotation)
            .filter(Annotation.task_id == task.id,
                    Annotation.completed_by == test_users[0].id,
                    Annotation.was_cancelled == False)  # noqa: E712
            .all()
        )
        assert len(anns) == 1, "duplicate submit must update in place, not insert"
        assert "full manual answer" in str(anns[0].result), "latest content wins"
        assert anns[0].auto_submitted is False
        assert r1.json()["id"] == r2.json()["id"]
        # counter must not double-count the in-place update
        test_db.refresh(task)
        assert task.total_annotations == 1

    def test_non_timer_project_does_not_dedup(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Non-timer projects keep the prior behavior — the dedup guard is scoped
        to strict-timer projects, so this path is unchanged."""
        project, tasks = _setup(test_db, test_users[0], test_org)
        hdr = {**auth_headers["admin"], "X-Organization-Context": test_org.id}
        url = f"/api/projects/tasks/{tasks[0].id}/annotations"
        body = {"result": [{"from_name": "text", "to_name": "text", "type": "textarea",
                            "value": {"text": ["a"]}}]}
        assert client.post(url, json=body, headers=hdr).status_code == 200
        assert client.post(url, json=body, headers=hdr).status_code == 200
        test_db.expire_all()
        n = (
            test_db.query(Annotation)
            .filter(Annotation.task_id == tasks[0].id,
                    Annotation.completed_by == test_users[0].id)
            .count()
        )
        assert n == 2  # no dedup on non-timer projects

    def test_create_annotation_task_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/tasks/nonexistent-task/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404

    def test_create_cancelled_annotation(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] == True  # noqa: E712

    def test_create_annotation_with_enhanced_timing(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["timed"]}}],
                "lead_time": 45.5,
                "active_duration_ms": 40000,
                "focused_duration_ms": 35000,
                "tab_switches": 3,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active_duration_ms") == 40000
        assert data.get("tab_switches") == 3

    def test_create_annotation_with_instruction_variant(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(
            test_db, test_users[0], test_org,
            conditional_instructions=[
                {"id": "variant-1", "content": "Do this", "weight": 1, "ai_allowed": True},
                {"id": "variant-2", "content": "Do that", "weight": 1, "ai_allowed": False},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["ai"]}}],
                "instruction_variant": "variant-1",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["instruction_variant"] == "variant-1"
        assert data["ai_assisted"] == True  # noqa: E712

    def test_annotation_marks_task_labeled(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, min_annotations_per_task=1)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["done"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        # Check task is labeled
        test_db.refresh(tasks[0])
        assert tasks[0].is_labeled == True  # noqa: E712


@pytest.mark.integration
class TestListAnnotations:
    """GET /api/projects/tasks/{task_id}/annotations (async DB lane)"""

    @pytest.mark.asyncio
    async def test_list_annotations_empty(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}/annotations",
            )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_annotations_after_create(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin)
        await _seed_annotation(async_test_db, tasks[0], project, admin.id)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}/annotations",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_annotations_all_users(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin)
        await _seed_annotation(
            async_test_db, tasks[0], project, admin.id,
            result=[{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["admin"]}}],
        )
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}/annotations?all_users=true",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_annotations_task_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/tasks/nonexistent/annotations",
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestUpdateAnnotation:
    """PATCH /api/projects/annotations/{annotation_id} (async DB lane)"""

    @pytest.mark.asyncio
    async def test_update_annotation_result(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin)
        ann = await _seed_annotation(
            async_test_db, tasks[0], project, admin.id,
            result=[{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["original"]}}],
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["updated"]}}]},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_annotation_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/annotations/nonexistent-ann-id",
                json={"result": []},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_annotation_cancel_status(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin)
        # Seed a non-cancelled annotation.
        ann = await _seed_annotation(
            async_test_db, tasks[0], project, admin.id,
            result=[{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel me"]}}],
            was_cancelled=False,
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel me"]}}],
                    "was_cancelled": True,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] == True  # noqa: E712
