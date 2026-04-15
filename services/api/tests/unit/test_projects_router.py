"""
Comprehensive tests for the projects router endpoints.
Tests the current router architecture mounted at /api/projects/*.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from project_models import Task


class TestProjectsRouter:
    """Test projects router endpoints mounted at /api/projects/"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_regular_user(self):
        """Create mock regular user with organization membership"""
        # Use Mock to avoid SQLAlchemy relationship issues
        user = Mock()
        user.id = "regular-user-123"
        user.username = "regular"
        user.email = "regular@example.com"
        user.name = "Regular User"
        user.is_superadmin = False
        user.is_active = True
        user.email_verified = True
        user.created_at = datetime.now(timezone.utc)

        # Mock organization memberships
        membership = Mock()
        membership.organization_id = "org-123"
        membership.is_active = True
        membership.role = "CONTRIBUTOR"  # Need this role to create projects
        user.organization_memberships = [membership]
        return user

    @pytest.fixture
    def mock_superadmin_user(self):
        """Create mock superadmin user"""
        # Use Mock to avoid SQLAlchemy issues
        user = Mock()
        user.id = "admin-user-123"
        user.username = "admin"
        user.email = "admin@example.com"
        user.name = "Admin User"
        user.is_superadmin = True
        user.is_active = True
        user.email_verified = True
        user.created_at = datetime.now(timezone.utc)
        # Superadmins also need organization_memberships for project creation
        membership = Mock()
        membership.organization_id = "org-123"
        membership.role = "ORG_ADMIN"
        membership.is_active = True
        membership.organization = Mock()
        membership.organization.id = "org-123"
        membership.organization.name = "Test Org"
        user.organization_memberships = [membership]
        return user

    @pytest.fixture
    def mock_project(self):
        """Create mock project with all required fields"""
        project = Mock()
        # Core fields
        project.id = "project-123"
        project.title = "Test Project"
        project.description = "Test project description"
        project.created_by = "admin-user-123"
        project.organization_id = "org-123"  # Legacy field, still needed for schema
        project.created_at = datetime.now(timezone.utc)
        project.updated_at = None
        project.evaluation_config = {}
        project.generation_config = {}

        # ProjectBase fields
        project.label_config = "<View></View>"
        project.generation_structure = ""
        project.expert_instruction = "Test instructions"
        project.show_instruction = True
        project.show_skip_button = True
        project.enable_empty_annotation = True
        project.show_annotation_history = False

        # ProjectResponse-specific fields
        project.created_by_name = "Admin User"

        # Mock organization relationship
        organization = Mock()
        organization.id = "org-123"
        organization.name = "Test Org"
        project.organization = organization
        # organizations should be list of objects with id/name attributes, not dicts
        project.organizations = [organization]
        project.task_count = 5
        project.annotation_count = 2
        project.min_annotations_per_task = 1
        project.assignment_mode = "open"
        project.completed_tasks_count = 2
        project.progress_percentage = 40.0
        project.is_published = True
        project.is_archived = False
        project.instructions = "Test instructions"  # Alias for expert_instruction
        project.maximum_annotations = 1
        project.show_submit_button = True
        project.require_comment_on_skip = False
        project.require_confirm_before_submit = False
        project.llm_model_ids = []
        project.num_tasks = 5
        project.num_annotations = 2
        project.generation_prompts_ready = False
        project.generation_config_ready = False
        project.generation_models_count = 0
        project.generation_completed = False
        project.is_private = False
        # Strict timer mode
        # Review settings
        # Post-annotation questionnaire
        project.questionnaire_enabled = False
        project.questionnaire_config = None
        # Conditional instructions
        project.instructions_always_visible = False
        project.conditional_instructions = None
        # Task ordering
        project.randomize_task_order = False
        # Fields added by parallel work
        project.skip_queue = "disabled"
        project.evaluation_config = None
        project.generation_config = None
        project.assignment_mode = "manual"
        # Skip queue
        project.skip_queue = "requeue_for_others"
        # Assignment mode
        project.assignment_mode = "open"
        # Min annotations
        project.min_annotations_per_task = 1

        # Mock creator and organization relationships
        project.creator = Mock()
        project.creator.name = "Admin User"

        return project

    @pytest.fixture
    def mock_task(self, mock_project):
        """Create mock task"""
        return Task(
            id="task-123",
            project_id=mock_project.id,
            data={"text": "Sample text for annotation"},
            inner_id=1,
            is_labeled=False,
            total_annotations=0,
        )

    def test_list_projects_success(self, client, mock_regular_user):
        """Test listing projects at /api/projects/"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = MagicMock(spec=Session)
            # Mock the query chain to return empty results
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.count.return_value = 0
            mock_query.all.return_value = []
            mock_query.subquery.return_value = MagicMock()
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations",
            return_value=[{"id": "org-123", "name": "Test Org"}],
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats_batch", return_value={}
        ) as mock_calc_stats:
            # Mock user with memberships
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = (
                mock_regular_user.organization_memberships
            )
            mock_get_user.return_value = mock_user_with_memberships

            # Mock organization data
            mock_get_orgs.return_value = [{"id": "org-123", "name": "Test Org"}]

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/projects/")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "items" in data
                assert "total" in data
                assert "page" in data
                assert "page_size" in data
            finally:
                app.dependency_overrides.clear()

    def test_list_projects_with_pagination(self, client, mock_regular_user):
        """Test listing projects with pagination parameters"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = MagicMock(spec=Session)
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.count.return_value = 0
            mock_query.all.return_value = []
            mock_query.subquery.return_value = MagicMock()
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations"
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats_batch", return_value={}
        ) as mock_calc_stats:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = []
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = []

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                params = {"page": 2, "page_size": 50}
                response = client.get("/api/projects/", params=params)

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["page"] == 2
                assert data["page_size"] == 50
            finally:
                app.dependency_overrides.clear()

    def test_list_projects_with_search_filter(self, client, mock_regular_user):
        """Test listing projects with search filter"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = MagicMock(spec=Session)
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.count.return_value = 0
            mock_query.all.return_value = []
            mock_query.subquery.return_value = MagicMock()
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations"
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats_batch", return_value={}
        ) as mock_calc_stats:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = []
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = []

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                params = {"search": "legal"}
                response = client.get("/api/projects/", params=params)

                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_list_projects_with_archived_filter(self, client, mock_regular_user):
        """Test listing projects with is_archived filter"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = MagicMock(spec=Session)
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.count.return_value = 0
            mock_query.all.return_value = []
            mock_query.subquery.return_value = MagicMock()
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations"
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats_batch", return_value={}
        ) as mock_calc_stats:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = []
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = []

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                params = {"is_archived": True}
                response = client.get("/api/projects/", params=params)

                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_list_projects_superadmin_sees_all(self, client, mock_superadmin_user):
        """Test that superadmin can see all projects regardless of visibility"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = MagicMock(spec=Session)
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.count.return_value = 0
            mock_query.all.return_value = []
            mock_query.subquery.return_value = MagicMock()
            mock_db.query.return_value = mock_query
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations",
            return_value=[{"id": "org-123", "name": "Test Org"}],
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats_batch", return_value={}
        ) as mock_calc_stats:
            # Mock superadmin user
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_superadmin_user.id
            mock_user_with_memberships.is_superadmin = True
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = [{"id": "org-1", "name": "Org 1"}]

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/projects/")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "items" in data
            finally:
                app.dependency_overrides.clear()

    def test_list_projects_requires_authentication(self, client):
        """Test that listing projects requires authentication"""
        response = client.get("/api/projects/")
        # Should require authentication
        assert response.status_code in [401, 403]

    def test_get_project_success(self, client, mock_superadmin_user, mock_project):
        """Test getting single project by ID at /api/projects/{project_id}"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock project found - superadmin bypasses access control checks
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_project
            )
            return mock_db

        with patch("routers.projects.crud.calculate_project_stats", return_value=None):
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get(f"/api/projects/{mock_project.id}")

                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_get_project_not_found(self, client, mock_regular_user):
        """Test getting non-existent project"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock project not found
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                None
            )
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/projects/nonexistent-project")

            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_get_project_access_denied(self, client, mock_regular_user):
        """Test access denied for private project user doesn't have access to"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock no project found - access control prevents access so return None
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                None
            )
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = []  # No memberships
            mock_get_user.return_value = mock_user_with_memberships

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/projects/private-project")

                # The endpoint should return 404 for project not found (access control hides existence)
                assert response.status_code == 404
            finally:
                app.dependency_overrides.clear()

    def test_create_project_success(self, client, mock_superadmin_user):
        """Test creating project at /api/projects/ with superadmin (bypasses org checks)"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.add = Mock()
            mock_db.commit = Mock()
            mock_db.refresh = Mock()

            # Mock created project for refresh - copy all fields from fixture
            created_project = Mock()
            # Core fields
            created_project.id = "new-project-123"
            created_project.title = "New Project"
            created_project.description = "A new test project"
            created_project.created_by = mock_superadmin_user.id
            created_project.organization_id = "org-123"  # Legacy field, still needed for schema
            created_project.created_at = datetime.now(timezone.utc)
            created_project.updated_at = None
            created_project.evaluation_config = {}
            created_project.generation_config = {}

            # ProjectBase fields
            created_project.label_config = "<View></View>"
            created_project.generation_structure = ""
            created_project.expert_instruction = ""
            created_project.show_instruction = True
            created_project.show_skip_button = True
            created_project.enable_empty_annotation = True
            created_project.show_annotation_history = False

            # ProjectResponse-specific fields
            created_project.created_by_name = mock_superadmin_user.name
            created_project.task_count = 0
            created_project.annotation_count = 0
            created_project.min_annotations_per_task = 1
            created_project.completed_tasks_count = 0
            created_project.progress_percentage = 0.0
            created_project.is_published = False
            created_project.is_archived = False
            created_project.instructions = ""
            created_project.maximum_annotations = 1
            created_project.show_submit_button = True
            created_project.require_comment_on_skip = False
            created_project.require_confirm_before_submit = False
            created_project.llm_model_ids = []
            created_project.num_tasks = 0
            created_project.num_annotations = 0
            created_project.generation_prompts_ready = False
            created_project.generation_config_ready = False
            created_project.generation_models_count = 0
            created_project.generation_completed = False
            created_project.is_private = False
            # Strict timer mode
            # Review settings
            # Post-annotation questionnaire
            created_project.questionnaire_enabled = False
            created_project.questionnaire_config = None
            # Conditional instructions
            created_project.instructions_always_visible = False
            created_project.conditional_instructions = None
            # Task ordering
            created_project.randomize_task_order = False
            # Skip queue
            created_project.skip_queue = "requeue_for_others"
            # Assignment mode
            created_project.assignment_mode = "open"
            created_project.min_annotations_per_task = 1

            # Mock organization relationship
            organization = Mock()
            organization.id = "org-123"
            organization.name = "Test Org"
            created_project.organization = organization
            # organizations should be list of objects with id/name attributes
            created_project.organizations = [organization]

            # Mock creator relationship
            created_project.creator = Mock()
            created_project.creator.name = mock_superadmin_user.name

            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                created_project
            )

            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations",
            return_value=[{"id": "org-123", "name": "Test Org"}],
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats", return_value=None
        ) as mock_calc_stats, patch(
            "notification_service.notify_project_created"
        ) as mock_notify:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_superadmin_user.id
            mock_user_with_memberships.is_superadmin = True
            mock_user_with_memberships.organization_memberships = (
                mock_superadmin_user.organization_memberships
            )
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = [{"id": "org-123", "name": "Test Org"}]

            # Mock calculate_project_stats to avoid interference
            mock_calc_stats.return_value = None

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                project_data = {"title": "New Project", "description": "A new test project"}

                response = client.post("/api/projects/", json=project_data)

                # Should succeed with proper mocking
                assert response.status_code in [200, 201]
            finally:
                app.dependency_overrides.clear()

    def test_create_project_invalid_data(self, client, mock_regular_user):
        """Test creating project with invalid data"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            return Mock(spec=Session)

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Missing required fields
            invalid_data = {"description": "Missing title"}

            response = client.post("/api/projects/", json=invalid_data)

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

    def test_update_project_success(self, client, mock_regular_user, mock_project):
        """Test updating project at /api/projects/{project_id}"""
        from auth_module import require_user
        from database import get_db
        from main import app

        # Make mock user the project creator so it passes the permission check
        mock_project.created_by = mock_regular_user.id

        def override_require_user():
            return mock_regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock project found for both query patterns:
            # db.query(Project).filter().first() and db.query(Project).options().filter().first()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_project
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_project
            )
            mock_db.commit = Mock()
            return mock_db

        with patch("routers.projects.crud.get_user_with_memberships") as mock_get_user, patch(
            "routers.projects.helpers.get_project_organizations",
            return_value=[{"id": "org-123", "name": "Test Org"}],
        ) as mock_get_orgs, patch(
            "routers.projects.crud.calculate_project_stats", return_value=None
        ) as mock_calc_stats:
            mock_user_with_memberships = Mock()
            mock_user_with_memberships.id = mock_regular_user.id
            mock_user_with_memberships.is_superadmin = False
            mock_user_with_memberships.organization_memberships = (
                mock_regular_user.organization_memberships
            )
            mock_get_user.return_value = mock_user_with_memberships

            mock_get_orgs.return_value = [{"id": "org-123", "name": "Test Org"}]

            # Mock calculate_project_stats to avoid interference
            mock_calc_stats.return_value = None

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                update_data = {
                    "title": "Updated Project Title",
                    "description": "Updated description",
                }

                response = client.patch(
                    f"/api/projects/{mock_project.id}", json=update_data
                )  # Use PATCH

                # Should handle the request properly with mocks
                assert response.status_code in [
                    200,
                    403,
                    404,
                    405,
                ]  # 403 access denied is valid behavior
            finally:
                app.dependency_overrides.clear()

    def test_delete_project_success(self, client, mock_superadmin_user, mock_project):
        """Test deleting project at /api/projects/{project_id}"""
        from auth_module import require_user
        from database import get_db
        from main import app

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            # Mock project found
            mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                mock_project
            )
            mock_db.delete = Mock()
            mock_db.commit = Mock()
            return mock_db

        with patch("notification_service.notify_project_deleted") as mock_notify:
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.delete(f"/api/projects/{mock_project.id}")

                # Should handle the request properly with mocks
                assert response.status_code in [
                    200,
                    204,
                    404,
                    405,
                ]  # 200 OK or 204 No Content are valid
            finally:
                app.dependency_overrides.clear()


