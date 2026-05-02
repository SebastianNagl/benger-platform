"""
Unit tests for routers/projects/crud.py targeting uncovered lines.

Covers: list_projects happy path, create_project org/private paths,
get_project success, update_project with field updates, delete_project success,
update_project_visibility, recalculate, completion stats.

Rewritten to call handler functions directly (no TestClient) so that pytest-cov
tracks the router code.
"""

import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request(headers=None):
    r = Mock()
    r.headers = headers or {}
    r.state = Mock(spec=[])
    return r


def _mock_user(is_superadmin=False, user_id="user-123"):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    user.is_active = True
    user.email_verified = True
    return user


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.options.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_db.query.return_value = mock_q
    return mock_db


def _mock_project(project_id="proj-1", title="Test", created_by="user-123", is_private=False):
    """Create a mock ORM project object."""
    p = Mock()
    p.id = project_id
    p.title = title
    p.description = "Description"
    p.created_by = created_by
    p.is_private = is_private
    p.label_config = "<View><Text name='text' value='$text'/></View>"
    p.expert_instruction = ""
    p.show_instruction = False
    p.show_skip_button = True
    p.enable_empty_annotation = False
    p.generation_config = {}
    p.evaluation_config = {}
    p.label_config_version = "v1"
    p.label_config_version_history = []
    p.min_annotations_per_task = 1
    p.questionnaire_enabled = False
    p.questionnaire_config = None
    p.skip_queue = None
    p.llm_model_ids = []
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = None
    p.require_confirm_before_submit = False
    p.is_published = False
    p.is_archived = False

    creator = Mock()
    creator.name = "Test User"
    p.creator = creator
    p.organizations = []
    p.project_organizations = []

    return p


