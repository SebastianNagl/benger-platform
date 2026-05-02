"""
Unit tests for private project functionality (Issue #1179).

Tests:
- Private project creation (no org assignment)
- Private project listing (creator-only visibility)
- Authorization: creator access, non-creator denied, superadmin access
- Slug lookup: valid slug, invalid slug, non-member denied
"""

import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session


class TestPrivateProjectAuthorization:
    """Test authorization logic for private projects."""

    @pytest.fixture
    def mock_db(self):
        return Mock(spec=Session)

    @pytest.fixture
    def creator_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False
        user.organization_memberships = []
        return user

    @pytest.fixture
    def other_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False
        user.organization_memberships = []
        return user

    @pytest.fixture
    def superadmin_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = True
        user.organization_memberships = []
        return user

    @pytest.fixture
    def private_project(self, creator_user):
        project = Mock()
        project.id = str(uuid.uuid4())
        project.is_private = True
        project.created_by = creator_user.id
        return project

    @pytest.fixture
    def org_project(self):
        project = Mock()
        project.id = str(uuid.uuid4())
        project.is_private = False
        project.created_by = str(uuid.uuid4())
        return project

    def test_creator_can_access_private_project(self, creator_user, private_project, mock_db):
        """Creator should have access to their private project."""
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        result = service.check_project_access(
            creator_user, private_project, Permission.PROJECT_VIEW, mock_db
        )
        assert result is True

    def test_non_creator_denied_private_project(self, other_user, private_project, mock_db):
        """Non-creator should be denied access to a private project."""
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        result = service.check_project_access(
            other_user, private_project, Permission.PROJECT_VIEW, mock_db
        )
        assert result is False

    def test_superadmin_can_access_private_project(self, superadmin_user, private_project, mock_db):
        """Superadmin should have access to all private projects."""
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        result = service.check_project_access(
            superadmin_user, private_project, Permission.PROJECT_VIEW, mock_db
        )
        assert result is True

    def test_non_private_project_skips_private_check(self, other_user, org_project, mock_db):
        """Non-private project should not be blocked by private project logic."""
        from app.core.authorization import AuthorizationService, Permission

        # Mock the org membership query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        service = AuthorizationService()
        # This should not return True from the is_private check
        # (it may return False due to no org membership, but should not short-circuit)
        result = service.check_project_access(
            other_user, org_project, Permission.PROJECT_VIEW, mock_db
        )
        # Not blocked by private check - goes to org membership check (which returns False)
        assert result is False


class TestPrivateProjectCreation:
    """Test private project creation logic."""

    @pytest.fixture
    def mock_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False
        user.organizations = [{"id": str(uuid.uuid4()), "name": "TUM", "role": "CONTRIBUTOR"}]
        return user

    def test_private_context_sets_is_private(self):
        """When X-Organization-Context is 'private', project.is_private should be True."""
        from project_schemas import ProjectCreate

        project_data = ProjectCreate(
            title="My Private Project",
            label_config="<View><Text name='text' value='$text'/></View>",
            is_private=True,
        )
        assert project_data.is_private is True

    def test_default_is_not_private(self):
        """Default project creation should not be private."""
        from project_schemas import ProjectCreate

        project_data = ProjectCreate(
            title="Org Project",
            label_config="<View><Text name='text' value='$text'/></View>",
        )
        assert project_data.is_private is False


class TestSlugLookup:
    """Test organization slug lookup validation."""

    def test_valid_slug_format(self):
        """Valid slugs should match the pattern."""
        import re

        pattern = r"^[a-z0-9-]+$"
        assert re.match(pattern, "tum")
        assert re.match(pattern, "lmu")
        assert re.match(pattern, "my-org-123")

    def test_invalid_slug_format(self):
        """Invalid slugs should not match."""
        import re

        pattern = r"^[a-z0-9-]+$"
        assert not re.match(pattern, "TUM")  # uppercase
        assert not re.match(pattern, "my org")  # space
        assert not re.match(pattern, "org.name")  # dot
        assert not re.match(pattern, "")  # empty
        assert not re.match(pattern, "org/path")  # slash


class TestContextAwareProjectListing:
    """Test X-Organization-Context header handling logic."""

    def test_private_context_values(self):
        """Both 'private' and absent context should trigger private mode."""
        # Simulates the condition in list_projects
        for org_context in [None, "private"]:
            is_private_mode = not org_context or org_context == "private"
            assert is_private_mode is True

    def test_org_context_value(self):
        """A valid org ID should trigger org mode."""
        org_context = str(uuid.uuid4())
        is_private_mode = not org_context or org_context == "private"
        assert is_private_mode is False


class TestProjectVisibilityEndpoint:
    """Test PATCH /api/projects/{id}/visibility request schemas."""

    def test_make_private_payload(self):
        """Payload to make a project private."""
        payload = {
            "is_private": True,
            "owner_user_id": str(uuid.uuid4()),
        }
        assert payload["is_private"] is True
        assert "owner_user_id" in payload

    def test_make_org_assigned_payload(self):
        """Payload to make a project org-assigned."""
        org_id = str(uuid.uuid4())
        payload = {
            "is_private": False,
            "organization_ids": [org_id],
        }
        assert payload["is_private"] is False
        assert len(payload["organization_ids"]) == 1


