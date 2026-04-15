"""
Integration tests for label config versioning on project updates.
Tests that project updates correctly create versions and preserve history.

Uses the shared PostgreSQL test database with per-test transaction rollback.
"""

from datetime import datetime, timezone

import pytest

from label_config_version_service import LabelConfigVersionService
from models import User
from project_models import Project


class TestProjectUpdateVersioning:
    """Test label config versioning during project updates"""

    @pytest.fixture(scope="function")
    def test_db_session(self, test_db):
        """Use the shared PostgreSQL test database session."""
        yield test_db

    @pytest.fixture
    def test_user(self, test_db_session):
        """Create test user"""
        user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password",
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(user)
        test_db_session.commit()
        test_db_session.refresh(user)
        return user

    @pytest.fixture
    def test_project(self, test_db_session, test_user: User):
        """Create test project with initial label config"""
        project = Project(
            id="test-project-123",
            title="Test Project",
            created_by=test_user.id,
            label_config="<View><Choices name='sentiment'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        test_db_session.add(project)
        test_db_session.commit()
        test_db_session.refresh(project)
        return project

    def test_update_label_config_creates_version(self, test_db_session, test_project: Project):
        """Test that updating label_config creates a new version"""
        # Get initial state
        test_project.label_config_version
        initial_schema = test_project.label_config

        # Update schema
        new_schema = "<View><Choices name='sentiment'/><Rating name='confidence'/></View>"

        # Simulate what the API does
        if LabelConfigVersionService.has_schema_changed(test_project, new_schema):
            new_version = LabelConfigVersionService.update_version_history(
                project=test_project,
                new_label_config=new_schema,
                description="Added confidence rating",
                user_id=test_project.created_by,
            )

        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify version was incremented
        assert test_project.label_config_version == "v2"
        assert test_project.label_config == new_schema

        # Verify old version was saved in history
        assert "v1" in test_project.label_config_history["versions"]
        v1_entry = test_project.label_config_history["versions"]["v1"]
        assert v1_entry["schema"] == initial_schema
        assert v1_entry["description"] == "Added confidence rating"

    def test_update_label_config_preserves_history(self, test_db_session, test_project: Project):
        """Test that multiple updates preserve all history"""
        # First update
        schema_v2 = "<View><Choices name='sentiment'/><Rating name='confidence'/></View>"
        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=schema_v2,
            description="Version 2",
            user_id=test_project.created_by,
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Second update
        schema_v3 = "<View><Choices name='sentiment'/><Rating name='confidence'/><TextArea name='notes'/></View>"
        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=schema_v3,
            description="Version 3",
            user_id=test_project.created_by,
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify current version
        assert test_project.label_config_version == "v3"
        assert test_project.label_config == schema_v3

        # Verify all history is preserved
        versions = test_project.label_config_history["versions"]
        assert "v1" in versions  # Original was saved
        assert "v2" in versions  # First update was saved

        # Verify v2 entry (description from when v3 was created, as v2 was archived then)
        assert versions["v2"]["schema"] == schema_v2
        assert versions["v2"]["description"] == "Version 3"  # Description from v2→v3 transition

    def test_update_label_config_no_change_no_increment(
        self, test_db_session, test_project: Project
    ):
        """Test that updating with same schema doesn't increment version"""
        initial_version = test_project.label_config_version
        same_schema = test_project.label_config

        # Try to update with same schema
        has_changed = LabelConfigVersionService.has_schema_changed(test_project, same_schema)

        assert has_changed is False  # No change detected
        assert test_project.label_config_version == initial_version  # Version not incremented

    def test_update_label_config_with_description(self, test_db_session, test_project: Project):
        """Test that custom description is saved correctly"""
        new_schema = "<View><Choices name='category'/></View>"
        custom_description = "Switched to category classification"

        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=new_schema,
            description=custom_description,
            user_id="custom-user-789",
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify description was saved
        v1_entry = test_project.label_config_history["versions"]["v1"]
        assert v1_entry["description"] == custom_description
        assert v1_entry["created_by"] == "custom-user-789"

    def test_update_label_config_whitespace_change(self, test_db_session, test_project: Project):
        """Test that whitespace-only changes are detected"""
        # Original schema (compact)
        original = "<View><Choices name='sentiment'/></View>"
        test_project.label_config = original
        test_db_session.commit()

        # Same schema with different whitespace
        whitespace_version = """<View>
  <Choices name='sentiment'/>
</View>"""

        has_changed = LabelConfigVersionService.has_schema_changed(test_project, whitespace_version)

        # Whitespace changes should be detected (they affect the hash)
        assert has_changed is True

    def test_concurrent_updates_consistency(self, test_db_session, test_project: Project):
        """Test that concurrent updates maintain version consistency"""
        # Simulate two updates happening in sequence
        # (Real concurrent updates would need transaction isolation testing)

        # Update 1: Add field
        schema_1 = "<View><Choices name='sentiment'/><Rating name='quality'/></View>"
        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=schema_1,
            description="User A adds quality",
            user_id="user-a",
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        assert test_project.label_config_version == "v2"

        # Update 2: Add different field
        schema_2 = (
            "<View><Choices name='sentiment'/><Rating name='quality'/><Number name='count'/></View>"
        )
        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=schema_2,
            description="User B adds count",
            user_id="user-b",
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify sequential updates work correctly
        assert test_project.label_config_version == "v3"
        assert "v1" in test_project.label_config_history["versions"]
        assert "v2" in test_project.label_config_history["versions"]

        # Verify User A's change was preserved in v2
        v2_entry = test_project.label_config_history["versions"]["v2"]
        assert v2_entry["created_by"] == "user-b"  # User B created v3, so v2 was saved by them
        assert v2_entry["schema"] == schema_1

    def test_version_history_structure(self, test_db_session, test_project: Project):
        """Test that version history has correct structure"""
        new_schema = "<View><TextArea name='notes'/></View>"

        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=new_schema,
            description="Test update",
            user_id=test_project.created_by,
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify history structure
        history = test_project.label_config_history
        assert "versions" in history
        assert "current_version" in history

        # Verify version entry structure
        v1_entry = history["versions"]["v1"]
        assert "schema" in v1_entry
        assert "created_at" in v1_entry
        assert "created_by" in v1_entry
        assert "description" in v1_entry
        assert "schema_hash" in v1_entry

    def test_schema_hash_computation(self, test_db_session, test_project: Project):
        """Test that schema hash is computed and stored"""
        new_schema = "<View><Choices name='category'/></View>"

        LabelConfigVersionService.update_version_history(
            project=test_project,
            new_label_config=new_schema,
            description="Test hash",
            user_id=test_project.created_by,
        )
        test_db_session.commit()
        test_db_session.refresh(test_project)

        # Verify hash was computed
        v1_entry = test_project.label_config_history["versions"]["v1"]
        assert "schema_hash" in v1_entry
        assert len(v1_entry["schema_hash"]) == 12  # Truncated SHA256

        # Verify hash matches schema
        expected_hash = LabelConfigVersionService.compute_schema_hash(
            test_project.label_config_history["versions"]["v1"]["schema"]
        )
        assert v1_entry["schema_hash"] == expected_hash

    def test_empty_to_schema_creates_version(self, test_db_session, test_user: User):
        """Test that adding schema to project without one creates version"""
        # Create project without label_config
        project = Project(
            id="test-project-empty",
            title="Empty Project",
            created_by=test_user.id,
            label_config=None,
            label_config_version=None,
            label_config_history=None,
        )
        test_db_session.add(project)
        test_db_session.commit()

        # Add schema
        new_schema = "<View><Choices name='sentiment'/></View>"
        new_version = LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=new_schema,
            description="Initial schema",
            user_id=test_user.id,
        )
        test_db_session.commit()
        test_db_session.refresh(project)

        # Should create v2 (increments from v1 default)
        # Note: This might be v2 based on service logic - see unit tests
        assert project.label_config_version is not None
        assert project.label_config == new_schema
        assert project.label_config_history is not None
