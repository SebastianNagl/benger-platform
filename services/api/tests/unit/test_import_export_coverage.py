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
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session


def _mock_request(headers=None, body=None):
    """Create a mock Request object.

    `body` can be bytes, str, or a JSON-serialisable Python object. When
    provided, exposes `request.stream()` as an async generator so the
    streaming-import handler can consume the body the same way Starlette
    delivers it in production.
    """
    r = Mock()
    r.headers = headers or {}
    r.state = Mock(spec=[])

    if body is None:
        chunks = []
    elif isinstance(body, bytes):
        chunks = [body]
    elif isinstance(body, str):
        chunks = [body.encode("utf-8")]
    else:
        chunks = [json.dumps(body).encode("utf-8")]

    async def _stream():
        for chunk in chunks:
            yield chunk

    r.stream = _stream
    return r


def _import_data_to_body(data):
    """Convert a ProjectImportData (or Mock thereof) into a JSON body.

    Tests build `ProjectImportData` instances or duck-typed mocks; the
    streaming handler now reads the raw body, so we serialise back to JSON.
    """
    if hasattr(data, "model_dump_json"):
        return data.model_dump_json().encode("utf-8")
    payload = {
        "data": getattr(data, "data", []) or [],
        "meta": getattr(data, "meta", None),
        "evaluation_runs": getattr(data, "evaluation_runs", None),
    }
    return json.dumps(payload).encode("utf-8")


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
                request=_mock_request(body={"data": [], "meta": {}}),
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
                request=_mock_request(body={"data": [], "meta": {}}),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
                request=_mock_request(body=_import_data_to_body(data)),
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
            request=_mock_request(body=_import_data_to_body(data)),
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
                q.filter.return_value.count.return_value = len(tasks)
            elif model == Annotation:
                q.filter.return_value.all.return_value = annotations
                q.filter.return_value.count.return_value = len(annotations)
            elif model == Generation:
                q.filter.return_value.all.return_value = generations
                q.filter.return_value.count.return_value = len(generations)
            elif model == PostAnnotationResponse:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.count.return_value = 0
            elif model == EvaluationRun:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.count.return_value = 0
            elif model == TaskEvaluation:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.count.return_value = 0
            else:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.first.return_value = None
                q.filter.return_value.count.return_value = 0
            return q

        mock_db.query.side_effect = query_side_effect

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.import_export.stream_export_json")
    async def test_export_json_format(self, mock_stream, mock_org, mock_access, mock_db):
        """Test JSON format export. JSON now returns a StreamingResponse so the
        body must be drained from `body_iterator` rather than read off `.body`,
        and the helper that emits the per-row JSON is patched in directly —
        the heavy serialization is exercised by the integration suite at
        `tests/integration/test_export_formats_coverage.py` instead."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])
        mock_stream.return_value = iter(['{"project": {"id": "x"}, "tasks": []}'])

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="json",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "application/json"
        chunks = []
        async for chunk in result.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        body = json.loads("".join(chunks))
        assert "project" in body
        assert "tasks" in body
        # Streaming helper was actually invoked rather than the legacy
        # in-memory builder (regression guard for the OOM fix).
        mock_stream.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.import_export.stream_export_flat_csv")
    async def test_export_csv_format(self, mock_stream, mock_org, mock_access, mock_db):
        """Test CSV format export. CSV streams via stream_export_flat_csv;
        body must be drained from the iterator. Real row layout is exercised
        by tests/integration/test_export_formats_coverage.py."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])
        mock_stream.return_value = iter(["task_id,task_data\n", "t1,\"{}\"\n"])

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="csv",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/csv"
        chunks = []
        async for chunk in result.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        content = "".join(chunks)
        assert "task_id" in content
        mock_stream.assert_called_once()

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
    @patch("routers.projects.import_export.stream_export_txt")
    async def test_export_txt_format(self, mock_stream, mock_org, mock_access, mock_db):
        """Test TXT format export. TXT streams via stream_export_txt; body
        must be drained from the iterator. Real formatting is exercised by
        tests/integration/test_export_formats_coverage.py."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])
        mock_stream.return_value = iter(["Project: Test Project\n", "Total Tasks: 1\n"])

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="txt",
            download=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "text/plain"
        chunks = []
        async for chunk in result.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        content = "".join(chunks)
        assert "Test Project" in content
        mock_stream.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    @patch("routers.projects.import_export.stream_export_label_studio")
    async def test_export_label_studio_format(self, mock_stream, mock_org, mock_access, mock_db):
        """Test Label Studio format export. Now streams via
        stream_export_label_studio; body must be drained from the iterator.
        Real LS conversion (including span format) is exercised by
        tests/unit/test_coverage_push_export_branches.py."""
        from routers.projects.import_export import export_project

        task = _mock_task()
        self._setup_export_db(mock_db, tasks=[task])
        mock_stream.return_value = iter(["[", "{\"id\": 1, \"data\": {}}", "]"])

        result = await export_project(
            project_id="project-123",
            request=_mock_request(),
            format="label_studio",
            download=False,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.media_type == "application/json"
        chunks = []
        async for chunk in result.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        body = json.loads("".join(chunks))
        assert isinstance(body, list)
        mock_stream.assert_called_once()

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
    @patch("routers.projects.import_export.stream_comprehensive_project_data_json")
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_success(self, mock_org, mock_access, mock_stream, mock_db):
        """Test successful full bulk export produces ZIP.

        The handler now streams each project's comprehensive JSON straight
        into the zip entry via stream_comprehensive_project_data_json and
        returns a FileResponse from a tempfile (zip on disk, not BytesIO)
        — this test only checks the wiring; the real per-row content is
        exercised by tests/routers/projects/test_export_import_roundtrip.py.
        """
        from routers.projects.import_export import bulk_export_full_projects

        project = _mock_project()
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_stream.return_value = iter(['{"project":{"title":"Test"},"tasks":[]}'])

        result = await bulk_export_full_projects(
            data={"project_ids": ["project-123"]},
            request=_mock_request(),
            current_user=_mock_user(is_superadmin=True),
            db=mock_db,
        )

        assert result.media_type == "application/zip"
        # FileResponse exposes the underlying tempfile path; read it back to
        # verify the zip is well-formed and contains the streamed entry.
        with zipfile.ZipFile(result.path, 'r') as zf:
            assert len(zf.namelist()) == 1
        mock_stream.assert_called_once()
        # The handler schedules an unlink-after-send background task; run it
        # ourselves here so the tempfile doesn't linger across tests.
        if result.background:
            result.background.func(*result.background.args, **result.background.kwargs)

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
    @patch("routers.projects.import_export.stream_comprehensive_project_data_json", side_effect=Exception("export error"))
    @patch("routers.projects.import_export.check_project_accessible", return_value=True)
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_bulk_export_full_error_handling(self, mock_org, mock_access, mock_stream, mock_db):
        """Test that errors in individual project exports are handled gracefully."""
        from routers.projects.import_export import bulk_export_full_projects

        project = _mock_project()
        mock_db.query.return_value.filter.return_value.first.return_value = project

        # Should raise 404 because the only project failed to export. The
        # handler also cleans up its tempfile on the empty-zip path, so no
        # file is left behind for the test to chase.
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
        """Create a mock UploadFile.

        The handler reads from `file.file` (a file-like object) rather than
        `await file.read()`, so we hand back a BytesIO that supports seek/read.
        """
        content = json.dumps(data).encode("utf-8")
        file = Mock()
        file.filename = filename
        file.file = BytesIO(content)
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
        file.file = zip_buffer
        return file

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_basic(self, mock_org, mock_driver, mock_db):
        """The endpoint spools the JSON upload and hands it to the streaming driver.

        Entity-insertion behaviour lives in the shared ``run_full_project_import``
        driver (issue #158) and is covered against a real DB in
        ``tests/integration/test_import_export_deep2.py::TestImportFullProject``.
        Here we verify the thin endpoint's own job: parse the upload into a
        seekable spool and forward it (plus the caller's id) to the driver,
        returning the driver's result unchanged.
        """
        from routers.projects.import_export import import_full_project

        captured = {}

        def fake_driver(db, fileobj, user_id):
            fileobj.seek(0)
            captured["body"] = fileobj.read()
            captured["user_id"] = user_id
            return {
                "message": "Project imported successfully",
                "project_title": "Test Import",
                "statistics": {"imported_counts": {"tasks": 1}},
            }

        mock_driver.side_effect = fake_driver

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
        user = _mock_user(is_superadmin=True)

        result = await import_full_project(
            request=_mock_request(),
            file=file,
            current_user=user,
            db=mock_db,
        )

        # Endpoint returns the driver's result unchanged.
        assert result["message"] == "Project imported successfully"
        assert result["project_title"] == "Test Import"
        assert result["statistics"]["imported_counts"]["tasks"] == 1
        # Driver received the uploaded JSON (seekable spool) and the caller's id.
        assert json.loads(captured["body"])["project"]["title"] == "Test Import"
        assert captured["user_id"] == user.id

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_invalid_json(self, mock_org, mock_db):
        """Test import with invalid JSON."""
        from routers.projects.import_export import import_full_project

        file = Mock()
        file.filename = "bad.json"
        file.file = BytesIO(b"not valid json{{{")

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
        file.file = BytesIO(b"data")

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "Only JSON and ZIP" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_from_zip(self, mock_org, mock_driver, mock_db):
        """The endpoint extracts the inner JSON from a ZIP into a seekable spool.

        ``zip_file.open()`` yields a non-seekable stream, so the endpoint copies
        the inner JSON into a ``SpooledTemporaryFile`` before the ijson driver
        (which seeks for multi-pass parsing) can consume it (issue #158). We
        assert the driver received the decompressed inner JSON.
        """
        from routers.projects.import_export import import_full_project

        captured = {}

        def fake_driver(db, fileobj, user_id):
            fileobj.seek(0)
            captured["body"] = fileobj.read()
            return {
                "message": "Project imported successfully",
                "project_title": "ZIP Import",
                "statistics": {"imported_counts": {"tasks": 0}},
            }

        mock_driver.side_effect = fake_driver

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
        # The driver saw the inner JSON, proving the zip was extracted into the spool.
        assert json.loads(captured["body"])["project"]["title"] == "ZIP Import"

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_bad_zip(self, mock_org, mock_db):
        """Test import with corrupt ZIP file."""
        from routers.projects.import_export import import_full_project

        file = Mock()
        file.filename = "corrupt.zip"
        file.file = BytesIO(b"not a zip file")

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
        file.file = zip_buffer

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "no JSON" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_no_org_membership(self, mock_org, mock_driver, mock_db):
        """Endpoint surfaces the driver's no-organization-membership error as 400.

        The driver raises ``ImportValidationError(400, ...)`` when the importing
        user has no org membership; the endpoint maps it to the same-status
        HTTPException and rolls back (issue #158).
        """
        from routers.projects.import_export import ImportValidationError, import_full_project

        mock_driver.side_effect = ImportValidationError(
            400, "User must be a member of an organization to import projects"
        )

        data = {"format_version": "1.0.0", "project": {"title": "Test"}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 400
        assert "organization" in str(exc_info.value.detail).lower()
        mock_db.rollback.assert_called()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_with_all_entity_types(self, mock_org, mock_driver, mock_db):
        """The endpoint forwards a multi-entity comprehensive body to the driver intact.

        FK-ordered insertion of every entity type is exercised against a real DB
        in ``tests/integration/test_import_export_deep2.py``; this unit test
        guards that the endpoint spools a large body without mangling it.
        """
        from routers.projects.import_export import import_full_project

        captured = {}

        def fake_driver(db, fileobj, user_id):
            fileobj.seek(0)
            captured["body"] = json.loads(fileobj.read())
            return {
                "message": "Project imported successfully",
                "project_title": "Full Import",
                "statistics": {"imported_counts": {"tasks": 1, "annotations": 1}},
            }

        mock_driver.side_effect = fake_driver

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
        # Body reached the driver intact — every entity array survived spooling.
        assert captured["body"]["post_annotation_responses"][0]["id"] == "par-1"
        assert captured["body"]["likert_scale_evaluations"][0]["rating"] == 4

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_db_error_rollback(self, mock_org, mock_driver, mock_db):
        """An unexpected driver error rolls back and surfaces as a 500.

        The driver owns the single end-of-import ``db.commit()``; if it (or any
        insert pass) raises, the endpoint's generic handler rolls back the
        partially-flushed rows and returns ``Import failed`` (issue #158).
        """
        from routers.projects.import_export import import_full_project

        mock_driver.side_effect = Exception("DB commit failed")

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
        assert exc_info.value.status_code == 500
        assert "Import failed" in str(exc_info.value.detail)
        mock_db.rollback.assert_called()

    @pytest.mark.asyncio
    @patch("routers.projects.import_export.run_full_project_import")
    @patch("routers.projects.import_export.get_org_context_from_request", return_value="org-123")
    async def test_import_full_project_no_active_membership(self, mock_org, mock_driver, mock_db):
        """Endpoint surfaces the driver's no-active-membership error as 400.

        The driver requires the importing user to have an *active* org
        membership and otherwise raises ``ImportValidationError(400, ...)``,
        which the endpoint maps to a same-status HTTPException (issue #158).
        """
        from routers.projects.import_export import ImportValidationError, import_full_project

        mock_driver.side_effect = ImportValidationError(
            400, "User must have an active organization membership"
        )

        data = {"format_version": "1.0.0", "project": {"title": "Test"}}
        file = self._create_upload_file(data)

        with pytest.raises(Exception) as exc_info:
            await import_full_project(
                request=_mock_request(),
                file=file,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 400
        assert "active organization" in str(exc_info.value.detail).lower()
        mock_db.rollback.assert_called()
