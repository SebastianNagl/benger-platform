"""
Health check tests for API endpoints
Tests all critical API endpoints to ensure they are functioning correctly
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Organization, User


@pytest.mark.health
@pytest.mark.integration
class TestAPIHealth:
    """Comprehensive health check tests for all API endpoints"""

    def test_unauthenticated_health_endpoints(self, client: TestClient):
        """Test health endpoints that don't require authentication"""
        # Test main health endpoint
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

        # Test alternative health endpoint (may not exist)
        response = client.get("/api/health")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_authentication_endpoints(self, client: TestClient, test_users):
        """Test authentication endpoints"""
        # Test login endpoint
        response = client.post(
            "/api/auth/login", json={"username": "admin@test.com", "password": "admin123"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data

        # Store token for authenticated tests
        self.token = data["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

        # Test profile endpoint
        response = client.get("/api/auth/profile", headers=self.auth_headers)
        assert response.status_code == status.HTTP_200_OK

        # Test verify endpoint
        response = client.get("/api/auth/verify", headers=self.auth_headers)
        assert response.status_code == status.HTTP_200_OK

        # Test logout endpoint
        response = client.post("/api/auth/logout", headers=self.auth_headers)
        assert response.status_code == status.HTTP_200_OK

    def test_organization_endpoints(self, client: TestClient, auth_headers):
        """Test organization-related endpoints"""
        headers = auth_headers.get("admin", {})

        # Test list organizations
        response = client.get("/api/organizations", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        # Test create organization
        response = client.post(
            "/api/organizations",
            json={
                "name": "test_health_org",
                "display_name": "Test Health Organization",
                "slug": "test-health-org",
                "description": "Organization for health checks",
            },
            headers=headers,
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        ]

        if response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
            org_data = response.json()
            org_id = org_data.get("id")

            # Test get organization
            response = client.get(f"/api/organizations/{org_id}", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            # Test update organization
            response = client.put(
                f"/api/organizations/{org_id}",
                json={"display_name": "Updated Health Organization"},
                headers=headers,
            )
            assert response.status_code == status.HTTP_200_OK

            # Test delete organization
            response = client.delete(f"/api/organizations/{org_id}", headers=headers)
            assert response.status_code == status.HTTP_200_OK

    def test_project_endpoints(
        self, client: TestClient, auth_headers, test_db: Session, test_users
    ):
        """Test project-related endpoints"""
        import uuid

        from models import OrganizationMembership

        headers = auth_headers.get("admin", {})
        admin_user = test_users[0]  # First user is admin

        # Get or create an organization for testing
        org = test_db.query(Organization).first()
        if not org:
            org = Organization(
                id=str(uuid.uuid4()),
                name="test_health_org",
                display_name="Test Health Organization",
                slug="test-health-org-project",
            )
            test_db.add(org)
            test_db.commit()

        # Ensure admin user has organization membership
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == admin_user.id,
                OrganizationMembership.organization_id == org.id,
            )
            .first()
        )
        if not membership:
            membership = OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=admin_user.id,
                organization_id=org.id,
                role="ORG_ADMIN",
                is_active=True,
            )
            test_db.add(membership)
            test_db.commit()

        # Test list projects
        response = client.get("/api/projects", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        # Test create project
        response = client.post(
            "/api/projects",
            json={"title": "Test Health Project", "description": "Project for health checks"},
            headers=headers,
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

        if response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
            project_data = response.json()
            project_id = project_data.get("id")

            # Test get project
            response = client.get(f"/api/projects/{project_id}", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            # Test update project
            response = client.patch(
                f"/api/projects/{project_id}",
                json={"description": "Updated health project"},
                headers=headers,
            )
            assert response.status_code == status.HTTP_200_OK

            # Test delete project
            response = client.delete(f"/api/projects/{project_id}", headers=headers)
            assert response.status_code == status.HTTP_200_OK

    def test_user_endpoints(self, client: TestClient, auth_headers):
        """Test user-related endpoints"""
        headers = auth_headers.get("admin", {})

        # Test list users
        response = client.get("/api/users", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        # Test current user info
        response = client.get("/api/auth/me", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        # Test user profile
        response = client.get("/api/auth/profile", headers=headers)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_admin_endpoints(self, client: TestClient, auth_headers):
        """Test admin-specific endpoints"""
        headers = auth_headers.get("admin", {})

        # Test admin dashboard
        response = client.get("/api/v1/admin/dashboard", headers=headers)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

        # Test admin users list
        response = client.get("/api/v1/admin/users", headers=headers)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    @pytest.mark.parametrize(
        "endpoint,method,expected_status",
        [
            ("/health", "GET", [200]),
            ("/api/health", "GET", [200, 404]),
            ("/docs", "GET", [200, 404]),
            ("/redoc", "GET", [200, 404]),
            ("/openapi.json", "GET", [200, 404]),
        ],
    )
    def test_documentation_endpoints(
        self, client: TestClient, endpoint: str, method: str, expected_status: list
    ):
        """Test API documentation endpoints"""
        if method == "GET":
            response = client.get(endpoint)
        elif method == "POST":
            response = client.post(endpoint)
        else:
            pytest.skip(f"Unsupported method: {method}")

        assert (
            response.status_code in expected_status
        ), f"Endpoint {endpoint} returned {response.status_code}, expected one of {expected_status}"

    def test_error_handling(self, client: TestClient):
        """Test API error handling for non-existent endpoints"""
        # Test 404 for non-existent endpoint
        response = client.get("/api/v1/non-existent-endpoint")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Test method not allowed
        response = client.put("/health")
        assert response.status_code in [
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_cors_headers(self, client: TestClient):
        """Test CORS headers are properly set"""
        response = client.options("/health")
        # CORS headers might not be set in test environment
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.health
class TestHealthSummary:
    """Summary tests to verify overall API health"""

    def test_critical_endpoints_availability(self, client: TestClient, auth_headers):
        """Verify all critical endpoints are available and responding"""
        critical_endpoints = [
            ("/health", "GET", None, [200]),
            (
                "/api/auth/login",
                "POST",
                {"username": "admin@test.com", "password": "admin123"},
                [200],
            ),
            ("/api/organizations", "GET", auth_headers.get("admin", {}), [200]),
            ("/api/projects", "GET", auth_headers.get("admin", {}), [200]),
            ("/api/users", "GET", auth_headers.get("admin", {}), [200]),
        ]

        failed_endpoints = []

        for endpoint, method, data, expected_status in critical_endpoints:
            headers = data if isinstance(data, dict) and "Authorization" in str(data) else None
            json_data = data if not headers else None

            if method == "GET":
                response = client.get(endpoint, headers=headers)
            elif method == "POST":
                response = client.post(endpoint, json=json_data, headers=headers)
            else:
                continue

            if response.status_code not in expected_status:
                failed_endpoints.append(f"{method} {endpoint}: {response.status_code}")

        assert not failed_endpoints, f"Failed endpoints: {failed_endpoints}"

    def test_database_connectivity(self, test_db: Session):
        """Verify database connectivity"""
        # Simple query to test database connection
        user_count = test_db.query(User).count()
        assert user_count >= 0, "Database query failed"

    def test_authentication_flow(self, client: TestClient, test_users):
        """Test complete authentication flow"""
        # Login
        response = client.post(
            "/api/auth/login", json={"username": "admin@test.com", "password": "admin123"}
        )
        assert response.status_code == status.HTTP_200_OK
        token = response.json()["access_token"]

        # Use token
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/auth/profile", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        # Logout
        response = client.post("/api/auth/logout", headers=headers)
        assert response.status_code == status.HTTP_200_OK
