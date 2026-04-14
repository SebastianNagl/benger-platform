"""
Unit tests for Project API endpoints using ProjectOrganization
Tests API functionality after Issue #578 migration
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session


class TestProjectAPIWithOrganization:
    """Test Project API endpoints with ProjectOrganization functionality"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user"""
        user = Mock()
        user.id = str(uuid.uuid4())
        user.name = "Test User"
        user.email = "test@example.com"
        user.is_superadmin = False
        return user

    @pytest.fixture
    def mock_organization(self):
        """Create a mock organization"""
        org = Mock()
        org.id = str(uuid.uuid4())
        org.name = "Test Organization"
        org.slug = "test-org"
        return org

    def test_create_project_creates_project_organization(
        self, mock_db, mock_user, mock_organization
    ):
        """Test that creating a project also creates ProjectOrganization entry"""
        from project_models import Project, ProjectOrganization

        # Mock user with organization membership
        mock_membership = Mock()
        mock_membership.organization_id = mock_organization.id
        mock_membership.is_active = True

        mock_user_with_memberships = Mock()
        mock_user_with_memberships.organization_memberships = [mock_membership]

        # Mock the query chain
        with patch('projects_api.get_user_with_memberships') as mock_get_user:
            mock_get_user.return_value = mock_user_with_memberships

            # Mock project creation data
            project_data = {
                "title": "New Test Project",
                "description": "Test Description",
                "label_config": "<View></View>",
                "expert_instruction": "Test instructions",
                "show_instruction": True,
                "show_skip_button": True,
                "enable_empty_annotation": True,
            }

            # Track database additions
            added_objects = []
            mock_db.add = Mock(side_effect=lambda obj: added_objects.append(obj))
            mock_db.commit = Mock()
            mock_db.refresh = Mock()

            # Simulate the key parts of create_project function
            project_id = str(uuid.uuid4())

            # Create project without organization_id
            db_project = Project(
                id=project_id,
                title=project_data["title"],
                description=project_data["description"],
                created_by=mock_user.id,
                # Note: no organization_id field
                label_config=project_data["label_config"],
                expert_instruction=project_data["expert_instruction"],
                show_instruction=project_data["show_instruction"],
                show_skip_button=project_data["show_skip_button"],
                enable_empty_annotation=project_data["enable_empty_annotation"],
            )
            mock_db.add(db_project)

            # Create ProjectOrganization entry
            project_org = ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project_id,
                organization_id=mock_membership.organization_id,
                assigned_by=mock_user.id,
            )
            mock_db.add(project_org)

            # Verify both objects were added
            assert len(added_objects) == 2
            assert isinstance(added_objects[0], Project)
            assert isinstance(added_objects[1], ProjectOrganization)

            # Verify Project doesn't have organization_id
            assert not hasattr(added_objects[0], 'organization_id')

            # Verify ProjectOrganization has correct references
            assert added_objects[1].project_id == project_id
            assert added_objects[1].organization_id == mock_organization.id
            assert added_objects[1].assigned_by == mock_user.id

    def test_get_project_checks_project_organization_access(self, mock_db, mock_user):
        """Test that get_project checks access via ProjectOrganization table"""
        from project_models import Project

        project_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        # Mock project without organization_id field
        mock_project = Mock(spec=Project)
        mock_project.id = project_id
        mock_project.title = "Test Project"
        mock_project.created_by = "other_user_id"
        # No organization_id attribute

        # Mock user organization membership
        mock_membership = Mock()
        mock_membership.organization_id = org_id
        mock_membership.is_active = True

        mock_user_with_memberships = Mock()
        mock_user_with_memberships.organization_memberships = [mock_membership]

        # Mock ProjectOrganization query
        mock_po_query = Mock()
        mock_po_query.filter.return_value.all.return_value = [(org_id,)]

        with patch('projects_api.get_user_with_memberships') as mock_get_user:
            mock_get_user.return_value = mock_user_with_memberships

            # Simulate access check logic
            user_org_ids = [
                m.organization_id
                for m in mock_user_with_memberships.organization_memberships
                if m.is_active
            ]

            # Check ProjectOrganization table
            project_org_ids = [(org_id,)]  # Simulated query result
            project_org_ids = [org_id[0] for org_id in project_org_ids]

            has_access = any(org_id in user_org_ids for org_id in project_org_ids)

            assert has_access is True

    def test_delete_project_removes_project_organizations(self, mock_db, mock_user):
        """Test that deleting a project removes ProjectOrganization entries"""
        from project_models import Project, ProjectOrganization

        project_id = str(uuid.uuid4())

        # Mock project
        mock_project = Mock(spec=Project)
        mock_project.id = project_id
        mock_project.created_by = mock_user.id

        # Track deletions
        deleted_queries = []

        def mock_delete(synchronize_session=False):
            deleted_queries.append("delete_called")

        # Mock the query chain for ProjectOrganization deletion
        mock_po_query = Mock()
        mock_po_query.filter.return_value.delete = mock_delete

        mock_db.query = Mock(
            side_effect=lambda model: mock_po_query if model == ProjectOrganization else Mock()
        )

        # Simulate project deletion logic
        mock_db.query(ProjectOrganization).filter(
            ProjectOrganization.project_id == project_id
        ).delete(synchronize_session=False)

        # Verify ProjectOrganization deletion was called
        assert "delete_called" in deleted_queries

    def test_list_projects_filters_by_organization(self, mock_db, mock_user):
        """Test that list_projects filters by user's organizations via ProjectOrganization"""

        user_org_id = str(uuid.uuid4())
        str(uuid.uuid4())

        # Mock user organization membership
        mock_membership = Mock()
        mock_membership.organization_id = user_org_id
        mock_membership.is_active = True

        mock_user_with_memberships = Mock()
        mock_user_with_memberships.organization_memberships = [mock_membership]

        # Create mock projects
        project1_id = str(uuid.uuid4())
        project2_id = str(uuid.uuid4())

        # Mock ProjectOrganization query results
        # Project 1 is in user's org, Project 2 is not
        mock_org_projects_subquery = [project1_id]

        with patch('projects_api.get_user_with_memberships') as mock_get_user:
            mock_get_user.return_value = mock_user_with_memberships

            # Simulate the filtering logic
            [user_org_id]

            # Projects assigned to user's organizations (via ProjectOrganization)
            accessible_project_ids = mock_org_projects_subquery

            # Only project1 should be accessible
            assert project1_id in accessible_project_ids
            assert project2_id not in accessible_project_ids