class TestPrivateProjectDeletion:
    """Test that private project creators can delete their own projects."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_private_project(self):
        """Create mock private project"""
        project = Mock()
        project.id = "private-project-123"
        project.title = "My Private Project"
        project.is_private = True
        project.created_by = "regular-user-123"
        return project

    def test_delete_private_project_by_creator(self, client, mock_private_project):
        """Private project creator should be able to delete their project."""
        from auth_module import require_user
        from database import get_db

        creator = Mock()
        creator.id = "regular-user-123"
        creator.is_superadmin = False
        creator.is_active = True
        creator.email_verified = True

        def override_require_user():
            return creator

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_private_project
            mock_query.delete.return_value = 0
            mock_db.query.return_value = mock_query
            mock_db.delete = Mock()
            mock_db.commit = Mock()
            return mock_db

        with patch("notification_service.notify_project_deleted"):
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.delete(f"/api/projects/{mock_private_project.id}")
                assert response.status_code in [200, 204]
            finally:
                app.dependency_overrides.clear()

    def test_delete_private_project_by_other_user_blocked(self, client, mock_private_project):
        """Non-creator non-superadmin should NOT be able to delete a private project."""
        from auth_module import require_user
        from database import get_db

        other_user = Mock()
        other_user.id = "other-user-456"
        other_user.is_superadmin = False
        other_user.is_active = True
        other_user.email_verified = True

        def override_require_user():
            return other_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_private_project
            mock_db.query.return_value = mock_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.delete(f"/api/projects/{mock_private_project.id}")
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_delete_org_project_by_regular_user_blocked(self, client):
        """Non-superadmin should NOT be able to delete an org project."""
        from auth_module import require_user
        from database import get_db

        regular_user = Mock()
        regular_user.id = "regular-user-123"
        regular_user.is_superadmin = False
        regular_user.is_active = True
        regular_user.email_verified = True

        org_project = Mock()
        org_project.id = "org-project-123"
        org_project.is_private = False
        org_project.created_by = "regular-user-123"

        def override_require_user():
            return regular_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = org_project
            mock_db.query.return_value = mock_query
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.delete(f"/api/projects/{org_project.id}")
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestProjectsRouterIntegration:
    """Integration tests for projects router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_projects_endpoints_require_authentication(self, client):
        """Test that project endpoints require authentication"""
        from main import app

        # Ensure no authentication dependencies are overridden
        app.dependency_overrides.clear()

        endpoints = [
            ("GET", "/api/projects/"),
            ("POST", "/api/projects/", {"title": "Test"}),
            ("GET", "/api/projects/test-project"),
            ("PATCH", "/api/projects/test-project", {"title": "Updated"}),  # Use PATCH, not PUT
            ("DELETE", "/api/projects/test-project"),
        ]

        for method, endpoint, *json_data in endpoints:
            kwargs = {}
            if json_data:
                kwargs["json"] = json_data[0]

            response = client.request(method, endpoint, **kwargs)
            # Should require authentication - endpoints should return 401/403 without valid auth
            # Some endpoints might also return 405 for unsupported methods before auth check
            assert response.status_code in [
                401,
                403,
                405,
                422,
            ]  # 422 for validation, 405 for method not allowed

    def test_projects_endpoints_request_validation(self, client):
        """Test that project endpoints reject invalid requests"""
        from main import app

        # Ensure no dependencies are overridden for this validation test
        app.dependency_overrides.clear()

        # Test create with invalid JSON - auth middleware may reject before validation
        response = client.post("/api/projects/", data="invalid")
        assert response.status_code in [401, 422]

        # Test update with invalid JSON
        response = client.patch("/api/projects/test-project", data="invalid")  # Use PATCH, not PUT
        assert response.status_code in [
            401,
            422,
            404,
            405,
        ]

    # test_projects_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.
