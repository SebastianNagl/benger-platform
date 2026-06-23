"""
Unit tests for routers/projects/tasks/* covering uncovered lines.

The task router handlers in ``listing.py``, ``fields.py``, ``metadata_ops.py``
and ``mutations.py`` were migrated to the async DB lane (``async def`` +
``db: AsyncSession = Depends(get_async_db)`` + ``await db.execute(select(...))``),
so the old ``MagicMock(spec=Session)`` / sync-helper-patch pattern no longer
reaches the handlers (a Mock is not an AsyncSession and the handlers call the
``_async`` helper twins). These now seed real rows via ``async_test_db`` and
drive the surface through ``async_test_client``; the exhaustive branch coverage
lives in ``tests/integration/test_project_tasks_branches.py``.

``bulk_export_tasks`` (export.py) stays on the SYNC lane — those tests still
use the sync ``client`` + ``test_db`` fixtures.

``extract_fields_from_data`` is a PURE helper (no DB) — its test class is left
unchanged.

NOTE: not runnable in this static-analysis environment (no test DB +
pytest-asyncio); verified via compile + ruff only.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, SkippedTask, Task


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
        username=f"tasks-unit-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Tasks Unit User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, assignment_mode="open", require_comment_on_skip=False,
                        is_private=True):
    p = Project(
        id=_uid(),
        title=f"Tasks Unit {uuid.uuid4().hex[:6]}",
        description="tasks unit coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        is_private=is_private,
        assignment_mode=assignment_mode,
        require_comment_on_skip=require_comment_on_skip,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project, owner, *, data=None, meta=None, inner_id=1):
    t = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data=data if data is not None else {"text": "Sample text"},
        meta=meta,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(t)
    await db.flush()
    return t


async def _share_org(db, project, member, *, role="ANNOTATOR"):
    """Attach a freshly-seeded org to ``project`` and give ``member`` a
    (non-admin by default) membership in it. This makes the project ACCESSIBLE
    to ``member`` (shared-org legacy access) so that handler tests can reach the
    *edit/permission* check rather than short-circuiting on the project-access
    check. An org-less, non-private project is only accessible to its creator,
    so without this an outsider gets "Access denied" before the edit check runs.
    """
    org = Organization(
        id=_uid(),
        name=f"Org {uuid.uuid4().hex[:6]}",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        display_name="Test Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=project.created_by,
        )
    )
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=member.id,
            organization_id=org.id,
            role=role,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return org


# ============= extract_fields_from_data (PURE — UNCHANGED) =============


class TestExtractFieldsFromData:
    """Test extract_fields_from_data helper."""

    def test_empty_dict(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({})
        assert result == []

    def test_non_dict_input(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data("not a dict")
        assert result == []

    def test_string_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"text": "Hello world"})
        assert len(result) == 1
        assert result[0]["path"] == "$text"
        assert result[0]["data_type"] == "string"
        assert result[0]["sample_value"] == "Hello world"

    def test_long_string_truncation(self):
        from routers.projects.tasks import extract_fields_from_data

        long_text = "x" * 200
        result = extract_fields_from_data({"content": long_text})
        assert result[0]["sample_value"].endswith("...")
        assert len(result[0]["sample_value"]) == 103  # 100 chars + "..."

    def test_nested_dict(self):
        from routers.projects.tasks import extract_fields_from_data

        data = {"context": {"jurisdiction": "DE", "type": "civil"}}
        result = extract_fields_from_data(data)

        # Should have the parent object + 2 nested fields
        paths = [f["path"] for f in result]
        assert "$context" in paths
        assert "$context.jurisdiction" in paths
        assert "$context.type" in paths

    def test_list_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"items": [1, 2, 3]})
        assert result[0]["data_type"] == "array"
        assert result[0]["sample_value"] == "[3 items]"

    def test_number_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"score": 42.5})
        assert result[0]["data_type"] == "number"
        assert result[0]["sample_value"] == "42.5"

    def test_boolean_field(self):
        from routers.projects.tasks import extract_fields_from_data

        # Note: In Python, isinstance(True, (int, float)) == True because bool subclasses int.
        # The code checks (int, float) before bool, so booleans are classified as "number".
        result = extract_fields_from_data({"is_active": True})
        assert result[0]["data_type"] == "number"
        assert result[0]["sample_value"] == "True"

    def test_none_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"value": None})
        assert result[0]["data_type"] == "unknown"
        assert result[0]["sample_value"] is None

    def test_sensitive_fields_filtered(self):
        from routers.projects.tasks import extract_fields_from_data

        data = {
            "text": "Question",
            "annotations": "should be filtered",
            "ground_truth": "should be filtered",
            "reference_answer": "should be filtered",
        }
        result = extract_fields_from_data(data)
        paths = [f["path"] for f in result]
        assert "$text" in paths
        assert "$annotations" not in paths
        assert "$ground_truth" not in paths
        assert "$reference_answer" not in paths

    def test_is_nested_flag(self):
        from routers.projects.tasks import extract_fields_from_data

        data = {"context": {"inner": "value"}}
        result = extract_fields_from_data(data)

        parent = next(f for f in result if f["path"] == "$context")
        child = next(f for f in result if f["path"] == "$context.inner")
        assert parent["is_nested"] == False  # noqa: E712
        assert child["is_nested"] == True  # noqa: E712


# ============= list_project_tasks =============


class TestListProjectTasks:
    """Test list_project_tasks endpoint (GET /api/projects/{id}/tasks)."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/tasks")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        # Owner creates a private project; a different non-superadmin user with
        # no membership / no org context cannot access it -> 403.
        owner = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(outsider):
            resp = await async_test_client.get(f"/api/projects/{project.id}/tasks")
        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()


