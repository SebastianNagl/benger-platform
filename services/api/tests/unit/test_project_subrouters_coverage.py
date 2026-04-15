"""
Unit tests for routers/projects/ subrouters — covers access control branches.
Tests use direct function calls with mocked DB to cover internal logic.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


# ============= projects/tasks.py =============


class TestListProjectTasks:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.tasks import list_project_tasks
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_project_tasks(
                project_id="proj-1", request=request, page=1, page_size=30,
                only_labeled=None, only_unlabeled=None, only_assigned=None,
                exclude_my_annotations=None, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.projects.tasks import list_project_tasks
        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.projects.tasks.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await list_project_tasks(
                    project_id="proj-1", request=request, page=1, page_size=30,
                    only_labeled=None, only_unlabeled=None, only_assigned=None,
                    exclude_my_annotations=None, current_user=user, db=db,
                )
            assert exc_info.value.status_code == 403


class TestSkipTask:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.tasks import skip_task
        from project_schemas import SkipTaskRequest
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await skip_task(project_id="proj-1", task_id="task-1",
                           request=request, skip_request=SkipTaskRequest(),
                           current_user=user, db=db)
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
                             current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestListTaskAssignments:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.assignments import list_task_assignments
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_task_assignments(project_id="proj-1", task_id="task-1",
                                       request=request, current_user=user, db=db)
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
                                        assignment_id="a-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestGetProjectWorkload:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.assignments import get_project_workload
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await get_project_workload(project_id="proj-1",
                                      current_user=user, db=db)
        assert exc_info.value.status_code == 404


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
                             page=1, page_size=30, status=None,
                             current_user=user, db=db)
        assert exc_info.value.status_code == 404


# ============= projects/members.py =============


class TestListProjectMembers:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.members import list_project_members
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_project_members(project_id="proj-1", request=request,
                                      current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestAddProjectMember:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.members import add_project_member
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await add_project_member(project_id="proj-1", user_id="u1",
                                    data={"role": "annotator"},
                                    current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestGetProjectAnnotators:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.members import get_project_annotators
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_project_annotators(project_id="proj-1", request=request,
                                        current_user=user, db=db)
        assert exc_info.value.status_code == 404


# ============= projects/reviews.py =============


class TestListQuestionnaireResponses:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.questionnaire import list_questionnaire_responses
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_questionnaire_responses(
                project_id="proj-1", request=request,
                current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404


# ============= projects/label_config_versions.py =============


class TestGetLabelConfigVersions:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.label_config_versions import get_label_config_versions
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
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
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
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


class TestListProjectOrganizations:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.organizations import list_project_organizations
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await list_project_organizations(
                project_id="proj-1", request=request,
                current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404


# ============= projects/import_export.py =============


class TestExportProject:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.projects.import_export import export_project
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await export_project(project_id="proj-1", request=request,
                               current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.projects.import_export import export_project
        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.projects.import_export.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await export_project(project_id="proj-1", request=request,
                                    current_user=user, db=db)
            assert exc_info.value.status_code == 403
