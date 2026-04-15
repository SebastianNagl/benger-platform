"""
Test for Issue #581: Fix 500 error on data import
Tests the fix for redundant ResponseGeneration import and missing project_id field
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy.orm import Session


def _mock_request():
    mock_request = Mock()
    mock_request.headers = {}
    mock_request.state = Mock(spec=[])
    return mock_request


class TestImportFix581:
    """Test suite for Issue #581 fix - import endpoint working for org_admin users"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        mock = MagicMock(spec=Session)
        mock.add = MagicMock()
        mock.commit = MagicMock()
        mock.rollback = MagicMock()
        mock.query.return_value.filter.return_value.first.return_value = Mock(
            id="test-project-id", title="Test Project"
        )
        mock.execute.return_value.scalar.return_value = True  # has_project_access
        return mock

    @pytest.fixture
    def mock_user_org_admin(self):
        """Create a mock org_admin user."""
        user = Mock()
        user.id = "user-123"
        user.name = "Test User"
        user.email = "test@example.com"
        user.is_superadmin = False
        user.role = "org_admin"
        return user

    @pytest.fixture
    def mock_user_superadmin(self):
        """Create a mock superadmin user."""
        user = Mock()
        user.id = "superadmin-123"
        user.name = "Super Admin"
        user.email = "admin@example.com"
        user.is_superadmin = True
        user.role = "superadmin"
        return user

    @pytest.fixture
    def import_data_with_generations(self):
        """Create import data that includes generations (triggers ResponseGeneration creation)"""
        return {
            "data": [
                {
                    "id": "task-001",
                    "data": {"text": "Sample task"},
                    "meta": {"category": "test"},
                    "annotations": [],
                    "generations": [
                        {
                            "model_id": "gpt-4",
                            "response_content": "Generated response",
                            "response_metadata": {},
                        }
                    ],
                }
            ],
            "meta": {"source": "test"},
        }

    @pytest.mark.asyncio
    @patch('routers.projects.import_export.check_project_accessible', return_value=True)
    @patch('projects_api.uuid.uuid4')
    async def test_import_data_with_generations_org_admin(
        self, mock_uuid, mock_access, mock_db, mock_user_org_admin, import_data_with_generations
    ):
        """Test that org_admin users can import data with generations after fix"""
        from project_schemas import ProjectImportData
        from projects_api import import_data

        # Setup UUID mock
        mock_uuid.side_effect = ["new-task-id", "response-gen-id", "generation-id"]

        # Convert dict to Pydantic model
        data = ProjectImportData(**import_data_with_generations)

        # Test import as org_admin
        result = await import_data(
            project_id="test-project-id", data=data, request=_mock_request(), current_user=mock_user_org_admin, db=mock_db
        )

        # Verify success
        assert result["created_tasks"] == 1
        assert result["created_generations"] == 1
        assert result["project_id"] == "test-project-id"

        # Verify commit was called (no exception thrown)
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    @pytest.mark.asyncio
    @patch('projects_api.uuid.uuid4')
    async def test_import_data_with_generations_superadmin(
        self, mock_uuid, mock_db, mock_user_superadmin, import_data_with_generations
    ):
        """Test that superadmin users can also import data with generations"""
        from project_schemas import ProjectImportData
        from projects_api import import_data

        # Setup UUID mock
        mock_uuid.side_effect = ["new-task-id", "response-gen-id", "generation-id"]

        # Convert dict to Pydantic model
        data = ProjectImportData(**import_data_with_generations)

        # Test import as superadmin
        result = await import_data(
            project_id="test-project-id", data=data, request=_mock_request(), current_user=mock_user_superadmin, db=mock_db
        )

        # Verify success
        assert result["created_tasks"] == 1
        assert result["created_generations"] == 1
        assert result["project_id"] == "test-project-id"

        # Verify commit was called
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    @pytest.mark.asyncio
    @patch('routers.projects.import_export.check_project_accessible', return_value=True)
    async def test_response_generation_has_correct_fields(
        self, mock_access, mock_db, mock_user_org_admin, import_data_with_generations
    ):
        """Test that ResponseGeneration is created with all required fields including project_id"""
        from project_schemas import ProjectImportData
        from projects_api import import_data

        # Convert dict to Pydantic model
        data = ProjectImportData(**import_data_with_generations)

        # Capture what's added to the database
        added_objects = []
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)

        # Import data
        with patch('projects_api.uuid.uuid4', side_effect=["task-id", "resp-gen-id", "gen-id"]):
            await import_data(
                project_id="test-project-id",
                data=data,
                request=_mock_request(),
                current_user=mock_user_org_admin,
                db=mock_db,
            )

        # Find ResponseGeneration object in added objects
        response_gen = None
        for obj in added_objects:
            if hasattr(obj, '__class__') and obj.__class__.__name__ == 'ResponseGeneration':
                response_gen = obj
                break

        # Verify ResponseGeneration has all required fields
        assert response_gen is not None, "ResponseGeneration should be created"
        assert response_gen.id == "resp-gen-id"
        assert response_gen.task_id == "task-id"
        assert response_gen.project_id == "test-project-id", "project_id field should be set"
        assert response_gen.model_id == "gpt-4"
        assert response_gen.status == "completed"
        assert response_gen.created_by == mock_user_org_admin.id

    def test_no_redundant_imports_in_function(self):
        """Test that there are no redundant imports in the import_data function"""
        import inspect

        from projects_api import import_data

        # Get the source code of the import_data function
        source = inspect.getsource(import_data)

        # Check that there's no local import of ResponseGeneration
        # (it should be imported at module level only)
        assert (
            "from models import ResponseGeneration" not in source
        ), "ResponseGeneration should not be imported inside the function"

    def test_calculate_generation_stats_no_redundant_import(self):
        """Test that calculate_generation_stats has no redundant import"""
        import inspect

        from projects_api import calculate_generation_stats

        # Get the source code of the function
        source = inspect.getsource(calculate_generation_stats)

        # Check that there's no local import of ResponseGeneration
        assert (
            "from models import ResponseGeneration" not in source
        ), "ResponseGeneration should not be imported inside calculate_generation_stats"

    @pytest.mark.asyncio
    @patch('routers.projects.import_export.check_project_accessible', return_value=True)
    @patch('projects_api.uuid.uuid4')
    async def test_import_without_generations_still_works(
        self, mock_uuid, mock_access, mock_db, mock_user_org_admin
    ):
        """Test that import without generations still works after fix"""
        from project_schemas import ProjectImportData
        from projects_api import import_data

        # Data without generations
        data = ProjectImportData(data=[{"data": {"text": "Task without generation"}, "meta": {}}])

        mock_uuid.return_value = "new-task-id"

        # Import should work without creating ResponseGeneration
        result = await import_data(
            project_id="test-project-id", data=data, request=_mock_request(), current_user=mock_user_org_admin, db=mock_db
        )

        assert result["created_tasks"] == 1
        assert result["created_generations"] == 0
        mock_db.commit.assert_called_once()