# ============= get_next_task =============


class TestGetNextTask:
    """Test get_next_task endpoint (GET /api/projects/{id}/next)."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        # get_next_task returns a 200 dict {detail, task: None}, NOT a 404.
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is None
        assert "not found" in body["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(outsider):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()


# ============= get_task =============


class TestGetTask:
    """Test get_task endpoint (GET /api/projects/tasks/{task_id})."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/tasks/{_uid()}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project, owner)
        await async_test_db.commit()
        with _as_user(outsider):
            resp = await async_test_client.get(f"/api/projects/tasks/{task.id}")
        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_task_success(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, data={"text": "Sample text"})
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/tasks/{task.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == task.id
        assert body["data"] == {"text": "Sample text"}


# ============= update_task_metadata =============


class TestUpdateTaskMetadata:
    """Test update_task_metadata (PATCH /api/projects/tasks/{task_id}/metadata)."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{_uid()}/metadata", json={"key": "value"}
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_merge_metadata(self, async_test_client, async_test_db):
        # Old mock_db.commit.assert_called_once() -> re-query the row and assert
        # the merged metadata was persisted.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, meta={"existing": "value"})
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata?merge=true",
                json={"new_key": "new_value"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Metadata updated successfully"
        assert body["meta"]["existing"] == "value"
        assert body["meta"]["new_key"] == "new_value"

        await async_test_db.commit()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.meta == {"existing": "value", "new_key": "new_value"}

    @pytest.mark.asyncio
    async def test_replace_metadata(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, meta={"existing": "value"})
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata?merge=false",
                json={"replaced": "data"},
            )
        assert resp.status_code == 200
        assert resp.json()["meta"] == {"replaced": "data"}

        await async_test_db.commit()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.meta == {"replaced": "data"}

    @pytest.mark.asyncio
    async def test_metadata_init_from_none(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, meta=None)
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata?merge=true",
                json={"key": "value"},
            )
        assert resp.status_code == 200
        assert resp.json()["meta"] == {"key": "value"}

        await async_test_db.commit()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.meta == {"key": "value"}


# ============= bulk_update_task_metadata =============


class TestBulkUpdateTaskMetadata:
    """Test bulk_update_task_metadata (PATCH /api/projects/tasks/bulk-metadata)."""

    @pytest.mark.asyncio
    async def test_no_tasks_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=true",
                json={"task_ids": [_uid()], "metadata": {"key": "val"}},
            )
        assert resp.status_code == 404
        assert "No tasks found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bulk_merge(self, async_test_client, async_test_db):
        # Old mock_db.commit.assert_called_once() -> re-query both rows and
        # assert the merged metadata persisted.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        t1 = await _make_task(async_test_db, project, user, meta={"existing": "data"}, inner_id=1)
        t2 = await _make_task(async_test_db, project, user, meta=None, inner_id=2)
        await async_test_db.commit()
        ids = [t1.id, t2.id]
        with _as_user(user):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=true",
                json={"task_ids": ids, "metadata": {"new": "value"}},
            )
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

        await async_test_db.commit()
        for tid in ids:
            refreshed = (
                await async_test_db.execute(select(Task).where(Task.id == tid))
            ).scalar_one()
            assert refreshed.meta.get("new") == "value"
        # t1 kept its existing key (merge).
        r1 = (await async_test_db.execute(select(Task).where(Task.id == t1.id))).scalar_one()
        assert r1.meta.get("existing") == "data"

    @pytest.mark.asyncio
    async def test_bulk_replace(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, meta={"old": "data"})
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=false",
                json={"task_ids": [task_id], "metadata": {"new": "data"}},
            )
        assert resp.status_code == 200

        await async_test_db.commit()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.meta == {"new": "data"}


# ============= update_task_data =============


class TestUpdateTaskData:
    """Test update_task_data (PUT /api/projects/{project_id}/tasks/{task_id})."""

    @pytest.mark.asyncio
    async def test_non_superadmin_denied(self, async_test_client, async_test_db):
        # A non-superadmin who is NOT the creator and not an org admin is denied
        # editing task data. The editor shares the project's org (so the
        # project-access check passes) but only as ANNOTATOR, so the edit-data
        # check (superadmin / creator / org-admin only) returns False.
        owner = await _make_user(async_test_db)
        editor = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner, is_private=False)
        await _share_org(async_test_db, project, editor, role="ANNOTATOR")
        task = await _make_task(async_test_db, project, owner)
        await async_test_db.commit()
        with _as_user(editor):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{task.id}",
                json={"data": {"text": "new"}},
            )
        # Access check (org-less non-private project is accessible) passes; the
        # edit-data check fails -> 403 "Only superadmins or organization admins".
        assert resp.status_code == 403
        assert "superadmin" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.put(
                f"/api/projects/{_uid()}/tasks/{_uid()}",
                json={"data": {"text": "new"}},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_data_provided(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{task.id}",
                json={"data": {}},
            )
        assert resp.status_code == 400
        assert "No data provided" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_success(self, async_test_client, async_test_db):
        # Old assertions on the mock task object -> re-query and assert the
        # merged data + appended audit_log persisted.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(
            async_test_db, project, user, data={"text": "old text"}, meta={}
        )
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{task_id}",
                json={"data": {"text": "new text"}},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["text"] == "new text"

        await async_test_db.commit()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.data["text"] == "new text"
        assert "audit_log" in refreshed.meta
        assert len(refreshed.meta["audit_log"]) == 1

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch(
        "routers.projects.tasks.mutations.check_user_can_edit_task_data_async",
        new_callable=AsyncMock,
        return_value=True,
    )
    async def test_update_db_error(self, mock_can_edit, mock_flag):
        """A commit failure rolls back and raises 500 'Failed to update'.

        Restored from HEAD (test_tasks_coverage.py::TestUpdateTaskData.
        test_update_db_error), adapted to the async handler signature. The
        handler is now ``async def update_task_data(... db: AsyncSession,
        access: ProjectAccess)`` and reaches the rollback branch only when
        ``await db.commit()`` raises (mutations.py:153-155). A real
        ``async_test_db`` commit can't be made to fail mid-test, so this drives
        the handler directly with an ``AsyncMock`` db whose ``commit`` raises —
        the same approach HEAD used (a Mock db with ``commit.side_effect``),
        translated to the async lane.
        """
        from routers.projects.deps import ProjectAccess
        from routers.projects.tasks.mutations import update_task_data

        project = MagicMock()
        project.id = "proj-1"

        task = Task(
            id="task-1",
            project_id="proj-1",
            inner_id=1,
            data={"text": "old"},
            meta={},
            created_by="user-1",
            updated_by="user-1",
        )

        # AsyncMock db: the single select() returns the task; commit() raises so
        # the except branch runs rollback() + HTTPException(500).
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = task
        db.execute.return_value = result
        db.commit.side_effect = Exception("DB error")

        current_user = MagicMock()
        current_user.id = "user-1"
        current_user.email = "user-1@example.com"
        current_user.is_superadmin = True

        access = ProjectAccess(project=project, user=current_user, org_context=None)

        with pytest.raises(HTTPException) as exc_info:
            await update_task_data(
                project_id="proj-1",
                task_id="task-1",
                data={"data": {"text": "new"}},
                current_user=current_user,
                db=db,
                access=access,
            )

        assert exc_info.value.status_code == 500
        assert "Failed to update" in str(exc_info.value.detail)
        db.rollback.assert_awaited_once()


# ============= bulk_delete_tasks =============


class TestBulkDeleteTasks:
    """Test bulk_delete_tasks (POST /api/projects/{project_id}/tasks/bulk-delete)."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/tasks/bulk-delete",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_client, async_test_db):
        # A non-superadmin who is not the creator and has no edit permission on
        # an accessible project -> 403 Permission denied. The outsider shares the
        # project's org (so project-access passes) but only as ANNOTATOR, so the
        # bulk-delete permission check (creator/superadmin/org-admin/contributor)
        # fails.
        owner = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner, is_private=False)
        await _share_org(async_test_db, project, outsider, role="ANNOTATOR")
        task = await _make_task(async_test_db, project, owner)
        await async_test_db.commit()
        with _as_user(outsider):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": [task.id]},
            )
        assert resp.status_code == 403
        assert "Permission denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_success(self, async_test_client, async_test_db):
        # Old: result["deleted"] count from mock rowcounts -> seed real tasks,
        # assert the count AND that the rows are gone from the DB.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        t1 = await _make_task(async_test_db, project, user, inner_id=1)
        t2 = await _make_task(async_test_db, project, user, inner_id=2)
        await async_test_db.commit()
        ids = [t1.id, t2.id]
        with _as_user(user), patch(
            "routers.projects.tasks.mutations._update_report_data_section_sync"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": ids},
            )
        assert resp.status_code == 200
        result = resp.json()
        assert result["deleted"] == 2

        await async_test_db.commit()
        remaining = (
            await async_test_db.execute(select(Task).where(Task.id.in_(ids)))
        ).scalars().all()
        assert remaining == []


