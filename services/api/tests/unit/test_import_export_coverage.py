"""
Unit tests for routers/projects/import_export.py covering uncovered lines.

Covers:
- import_project_data endpoint (lines 164-444)
- export_project endpoint (lines 447-861) with all formats
- bulk_export_projects endpoint (lines 864-995)
- bulk_export_full_projects endpoint (lines 998-1091)
- import_full_project endpoint (lines 1094-1741)
"""

import json
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session


def _mock_request(headers=None):
    """Create a mock Request object."""
    r = Mock()
    r.headers = headers or {}
    r.state = Mock(spec=[])
    return r


def _mock_user(is_superadmin=False, user_id="user-123"):
    """Create a mock user."""
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    user.is_active = True
    return user


def _mock_project(project_id="project-123", title="Test Project"):
    """Create a mock project."""
    p = Mock()
    p.id = project_id
    p.title = title
    p.description = "Test description"
    p.created_at = datetime.now(timezone.utc)
    p.created_by = "user-123"
    p.label_config = "<View></View>"
    p.expert_instruction = "Instructions"
    p.organizations = []
    return p


def _mock_task(task_id="task-1", project_id="project-123"):
    """Create a mock task."""
    t = Mock()
    t.id = task_id
    t.project_id = project_id
    t.data = {"text": "Sample task text"}
    t.meta = {"tag": "test"}
    t.inner_id = 1
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = None
    t.is_labeled = False
    return t


def _mock_annotation(ann_id="ann-1", task_id="task-1"):
    """Create a mock annotation."""
    a = Mock()
    a.id = ann_id
    a.task_id = task_id
    a.project_id = "project-123"
    a.result = [{"from_name": "answer", "type": "textarea", "value": {"text": ["test"]}}]
    a.completed_by = "user-123"
    a.was_cancelled = False
    a.ground_truth = False
    a.lead_time = 10.0
    a.draft = None
    a.prediction_scores = None
    a.reviewed_by = None
    a.reviewed_at = None
    a.review_result = None
    a.created_at = datetime.now(timezone.utc)
    a.updated_at = None
    return a


def _mock_generation(gen_id="gen-1", task_id="task-1"):
    """Create a mock generation."""
    g = Mock()
    g.id = gen_id
    g.task_id = task_id
    g.model_id = "gpt-4"
    g.response_content = "Generated response"
    g.case_data = '{"text": "test"}'
    g.response_metadata = {}
    g.created_at = datetime.now(timezone.utc)
    return g


