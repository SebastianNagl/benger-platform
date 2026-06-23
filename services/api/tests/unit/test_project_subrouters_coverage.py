"""
Unit tests for routers/projects/ subrouters — covers access control branches.
Tests use direct function calls with mocked DB to cover internal logic.

Handlers on the async DB lane (``Depends(get_async_db)`` + ``await db.execute``)
get an ``AsyncMock``-backed fake session via :func:`_async_db_returning`;
handlers still on the sync DB lane keep the ``Mock``-``db.query`` style.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException


def _async_db_returning(scalar=None, scalars_list=None):
    """Build a fake AsyncSession whose ``await db.execute(...)`` resolves to a
    result object yielding ``scalar`` from ``.scalar_one_or_none()`` and
    ``scalars_list`` from ``.scalars().all()``. Mirrors just enough of the
    async result API for the project-not-found / access preamble branches."""
    result = Mock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar.return_value = scalar
    scalars = Mock()
    scalars.all.return_value = scalars_list or []
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    db = Mock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock(return_value=scalar)
    return db


# ============= projects/tasks.py =============


class TestListProjectTasks:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        # list_project_tasks delegates project existence + read access to the
        # `require_project_access` dependency, so the 404 now lives there.
        from routers.projects.deps import require_project_access
        dep = require_project_access()
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await dep(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.projects.deps import require_project_access
        dep = require_project_access()
        project = Mock()
        db = _async_db_returning(scalar=project)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch(
            "routers.projects.deps.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await dep(project_id="proj-1", request=request, current_user=user, db=db)
            assert exc_info.value.status_code == 403


class TestSkipTask:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.tasks import skip_task
        from project_schemas import SkipTaskRequest
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await skip_task(project_id="proj-1", task_id="task-1",
                           request=request, skip_request=SkipTaskRequest(),  # noqa: E128
                           current_user=user, db=db)  # noqa: E128
        assert exc_info.value.status_code == 404


# ============= projects/assignments.py =============


class TestAssignTasks:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.assignments import assign_tasks
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await assign_tasks(project_id="proj-1", data={},
                             current_user=user, db=db)  # noqa: E128
        assert exc_info.value.status_code == 404


class TestListTaskAssignments:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        # list_task_assignments is on the async DB lane now.
        from routers.projects.assignments import list_task_assignments
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_task_assignments(project_id="proj-1", task_id="task-1",
                                       request=request, current_user=user, db=db)  # noqa: E128
        assert exc_info.value.status_code == 404


class TestRemoveTaskAssignment:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.assignments import remove_task_assignment
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await remove_task_assignment(project_id="proj-1", task_id="task-1",
                                        assignment_id="a-1", current_user=user, db=db)  # noqa: E128
        assert exc_info.value.status_code == 404


# Note: TestGetProjectWorkload was removed — the get_project_workload
# function no longer exists in routers.projects.assignments.


class TestGetMyTasks:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.assignments import get_my_tasks
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_my_tasks(project_id="proj-1", request=request,
                             page=1, page_size=30, status=None,  # noqa: E128
                             current_user=user, db=db)  # noqa: E128
        assert exc_info.value.status_code == 404


# ============= projects/members.py =============


class TestListProjectMembers:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        # list_project_members delegates the 404 to require_project_access.
        from routers.projects.deps import require_project_access
        dep = require_project_access()
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await dep(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestGetProjectAnnotators:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        # get_project_annotators delegates the 404 to require_project_access.
        from routers.projects.deps import require_project_access
        dep = require_project_access()
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await dep(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


# ============= projects/reviews.py =============


class TestListQuestionnaireResponses:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        # list_questionnaire_responses now delegates the project-existence /
        # access preamble to the require_project_access dependency, so the 404
        # is enforced there (not inline in the handler).
        from routers.projects.deps import require_project_access
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        dependency = require_project_access(min_role="edit")
        with pytest.raises(HTTPException) as exc_info:
            await dependency(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


# ============= projects/label_config_versions.py =============


class TestGetLabelConfigVersions:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.label_config_versions import get_label_config_versions
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_label_config_versions(
                project_id="proj-1", request=request,
                current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404


class TestGetLabelConfigVersion:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.label_config_versions import get_label_config_version
        db = _async_db_returning(scalar=None)
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_label_config_version(
                project_id="proj-1", version=1,
                request=request, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404


# ============= projects/organizations.py =============


# Note: TestListProjectOrganizations was removed — per-project
# organization listing/assignment endpoints (routers/projects/organizations.py)
# were removed; org assignment now flows through PATCH /{id}/visibility.


# ============= projects/import_export.py =============


# Note: TestExportProject was removed — the synchronous GET /{id}/export
# handler (export_project) was deleted in the #158 follow-up. Export now runs
# only through the async object-storage job flow (POST /{id}/exports); its
# not-found / access-denied paths are covered in
# tests/integration/test_export_jobs_api.py.