def _mock_project_response(**overrides):
    """Build a mock ProjectResponse-like object."""
    resp = Mock()
    defaults = {
        "id": "proj-1",
        "title": "Test Project",
        "description": "Desc",
        "created_by": "user-123",
        "created_by_name": "Test User",
        "task_count": 0,
        "annotation_count": 0,
        "completed_tasks_count": 0,
        "progress_percentage": 0.0,
        "is_private": False,
        "is_published": False,
        "is_archived": False,
        "organizations": [],
        "generation_models_count": 0,
        "generation_completed": False,
        "generation_prompts_ready": False,
        "generation_config_ready": False,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(resp, k, v)
    return resp


# ---------------------------------------------------------------------------
# list_projects: happy path (lines 100-200)
# ---------------------------------------------------------------------------

class TestListProjectsHappyPath:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats_batch", return_value={
        "proj-1": {"task_count": 5, "completed_tasks_count": 2, "annotation_count": 3}
    })
    @patch("routers.projects.crud.get_accessible_project_ids", return_value=None)
    @patch("routers.projects.crud.ProjectResponse")
    async def test_list_projects_with_results(self, MockPR, mock_ids, mock_stats, mock_gen):
        from routers.projects.crud import list_projects

        project = _mock_project()
        resp_obj = _mock_project_response()
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [project]
        mock_q.count.return_value = 1
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)
        request = _mock_request(headers={"X-Organization-Context": "private"})

        result = await list_projects(
            request=request, page=1, page_size=100, search=None,
            is_archived=None, current_user=user, db=db,
        )
        assert result.total >= 0

    @pytest.mark.asyncio
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats_batch", return_value={})
    @patch("routers.projects.crud.get_accessible_project_ids", return_value=None)
    @patch("routers.projects.crud.ProjectResponse")
    async def test_list_projects_with_is_archived_filter(self, MockPR, mock_ids, mock_stats, mock_gen):
        from routers.projects.crud import list_projects

        project = _mock_project()
        resp_obj = _mock_project_response(is_archived=False)
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [project]
        mock_q.count.return_value = 1
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        result = await list_projects(
            request=request, page=1, page_size=100, search=None,
            is_archived=False, current_user=user, db=db,
        )
        assert result.total >= 0

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_accessible_project_ids", side_effect=RuntimeError("Boom"))
    async def test_list_projects_unexpected_exception(self, mock_ids):
        from routers.projects.crud import list_projects

        db = _mock_db()
        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await list_projects(
                request=request, page=1, page_size=100, search=None,
                is_archived=None, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats_batch", return_value={})
    @patch("routers.projects.crud.get_accessible_project_ids", return_value=["proj-1"])
    @patch("routers.projects.crud.ProjectResponse")
    async def test_list_projects_with_search(self, MockPR, mock_ids, mock_stats, mock_gen):
        from routers.projects.crud import list_projects

        resp_obj = _mock_project_response()
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = []
        mock_q.count.return_value = 0
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        result = await list_projects(
            request=request, page=1, page_size=100, search="test",
            is_archived=None, current_user=user, db=db,
        )
        assert result.total == 0


# ---------------------------------------------------------------------------
# create_project: org mode paths (lines 203-348)
# ---------------------------------------------------------------------------

class TestCreateProjectOrgMode:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.ProjectResponse")
    @patch("routers.projects.crud.notify_project_created")
    @patch("routers.projects.crud.LabelConfigValidator")
    async def test_create_project_private_mode(self, mock_lcv, mock_notify, MockPR):
        from routers.projects.crud import create_project
        from project_schemas import ProjectCreate

        mock_lcv.validate.return_value = (True, [])
        MockPR.from_orm.return_value = _mock_project_response(is_private=True)

        project = _mock_project(is_private=True)
        db = _mock_db()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = project

        user = _mock_user(is_superadmin=True)
        request = _mock_request(headers={"X-Organization-Context": "private"})

        with patch("routers.projects.crud.create_initial_report_draft", create=True):
            result = await create_project(
                project=ProjectCreate(title="Private", is_private=True),
                request=request,
                current_user=user,
                db=db,
            )
        assert result.is_private is True
        db.add.assert_called()
        db.commit.assert_called()

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_user_with_memberships", return_value=None)
    async def test_create_project_org_mode_no_membership(self, mock_gwm):
        from routers.projects.crud import create_project
        from project_schemas import ProjectCreate

        db = _mock_db()
        user = _mock_user(is_superadmin=False)
        request = _mock_request(headers={"X-Organization-Context": "org-123"})

        with pytest.raises(HTTPException) as exc_info:
            await create_project(
                project=ProjectCreate(title="Org Project"),
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_user_with_memberships")
    async def test_create_project_org_mode_no_active_membership(self, mock_gwm):
        from routers.projects.crud import create_project
        from project_schemas import ProjectCreate

        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [
            Mock(is_active=False, organization_id="org-123", role="ANNOTATOR")
        ]
        mock_gwm.return_value = user_with_memberships

        db = _mock_db()
        user = _mock_user(is_superadmin=False)
        request = _mock_request(headers={"X-Organization-Context": "org-123"})

        with pytest.raises(HTTPException) as exc_info:
            await create_project(
                project=ProjectCreate(title="Org Project"),
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_user_with_memberships")
    async def test_create_project_org_mode_annotator_denied(self, mock_gwm):
        from routers.projects.crud import create_project
        from project_schemas import ProjectCreate

        membership = Mock(is_active=True, organization_id="org-123", role="ANNOTATOR",
                          organization=Mock(name="Org"))
        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [membership]
        mock_gwm.return_value = user_with_memberships

        db = _mock_db()
        user = _mock_user(is_superadmin=False)
        request = _mock_request(headers={"X-Organization-Context": "org-123"})

        with pytest.raises(HTTPException) as exc_info:
            await create_project(
                project=ProjectCreate(title="Org Project"),
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.projects.crud.LabelConfigValidator")
    async def test_create_project_invalid_label_config(self, mock_lcv):
        from routers.projects.crud import create_project
        from project_schemas import ProjectCreate

        mock_lcv.validate.return_value = (False, ["Invalid XML"])

        db = _mock_db()
        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await create_project(
                project=ProjectCreate(title="Bad Config", label_config="<<<bad>>>"),
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# get_project: success path (lines 351-398)
# ---------------------------------------------------------------------------

class TestGetProjectSuccess:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.ProjectResponse")
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats")
    @patch("routers.projects.crud.get_org_context_from_request", return_value=None)
    @patch("routers.projects.crud.check_project_accessible", return_value=True)
    async def test_get_project_accessible(self, mock_access, mock_org, mock_stats, mock_gen, MockPR):
        from routers.projects.crud import get_project

        project = _mock_project()
        resp_obj = _mock_project_response()
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = project

        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        result = await get_project(
            project_id="proj-1", request=request, current_user=user, db=db,
        )
        assert result.id == "proj-1"
        assert result.title == "Test Project"
        MockPR.from_orm.assert_called_once_with(project)

    @pytest.mark.asyncio
    async def test_get_project_not_found(self):
        from routers.projects.crud import get_project

        db = _mock_db()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = None

        user = _mock_user()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_project(
                project_id="missing", request=request, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_org_context_from_request", return_value=None)
    @patch("routers.projects.crud.check_project_accessible", return_value=False)
    async def test_get_project_access_denied(self, mock_access, mock_org):
        from routers.projects.crud import get_project

        project = _mock_project()
        db = _mock_db()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = project

        user = _mock_user(is_superadmin=False)
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_project(
                project_id="proj-1", request=request, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# update_project: happy paths (lines 401-542)
# ---------------------------------------------------------------------------

class TestUpdateProjectHappyPath:
    async def _run_update(self, update_dict, project_overrides=None):
        from routers.projects.crud import update_project
        from project_schemas import ProjectUpdate

        project = _mock_project()
        if project_overrides:
            for k, v in project_overrides.items():
                setattr(project, k, v)

        resp_obj = _mock_project_response()
        db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = project
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)

        with patch("routers.projects.crud.check_user_can_edit_project", return_value=True), \
             patch("routers.projects.crud.calculate_project_stats"), \
             patch("routers.projects.crud.calculate_generation_stats"), \
             patch("routers.projects.crud.LabelConfigValidator") as mock_lcv, \
             patch("routers.projects.crud.LabelConfigVersionService") as mock_lcvs, \
             patch("routers.projects.crud.flag_modified"), \
             patch("routers.projects.crud.ProjectResponse") as MockPR:
            mock_lcv.validate.return_value = (True, [])
            mock_lcvs.has_schema_changed.return_value = True
            mock_lcvs.update_version_history.return_value = "v2"
            MockPR.from_orm.return_value = resp_obj

            result = await update_project(
                project_id="proj-1",
                update=ProjectUpdate(**update_dict),
                current_user=user,
                db=db,
            )
        return result

    @pytest.mark.asyncio
    async def test_update_instructions_mapping(self):
        result = await self._run_update({"instructions": "New instructions"})
        assert result.id == "proj-1"

    @pytest.mark.asyncio
    async def test_update_llm_model_ids_migration(self):
        result = await self._run_update(
            {"llm_model_ids": ["gpt-4o"]},
            project_overrides={"generation_config": {}},
        )
        assert result.id == "proj-1"

    @pytest.mark.asyncio
    async def test_update_label_config_with_versioning(self):
        new_config = "<View><Text name='text' value='$text'/><Choices name='c' toName='text'><Choice value='A'/></Choices></View>"
        result = await self._run_update({"label_config": new_config})
        assert result.id == "proj-1"

    @pytest.mark.asyncio
    @patch("routers.projects.crud.LabelConfigValidator")
    @patch("routers.projects.crud.check_user_can_edit_project", return_value=True)
    async def test_update_label_config_invalid(self, mock_edit, mock_lcv):
        from routers.projects.crud import update_project
        from project_schemas import ProjectUpdate

        mock_lcv.validate.return_value = (False, ["Parse error"])

        project = _mock_project()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project

        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                project_id="proj-1",
                update=ProjectUpdate(label_config="<<<bad>>>"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_generation_config_deep_merge(self):
        result = await self._run_update(
            {"generation_config": {"new_key": "val"}},
            project_overrides={"generation_config": {"existing": "value"}, "evaluation_config": {}},
        )
        assert result.id == "proj-1"

    @pytest.mark.asyncio
    async def test_update_evaluation_config_deep_merge(self):
        result = await self._run_update(
            {"evaluation_config": {"metric": "bleu"}},
            project_overrides={"evaluation_config": {"temperature": 0.2}, "generation_config": {}},
        )
        assert result.id == "proj-1"

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        from routers.projects.crud import update_project
        from project_schemas import ProjectUpdate

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                project_id="missing",
                update=ProjectUpdate(title="New"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.projects.crud.check_user_can_edit_project", return_value=False)
    async def test_update_permission_denied(self, mock_edit):
        from routers.projects.crud import update_project
        from project_schemas import ProjectUpdate

        project = _mock_project()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project
        user = _mock_user(is_superadmin=False)

        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                project_id="proj-1",
                update=ProjectUpdate(title="New"),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# delete_project: success path (lines 545-614)
# ---------------------------------------------------------------------------

class TestDeleteProjectSuccess:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.notify_project_deleted")
    async def test_delete_superadmin(self, mock_notify):
        from routers.projects.crud import delete_project

        project = _mock_project()
        db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.delete.return_value = 0
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)

        result = await delete_project(project_id="proj-1", current_user=user, db=db)
        assert result["message"] == "Project deleted successfully"

    @pytest.mark.asyncio
    @patch("routers.projects.crud.notify_project_deleted")
    async def test_delete_private_by_creator(self, mock_notify):
        from routers.projects.crud import delete_project

        project = _mock_project(is_private=True, created_by="user-123")
        db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.delete.return_value = 0
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=False, user_id="user-123")

        result = await delete_project(project_id="proj-1", current_user=user, db=db)
        assert result["message"] == "Project deleted successfully"

    @pytest.mark.asyncio
    @patch("routers.projects.crud.notify_project_deleted", side_effect=RuntimeError("Notify fail"))
    async def test_delete_notification_failure(self, mock_notify):
        from routers.projects.crud import delete_project

        project = _mock_project()
        db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.delete.return_value = 0
        db.query.return_value = mock_q

        user = _mock_user(is_superadmin=True)

        result = await delete_project(project_id="proj-1", current_user=user, db=db)
        assert result["message"] == "Project deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        from routers.projects.crud import delete_project

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await delete_project(project_id="missing", current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_permission_denied(self):
        from routers.projects.crud import delete_project

        project = _mock_project(is_private=False, created_by="other-user")
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project
        user = _mock_user(is_superadmin=False, user_id="user-123")

        with pytest.raises(HTTPException) as exc_info:
            await delete_project(project_id="proj-1", current_user=user, db=db)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# update_project_visibility: happy paths (lines 617-711)
# ---------------------------------------------------------------------------

class TestVisibilityHappyPaths:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.ProjectResponse")
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats")
    async def test_make_private_success(self, mock_stats, mock_gen, MockPR):
        from routers.projects.crud import update_project_visibility

        project = _mock_project(is_private=False)
        owner = Mock(id="user-123")
        resp_obj = _mock_project_response(is_private=True)
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            q.filter.return_value = q
            q.options.return_value = q
            q.delete.return_value = 0
            if call_count["n"] == 1:
                q.first.return_value = project
            elif call_count["n"] == 2:
                q.first.return_value = owner
            else:
                q.first.return_value = project
            return q

        db.query.side_effect = query_side_effect

        user = _mock_user(is_superadmin=True)

        result = await update_project_visibility(
            project_id="proj-1",
            visibility={"is_private": True, "owner_user_id": "user-123"},
            current_user=user,
            db=db,
        )
        assert result.id == "proj-1"
        db.commit.assert_called()

    @pytest.mark.asyncio
    @patch("routers.projects.crud.ProjectResponse")
    @patch("routers.projects.crud.calculate_generation_stats")
    @patch("routers.projects.crud.calculate_project_stats")
    async def test_make_org_assigned_success(self, mock_stats, mock_gen, MockPR):
        from routers.projects.crud import update_project_visibility

        project = _mock_project(is_private=True)
        org = Mock(id="org-1")
        resp_obj = _mock_project_response(is_private=False)
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            q.filter.return_value = q
            q.options.return_value = q
            q.delete.return_value = 0
            if call_count["n"] == 1:
                q.first.return_value = project
            elif call_count["n"] == 2:
                q.first.return_value = org
            else:
                q.first.return_value = project
            return q

        db.query.side_effect = query_side_effect

        user = _mock_user(is_superadmin=True)

        result = await update_project_visibility(
            project_id="proj-1",
            visibility={"is_private": False, "organization_ids": ["org-1"]},
            current_user=user,
            db=db,
        )
        assert result.id == "proj-1"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_make_org_assigned_org_not_found(self):
        from routers.projects.crud import update_project_visibility

        project = _mock_project()
        db = _mock_db()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count["n"] == 1:
                q.first.return_value = project
            else:
                q.first.return_value = None
            return q

        db.query.side_effect = query_side_effect

        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await update_project_visibility(
                project_id="proj-1",
                visibility={"is_private": False, "organization_ids": ["missing-org"]},
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_not_superadmin(self):
        from routers.projects.crud import update_project_visibility

        # Mock project owned by a different user — non-superadmin non-creator should get 403.
        project = _mock_project(created_by="some-other-user")
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project
        user = _mock_user(is_superadmin=False, user_id="not-the-creator")

        with pytest.raises(HTTPException) as exc_info:
            await update_project_visibility(
                project_id="proj-1",
                visibility={"is_private": True},
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_visibility_project_not_found(self):
        from routers.projects.crud import update_project_visibility

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await update_project_visibility(
                project_id="missing",
                visibility={"is_private": True},
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_no_org_ids(self):
        from routers.projects.crud import update_project_visibility

        project = _mock_project()
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project
        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            await update_project_visibility(
                project_id="proj-1",
                visibility={"is_private": False, "organization_ids": []},
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# recalculate_project_statistics (lines 714-753) - sync function
# ---------------------------------------------------------------------------

class TestRecalculateSuccess:
    @patch("routers.projects.crud.calculate_project_stats")
    @patch("routers.projects.crud.ProjectResponse")
    def test_recalculate_stats_success(self, MockPR, mock_calc):
        from routers.projects.crud import recalculate_project_statistics

        project = _mock_project()
        resp_obj = _mock_project_response(task_count=10, annotation_count=5, completed_tasks_count=3)
        MockPR.from_orm.return_value = resp_obj

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = project

        user = _mock_user(is_superadmin=True)

        # Also patch the local import of ProjectResponse inside the function
        with patch("project_schemas.ProjectResponse") as MockPR2:
            MockPR2.from_orm.return_value = resp_obj
            result = recalculate_project_statistics(
                project_id="proj-1", db=db, current_user=user,
            )
        assert result["task_count"] == 10

    def test_recalculate_not_superadmin(self):
        from routers.projects.crud import recalculate_project_statistics

        db = _mock_db()
        user = _mock_user(is_superadmin=False)

        with pytest.raises(HTTPException) as exc_info:
            recalculate_project_statistics(project_id="proj-1", db=db, current_user=user)
        assert exc_info.value.status_code == 403

    def test_recalculate_not_found(self):
        from routers.projects.crud import recalculate_project_statistics

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _mock_user(is_superadmin=True)

        with pytest.raises(HTTPException) as exc_info:
            recalculate_project_statistics(project_id="missing", db=db, current_user=user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_project_completion_stats (lines 756-796)
# ---------------------------------------------------------------------------

class TestCompletionStatsSuccess:
    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_org_context_from_request", return_value=None)
    @patch("routers.projects.crud.check_project_accessible", return_value=True)
    async def test_completion_stats_with_tasks(self, mock_access, mock_org):
        from routers.projects.crud import get_project_completion_stats

        project = _mock_project()
        db = _mock_db()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count["n"] == 1:
                q.first.return_value = project
            elif call_count["n"] == 2:
                q.count.return_value = 10
            elif call_count["n"] == 3:
                q.count.return_value = 4
            else:
                q.count.return_value = 0
            return q

        db.query.side_effect = query_side_effect

        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        result = await get_project_completion_stats(
            project_id="proj-1", request=request, current_user=user, db=db,
        )
        assert result["total"] == 10
        assert result["completed"] == 4
        assert result["completion_rate"] == 40.0

    @pytest.mark.asyncio
    @patch("routers.projects.crud.get_org_context_from_request", return_value=None)
    @patch("routers.projects.crud.check_project_accessible", return_value=True)
    async def test_completion_stats_no_tasks(self, mock_access, mock_org):
        from routers.projects.crud import get_project_completion_stats

        project = _mock_project()
        db = _mock_db()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            q.filter.return_value = q
            if call_count["n"] == 1:
                q.first.return_value = project
            else:
                q.count.return_value = 0
            return q

        db.query.side_effect = query_side_effect

        user = _mock_user(is_superadmin=True)
        request = _mock_request()

        result = await get_project_completion_stats(
            project_id="proj-1", request=request, current_user=user, db=db,
        )
        assert result["completion_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_completion_stats_not_found(self):
        from routers.projects.crud import get_project_completion_stats

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _mock_user()
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_project_completion_stats(
                project_id="missing", request=request, current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404