# ============= bulk_export_tasks (SYNC — unchanged DB lane) =============


class TestBulkExportTasks:
    """Test bulk_export_tasks (POST /api/projects/{project_id}/tasks/bulk-export).

    This handler stays on the SYNC DB lane (``db: Session = Depends(get_db)``),
    so these tests use the sync ``client`` + ``test_db`` fixtures rather than
    the async ones.
    """

    def _seed_sync_user(self, db, *, is_superadmin=True):
        u = User(
            id=_uid(),
            username=f"export-unit-{_uid()[:8]}",
            email=f"{_uid()[:8]}@example.com",
            name="Export Unit User",
            is_superadmin=is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(u)
        db.flush()
        return u

    def _seed_sync_project(self, db, owner):
        p = Project(
            id=_uid(),
            title=f"Export Unit {uuid.uuid4().hex[:6]}",
            description="export unit coverage",
            label_config='<View><Text name="text" value="$text"/></View>',
            created_by=owner.id,
            is_published=True,
            is_private=True,
            assignment_mode="open",
        )
        db.add(p)
        db.flush()
        return p

    def test_project_not_found(self, client, test_db):
        user = self._seed_sync_user(test_db)
        test_db.commit()
        with _as_user(user):
            resp = client.post(
                f"/api/projects/{_uid()}/tasks/bulk-export",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_export_unsupported_format(self, client, test_db):
        user = self._seed_sync_user(test_db)
        project = self._seed_sync_project(test_db, user)
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={"text": "test"},
            created_by=user.id,
            updated_by=user.id,
        )
        test_db.add(task)
        test_db.commit()
        with _as_user(user):
            resp = client.post(
                f"/api/projects/{project.id}/tasks/bulk-export",
                json={"task_ids": [task.id], "format": "xml"},
            )
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]


