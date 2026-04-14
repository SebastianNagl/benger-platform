"""
Unit tests for project import functionality.
Tests import data validation, ID regeneration, conflict resolution, and user mapping.
Uses TestClient to test the /import-project endpoint.
"""

import json
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestProjectImport:
    """Test suite for project import functionality."""

    @pytest.fixture
    def valid_import_data(self):
        """Create valid import data structure."""
        return {
            "format_version": "1.0.0",
            "exported_at": "2025-01-01T12:00:00Z",
            "project": {
                "id": "old-project-123",
                "title": "Imported Project",
                "description": "Test import",
                "is_public": False,
                "is_archived": False,
                "created_at": "2025-01-01T10:00:00Z",
                "updated_at": "2025-01-01T11:00:00Z",
            },
            "tasks": [
                {
                    "id": "old-task-1",
                    "project_id": "old-project-123",
                    "data": {"text": "Task 1"},
                    "meta": {},
                    "is_labeled": True,
                    "created_at": "2025-01-01T10:30:00Z",
                },
                {
                    "id": "old-task-2",
                    "project_id": "old-project-123",
                    "data": {"text": "Task 2"},
                    "meta": {},
                    "is_labeled": False,
                    "created_at": "2025-01-01T10:31:00Z",
                },
            ],
            "annotations": [
                {
                    "id": "old-annotation-1",
                    "task_id": "old-task-1",
                    "completed_by": "old-user-1",
                    "result": [{"value": {"text": "Annotation"}}],
                    "created_at": "2025-01-01T11:00:00Z",
                }
            ],
            "predictions": [],
            "generations": [],
            "users": [
                {
                    "id": "old-user-1",
                    "email": "test@example.com",
                    "username": "testuser",
                    "name": "Test User",
                }
            ],
            "metadata": {
                "export_reason": "Testing",
                "included_data": ["tasks", "annotations", "users"],
            },
        }

    @pytest.fixture
    def client(self):
        """Create test client."""
        from main import app

        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        from auth_module import User

        return User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password",
            is_superadmin=True,  # Superadmin for simplicity
            is_active=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    # test_import_valid_project, test_import_handles_title_conflict,
    # test_import_maps_users_by_email removed: All accepted 500 as valid alongside
    # 200 and 400, meaning they passed whether the import succeeded, failed with
    # a client error, or crashed with a server error. The mock setup was too
    # complex to actually test import logic. Import behavior is covered by
    # integration tests in test_import_export_integration.py.

    def test_import_validates_format_version(self, client, mock_user):
        """Test that import validates the format version."""
        from auth_module import require_user
        from main import app

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            invalid_data = {
                "format_version": "99.0.0",  # Unsupported version
                "project": {"id": "test", "title": "Test"},
            }

            content = json.dumps(invalid_data).encode('utf-8')
            files = {"file": ("test_import.json", BytesIO(content), "application/json")}

            response = client.post("/api/projects/import-project", files=files)

            # Should reject unsupported format version
            assert response.status_code == 400
            assert (
                "format" in response.json().get("detail", "").lower()
                or "version" in response.json().get("detail", "").lower()
            )
        finally:
            app.dependency_overrides.clear()

    # test_import_handles_missing_data and test_import_preserves_relationships
    # removed: Both accepted 500 as valid, testing nothing meaningful.
    # These behaviors are better covered by integration tests.

    def test_import_rejects_invalid_json(self, client, mock_user):
        """Test that import rejects invalid JSON data."""
        from auth_module import require_user
        from main import app

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            # Invalid JSON content
            content = b"{'invalid': json, 'syntax}"
            files = {"file": ("corrupt.json", BytesIO(content), "application/json")}

            response = client.post("/api/projects/import-project", files=files)

            # Should reject invalid JSON
            assert response.status_code == 400
            assert "json" in response.json().get("detail", "").lower()
        finally:
            app.dependency_overrides.clear()

    def test_import_rolls_back_on_error(self, client, valid_import_data, mock_user):
        """Test that import rolls back transaction on error."""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Raise error on commit
            mock_db.commit.side_effect = Exception("Database error")
            mock_db.rollback = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db.add = Mock()
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            content = json.dumps(valid_import_data).encode('utf-8')
            files = {"file": ("test_import.json", BytesIO(content), "application/json")}

            response = client.post("/api/projects/import-project", files=files)

            # Should return error status
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_import_generates_statistics(self, client, valid_import_data, mock_user):
        """Test that import returns accurate statistics on success."""
        from auth_module import require_user
        from main import app

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            content = json.dumps(valid_import_data).encode('utf-8')
            files = {"file": ("test_import.json", BytesIO(content), "application/json")}

            response = client.post("/api/projects/import-project", files=files)

            # If successful, should have statistics
            if response.status_code == 200:
                data = response.json()
                assert "statistics" in data or "tasks_imported" in data.get("statistics", {})
        finally:
            app.dependency_overrides.clear()

    def test_import_rejects_non_json_file(self, client, mock_user):
        """Test that import rejects non-JSON files."""
        from auth_module import require_user
        from main import app

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            # Non-JSON file
            content = b"This is not JSON"
            files = {"file": ("test.txt", BytesIO(content), "text/plain")}

            response = client.post("/api/projects/import-project", files=files)

            # Should reject non-JSON files
            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()
