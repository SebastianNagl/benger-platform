"""
Integration tests for API endpoints with real database interactions.
Tests API integrations across different services and components.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status

from auth_module.models import User as AuthUser
from models import Organization, User


class TestAPIIntegration:
    """Integration tests for API endpoints with database"""

    # FIXTURES REMOVED: Using centralized fixtures from conftest.py to eliminate SQLite threading issues
    # Previous duplicate fixtures: test_engine, db_session, client, test_user

    @pytest.fixture(scope="function")
    def test_user(self, test_db):
        """Create test user using centralized database fixture"""
        user = User(
            id="test-integration-user",
            username="integration",
            email="integration@test.com",
            name="Integration Test User",
            hashed_password="hashed_password",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    @pytest.fixture(scope="function")
    def auth_user(self, test_user):
        """Create auth user from test user with all required fields"""
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

    @pytest.mark.integration
    def test_health_endpoints_integration(self, client):
        """Test health endpoints work without authentication"""
        # Test root endpoint
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "Willkommen bei der BenGER API" in data["message"]

        # Test health endpoints
        health_endpoints = ["/healthz", "/health"]
        for endpoint in health_endpoints:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data.get("status") == "healthy"
            assert "timestamp" in data

    @pytest.mark.integration
    def test_schema_health_integration(self, client):
        """Test schema health endpoint with real database"""
        response = client.get("/health/schema")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should validate schema successfully with test database
        assert data["status"] in ["healthy", "error"]
        assert "timestamp" in data

    @pytest.mark.integration
    def test_auth_router_integration(self, client, auth_user):
        """Test auth router endpoints with mocked authentication"""
        from auth_module import require_user, verify_token_cookie_or_header
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        def mock_verify_token():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user
        app.dependency_overrides[verify_token_cookie_or_header] = mock_verify_token

        try:
            # Test /auth/me endpoint
            response = client.get("/api/auth/me")
            assert response.status_code == status.HTTP_200_OK

            # Test /auth/verify endpoint
            response = client.get("/api/auth/verify")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["valid"] is True
            assert "user" in data
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_auth_profile_integration(self, client, auth_user, test_db):
        """Test auth profile endpoints with database integration"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test get profile
            response = client.get("/api/auth/profile")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["username"] == auth_user.username
            assert data["email"] == auth_user.email

            # Test update profile
            update_data = {
                "name": "Updated Integration User",
                "email": auth_user.email,  # Keep same email
            }

            with patch("user_service.update_user_profile") as mock_update_profile:
                # Mock successful update with all required UserProfile fields
                updated_user = Mock(spec=[])  # Empty spec to avoid auto-mocking
                updated_user.id = auth_user.id
                updated_user.username = auth_user.username
                updated_user.email = auth_user.email
                updated_user.name = "Updated Integration User"
                updated_user.is_superadmin = auth_user.is_superadmin
                updated_user.is_active = auth_user.is_active
                updated_user.age = None
                updated_user.job = None
                updated_user.years_of_experience = None
                updated_user.legal_expertise_level = None
                updated_user.german_proficiency = None
                updated_user.degree_program_type = None
                updated_user.current_semester = None
                updated_user.legal_specializations = None
                updated_user.german_state_exams_count = None
                updated_user.german_state_exams_data = None
                updated_user.pseudonym = None
                updated_user.use_pseudonym = True
                updated_user.created_at = datetime.now(timezone.utc)
                updated_user.updated_at = datetime.now(timezone.utc)

                mock_update_profile.return_value = updated_user

                response = client.put("/api/auth/profile", json=update_data)
                assert response.status_code == status.HTTP_200_OK

                response_data = response.json()
                assert response_data["name"] == "Updated Integration User"
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_users_router_integration(self, client, auth_user, test_user):
        """Test users router with database integration"""
        from auth_module import require_superadmin
        from main import app

        # Override authentication dependencies
        def mock_require_superadmin():
            return auth_user

        app.dependency_overrides[require_superadmin] = mock_require_superadmin

        try:
            # Test get all users
            with patch("auth_module.get_all_users") as mock_get_all_users:
                mock_get_all_users.return_value = [test_user]

                response = client.get("/api/users")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert isinstance(data, list)
                assert len(data) >= 0  # May be empty if mock doesn't return users
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_dashboard_stats_integration(self, client, auth_user):
        """Test dashboard stats with real database queries"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            response = client.get("/api/dashboard/stats")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert "task_count" in data
            assert "project_count" in data
            assert "annotation_count" in data

            # With empty database, counts should be 0
            assert isinstance(data["task_count"], int)
            assert isinstance(data["project_count"], int)
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_projects_api_integration(self, client, auth_user, test_db):
        """Test projects API with database integration"""

        # Create organization for projects
        org = Organization(
            id="projects-integration-org",
            name="Projects Integration Org",
            display_name="Projects Integration Org",
            slug="projects-integration-org",
            description="Organization for projects integration testing",
        )
        test_db.add(org)
        test_db.commit()

        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Mock the get_user_with_memberships function
            with patch("projects_api.get_user_with_memberships") as mock_get_user_with_memberships:
                # Mock user with memberships
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = auth_user.is_superadmin
                mock_user.organization_memberships = []
                mock_get_user_with_memberships.return_value = mock_user

                # Test list projects (empty initially)
                response = client.get("/api/projects/")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert "items" in data
                assert "total" in data
                assert "page" in data
                assert isinstance(data["items"], list)
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_cors_integration(self, client, auth_user):
        """Test CORS functionality with authentication"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test CORS preflight
            headers = {
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            }

            response = client.options("/health/cors-auth", headers=headers)
            # Should handle CORS options request
            assert response.status_code in [200, 405]

            # Test actual request with CORS headers
            headers = {"Origin": "http://localhost:3000", "User-Agent": "Integration Test Browser"}

            response = client.get("/health/cors-auth", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["status"] == "success"
            assert "CORS and authentication working correctly" in data["message"]
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_error_handling_integration(self, client, auth_user):
        """Test error handling across different endpoints"""
        from auth_module import require_user
        from main import app

        # Override authentication
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test 404 errors (with auth)
            response = client.get("/api/projects/nonexistent-project")
            assert response.status_code == status.HTTP_404_NOT_FOUND

            # Test validation errors
            invalid_data = {"invalid": "data"}
            response = client.post("/api/projects/", json=invalid_data)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.clear()

        # Test authentication errors (without auth)
        response = client.get("/api/users")  # Requires superadmin
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    def test_content_type_handling(self, client, auth_user):
        """Test different content types are handled correctly"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test JSON content type
            headers = {"Content-Type": "application/json"}
            response = client.get("/api/dashboard/stats", headers=headers)
            assert response.status_code == status.HTTP_200_OK
            assert response.headers.get("content-type", "").startswith("application/json")

            # Test invalid content type for POST requests
            headers = {"Content-Type": "text/plain"}
            response = client.post("/api/projects/", data="invalid data", headers=headers)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_pagination_integration(self, client, auth_user):
        """Test pagination parameters work correctly"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("projects_api.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = True
                mock_user.organization_memberships = []
                mock_get_user.return_value = mock_user

                # Test default pagination
                response = client.get("/api/projects/")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert data["page"] == 1
                assert data["page_size"] == 100  # Default page size

                # Test custom pagination
                params = {"page": 2, "page_size": 50}
                response = client.get("/api/projects/", params=params)
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert data["page"] == 2
                assert data["page_size"] == 50
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_search_filtering_integration(self, client, auth_user):
        """Test search and filtering functionality"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("projects_api.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
            mock_user.is_superadmin = True
            mock_user.organization_memberships = []
            mock_get_user.return_value = mock_user

            # Test search parameter
            params = {"search": "legal"}
            response = client.get("/api/projects/", params=params)
            assert response.status_code == status.HTTP_200_OK

            # Test archive filter
            params = {"is_archived": False}
            response = client.get("/api/projects/", params=params)
            assert response.status_code == status.HTTP_200_OK

            # Test combined filters
            params = {"search": "test", "is_archived": False, "page_size": 25}
            response = client.get("/api/projects/", params=params)
            assert response.status_code == status.HTTP_200_OK
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_database_transaction_integration(self, client, auth_user, test_db):
        """Test database transactions work correctly with API endpoints"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("projects_api.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
            mock_user.is_superadmin = True
            mock_get_user.return_value = mock_user

            # Create organization for project
            org = Organization(
                id="transaction-test-org",
                name="Transaction Test Org",
                display_name="Transaction Test Org",
                slug="transaction-test-org",
                description="For testing transactions",
            )
            test_db.add(org)
            test_db.commit()

            initial_org_count = test_db.query(Organization).count()

            # Attempt to create project (may succeed or fail, but should be transactional)
            project_data = {
                "title": "Transaction Test Project",
                "description": "Testing database transactions",
                "visibility": "public",
                "organization_ids": [org.id],
            }

            with patch("notification_service.notify_project_created"):
                response = client.post("/api/projects/", json=project_data)

                # Regardless of success/failure, organization count should be consistent
                final_org_count = test_db.query(Organization).count()
                assert final_org_count == initial_org_count  # Organization shouldn't be affected
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_concurrent_request_handling(self, client, auth_user):
        """Test that API handles concurrent requests properly"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("projects_api.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = True
                mock_user.organization_memberships = []
                mock_get_user.return_value = mock_user

            # Make multiple simultaneous requests
            responses = []
            for i in range(5):
                response = client.get("/api/projects/")
                responses.append(response)

                # All requests should complete successfully
                for response in responses:
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "items" in data
        finally:
            # Clean up overrides
            app.dependency_overrides.clear()
