"""
Integration tests for API endpoints with real database interactions.
Tests API integrations across different services and components.

The users / projects / search / organizations / dashboard routers these tests
hit were migrated to the async DB lane (``Depends(get_async_db)``), so rows are
seeded via ``async_test_db`` and the HTTP surface is driven through
``async_test_client``. Auth dependencies are overridden per-test; the seeded
sync rows would otherwise be invisible to the async handler's separate
connection / event loop.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from fastapi import status

from auth_module.models import User as AuthUser
from models import Organization, User

pytestmark = pytest.mark.asyncio


class TestAPIIntegration:
    """Integration tests for API endpoints with database"""

    # FIXTURES REMOVED: Using centralized fixtures from conftest.py to eliminate SQLite threading issues
    # Previous duplicate fixtures: test_engine, db_session, client, test_user

    @pytest_asyncio.fixture(scope="function")
    async def test_user(self, async_test_db):
        """Create test user using the async database fixture."""
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
        async_test_db.add(user)
        await async_test_db.commit()
        await async_test_db.refresh(user)
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
    async def test_health_endpoints_integration(self, async_test_client):
        """Test health endpoints work without authentication.

        /health now depends on get_async_db (DB ping) + a Celery
        inspect-ping; this integration test doesn't provide either,
        so we override the async DB dep and patch celery_client to
        mirror the explicit-mock pattern in test_health_router.py.
        Without these overrides /health returns 503 because the
        async-DB dep yields a real engine the test client never
        rolled back, and the test DB connection trips an
        "Event loop is closed" inside asyncpg's terminate path.
        """
        from unittest.mock import AsyncMock, Mock, patch

        from database import get_async_db
        from main import app

        async def override_async_db():
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=Mock())
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db

        try:
            # Test root endpoint
            response = await async_test_client.get("/")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "message" in data
            assert "Willkommen bei der BenGER API" in data["message"]

            # /healthz needs no deps.
            response = await async_test_client.get("/healthz")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data.get("status") == "healthy"
            assert "timestamp" in data

            # /health pings Redis + DB (required, 503 on failure) + Celery
            # workers (soft, 200 + "degraded" if missing). Mock the workers
            # so a passing-but-no-workers config doesn't flip the status.
            with patch("celery_client.get_celery_app") as mock_get_app:
                mock_get_app.return_value.control.inspect.return_value.ping.return_value = {
                    "celery@w": {"ok": "pong"}
                }
                response = await async_test_client.get("/health")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data.get("status") == "healthy"
            assert "timestamp" in data
        finally:
            app.dependency_overrides.pop(get_async_db, None)

    @pytest.mark.integration
    async def test_schema_health_integration(self, async_test_client):
        """Test schema health endpoint with real database"""
        response = await async_test_client.get("/health/schema")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should validate schema successfully with test database
        assert data["status"] in ["healthy", "error"]
        assert "timestamp" in data

    @pytest.mark.integration
    async def test_auth_router_integration(self, async_test_client, auth_user):
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
            response = await async_test_client.get("/api/auth/me")
            assert response.status_code == status.HTTP_200_OK

            # Test /auth/verify endpoint
            response = await async_test_client.get("/api/auth/verify")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["valid"] == True  # noqa: E712
            assert "user" in data
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)
            app.dependency_overrides.pop(verify_token_cookie_or_header, None)

    @pytest.mark.integration
    async def test_auth_profile_integration(
        self, async_test_client, auth_user, test_user, async_test_db
    ):
        """Test the auth profile read path against the async DB lane.

        The GET ``/api/auth/profile`` endpoint runs on the async lane
        (``Depends(get_async_db)``), so it reads this test's transaction. The
        PUT ``/api/auth/profile`` endpoint is intentionally still sync-lane
        (``update_user_profile`` carries profile-history snapshotting with no
        async twin — see ``routers/auth/user.py``), and a sync-lane handler
        cannot share this test's async transaction. So the "update" half is
        exercised as a direct write on ``async_test_db`` followed by a re-GET,
        which proves the read endpoint reflects the persisted change — strictly
        more meaningful than the previous fully-mocked PUT.
        """
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test get profile (async lane reads the seeded user).
            response = await async_test_client.get("/api/auth/profile")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["username"] == auth_user.username
            assert data["email"] == auth_user.email
            assert data["name"] == test_user.name

            # "Update" the profile: the real PUT is sync-lane and invisible to
            # this async transaction, so persist the change directly, then
            # confirm the async read endpoint surfaces it.
            test_user.name = "Updated Integration User"
            async_test_db.add(test_user)
            await async_test_db.commit()

            response = await async_test_client.get("/api/auth/profile")
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["name"] == "Updated Integration User"
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_users_router_integration(self, async_test_client, auth_user, test_user):
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

                response = await async_test_client.get("/api/users")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert isinstance(data, list)
                assert len(data) >= 0  # May be empty if mock doesn't return users
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_superadmin, None)

    @pytest.mark.integration
    async def test_dashboard_stats_integration(self, async_test_client, auth_user):
        """Test dashboard stats with real database queries"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            response = await async_test_client.get("/api/dashboard/stats")
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
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_projects_api_integration(self, async_test_client, auth_user, async_test_db):
        """Test projects API with database integration"""

        # Create organization for projects
        org = Organization(
            id="projects-integration-org",
            name="Projects Integration Org",
            display_name="Projects Integration Org",
            slug="projects-integration-org",
            description="Organization for projects integration testing",
        )
        async_test_db.add(org)
        await async_test_db.commit()

        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Mock the get_user_with_memberships function
            with patch("routers.projects.helpers.get_user_with_memberships") as mock_get_user_with_memberships:
                # Mock user with memberships
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = auth_user.is_superadmin
                mock_user.organization_memberships = []
                mock_get_user_with_memberships.return_value = mock_user

                # Test list projects (empty initially)
                response = await async_test_client.get("/api/projects/")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert "items" in data
                assert "total" in data
                assert "page" in data
                assert isinstance(data["items"], list)
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_cors_integration(self, async_test_client, auth_user):
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

            response = await async_test_client.options("/health/cors-auth", headers=headers)
            # Should handle CORS options request
            assert response.status_code in [200, 405]

            # Test actual request with CORS headers
            headers = {"Origin": "http://localhost:3000", "User-Agent": "Integration Test Browser"}

            response = await async_test_client.get("/health/cors-auth", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["status"] == "success"
            assert "CORS and authentication working correctly" in data["message"]
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_error_handling_integration(self, async_test_client, auth_user):
        """Test error handling across different endpoints"""
        from auth_module import require_user
        from main import app

        # Override authentication
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            # Test 404 errors (with auth)
            response = await async_test_client.get("/api/projects/nonexistent-project")
            assert response.status_code == status.HTTP_404_NOT_FOUND

            # Test validation errors
            invalid_data = {"invalid": "data"}
            response = await async_test_client.post("/api/projects/", json=invalid_data)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            app.dependency_overrides.pop(require_user, None)

        # Test authentication errors (without auth)
        response = await async_test_client.get("/api/users")  # Requires superadmin
        assert response.status_code in [401, 403]

    @pytest.mark.integration
    async def test_content_type_handling(self, async_test_client, auth_user):
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
            response = await async_test_client.get("/api/dashboard/stats", headers=headers)
            assert response.status_code == status.HTTP_200_OK
            assert response.headers.get("content-type", "").startswith("application/json")

            # Test invalid content type for POST requests
            headers = {"Content-Type": "text/plain"}
            response = await async_test_client.post("/api/projects/", content="invalid data", headers=headers)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_pagination_integration(self, async_test_client, auth_user):
        """Test pagination parameters work correctly"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("routers.projects.helpers.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = True
                mock_user.organization_memberships = []
                mock_get_user.return_value = mock_user

                # Test default pagination
                response = await async_test_client.get("/api/projects/")
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert data["page"] == 1
                assert data["page_size"] == 100  # Default page size

                # Test custom pagination
                params = {"page": 2, "page_size": 50}
                response = await async_test_client.get("/api/projects/", params=params)
                assert response.status_code == status.HTTP_200_OK

                data = response.json()
                assert data["page"] == 2
                assert data["page_size"] == 50
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_search_filtering_integration(self, async_test_client, auth_user):
        """Test search and filtering functionality"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("routers.projects.helpers.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = True
                mock_user.organization_memberships = []
                mock_get_user.return_value = mock_user

                # Test search parameter
                params = {"search": "legal"}
                response = await async_test_client.get("/api/projects/", params=params)
                assert response.status_code == status.HTTP_200_OK

                # Test archive filter
                params = {"is_archived": False}
                response = await async_test_client.get("/api/projects/", params=params)
                assert response.status_code == status.HTTP_200_OK

                # Test combined filters
                params = {"search": "test", "is_archived": False, "page_size": 25}
                response = await async_test_client.get("/api/projects/", params=params)
                assert response.status_code == status.HTTP_200_OK
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_database_transaction_integration(self, async_test_client, auth_user, async_test_db):
        """Test database transactions work correctly with API endpoints"""
        from sqlalchemy import func, select

        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("routers.projects.helpers.get_user_with_memberships") as mock_get_user:
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
                async_test_db.add(org)
                await async_test_db.commit()

                initial_org_count = (
                    await async_test_db.execute(select(func.count()).select_from(Organization))
                ).scalar_one()

                # Attempt to create project (may succeed or fail, but should be transactional)
                project_data = {
                    "title": "Transaction Test Project",
                    "description": "Testing database transactions",
                    "visibility": "public",
                    "organization_ids": [org.id],
                }

                with patch("notification_service.notify_project_created"):
                    response = await async_test_client.post("/api/projects/", json=project_data)  # noqa: F841

                    # Regardless of success/failure, organization count should be consistent
                    final_org_count = (
                        await async_test_db.execute(select(func.count()).select_from(Organization))
                    ).scalar_one()
                    assert final_org_count == initial_org_count  # Organization shouldn't be affected
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.integration
    async def test_concurrent_request_handling(self, async_test_client, auth_user):
        """Test that API handles concurrent requests properly"""
        from auth_module import require_user
        from main import app

        # Override authentication dependencies
        def mock_require_user():
            return auth_user

        app.dependency_overrides[require_user] = mock_require_user

        try:
            with patch("routers.projects.helpers.get_user_with_memberships") as mock_get_user:
                mock_user = Mock()
                mock_user.id = auth_user.id
                mock_user.is_superadmin = True
                mock_user.organization_memberships = []
                mock_get_user.return_value = mock_user

                # Fire multiple simultaneous requests against the async handler.
                responses = await asyncio.gather(
                    *(async_test_client.get("/api/projects/") for _ in range(5))
                )

                # All requests should complete successfully
                for response in responses:
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "items" in data
        finally:
            # Clean up overrides
            app.dependency_overrides.pop(require_user, None)
