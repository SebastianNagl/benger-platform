"""
Unit tests for routers/projects/import_export.py covering uncovered lines.

Covers:
- bulk_export_projects endpoint (POST /bulk-export)
- bulk_export_full_projects endpoint (POST /bulk-export-full)

The single-project sync import/export endpoints were removed in the #158
follow-up (object storage is now the only transport — see CLAUDE.md "Object
storage (MinIO)"). The async job endpoints are covered by the integration
round-trip tests against the shared drivers. Only the multi-project bulk-export
admin endpoints (still synchronous, out of #158 scope) remain unit-tested here.
"""

import json
import zipfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

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
