"""
Integration tests for label config version API endpoints.
Tests GET endpoints for listing, retrieving, comparing versions, and generation distribution.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from database import Base, get_db
from label_config_version_service import LabelConfigVersionService
from main import app
from models import User
from project_models import Project


class TestLabelConfigVersionEndpoints:
    """Test label config version API endpoints"""

    @pytest.fixture(scope="function")
    def test_db_session(self, test_db):
        """Use the shared PostgreSQL test database session."""
        yield test_db

    @pytest.fixture
    def auth_user(self, test_user):
        """Create auth user for dependency override"""
        # Convert DB User to AuthUser model
        return AuthUser(
            id=test_user.id,
            username=test_user.username,
            email=test_user.email,
            name=test_user.name,
            is_superadmin=test_user.is_superadmin,
            is_active=test_user.is_active,
            email_verified=test_user.email_verified,
            created_at=test_user.created_at,
        )

    @pytest.fixture(scope="function")
    def client_with_db(self, test_db_session, auth_user):
        """Create test client with database and auth overrides"""

        def override_get_db():
            try:
                yield test_db_session
            finally:
                pass

        def override_get_current_user():
            return auth_user

        def override_require_user():
            return auth_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[require_user] = override_require_user
        client = TestClient(app)
        yield client
        app.dependency_overrides = {}

    @pytest.fixture
    def test_user(self, test_db_session):
        """Create test user"""
        user = User(
            id="test-user-version-endpoints",
            username="versionuser",
            email="version@test.com",
            name="Version User",
            hashed_password="hashed_password",
            is_superadmin=True,  # For auth bypass in tests
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        test_db_session.add(user)
        test_db_session.commit()
        test_db_session.refresh(user)
        return user

    @pytest.fixture
    def test_project_with_versions(self, test_db_session, test_user):
        """Create test project with multiple schema versions"""
        # Create project with v1
        project = Project(
            id="test-project-versions",
            title="Version Test Project",
            created_by=test_user.id,
            label_config="<View><Choices name='sentiment'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        test_db_session.add(project)
        test_db_session.commit()
        test_db_session.refresh(project)

        # Update to v2
        schema_v2 = "<View><Choices name='sentiment'/><Rating name='confidence'/></View>"
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_v2,
            description="Added confidence rating field",
            user_id=test_user.id,
        )
        test_db_session.commit()
        test_db_session.refresh(project)

        # Update to v3
        schema_v3 = "<View><Choices name='sentiment'/><Rating name='confidence'/><TextArea name='notes'/></View>"
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_v3,
            description="Added notes field",
            user_id=test_user.id,
        )
        test_db_session.commit()
        test_db_session.refresh(project)

        return project

    # ==================================================================
    # GET /projects/{id}/label-config/versions - List Versions
    # ==================================================================

    def test_list_versions_with_history(self, client_with_db, test_project_with_versions):
        """Test listing all versions of a project with history"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions"
        )

        assert response.status_code == 200
        data = response.json()

        # Response should have versions key
        assert "versions" in data
        versions_list = data["versions"]

        # Should have 3 versions (v1, v2, v3)
        assert len(versions_list) >= 3

        # Verify versions are present
        versions = [v["version"] for v in versions_list]
        assert "v1" in versions
        assert "v2" in versions
        assert "v3" in versions

        # Verify v3 is marked as current
        v3_entry = next(v for v in versions_list if v["version"] == "v3")
        assert v3_entry["is_current"] is True

        # Verify v1 and v2 are not current
        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        v2_entry = next(v for v in versions_list if v["version"] == "v2")
        assert v1_entry["is_current"] is False
        assert v2_entry["is_current"] is False

    def test_list_versions_no_history(self, client_with_db, test_db_session, test_user):
        """Test listing versions for project without history"""
        # Create project with no version history
        project = Project(
            id="test-project-no-history",
            title="No History Project",
            created_by=test_user.id,
            label_config="<View><Choices name='test'/></View>",
            label_config_version="v1",
            label_config_history=None,
        )
        test_db_session.add(project)
        test_db_session.commit()

        response = client_with_db.get(f"/api/projects/{project.id}/label-config/versions")

        assert response.status_code == 200
        data = response.json()

        # Should have at least 1 version (current)
        assert "versions" in data
        assert len(data["versions"]) >= 1

    def test_list_versions_project_not_found(self, client_with_db):
        """Test listing versions for non-existent project returns 404"""
        response = client_with_db.get("/api/projects/non-existent-project/label-config/versions")

        assert response.status_code == 404

    # ==================================================================
    # GET /projects/{id}/label-config/versions/{version} - Get Version
    # ==================================================================

    def test_get_version_current(self, client_with_db, test_project_with_versions):
        """Test retrieving current version schema"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions/v3"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify schema content
        assert "schema" in data
        assert "<TextArea name='notes'/>" in data["schema"]
        assert data["version"] == "v3"
        assert data["is_current"] is True

    def test_get_version_historical(self, client_with_db, test_project_with_versions):
        """Test retrieving historical version schema"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions/v1"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify old schema content
        assert "schema" in data
        assert "<Choices name='sentiment'/>" in data["schema"]
        assert "<Rating" not in data["schema"]  # v1 didn't have rating
        assert data["version"] == "v1"
        assert data["is_current"] is False

    def test_get_version_not_found(self, client_with_db, test_project_with_versions):
        """Test retrieving non-existent version returns 404"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions/v99"
        )

        assert response.status_code == 404

    def test_get_version_project_not_found(self, client_with_db):
        """Test retrieving version for non-existent project returns 404"""
        response = client_with_db.get("/api/projects/non-existent-project/label-config/versions/v1")

        assert response.status_code == 404

    # ==================================================================
    # GET /projects/{id}/label-config/compare/{v1}/{v2} - Compare
    # ==================================================================

    def test_compare_versions_fields_added(self, client_with_db, test_project_with_versions):
        """Test comparing versions shows fields added"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/compare/v1/v2"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify comparison results
        assert data["version1"] == "v1"
        assert data["version2"] == "v2"

        # v2 added confidence rating
        assert "confidence" in data["fields_added"]

        # No fields removed
        assert len(data["fields_removed"]) == 0

        # No breaking changes (only additions)
        assert data["has_breaking_changes"] is False

    def test_compare_versions_fields_removed(self, client_with_db, test_db_session, test_user):
        """Test comparing versions detects removed fields (breaking change)"""
        # Create project with fields
        project = Project(
            id="test-project-removal",
            title="Removal Test",
            created_by=test_user.id,
            label_config="<View><Choices name='a'/><Rating name='b'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        test_db_session.add(project)
        test_db_session.commit()

        # Update by removing field
        schema_v2 = "<View><Choices name='a'/></View>"  # Removed rating 'b'
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config=schema_v2,
            description="Removed field b",
            user_id=test_user.id,
        )
        test_db_session.commit()

        response = client_with_db.get(f"/api/projects/{project.id}/label-config/compare/v1/v2")

        assert response.status_code == 200
        data = response.json()

        # Field 'b' was removed
        assert "b" in data["fields_removed"]

        # This is a breaking change
        assert data["has_breaking_changes"] is True

    def test_compare_versions_breaking_changes_flag(
        self, client_with_db, test_db_session, test_user
    ):
        """Test that has_breaking_changes flag is set correctly"""
        # Create test project
        project = Project(
            id="test-breaking-changes",
            title="Breaking Changes Test",
            created_by=test_user.id,
            label_config="<View><Choices name='x'/><Choices name='y'/></View>",
            label_config_version="v1",
            label_config_history={"versions": {}},
        )
        test_db_session.add(project)
        test_db_session.commit()

        # Remove field y (breaking change)
        LabelConfigVersionService.update_version_history(
            project=project,
            new_label_config="<View><Choices name='x'/></View>",
            description="Removed y",
            user_id=test_user.id,
        )
        test_db_session.commit()

        response = client_with_db.get(f"/api/projects/{project.id}/label-config/compare/v1/v2")

        assert response.status_code == 200
        data = response.json()
        assert data["has_breaking_changes"] is True

    def test_compare_versions_invalid_versions(self, client_with_db, test_project_with_versions):
        """Test comparing with invalid version returns error"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/compare/v1/v99"
        )

        # Should return error (404 or specific error response)
        assert response.status_code in [404, 400, 422]

    # ==================================================================
    # Additional Tests
    # ==================================================================

    def test_version_metadata_includes_user_info(self, client_with_db, test_project_with_versions):
        """Test that version metadata includes user information"""
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions"
        )

        assert response.status_code == 200
        data = response.json()
        versions_list = data["versions"]

        # Check v1 entry has metadata
        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        if "created_by" in v1_entry:  # May not be present for all versions
            assert v1_entry["created_by"] is not None

        if "created_at" in v1_entry:
            assert v1_entry["created_at"] is not None

    def test_version_schema_hash_consistency(self, client_with_db, test_project_with_versions):
        """Test that schema hashes are consistent"""
        # Get version list
        response = client_with_db.get(
            f"/api/projects/{test_project_with_versions.id}/label-config/versions"
        )

        assert response.status_code == 200
        data = response.json()
        versions_list = data["versions"]

        # Get v1's hash
        v1_entry = next(v for v in versions_list if v["version"] == "v1")
        if "schema_hash" in v1_entry:
            v1_hash = v1_entry["schema_hash"]
            assert len(v1_hash) == 12  # Truncated SHA256

            # Retrieve v1 schema
            schema_response = client_with_db.get(
                f"/api/projects/{test_project_with_versions.id}/label-config/versions/v1"
            )
            v1_schema = schema_response.json()["schema"]

            # Compute hash and verify it matches
            from label_config_version_service import LabelConfigVersionService

            computed_hash = LabelConfigVersionService.compute_schema_hash(v1_schema)
            assert computed_hash == v1_hash