# ============= bulk_archive_tasks =============


class TestBulkArchiveTasks:
    """Test bulk_archive_tasks (POST /api/projects/{project_id}/tasks/bulk-archive)."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/tasks/bulk-archive",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_client, async_test_db):
        # bulk_archive permission is creator-or-superadmin only. The outsider
        # shares the project's org (so project-access passes) but is not the
        # creator nor a superadmin, so the archive permission check fails.
        owner = await _make_user(async_test_db)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner, is_private=False)
        await _share_org(async_test_db, project, outsider, role="ANNOTATOR")
        await async_test_db.commit()
        with _as_user(outsider):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-archive",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 403
        assert "Permission denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_archive_success(self, async_test_client, async_test_db):
        # Old: task.meta["is_archived"] on the mock -> re-query and assert it
        # persisted.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user, meta={})
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-archive",
                json={"task_ids": [task_id]},
            )
        assert resp.status_code == 200
        assert resp.json()["archived"] == 1

        await async_test_db.commit()
        # async_test_db (expire_on_commit=False) is the same session the handler
        # mutated, so the cached Task carries the in-memory meta change even if
        # flag_modified was missing / nothing persisted. expire_all() forces a
        # real round-trip so this re-read would actually catch a lost write.
        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed.meta["is_archived"] is True


# ============= skip_task =============


class TestSkipTask:
    """Test skip_task (POST /api/projects/{project_id}/tasks/{task_id}/skip)."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{_uid()}/skip",
                json={},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_comment_required(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, user, require_comment_on_skip=True
        )
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/skip",
                json={},
            )
        assert resp.status_code == 400
        assert "Comment is required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_skip_success(self, async_test_client, async_test_db):
        # Old: mock_db.add/commit assertions on the SkippedTask -> re-query the
        # persisted SkippedTask row and assert its fields.
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        task_id = task.id
        with _as_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{task_id}/skip",
                json={"comment": "Too difficult"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == task_id
        assert body["comment"] == "Too difficult"

        await async_test_db.commit()
        record = (
            await async_test_db.execute(
                select(SkippedTask).where(
                    SkippedTask.task_id == task_id,
                    SkippedTask.skipped_by == user.id,
                )
            )
        ).scalar_one()
        assert record.comment == "Too difficult"


# ============= get_task_data_fields =============


class TestGetTaskDataFields:
    """Test get_task_data_fields (GET /api/projects/{project_id}/task-fields)."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/task-fields")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_tasks(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fields"] == []
        assert body["sample_task_count"] == 0

    @pytest.mark.asyncio
    async def test_fields_discovered(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, user)
        await _make_task(
            async_test_db,
            project,
            user,
            data={"text": "Hello", "score": 42, "context": {"type": "legal"}},
        )
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_task_count"] == 1
        paths = [f["path"] for f in body["fields"]]
        assert "$text" in paths
        assert "$score" in paths