class TestImportProjectData:
    """Test import_project_data endpoint (POST /{project_id}/import)."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock(spec=Session)
        db.add = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_project_not_found(self, mock_org, mock_access, mock_db):
        """Test import when project does not exist."""
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await import_project_data(
                project_id="nonexistent",
                data=Mock(data=[], meta={}, evaluation_runs=None),
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=False)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_access_denied(self, mock_org, mock_access, mock_db):
        """Test import when user has no access."""
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        with pytest.raises(Exception) as exc_info:
            await import_project_data(
                project_id="project-123",
                data=Mock(data=[], meta={}, evaluation_runs=None),
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "denied" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_basic_tasks(self, mock_org, mock_access, mock_report, mock_db):
        """Test importing basic tasks without annotations."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[
                {"data": {"text": "Task 1"}, "meta": {"source": "test"}},
                {"data": {"text": "Task 2"}, "meta": {}},
            ],
            meta={"global_key": "global_value"},
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_tasks"] == 2
        assert result["created_annotations"] == 0
        assert result["created_generations"] == 0
        assert result["project_id"] == "project-123"

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_tasks_with_annotations(self, mock_org, mock_access, mock_report, mock_db):
        """Test importing tasks with annotations and questionnaire responses."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[
                {
                    "id": "task-001",
                    "data": {"text": "Task with annotations"},
                    "meta": {},
                    "annotations": [
                        {
                            "result": [{"value": {"text": "Answer"}}],
                            "completed_by": "user-1",
                            "was_cancelled": False,
                            "questionnaire_response": {
                                "result": [{"value": "Good"}],
                            },
                        }
                    ],
                }
            ]
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_tasks"] == 1
        assert result["created_annotations"] == 1
        assert result["created_questionnaire_responses"] == 1

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_tasks_with_generations(self, mock_org, mock_access, mock_report, mock_db):
        """Test importing tasks with generations."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[
                {
                    "id": "task-001",
                    "data": {"text": "Task with generations"},
                    "meta": {},
                    "generations": [
                        {
                            "id": "gen-old-1",
                            "model_id": "gpt-4",
                            "response_content": "Generated answer",
                            "evaluations": [
                                {
                                    "evaluation_run_id": "er-1",
                                    "field_name": "answer",
                                    "metrics": {"accuracy": 0.9},
                                    "passed": True,
                                }
                            ],
                        }
                    ],
                }
            ]
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_tasks"] == 1
        assert result["created_generations"] == 1
        assert result["created_task_evaluations"] == 1

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_with_evaluation_runs(self, mock_org, mock_access, mock_report, mock_db):
        """Test importing evaluation runs."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[{"data": {"text": "Task"}, "meta": {}}],
            evaluation_runs=[
                {
                    "id": "er-old-1",
                    "model_id": "gpt-4",
                    "evaluation_type_ids": ["accuracy"],
                    "metrics": {"accuracy": 0.85},
                    "status": "completed",
                    "samples_evaluated": 10,
                }
            ],
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_evaluation_runs"] == 1

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_with_task_level_evaluations(self, mock_org, mock_access, mock_report, mock_db):
        """Test importing task-level evaluations."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[
                {
                    "data": {"text": "Task"},
                    "meta": {},
                    "evaluations": [
                        {
                            "evaluation_id": "eval-1",
                            "field_name": "answer",
                            "metrics": {"score": 0.9},
                            "passed": True,
                        }
                    ],
                }
            ]
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_task_evaluations"] == 1

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_rollback_on_error(self, mock_org, mock_access, mock_db):
        """Test that import rolls back on database error."""
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()
        mock_db.commit.side_effect = Exception("DB error")

        from project_schemas import ProjectImportData

        data = ProjectImportData(data=[{"data": {"text": "Task"}, "meta": {}}])

        with pytest.raises(Exception) as exc_info:
            await import_project_data(
                project_id="project-123",
                data=data,
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Failed to import data" in str(exc_info.value.detail)
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    @patch("report_service.update_report_data_section")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_inner_id_extraction_numeric_string(self, mock_org, mock_access, mock_report, mock_db):
        """Test inner_id extraction from task IDs like 'task-001'."""
        from project_schemas import ProjectImportData
        from routers.projects.import_export import import_project_data

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        data = ProjectImportData(
            data=[
                {"id": "task-042", "data": {"text": "Numeric id task"}, "meta": {}},
                {"id": 7, "data": {"text": "Integer id task"}, "meta": {}},
            ]
        )

        result = await import_project_data(
            project_id="project-123",
            data=data,
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["created_tasks"] == 2


class TestExportProject:
    """Test export_project endpoint (GET /{project_id}/export)."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    def _setup_export_db(self, mock_db, tasks=None, annotations=None, generations=None):
        """Set up mock db for export queries."""
        tasks = tasks or []
        annotations = annotations or []
        generations = generations or []

        from project_models import Annotation, PostAnnotationResponse, Project, Task
        from models import EvaluationRun, Generation, TaskEvaluation

        def query_side_effect(model):
            q = MagicMock()
            if model == Project:
                q.filter.return_value.first.return_value = _mock_project()
            elif model == Task:
                q.filter.return_value.all.return_value = tasks
            elif model == Annotation:
                q.filter.return_value.all.return_value = annotations
            elif model == Generation:
                q.filter.return_value.all.return_value = generations
            elif model == PostAnnotationResponse:
                q.filter.return_value.all.return_value = []
            elif model == EvaluationRun:
                q.filter.return_value.all.return_value = []
            elif model == TaskEvaluation:
                q.filter.return_value.all.return_value = []
            else:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.first.return_value = None
                q.filter.return_value.count.return_value = 0
            return q

        mock_db.query.side_effect = query_side_effect

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_task")
    @patch("routers.projects.serializers.serialize_evaluation_run")
    async def test_export_json_format(self, mock_ser_er, mock_ser_task, mock_judge, mock_eval_idx, mock_org, mock_access, mock_db):
        """Test JSON format export."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])

        mock_ser_task.return_value = {"id": "task-1", "data": {"text": "test"}, "is_labeled": False, "created_at": None}

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="json",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "application/json"
        body = json.loads(result.body.decode())
        assert "project" in body
        assert "tasks" in body

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_task")
    @patch("routers.projects.serializers.serialize_evaluation_run")
    async def test_export_csv_format(self, mock_ser_er, mock_ser_task, mock_judge, mock_eval_idx, mock_org, mock_access, mock_db):
        """Test CSV format export."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])

        mock_ser_task.return_value = {
            "id": "task-1",
            "data": {"text": "test"},
            "is_labeled": False,
            "created_at": None,
        }

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="csv",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/csv"
        content = result.body.decode()
        assert "task_id" in content

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_task")
    @patch("routers.projects.serializers.serialize_evaluation_run")
    async def test_export_tsv_format(self, mock_ser_er, mock_ser_task, mock_judge, mock_eval_idx, mock_org, mock_access, mock_db):
        """Test TSV format export."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])

        mock_ser_task.return_value = {
            "id": "task-1",
            "data": {"text": "test"},
            "is_labeled": False,
            "created_at": None,
        }

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="tsv",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/tab-separated-values"

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_task")
    @patch("routers.projects.serializers.serialize_evaluation_run")
    async def test_export_txt_format(self, mock_ser_er, mock_ser_task, mock_judge, mock_eval_idx, mock_org, mock_access, mock_db):
        """Test TXT format export."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])

        mock_ser_task.return_value = {
            "id": "task-1",
            "data": {"text": "test"},
            "is_labeled": False,
            "created_at": None,
            "annotations": [],
            "generations": [],
            "evaluations": [],
        }

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="txt",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/plain"
        content = result.body.decode()
        assert "Test Project" in content

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.serializers.build_evaluation_indexes", return_value=({}, {}))
    @patch("routers.projects.serializers.build_judge_model_lookup", return_value={})
    @patch("routers.projects.serializers.serialize_evaluation_run")
    async def test_export_label_studio_format(self, mock_ser_er, mock_judge, mock_eval_idx, mock_org, mock_access, mock_db):
        """Test Label Studio format export."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        ann = _mock_annotation()
        gen = _mock_generation()
        self._setup_export_db(mock_db, tasks=[task], annotations=[ann], generations=[gen])

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="label_studio",
            download=False,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "application/json"
        body = json.loads(result.body.decode())
        assert isinstance(body, list)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_export_project_not_found(self, mock_org, mock_access, mock_db):
        """Test export when project not found."""
        from routers.projects.import_export import export_project

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await export_project(
                project_id="nonexistent",
                request=_mock_request(),
                format="json",
                download=True,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=False)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_export_access_denied(self, mock_org, mock_access, mock_db):
        """Test export when access denied."""
        from routers.projects.import_export import export_project

        mock_db.query.return_value.filter.return_value.first.return_value = _mock_project()

        with pytest.raises(Exception) as exc_info:
            await export_project(
                project_id="project-123",
                request=_mock_request(),
                format="json",
                download=True,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "denied" in str(exc_info.value.detail).lower()


class TestBulkExportProjects:
    """Test bulk_export_projects endpoint (POST /bulk-export)."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_json(self, mock_org, mock_access, mock_db):
        """Test bulk export in JSON format."""
        from routers.projects.import_export import bulk_export_projects

        project = _mock_project()
        task = _mock_task()

        from project_models import Annotation, Project, Task

        call_count = {"n": 0}

        def query_side_effect(model):
            call_count["n"] += 1
            q = MagicMock()
            if model == Project:
                q.filter.return_value.first.return_value = project
            elif model == Task:
                q.filter.return_value.count.return_value = 5
                q.filter.return_value.all.return_value = [task]
            elif model == Annotation:
                q.filter.return_value.count.return_value = 2
            else:
                q.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await bulk_export_projects(
            data={"project_ids": ["project-123"], "format": "json", "include_data": True},
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "application/json"
        body = json.loads(result.body.decode())
        assert "projects" in body
        assert len(body["projects"]) == 1

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_csv(self, mock_org, mock_access, mock_db):
        """Test bulk export in CSV format."""
        from routers.projects.import_export import bulk_export_projects

        project = _mock_project()

        from project_models import Annotation, Project, Task

        def query_side_effect(model):
            q = MagicMock()
            if model == Project:
                q.filter.return_value.first.return_value = project
            elif model == Task:
                q.filter.return_value.count.return_value = 3
            elif model == Annotation:
                q.filter.return_value.count.return_value = 1
            else:
                q.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await bulk_export_projects(
            data={"project_ids": ["project-123"], "format": "csv", "include_data": False},
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/csv"
        content = result.body.decode()
        assert "project_id" in content

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_unsupported_format(self, mock_org, mock_db):
        """Test bulk export with unsupported format raises error."""
        from routers.projects.import_export import bulk_export_projects

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await bulk_export_projects(
                data={"project_ids": [], "format": "xml"},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Unsupported format" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=False)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_skips_inaccessible_projects(self, mock_org, mock_access, mock_db):
        """Test that inaccessible projects are skipped in bulk export."""
        from routers.projects.import_export import bulk_export_projects

        project = _mock_project()
        mock_db.query.return_value.filter.return_value.first.return_value = project

        result = await bulk_export_projects(
            data={"project_ids": ["project-123"], "format": "json"},
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        body = json.loads(result.body.decode())
        assert len(body["projects"]) == 0


class TestBulkExportFullProjects:
    """Test bulk_export_full_projects endpoint (POST /bulk-export-full)."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_no_project_ids(self, mock_org, mock_db):
        """Test error when no project IDs provided."""
        from routers.projects.import_export import bulk_export_full_projects

        with pytest.raises(Exception) as exc_info:
            await bulk_export_full_projects(
                data={"project_ids": []},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "No project IDs" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_comprehensive_project_data")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_success(self, mock_org, mock_access, mock_comprehensive, mock_db):
        """Test successful full bulk export produces ZIP."""
        from routers.projects.import_export import bulk_export_full_projects

        project = _mock_project()
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_comprehensive.return_value = {"project": {"title": "Test"}, "tasks": []}

        result = await bulk_export_full_projects(
            data={"project_ids": ["project-123"]},
            request=_mock_request(),
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result.media_type == "application/zip"
        # Verify it's a valid ZIP
        zip_buffer = BytesIO(result.body)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            assert len(zf.namelist()) == 1

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_project_not_found(self, mock_org, mock_access, mock_db):
        """Test that non-existent projects result in 404."""
        from routers.projects.import_export import bulk_export_full_projects

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await bulk_export_full_projects(
                data={"project_ids": ["nonexistent"]},
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "No projects could be exported" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_comprehensive_project_data", side_effect=Exception("export error"))
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_error_handling(self, mock_org, mock_access, mock_comprehensive, mock_db):
        """Test that errors in individual project exports are handled gracefully."""
        from routers.projects.import_export import bulk_export_full_projects

        project = _mock_project()
        mock_db.query.return_value.filter.return_value.first.return_value = project

        # Should raise 404 because the only project failed to export
        with pytest.raises(Exception) as exc_info:
            await bulk_export_full_projects(
                data={"project_ids": ["project-123"]},
                request=_mock_request(),
                current_user=_mock_user(is_superadmin=True),
                db=mock_db,
            )
        assert "No projects could be exported" in str(exc_info.value.detail)


class TestImportFullProject:
    """Test import_full_project endpoint (POST /import-project)."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock(spec=Session)
        db.add = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        db.flush = MagicMock()
        return db

    def _create_upload_file(self, data, filename="test.json"):
        """Create a mock UploadFile."""
        content = json.dumps(data).encode("utf-8")
        file = Mock()
        file.filename = filename
        file.read = AsyncMock(return_value=content)
        return file

    def _create_zip_upload_file(self, data, filename="test.zip"):
        """Create a mock ZIP UploadFile containing a JSON file."""
        json_content = json.dumps(data).encode("utf-8")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("project.json", json_content)
        zip_buffer.seek(0)
        file = Mock()
        file.filename = filename
        file.read = AsyncMock(return_value=zip_buffer.getvalue())
        return file

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.notify_project_created")
    @patch("routers.projects.import_export.get_user_with_memberships")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_basic(self, mock_org, mock_get_user, mock_notify, mock_db):
        """Test basic full project import."""
        from routers.projects.import_export import import_full_project

        # Mock user memberships
        membership = Mock()
        membership.organization_id = "org-123"
        membership.is_active = True
        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [membership]
        mock_get_user.return_value = user_with_memberships

        # Mock db.query(Project).filter(Project.title == ...).first() -> None (no conflict)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        import_data = {
            "format_version": "1.0.0",
            "project": {
                "id": "old-project-1",
                "title": "Test Import",
                "description": "A test project",
            },
            "tasks": [
                {"id": "old-task-1", "data": {"text": "Task 1"}, "is_labeled": False}
            ],
            "annotations": [],
            "users": [],
        }

        file = self._create_upload_file(import_data)

        result = await import_full_project(
            request=_mock_request(),
            file=file,
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result["message"] == "Project imported successfully"
        assert result["project_title"] == "Test Import"
        assert result["statistics"]["imported_counts"]["tasks"] == 1

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_invalid_json(self, mock_org, mock_db):
        """Test import with invalid JSON."""
        from routers.projects.import_export import import_full_project

        file = Mock()
        file.filename = "bad.json"
        file.read = AsyncMock(return_value=b"not valid json{{{")

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Invalid JSON" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_unsupported_format_version(self, mock_org, mock_db):
        """Test import with unsupported format version."""
        from routers.projects.import_export import import_full_project

        data = {"format_version": "2.0.0", "project": {"title": "Test"}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Unsupported" in str(exc_info.value.detail)

    def _create_upload_file(self, data, filename="test.json"):
        content = json.dumps(data).encode("utf-8")
        file = Mock()
        file.filename = filename
        file.read = AsyncMock(return_value=content)
        return file

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_no_project_data(self, mock_org, mock_db):
        """Test import with missing project data."""
        from routers.projects.import_export import import_full_project

        data = {"format_version": "1.0.0", "project": {}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "No project data" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_unsupported_file_type(self, mock_org, mock_db):
        """Test import with unsupported file type."""
        from routers.projects.import_export import import_full_project

        file = Mock()
        file.filename = "test.csv"
        file.read = AsyncMock(return_value=b"data")

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Only JSON and ZIP" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.notify_project_created")
    @patch("routers.projects.import_export.get_user_with_memberships")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_from_zip(self, mock_org, mock_get_user, mock_notify, mock_db):
        """Test importing from a ZIP file."""
        from routers.projects.import_export import import_full_project

        membership = Mock()
        membership.organization_id = "org-123"
        membership.is_active = True
        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [membership]
        mock_get_user.return_value = user_with_memberships

        mock_db.query.return_value.filter.return_value.first.return_value = None

        import_data = {
            "format_version": "1.0.0",
            "project": {"id": "old-p-1", "title": "ZIP Import"},
            "tasks": [],
            "users": [],
        }

        file = self._create_zip_upload_file(import_data)

        result = await import_full_project(
            request=_mock_request(),
            file=file,
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result["project_title"] == "ZIP Import"

    def _create_zip_upload_file(self, data, filename="test.zip"):
        json_content = json.dumps(data).encode("utf-8")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("project.json", json_content)
        zip_buffer.seek(0)
        file = Mock()
        file.filename = filename
        file.read = AsyncMock(return_value=zip_buffer.getvalue())
        return file

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_bad_zip(self, mock_org, mock_db):
        """Test import with corrupt ZIP file."""
        from routers.projects.import_export import import_full_project

        file = Mock()
        file.filename = "corrupt.zip"
        file.read = AsyncMock(return_value=b"not a zip file")

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Invalid ZIP" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_zip_no_json(self, mock_org, mock_db):
        """Test import from ZIP with no JSON files inside."""
        from routers.projects.import_export import import_full_project

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("readme.txt", "No JSON here")
        zip_buffer.seek(0)

        file = Mock()
        file.filename = "nojson.zip"
        file.read = AsyncMock(return_value=zip_buffer.getvalue())

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "no JSON" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_user_with_memberships")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_no_org_membership(self, mock_org, mock_get_user, mock_db):
        """Test import when user has no organization membership."""
        from routers.projects.import_export import import_full_project

        mock_get_user.return_value = Mock(organization_memberships=[])
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = {"format_version": "1.0.0", "project": {"title": "Test"}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "organization" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.notify_project_created")
    @patch("routers.projects.import_export.get_user_with_memberships")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_with_all_entity_types(self, mock_org, mock_get_user, mock_notify, mock_db):
        """Test importing a project with all entity types."""
        from routers.projects.import_export import import_full_project

        membership = Mock()
        membership.organization_id = "org-123"
        membership.is_active = True
        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [membership]
        mock_get_user.return_value = user_with_memberships
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        data = {
            "format_version": "1.0.0",
            "project": {"id": "old-proj", "title": "Full Import"},
            "tasks": [{"id": "t-1", "data": {"text": "Task"}}],
            "annotations": [
                {"id": "a-1", "task_id": "t-1", "completed_by": "u-1", "result": []}
            ],
            "users": [{"id": "u-1", "email": "user@example.com"}],
            "response_generations": [
                {"id": "rg-1", "task_id": "t-1", "model_id": "gpt-4", "status": "completed"}
            ],
            "generations": [
                {"id": "g-1", "task_id": "t-1", "generation_id": "rg-1", "model_id": "gpt-4"}
            ],
            "evaluations": [
                {"id": "e-1", "model_id": "gpt-4", "status": "completed"}
            ],
            "evaluation_metrics": [
                {"id": "em-1", "evaluation_id": "e-1", "evaluation_type_id": "acc", "value": 0.9}
            ],
            "task_evaluations": [
                {"id": "te-1", "evaluation_id": "e-1", "task_id": "t-1"}
            ],
            "human_evaluation_sessions": [
                {"id": "hes-1", "evaluator_id": "u-1", "session_type": "likert"}
            ],
            "preference_rankings": [
                {"id": "pr-1", "session_id": "hes-1", "task_id": "t-1", "winner": "a"}
            ],
            "likert_scale_evaluations": [
                {"id": "lse-1", "session_id": "hes-1", "task_id": "t-1", "dimension": "quality", "rating": 4}
            ],
            "project_members": [
                {"id": "pm-1", "user_id": "u-1", "role": "annotator"}
            ],
            "task_assignments": [],
            "post_annotation_responses": [
                {"id": "par-1", "annotation_id": "a-1", "task_id": "t-1", "result": []}
            ],
        }

        file = self._create_upload_file(data)

        result = await import_full_project(
            request=_mock_request(),
            file=file,
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result["message"] == "Project imported successfully"
        stats = result["statistics"]["imported_counts"]
        assert stats["tasks"] == 1
        assert stats["annotations"] == 1

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_db_error_rollback(self, mock_org, mock_db):
        """Test that database errors cause rollback."""
        from routers.projects.import_export import import_full_project

        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("DB commit failed")

        # Need user memberships for the code to get past that check
        with patch("routers.projects.import_export.get_user_with_memberships") as mock_get_user:
            membership = Mock()
            membership.organization_id = "org-123"
            membership.is_active = True
            user_with_memberships = Mock()
            user_with_memberships.organization_memberships = [membership]
            mock_get_user.return_value = user_with_memberships

            data = {
                "format_version": "1.0.0",
                "project": {"title": "Test"},
                "tasks": [],
            }
            file = self._create_upload_file(data)

            with pytest.raises(Exception) as exc_info:
                await import_full_project(
                    request=_mock_request(),
                    file=file,
                    current_user=_mock_user(is_superadmin=True),
                    db=mock_db,
                )
            assert "Import failed" in str(exc_info.value.detail)
            mock_db.rollback.assert_called()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_user_with_memberships")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_no_active_membership(self, mock_org, mock_get_user, mock_db):
        """Test import when user has no active organization membership."""
        from routers.projects.import_export import import_full_project

        inactive_membership = Mock()
        inactive_membership.is_active = False
        user_with_memberships = Mock()
        user_with_memberships.organization_memberships = [inactive_membership]
        mock_get_user.return_value = user_with_memberships
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = {"format_version": "1.0.0", "project": {"title": "Test"}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "active organization" in str(exc_info.value.detail).lower()