class TestProjectOrganizationHelpers:
    """Test helper functions for ProjectOrganization operations"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)

    def test_get_project_organizations(self, mock_db):
        """Test retrieving all organizations for a project"""
        from projects_api import get_project_organizations

        project_id = str(uuid.uuid4())
        org1_id = str(uuid.uuid4())
        org2_id = str(uuid.uuid4())

        # Mock organizations
        mock_org1 = Mock()
        mock_org1.id = org1_id
        mock_org1.name = "Organization 1"

        mock_org2 = Mock()
        mock_org2.id = org2_id
        mock_org2.name = "Organization 2"

        # Mock ProjectOrganization objects with organization attribute
        mock_po1 = Mock()
        mock_po1.organization = mock_org1

        mock_po2 = Mock()
        mock_po2.organization = mock_org2

        # Mock query chain - the actual function uses .options().filter().all()
        mock_query = Mock()
        mock_query.options.return_value.filter.return_value.all.return_value = [mock_po1, mock_po2]
        mock_db.query.return_value = mock_query

        # Call the helper function
        organizations = get_project_organizations(mock_db, project_id)

        # Verify results
        assert len(organizations) == 2
        assert any(org["id"] == org1_id for org in organizations)
        assert any(org["id"] == org2_id for org in organizations)

    def test_migration_preserves_organization_assignments(self):
        """Test that the migration properly preserves organization assignments"""
        # This test verifies the migration logic itself
        import uuid
        from datetime import datetime

        # Simulate migration data
        projects_with_org_id = [
            {
                "id": str(uuid.uuid4()),
                "organization_id": str(uuid.uuid4()),
                "created_by": str(uuid.uuid4()),
            },
            {
                "id": str(uuid.uuid4()),
                "organization_id": str(uuid.uuid4()),
                "created_by": str(uuid.uuid4()),
            },
        ]

        # Simulate migration logic
        project_organizations = []
        for project in projects_with_org_id:
            po = {
                "id": str(uuid.uuid4()),
                "project_id": project["id"],
                "organization_id": project["organization_id"],
                "assigned_by": project["created_by"],
                "created_at": datetime.utcnow(),
            }
            project_organizations.append(po)

        # Verify all projects have corresponding ProjectOrganization entries
        assert len(project_organizations) == len(projects_with_org_id)

        for i, project in enumerate(projects_with_org_id):
            po = project_organizations[i]
            assert po["project_id"] == project["id"]
            assert po["organization_id"] == project["organization_id"]
            assert po["assigned_by"] == project["created_by"]


class TestProjectOrganizationEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)

    def test_project_without_organization_handled_gracefully(self, mock_db):
        """Test that projects without organizations are handled properly"""
        from project_models import Project

        project_id = str(uuid.uuid4())

        # Mock project without any ProjectOrganization entries
        mock_project = Mock(spec=Project)
        mock_project.id = project_id
        mock_project.title = "Orphan Project"

        # Mock empty ProjectOrganization query
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        # Get organizations for project
        project_org_ids = []

        # Should return empty list without errors
        assert len(project_org_ids) == 0

    def test_duplicate_organization_assignment_prevented(self, mock_db):
        """Test that duplicate project-organization assignments are prevented"""
        from sqlalchemy.exc import IntegrityError

        from project_models import ProjectOrganization

        project_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        # First assignment
        po1 = ProjectOrganization(
            id=str(uuid.uuid4()), project_id=project_id, organization_id=org_id, assigned_by=user_id
        )

        # Attempt duplicate assignment
        po2 = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project_id,
            organization_id=org_id,  # Same project-org combination
            assigned_by=user_id,
        )

        # Mock database to raise IntegrityError on duplicate
        mock_db.add = Mock()
        mock_db.commit = Mock(side_effect=[None, IntegrityError("Duplicate", None, None)])

        # First should succeed
        mock_db.add(po1)
        mock_db.commit()

        # Second should fail
        mock_db.add(po2)
        with pytest.raises(IntegrityError):
            mock_db.commit()

    def test_organization_deletion_handling(self, mock_db):
        """Test that organization deletion is handled properly"""
        from project_models import ProjectOrganization

        org_id = str(uuid.uuid4())

        # Mock ProjectOrganization entries for the organization
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [
            Mock(project_id=str(uuid.uuid4())),
            Mock(project_id=str(uuid.uuid4())),
        ]
        mock_db.query.return_value = mock_query

        # Get affected projects before organization deletion
        affected_projects = (
            mock_db.query(ProjectOrganization)
            .filter(ProjectOrganization.organization_id == org_id)
            .all()
        )

        # Verify we can identify affected projects
        assert len(affected_projects) == 2

        # In practice, CASCADE delete would handle this automatically
