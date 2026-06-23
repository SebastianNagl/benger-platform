"""
Health check tests for API endpoints
Tests all critical API endpoints to ensure they are functioning correctly
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import User


# ---------------------------------------------------------------------------
# Async-lane helpers for endpoints whose routers were migrated to get_async_db
# (organizations / projects / users). The sync ``client``/``test_db`` fixtures
# can't drive those handlers because the async session opens a separate
# connection that can't see the sync test transaction.
# ---------------------------------------------------------------------------


async def _make_health_admin(db) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"health-admin-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@health.test",
        name="Health Admin",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@contextmanager
def _as_health_user(db_user: User):
    # Override BOTH require_user and get_current_user — the migrated org /
    # project / user routers split between the two auth dependencies, and
    # neither can resolve a real token in the bare async test client.
    from auth_module.dependencies import get_current_user, require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.health
@pytest.mark.integration
class TestAPIHealth:
    """Comprehensive health check tests for all API endpoints"""

    def test_unauthenticated_health_endpoints(self, client: TestClient):
        """Test health endpoints that don't require authentication.

        /health now depends on a working DB session + Celery worker
        ping; both need mocks in the bare-test-client environment
        (see test_health_router.py for the canonical override pattern).
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
            with patch("celery_client.get_celery_app") as mock_get_app:
                mock_get_app.return_value.control.inspect.return_value.ping.return_value = {
                    "celery@w": {"ok": "pong"}
                }
                response = client.get("/health")
            assert response.status_code == status.HTTP_200_OK

            # Test alternative health endpoint (may not exist)
            response = client.get("/api/health")
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        finally:
            app.dependency_overrides.clear()

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

    @pytest.mark.asyncio
    async def test_organization_endpoints(self, async_test_client, async_test_db):
        """Test organization-related endpoints.

        The organizations router moved to the async DB lane, so this drives the
        async client + async session with a per-test superadmin override (the
        sync ``client``/``test_db`` can't see the async handler's transaction).
        """
        admin = await _make_health_admin(async_test_db)
        await async_test_db.commit()

        with _as_health_user(admin):
            # Test list organizations. The route is ``/api/organizations/`` —
            # the async client doesn't auto-follow the 307 the sync TestClient
            # would, so follow it explicitly (or hit the canonical path).
            response = await async_test_client.get(
                "/api/organizations/", follow_redirects=True
            )
            assert response.status_code == status.HTTP_200_OK

            # Test create organization
            response = await async_test_client.post(
                "/api/organizations/",
                json={
                    "name": "test_health_org",
                    "display_name": "Test Health Organization",
                    "slug": f"test-health-org-{uuid.uuid4().hex[:8]}",
                    "description": "Organization for health checks",
                },
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
                response = await async_test_client.get(f"/api/organizations/{org_id}")
                assert response.status_code == status.HTTP_200_OK

                # Test update organization
                response = await async_test_client.put(
                    f"/api/organizations/{org_id}",
                    json={"display_name": "Updated Health Organization"},
                )
                assert response.status_code == status.HTTP_200_OK

                # Test delete organization
                response = await async_test_client.delete(f"/api/organizations/{org_id}")
                assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_project_endpoints(self, async_test_client, async_test_db):
        """Test project-related endpoints (projects router is on the async DB
        lane). Drives the async client + session with a superadmin override."""
        admin = await _make_health_admin(async_test_db)
        await async_test_db.commit()

        with _as_health_user(admin):
            # Test list projects (route is ``/api/projects/`` — follow the 307).
            response = await async_test_client.get(
                "/api/projects/", follow_redirects=True
            )
            assert response.status_code == status.HTTP_200_OK

            # Test create project
            response = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Test Health Project",
                    "description": "Project for health checks",
                },
            )
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

            if response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
                project_data = response.json()
                project_id = project_data.get("id")

                # Test get project
                response = await async_test_client.get(f"/api/projects/{project_id}")
                assert response.status_code == status.HTTP_200_OK

                # Test update project
                response = await async_test_client.patch(
                    f"/api/projects/{project_id}",
                    json={"description": "Updated health project"},
                )
                assert response.status_code == status.HTTP_200_OK

                # Test delete project
                response = await async_test_client.delete(f"/api/projects/{project_id}")
                assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_user_endpoints(self, async_test_client, async_test_db):
        """Test user-related endpoints (users router is on the async DB lane)."""
        admin = await _make_health_admin(async_test_db)
        await async_test_db.commit()

        with _as_health_user(admin):
            # Test list users
            response = await async_test_client.get("/api/users")
            assert response.status_code == status.HTTP_200_OK

            # Test current user info
            response = await async_test_client.get("/api/auth/me")
            assert response.status_code == status.HTTP_200_OK

            # Test user profile
            response = await async_test_client.get("/api/auth/profile")
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
            # /health intentionally removed from this list — it now needs
            # DB + Celery dep mocks (see test_unauthenticated_health_endpoints
            # above). Without mocks the bare TestClient hits a real async
            # engine that returns 503 on the SELECT 1 probe.
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
@pytest.mark.integration
class TestHealthDegradedContract:
    """Dependency-matrix tests for GET /health (extended#33).

    Contract as implemented in services/api/routers/health.py:

      - Postgres is REQUIRED: DB failure -> 503 + status="unhealthy"
        (K8s evicts the pod). The DB check short-circuits before the
        Celery probe, so celery_workers stays "unknown".
      - Celery is SOFT: workers unreachable -> 200 + status="degraded".
        The API still serves sync traffic; async tasks just queue, so
        operators alert on the body field instead of K8s evicting.
      - Redis is REQUIRED: unavailable -> 503 + status="unhealthy".
      - Everything up -> 200 + status="healthy".

    DB and Celery are mocked via dependency override / patch (same
    pattern as test_unauthenticated_health_endpoints above); Redis comes
    from the real test container except in the explicit Redis-down test.
    """

    @pytest.mark.parametrize(
        "db_up,celery_up,expected_http,expected_status",
        [
            (True, True, 200, "healthy"),
            (True, False, 200, "degraded"),
            (False, True, 503, "unhealthy"),
            (False, False, 503, "unhealthy"),
        ],
        ids=["all-up", "celery-down", "db-down", "db-and-celery-down"],
    )
    def test_health_dependency_matrix(
        self,
        client: TestClient,
        db_up: bool,
        celery_up: bool,
        expected_http: int,
        expected_status: str,
    ):
        from unittest.mock import AsyncMock, Mock, patch

        from database import get_async_db
        from main import app

        async def override_async_db():
            mock_db = AsyncMock()
            if db_up:
                mock_db.execute = AsyncMock(return_value=Mock())
            else:
                mock_db.execute = AsyncMock(side_effect=Exception("DB unreachable"))
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db
        try:
            with patch("celery_client.get_celery_app") as mock_get_app:
                ping = mock_get_app.return_value.control.inspect.return_value.ping
                ping.return_value = (
                    {"celery@worker1": {"ok": "pong"}} if celery_up else None
                )
                response = client.get("/health")
        finally:
            app.dependency_overrides.pop(get_async_db, None)

        assert response.status_code == expected_http
        data = response.json()
        assert data["status"] == expected_status

        if db_up:
            assert data["redis"] == "connected"
            assert data["database"] == "connected"
            if celery_up:
                assert "reachable" in data["celery_workers"]
            else:
                assert data["celery_workers"] == "no_workers_responding"
        else:
            assert data["database"] == "error"
            # DB failure returns before the Celery probe runs.
            assert data["celery_workers"] == "unknown"

    def test_celery_inspect_exception_marks_degraded(self, client: TestClient):
        """A broker error (not just silence) is also a soft failure:
        celery_workers="error", status="degraded", still HTTP 200."""
        from unittest.mock import AsyncMock, Mock, patch

        from database import get_async_db
        from main import app

        async def override_async_db():
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=Mock())
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db
        try:
            with patch("celery_client.get_celery_app") as mock_get_app:
                mock_get_app.return_value.control.inspect.return_value.ping.side_effect = Exception(
                    "broker unreachable"
                )
                response = client.get("/health")
        finally:
            app.dependency_overrides.pop(get_async_db, None)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"
        assert data["celery_workers"] == "error"

    def test_redis_unavailable_returns_503(self, client: TestClient):
        """Redis is a hard dependency: unavailable -> 503 + "unhealthy".
        The Redis check runs first, so database/celery stay "unknown"."""
        from unittest.mock import patch

        with patch("services.redis_cache.cache") as mock_cache:
            mock_cache.is_available = False
            mock_cache.redis_client = None
            response = client.get("/health")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["redis"] == "unavailable"
        assert data["database"] == "unknown"
        assert data["celery_workers"] == "unknown"


@pytest.mark.health
class TestHealthSummary:
    """Summary tests to verify overall API health"""

    def test_critical_endpoints_availability(self, client: TestClient, auth_headers):
        """Verify all critical endpoints are available and responding"""
        critical_endpoints = [
            # /health needs DB + Celery dep mocks to return 200 in the bare test
            # client (the SELECT 1 / Redis probe 503s unmocked — see the
            # documented note in test_documentation_endpoints and the mocked
            # TestHealthDegradedContract). For this availability smoke we only
            # assert it's *reachable and responds*, so 503 is acceptable here.
            ("/health", "GET", None, [200, 503]),
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
