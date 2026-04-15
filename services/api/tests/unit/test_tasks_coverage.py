"""
Unit tests for routers/projects/tasks.py covering uncovered lines.

Covers:
- list_project_tasks endpoint (lines 37-229)
- get_next_task endpoint (lines 232-421)
- get_task endpoint (lines 424-475)
- update_task_metadata endpoint (lines 478-526)
- bulk_update_task_metadata endpoint (lines 529-585)
- update_task_data endpoint (lines 588-704)
- bulk_delete_tasks endpoint (lines 707-766)
- bulk_export_tasks endpoint (lines 769-982)
- bulk_archive_tasks endpoint (lines 985-1023)
- skip_task endpoint (lines 1026-1084)
- extract_fields_from_data helper (lines 1102-1160)
- get_task_data_fields endpoint (lines 1163-1231)
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session


def _mock_request(headers=None):
    r = Mock()
    r.headers = headers or {}
    r.state = Mock(spec=[])
    return r


def _mock_user(user_id="user-123", is_superadmin=False):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    return user


def _mock_project(project_id="project-123", assignment_mode="open"):
    p = Mock()
    p.id = project_id
    p.title = "Test Project"
    p.created_by = "user-123"
    p.assignment_mode = assignment_mode
    p.randomize_task_order = False
    p.skip_queue = "requeue_for_others"
    p.require_comment_on_skip = False
    return p


def _mock_task(task_id="task-1", project_id="project-123"):
    t = Mock()
    t.id = task_id
    t.project_id = project_id
    t.inner_id = 1
    t.data = {"text": "Sample text"}
    t.meta = {"tag": "test"}
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = None
    t.is_labeled = False
    t.total_annotations = 0
    t.cancelled_annotations = 0
    t.total_generations = 0
    t.llm_responses = None
    t.llm_evaluations = None
    t.comment_count = 0
    t.unresolved_comment_count = 0
    t.last_comment_updated_at = None
    t.comment_authors = None
    t.file_upload_id = None
    t.created_by = "user-123"
    t.updated_by = None
    return t


# ============= extract_fields_from_data =============


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

        # Note: In Python, isinstance(True, (int, float)) is True because bool subclasses int.
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
        assert parent["is_nested"] is False
        assert child["is_nested"] is True


# ============= list_project_tasks =============


class TestListProjectTasks:
    """Test list_project_tasks endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.tasks.get_user_with_memberships")
    async def test_project_not_found(self, mock_get_user, mock_org, mock_access, mock_db):
        from routers.projects.tasks import list_project_tasks

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await list_project_tasks(
                project_id="nonexistent",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=False)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import list_project_tasks

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        with pytest.raises(Exception) as exc_info:
            await list_project_tasks(
                project_id="project-123",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "denied" in str(exc_info.value.detail).lower()


# ============= get_next_task =============


class TestGetNextTask:
    """Test get_next_task endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_next_task

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await get_next_task(
            project_id="nonexistent",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["task"] is None
        assert "not found" in result["detail"].lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=False)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_next_task

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        with pytest.raises(Exception) as exc_info:
            await get_next_task(
                project_id="project-123",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "denied" in str(exc_info.value.detail).lower()


# ============= get_task =============


class TestGetTask:
    """Test get_task endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.check_task_assigned_to_user", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_task_not_found(self, mock_org, mock_assign, mock_access, mock_db):
        from routers.projects.tasks import get_task

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_task(
                task_id="nonexistent",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=False)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_task

        task = _mock_task()
        mock_db.query.return_value.filter.return_value.first.return_value = task

        with pytest.raises(Exception) as exc_info:
            await get_task(
                task_id="task-1",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "denied" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.check_task_assigned_to_user", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_get_task_success(self, mock_org, mock_assign, mock_access, mock_db):
        from routers.projects.tasks import get_task

        task = _mock_task()
        project = _mock_project()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                # Task lookup
                q.filter.return_value.first.return_value = task
            elif call_count["n"] == 2:
                # Project lookup
                q.filter.return_value.first.return_value = project
            elif call_count["n"] == 3:
                # Generation count
                q.filter.return_value.scalar.return_value = 2
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_task(
            task_id="task-1",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["id"] == "task-1"
        assert result["data"] == {"text": "Sample text"}


# ============= update_task_metadata =============


class TestUpdateTaskMetadata:
    """Test update_task_metadata endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_task_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import update_task_metadata

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await update_task_metadata(
                task_id="nonexistent",
                metadata={"key": "value"},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_merge_metadata(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import update_task_metadata

        task = _mock_task()
        task.meta = {"existing": "value"}
        mock_db.query.return_value.filter.return_value.first.return_value = task

        result = await update_task_metadata(
            task_id="task-1",
            metadata={"new_key": "new_value"},
            request=_mock_request(),
            merge=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["message"] == "Metadata updated successfully"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_replace_metadata(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import update_task_metadata

        task = _mock_task()
        task.meta = {"existing": "value"}
        mock_db.query.return_value.filter.return_value.first.return_value = task

        result = await update_task_metadata(
            task_id="task-1",
            metadata={"replaced": "data"},
            request=_mock_request(),
            merge=False,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert task.meta == {"replaced": "data"}

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_metadata_init_from_none(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import update_task_metadata

        task = _mock_task()
        task.meta = None
        mock_db.query.return_value.filter.return_value.first.return_value = task

        result = await update_task_metadata(
            task_id="task-1",
            metadata={"key": "value"},
            request=_mock_request(),
            merge=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert task.meta == {"key": "value"}


# ============= bulk_update_task_metadata =============


class TestBulkUpdateTaskMetadata:
    """Test bulk_update_task_metadata endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_no_tasks_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import bulk_update_task_metadata

        mock_db.query.return_value.filter.return_value.all.return_value = []

        with pytest.raises(Exception) as exc_info:
            await bulk_update_task_metadata(
                task_ids=["nonexistent"],
                metadata={"key": "val"},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "No tasks found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_bulk_merge(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import bulk_update_task_metadata

        task1 = _mock_task(task_id="t-1")
        task1.meta = {"existing": "data"}
        task2 = _mock_task(task_id="t-2")
        task2.meta = None

        mock_db.query.return_value.filter.return_value.all.return_value = [task1, task2]

        result = await bulk_update_task_metadata(
            task_ids=["t-1", "t-2"],
            metadata={"new": "value"},
            request=_mock_request(),
            merge=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["updated_count"] == 2
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_bulk_replace(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import bulk_update_task_metadata

        task = _mock_task(task_id="t-1")
        task.meta = {"old": "data"}
        mock_db.query.return_value.filter.return_value.all.return_value = [task]

        result = await bulk_update_task_metadata(
            task_ids=["t-1"],
            metadata={"new": "data"},
            request=_mock_request(),
            merge=False,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert task.meta == {"new": "data"}


# ============= update_task_data =============


class TestUpdateTaskData:
    """Test update_task_data endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_non_superadmin_denied(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import update_task_data

        with pytest.raises(Exception) as exc_info:
            await update_task_data(
                project_id="proj-1",
                task_id="task-1",
                data={"data": {"text": "new"}},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=False),
                db=mock_db,
            )
        assert "superadmin" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import update_task_data

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await update_task_data(
                project_id="nonexistent",
                task_id="task-1",
                data={"data": {"text": "new"}},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=True),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_no_data_provided(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import update_task_data

        project = _mock_project()
        task = _mock_task()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            elif call_count["n"] == 2:
                q.filter.return_value.first.return_value = task
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await update_task_data(
                project_id="proj-1",
                task_id="task-1",
                data={"data": {}},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=True),
                db=mock_db,
            )
        assert "No data provided" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_update_success(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import update_task_data

        project = _mock_project()
        task = _mock_task()
        task.data = {"text": "old text"}
        task.meta = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            elif call_count["n"] == 2:
                q.filter.return_value.first.return_value = task
            elif call_count["n"] == 3:
                q.filter.return_value.scalar.return_value = 0
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        result = await update_task_data(
            project_id="proj-1",
            task_id="task-1",
            data={"data": {"text": "new text"}},
            request=_mock_request(),
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result["data"]["text"] == "new text"
        assert "audit_log" in task.meta

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.attributes.flag_modified")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_update_db_error(self, mock_org, mock_access, mock_flag, mock_db):
        from routers.projects.tasks import update_task_data

        project = _mock_project()
        task = _mock_task()
        task.data = {"text": "old"}
        task.meta = {}
        mock_db.commit.side_effect = Exception("DB error")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            elif call_count["n"] == 2:
                q.filter.return_value.first.return_value = task
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await update_task_data(
                project_id="proj-1",
                task_id="task-1",
                data={"data": {"text": "new"}},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=True),
                db=mock_db,
            )
        assert "Failed to update" in str(exc_info.value.detail)
        mock_db.rollback.assert_called_once()


# ============= bulk_delete_tasks =============


class TestBulkDeleteTasks:
    """Test bulk_delete_tasks endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import bulk_delete_tasks

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await bulk_delete_tasks(
                project_id="nonexistent",
                data={"task_ids": ["t-1"]},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_user_can_edit_project", return_value=False)
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_permission_denied(self, mock_org, mock_access, mock_edit, mock_db):
        from routers.projects.tasks import bulk_delete_tasks

        project = _mock_project()
        project.created_by = "other-user"
        mock_db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(Exception) as exc_info:
            await bulk_delete_tasks(
                project_id="proj-1",
                data={"task_ids": ["t-1"]},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=False),
                db=mock_db,
            )
        assert "Permission denied" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.tasks.check_user_can_edit_project", return_value=True)
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_delete_success(self, mock_org, mock_access, mock_edit, mock_report, mock_db):
        from routers.projects.tasks import bulk_delete_tasks

        project = _mock_project()
        project.created_by = "user-123"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            elif call_count["n"] <= 3:
                q.filter.return_value.delete.return_value = 1
            else:
                q.filter.return_value.count.return_value = 4
            return q

        mock_db.query.side_effect = query_side_effect

        result = await bulk_delete_tasks(
            project_id="proj-1",
            data={"task_ids": ["t-1", "t-2"]},
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert "deleted" in result
        assert isinstance(result["deleted"], int)
        assert result["deleted"] == 2  # 2 task_ids requested


# ============= bulk_export_tasks =============


class TestBulkExportTasks:
    """Test bulk_export_tasks endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import bulk_export_tasks

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await bulk_export_tasks(
                project_id="nonexistent",
                data={"task_ids": ["t-1"]},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_task")
    @patch("routers.projects.serializers.serialize_evaluation_run")
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_export_unsupported_format(self, mock_org, mock_access, mock_ser_er, mock_ser_task, mock_judge, mock_eval_idx, mock_db):
        from routers.projects.tasks import bulk_export_tasks

        project = _mock_project()
        task = _mock_task()

        from project_models import Annotation, PostAnnotationResponse, Project, Task
        from models import EvaluationRun, Generation, TaskEvaluation

        def query_side_effect(model):
            q = MagicMock()
            if model == Project:
                q.filter.return_value.first.return_value = project
            elif model == Task:
                q.filter.return_value.all.return_value = [task]
            elif model == Annotation:
                q.filter.return_value.all.return_value = []
            elif model == Generation:
                q.filter.return_value.all.return_value = []
            elif model == PostAnnotationResponse:
                q.filter.return_value.all.return_value = []
            elif model == EvaluationRun:
                q.filter.return_value.all.return_value = []
            elif model == TaskEvaluation:
                q.filter.return_value.all.return_value = []
            else:
                q.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect
        mock_ser_task.return_value = {"id": "task-1", "data": {"text": "test"}, "is_labeled": False, "created_at": None}

        with pytest.raises(Exception) as exc_info:
            await bulk_export_tasks(
                project_id="proj-1",
                data={"task_ids": ["task-1"], "format": "xml"},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Unsupported format" in str(exc_info.value.detail)


# ============= bulk_archive_tasks =============


class TestBulkArchiveTasks:
    """Test bulk_archive_tasks endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import bulk_archive_tasks

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await bulk_archive_tasks(
                project_id="nonexistent",
                data={"task_ids": ["t-1"]},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_user_can_edit_project", return_value=False)
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_permission_denied(self, mock_org, mock_access, mock_edit, mock_db):
        from routers.projects.tasks import bulk_archive_tasks

        project = _mock_project()
        project.created_by = "other-user"
        mock_db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(Exception) as exc_info:
            await bulk_archive_tasks(
                project_id="proj-1",
                data={"task_ids": ["t-1"]},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=False),
                db=mock_db,
            )
        assert "Permission denied" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_user_can_edit_project", return_value=True)
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_archive_success(self, mock_org, mock_access, mock_edit, mock_db):
        from routers.projects.tasks import bulk_archive_tasks

        project = _mock_project()
        project.created_by = "user-123"
        task = _mock_task()
        task.meta = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.first.return_value = task
            return q

        mock_db.query.side_effect = query_side_effect

        result = await bulk_archive_tasks(
            project_id="proj-1",
            data={"task_ids": ["task-1"]},
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["archived"] == 1
        assert task.meta["is_archived"] is True


# ============= skip_task =============


class TestSkipTask:
    """Test skip_task endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.check_task_assigned_to_user", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_task_not_found(self, mock_org, mock_assign, mock_access, mock_db):
        from routers.projects.tasks import skip_task
        from project_schemas import SkipTaskRequest

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await skip_task(
                project_id="proj-1",
                task_id="nonexistent",
                skip_request=SkipTaskRequest(),
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.check_task_assigned_to_user", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_comment_required(self, mock_org, mock_assign, mock_access, mock_db):
        from routers.projects.tasks import skip_task
        from project_schemas import SkipTaskRequest

        task = _mock_task()
        project = _mock_project()
        project.require_comment_on_skip = True

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = task
            elif call_count["n"] == 2:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await skip_task(
                project_id="proj-1",
                task_id="task-1",
                skip_request=SkipTaskRequest(comment=None),
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Comment is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.check_task_assigned_to_user", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_skip_success(self, mock_org, mock_assign, mock_access, mock_db):
        from routers.projects.tasks import skip_task
        from project_schemas import SkipTaskRequest

        task = _mock_task()
        project = _mock_project()
        project.require_comment_on_skip = False

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = task
            elif call_count["n"] == 2:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        result = await skip_task(
            project_id="proj-1",
            task_id="task-1",
            skip_request=SkipTaskRequest(comment="Too difficult"),
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Verify the skip record has correct fields
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.task_id == "task-1"
        assert added_obj.comment == "Too difficult"


# ============= get_task_data_fields =============


class TestGetTaskDataFields:
    """Test get_task_data_fields endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_project_not_found(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_task_data_fields

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_task_data_fields(
                project_id="nonexistent",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_no_tasks(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_task_data_fields

        project = _mock_project()

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.limit.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_task_data_fields(
            project_id="proj-1",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["fields"] == []
        assert result["sample_task_count"] == 0

    @pytest.mark.asyncio
    @patch("routers.projects.tasks.check_project_accessible", return_value=True)
    @patch("routers.projects.tasks.get_org_context_from_request", return_value="org-123")
    async def test_fields_discovered(self, mock_org, mock_access, mock_db):
        from routers.projects.tasks import get_task_data_fields

        project = _mock_project()
        task = _mock_task()
        task.data = {"text": "Hello", "score": 42, "context": {"type": "legal"}}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.limit.return_value.all.return_value = [task]
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_task_data_fields(
            project_id="proj-1",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["sample_task_count"] == 1
        paths = [f["path"] for f in result["fields"]]
        assert "$text" in paths
        assert "$score" in paths
