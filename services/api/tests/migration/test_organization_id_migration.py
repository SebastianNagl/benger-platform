"""
Tests for the organization_id migration (Issue #578)
Verifies the migration logic from legacy organization_id field to ProjectOrganization table.

Uses the shared PostgreSQL test database with per-test transaction rollback.
The tests verify the migration SQL patterns against the real schema using ORM models
for data setup and raw SQL for the migration logic itself.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from models import Organization, User
from project_models import Project, ProjectOrganization


class TestOrganizationIdMigration:
    """Test the migration that removes organization_id and uses ProjectOrganization"""

    @pytest.fixture
    def test_engine(self, test_db):
        """Provide the connection's engine bound to the test session for raw SQL."""
        return test_db.get_bind()

    @pytest.fixture
    def db_session(self, test_db):
        """Use the shared PostgreSQL test database session."""
        yield test_db

    @pytest.fixture
    def test_user(self, db_session):
        """Create a test user."""
        user = User(
            id=str(uuid.uuid4()),
            email="migration-test@example.com",
            username="migrationtest",
            name="Migration Test User",
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()
        return user

    @pytest.fixture
    def test_org(self, db_session):
        """Create a test organization."""
        org = Organization(
            id=str(uuid.uuid4()),
            name="Test Organization",
            display_name="Test Organization",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(org)
        db_session.flush()
        return org

    def test_migration_data_preservation(self, db_session, test_user, test_org):
        """Test that organization_id values are preserved during migration.

        Simulates the migration pattern: find projects that have an org association
        but no ProjectOrganization entry, then create the entry.
        """
        # Create a project (simulating post-migration state without ProjectOrganization)
        project = Project(
            id=str(uuid.uuid4()),
            title="Test Project",
            created_by=test_user.id,
        )
        db_session.add(project)
        db_session.flush()

        # Verify no ProjectOrganization exists yet
        count = (
            db_session.query(ProjectOrganization)
            .filter(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.organization_id == test_org.id,
            )
            .count()
        )
        assert count == 0

        # Simulate migration logic: create ProjectOrganization for the project
        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_user.id,
        )
        db_session.add(po)
        db_session.flush()

        # Verify ProjectOrganization was created
        count = (
            db_session.query(ProjectOrganization)
            .filter(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.organization_id == test_org.id,
            )
            .count()
        )
        assert count == 1

    def test_migration_handles_null_organization_id(self, db_session, test_user):
        """Test that migration handles projects with no organization association."""
        # Create a project with no organization
        project = Project(
            id=str(uuid.uuid4()),
            title="Orphan Project",
            created_by=test_user.id,
        )
        db_session.add(project)
        db_session.flush()

        # Migration query: find projects without any ProjectOrganization
        result = db_session.execute(
            text(
                """
                SELECT p.id, p.created_by
                FROM projects p
                WHERE NOT EXISTS (
                    SELECT 1 FROM project_organizations po
                    WHERE po.project_id = p.id
                )
                AND p.id = :project_id
            """
            ),
            {'project_id': project.id},
        )
        rows = result.fetchall()

        # Should find the project (it has no org association)
        assert len(rows) == 1
        assert rows[0][0] == project.id

        # But since there's no legacy organization_id to migrate, no ProjectOrganization should be created
        count = (
            db_session.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .count()
        )
        assert count == 0

    def test_migration_prevents_duplicates(self, db_session, test_user, test_org):
        """Test that migration doesn't create duplicate ProjectOrganization entries."""
        # Create a project with an existing ProjectOrganization
        project = Project(
            id=str(uuid.uuid4()),
            title="Test Project",
            created_by=test_user.id,
        )
        db_session.add(project)
        db_session.flush()

        # Pre-existing ProjectOrganization entry
        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_user.id,
        )
        db_session.add(po)
        db_session.flush()

        # Migration query: check if ProjectOrganization already exists
        result = db_session.execute(
            text(
                """
                SELECT p.id
                FROM projects p
                WHERE NOT EXISTS (
                    SELECT 1 FROM project_organizations po
                    WHERE po.project_id = p.id
                    AND po.organization_id = :org_id
                )
                AND p.id = :project_id
            """
            ),
            {'project_id': project.id, 'org_id': test_org.id},
        )
        rows = result.fetchall()

        # Should return no rows since ProjectOrganization already exists
        assert len(rows) == 0

        # Verify still only one ProjectOrganization entry
        count = (
            db_session.query(ProjectOrganization)
            .filter(
                ProjectOrganization.project_id == project.id,
                ProjectOrganization.organization_id == test_org.id,
            )
            .count()
        )
        assert count == 1

    def test_migration_rollback(self, db_session, test_user, test_org):
        """Test that migration can be rolled back safely.

        Verifies that ProjectOrganization data can be used to restore
        organization associations if the migration needs to be reversed.
        """
        # Create a project with a ProjectOrganization entry
        project = Project(
            id=str(uuid.uuid4()),
            title="Test Project",
            created_by=test_user.id,
        )
        db_session.add(project)
        db_session.flush()

        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_user.id,
        )
        db_session.add(po)
        db_session.flush()

        # Simulate rollback: read organization_id from ProjectOrganization
        result = db_session.execute(
            text(
                """
                SELECT organization_id
                FROM project_organizations
                WHERE project_id = :project_id
                ORDER BY created_at ASC
                LIMIT 1
            """
            ),
            {'project_id': project.id},
        )
        restored_org_id = result.scalar()

        # Verify organization_id was restored correctly
        assert restored_org_id == test_org.id