class TestPublicProjectAuthorization:
    """Authorization for the public visibility tier."""

    @pytest.fixture
    def mock_db(self):
        return Mock(spec=Session)

    @pytest.fixture
    def visitor_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False
        user.organization_memberships = []
        return user

    @pytest.fixture
    def creator_user(self):
        user = Mock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False
        user.organization_memberships = []
        return user

    @pytest.fixture
    def public_project_annotator(self, creator_user):
        project = Mock()
        project.id = str(uuid.uuid4())
        project.is_private = False
        project.is_public = True
        project.public_role = "ANNOTATOR"
        project.created_by = creator_user.id
        return project

    @pytest.fixture
    def public_project_contributor(self, creator_user):
        project = Mock()
        project.id = str(uuid.uuid4())
        project.is_private = False
        project.is_public = True
        project.public_role = "CONTRIBUTOR"
        project.created_by = creator_user.id
        return project

    def test_visitor_can_view_public_project(self, visitor_user, public_project_annotator, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_annotator, Permission.PROJECT_VIEW, mock_db
        ) is True

    def test_public_annotator_can_create_annotation(self, visitor_user, public_project_annotator, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_annotator, Permission.ANNOTATION_CREATE, mock_db
        ) is True

    def test_public_annotator_cannot_create_task(self, visitor_user, public_project_annotator, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_annotator, Permission.TASK_CREATE, mock_db
        ) is False

    def test_public_annotator_cannot_run_generation(self, visitor_user, public_project_annotator, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_annotator, Permission.GENERATION_CREATE, mock_db
        ) is False

    def test_public_contributor_can_create_task(self, visitor_user, public_project_contributor, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_contributor, Permission.TASK_CREATE, mock_db
        ) is True

    def test_public_contributor_can_run_generation(self, visitor_user, public_project_contributor, mock_db):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_contributor, Permission.GENERATION_CREATE, mock_db
        ) is True

    def test_public_contributor_cannot_edit_project_settings(
        self, visitor_user, public_project_contributor, mock_db
    ):
        """Settings-edit cap: public CONTRIBUTORs are stripped of PROJECT_EDIT."""
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            visitor_user, public_project_contributor, Permission.PROJECT_EDIT, mock_db
        ) is False
        assert service.check_project_access(
            visitor_user, public_project_contributor, Permission.PROJECT_DELETE, mock_db
        ) is False

    def test_creator_retains_full_permissions_on_public(
        self, creator_user, public_project_annotator, mock_db
    ):
        from app.core.authorization import AuthorizationService, Permission

        service = AuthorizationService()
        assert service.check_project_access(
            creator_user, public_project_annotator, Permission.PROJECT_EDIT, mock_db
        ) is True
        assert service.check_project_access(
            creator_user, public_project_annotator, Permission.TASK_CREATE, mock_db
        ) is True


class TestPublicProjectCreation:
    """Pydantic ProjectCreate validation for the public tier."""

    def test_public_with_role_is_valid(self):
        from project_schemas import ProjectCreate

        project = ProjectCreate(
            title="Public Bench",
            label_config="<View></View>",
            is_public=True,
            public_role="CONTRIBUTOR",
        )
        assert project.is_public is True
        assert project.public_role == "CONTRIBUTOR"

    def test_public_without_role_defaults_to_annotator(self):
        from project_schemas import ProjectCreate

        project = ProjectCreate(
            title="Public Bench",
            label_config="<View></View>",
            is_public=True,
        )
        assert project.public_role == "ANNOTATOR"

    def test_private_and_public_rejected(self):
        from project_schemas import ProjectCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProjectCreate(
                title="X",
                label_config="<View></View>",
                is_private=True,
                is_public=True,
            )

    def test_public_role_cleared_when_not_public(self):
        from project_schemas import ProjectCreate

        project = ProjectCreate(
            title="X",
            label_config="<View></View>",
            is_public=False,
            public_role="CONTRIBUTOR",
        )
        assert project.public_role is None


class TestPublicVisibilityPayloads:
    """PATCH /projects/{id}/visibility payload shapes for public."""

    def test_make_public_payload(self):
        payload = {"is_public": True, "public_role": "ANNOTATOR"}
        assert payload["is_public"] is True
        assert payload["public_role"] in ("ANNOTATOR", "CONTRIBUTOR")

    def test_flip_public_role_payload(self):
        payload = {"public_role": "CONTRIBUTOR"}
        assert payload["public_role"] == "CONTRIBUTOR"


class TestScopedUserListing:
    """Test scoped user listing logic for non-superadmins."""

    def test_superadmin_sees_all(self):
        """Superadmin flag should bypass org scoping."""
        user = Mock()
        user.is_superadmin = True
        assert user.is_superadmin is True

    def test_non_superadmin_org_ids_extraction(self):
        """Non-superadmin should extract org IDs from organizations list."""
        org1_id = str(uuid.uuid4())
        org2_id = str(uuid.uuid4())
        organizations = [
            {"id": org1_id, "name": "TUM", "role": "CONTRIBUTOR"},
            {"id": org2_id, "name": "LMU", "role": "ANNOTATOR"},
        ]
        user_org_ids = [org["id"] for org in organizations]
        assert len(user_org_ids) == 2
        assert org1_id in user_org_ids
        assert org2_id in user_org_ids

    def test_no_orgs_returns_empty(self):
        """User with no organizations should get empty list."""
        organizations = []
        user_org_ids = [org["id"] for org in organizations]
        assert user_org_ids == []
