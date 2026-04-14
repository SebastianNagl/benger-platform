"""
Tests for prompt_structures router.

Targets: routers/prompt_structures.py lines 33-39, 49-66, 71-81, 99-123, 139-173, 189-217, 235-263, 279-310
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestValidateStructureKey:
    """Test the validate_structure_key helper."""

    def test_valid_key(self):
        from routers.prompt_structures import validate_structure_key
        # Should not raise
        validate_structure_key("my_structure_1")

    def test_valid_key_with_hyphens(self):
        from routers.prompt_structures import validate_structure_key
        validate_structure_key("my-structure")

    def test_empty_key_raises(self):
        from routers.prompt_structures import validate_structure_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("")
        assert exc_info.value.status_code == 400

    def test_too_long_key_raises(self):
        from routers.prompt_structures import validate_structure_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("a" * 51)
        assert exc_info.value.status_code == 400

    def test_invalid_characters_raises(self):
        from routers.prompt_structures import validate_structure_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("invalid key!")
        assert exc_info.value.status_code == 400

    def test_special_characters_raises(self):
        from routers.prompt_structures import validate_structure_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("key/with/slashes")
        assert exc_info.value.status_code == 400


class TestEnsureGenerationConfigStructure:
    """Test ensure_generation_config_structure helper."""

    def test_none_config(self):
        from routers.prompt_structures import ensure_generation_config_structure
        project = Mock()
        project.generation_config = None
        ensure_generation_config_structure(project)
        assert project.generation_config is not None
        assert "selected_configuration" in project.generation_config
        assert "prompt_structures" in project.generation_config

    def test_empty_config(self):
        from routers.prompt_structures import ensure_generation_config_structure
        project = Mock()
        project.generation_config = {}
        ensure_generation_config_structure(project)
        assert "selected_configuration" in project.generation_config
        assert "prompt_structures" in project.generation_config

    def test_partial_config(self):
        from routers.prompt_structures import ensure_generation_config_structure
        project = Mock()
        project.generation_config = {"selected_configuration": {"models": []}}
        ensure_generation_config_structure(project)
        assert "prompt_structures" in project.generation_config


class TestGetProjectOr403:
    """Test get_project_or_403 helper."""

    def test_project_not_found(self):
        from routers.prompt_structures import get_project_or_403
        from fastapi import HTTPException

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_project_or_403("proj-1", Mock(), mock_db)
        assert exc_info.value.status_code == 404

    def test_no_permission(self):
        from routers.prompt_structures import get_project_or_403
        from fastapi import HTTPException

        mock_db = Mock(spec=Session)
        mock_project = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.prompt_structures.auth_service") as mock_auth:
            mock_auth.check_project_access.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_project_or_403("proj-1", Mock(), mock_db)
            assert exc_info.value.status_code == 403


class TestPromptStructureEndpoints:
    """Test prompt structure CRUD endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        return User(
            id="ps-user",
            username="psuser",
            email="ps@test.com",
            name="PS User",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def _setup_overrides(self, mock_user, mock_db):
        from database import get_db
        from auth_module.dependencies import require_user
        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

    def test_create_structure(self, client, mock_user):
        """Test creating a prompt structure."""
        mock_db = Mock(spec=Session)

        class FakeProject:
            id = "proj-1"
            generation_config = {}

        mock_project = FakeProject()

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch("routers.prompt_structures.auth_service") as mock_auth, \
             patch("sqlalchemy.orm.attributes.flag_modified"):
            mock_auth.check_project_access.return_value = True

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.put(
                    "/api/projects/proj-1/generation-config/structures/my_struct",
                    json={
                        "name": "My Structure",
                        "system_prompt": "You are a legal expert.",
                        "instruction_prompt": "Analyze: {text}",
                    },
                )
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["key"] == "my_struct"
            finally:
                app.dependency_overrides.clear()

    def test_delete_structure_not_found(self, client, mock_user):
        """Test deleting non-existent structure."""
        mock_db = Mock(spec=Session)
        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.generation_config = {"prompt_structures": {}}

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.prompt_structures.auth_service") as mock_auth:
            mock_auth.check_project_access.return_value = True

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.delete(
                    "/api/projects/proj-1/generation-config/structures/nonexistent"
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_delete_structure_removes_from_active(self, client, mock_user):
        """Test deleting structure removes it from active_structures."""
        mock_db = Mock(spec=Session)

        # Use a real object to avoid Mock subscription issues
        class FakeProject:
            id = "proj-1"
            generation_config = {
                "prompt_structures": {"my_struct": {"system_prompt": "test", "name": "test", "instruction_prompt": "test"}},
                "selected_configuration": {"active_structures": ["my_struct", "other"], "models": []},
            }

        mock_project = FakeProject()

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        mock_db.commit.return_value = None

        with patch("routers.prompt_structures.auth_service") as mock_auth, \
             patch("sqlalchemy.orm.attributes.flag_modified"):
            mock_auth.check_project_access.return_value = True

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.delete(
                    "/api/projects/proj-1/generation-config/structures/my_struct"
                )
                assert response.status_code == status.HTTP_200_OK
                # Verify my_struct removed from active_structures
                assert "my_struct" not in mock_project.generation_config["selected_configuration"]["active_structures"]
            finally:
                app.dependency_overrides.clear()

    def test_set_active_structures_invalid_key(self, client, mock_user):
        """Test setting active structures with non-existent key."""
        mock_db = Mock(spec=Session)
        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.generation_config = {"prompt_structures": {"existing": {}}}

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.prompt_structures.auth_service") as mock_auth:
            mock_auth.check_project_access.return_value = True

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.put(
                    "/api/projects/proj-1/generation-config/structures",
                    json=["nonexistent"],
                )
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_list_structures_project_not_found(self, client, mock_user):
        """Test listing structures for non-existent project."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        self._setup_overrides(mock_user, mock_db)
        try:
            response = client.get("/api/projects/nonexistent/generation-config/structures")
            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_get_structure_not_found(self, client, mock_user):
        """Test getting non-existent structure."""
        mock_db = Mock(spec=Session)
        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.generation_config = {"prompt_structures": {}}

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.prompt_structures.auth_service") as mock_auth:
            mock_auth.check_project_access.return_value = True

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.get(
                    "/api/projects/proj-1/generation-config/structures/nonexistent"
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_get_structure_no_permission(self, client, mock_user):
        """Test getting structure without permission."""
        mock_db = Mock(spec=Session)
        mock_project = Mock()
        mock_project.id = "proj-1"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_project
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.prompt_structures.auth_service") as mock_auth:
            mock_auth.check_project_access.return_value = False

            self._setup_overrides(mock_user, mock_db)
            try:
                response = client.get(
                    "/api/projects/proj-1/generation-config/structures/my_struct"
                )
                assert response.status_code == status.HTTP_403_FORBIDDEN
            finally:
                app.dependency_overrides.clear()
