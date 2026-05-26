"""
Extended tests for health router - covering uncovered branches.

Targets: routers/health.py lines 24, 30, 40-62, 68, 82-94, 117-171, 188-226
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from models import User


class TestHealthEndpoints:
    """Test health check endpoints covering all branches."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="health-admin",
            username="healthadmin",
            email="healthadmin@test.com",
            name="Health Admin",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_user(self):
        return User(
            id="health-user",
            username="healthuser",
            email="healthuser@test.com",
            name="Health User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_root_endpoint(self, client):
        """Test root endpoint returns welcome message."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert "BenGER" in response.json()["message"]

    def test_healthz_endpoint(self, client):
        """Test /healthz kubernetes probe endpoint."""
        response = client.get("/healthz")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "healthy"

    def test_health_redis_connected(self, client):
        """Test /health with connected Redis (and DB + Celery mocked OK)."""
        from database import get_async_db

        async def override_async_db():
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=Mock())
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db
        try:
            mock_redis = Mock()
            mock_redis.ping.return_value = True
            with patch("services.redis_cache.cache") as mock_cache, \
                 patch("celery_client.get_celery_app") as mock_get_app:
                mock_cache.is_available = True
                mock_cache.redis_client = mock_redis
                mock_get_app.return_value.control.inspect.return_value.ping.return_value = {
                    "celery@w": {"ok": "pong"}
                }
                response = client.get("/health")
                assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()

    def test_health_redis_unavailable(self, client):
        """Test /health with unavailable Redis returns 503."""
        with patch("services.redis_cache.cache") as mock_cache:
            mock_cache.is_available = False
            mock_cache.redis_client = None

            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["redis"] == "unavailable"

    def test_health_redis_ping_error(self, client):
        """Test /health with Redis ping error returns 503 + 'unhealthy'.
        Redis is a required dep — failure means K8s must evict (`unhealthy`
        is what the 503 body now carries; the prior "degraded" string was
        inconsistent with the 503 status code)."""
        with patch("services.redis_cache.cache") as mock_cache:
            mock_cache.is_available = True
            mock_cache.redis_client = Mock()
            mock_cache.redis_client.ping.side_effect = Exception("Connection refused")

            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"

    def test_health_cors_auth(self, client, mock_user):
        """Test /health/cors-auth endpoint."""
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        app.dependency_overrides[require_user] = override_require_user
        try:
            response = client.get("/health/cors-auth")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["user_id"] == mock_user.id
        finally:
            app.dependency_overrides.clear()

    def test_health_schema_check_success(self, client):
        """Test /health/schema with healthy schema. Endpoint is async since
        the Phase 0 migration — must override get_async_db, not get_db.
        The handler unpacks .scalar() on two of the four queries (statement_
        timeout + application_name) and stuffs them into the JSON body, so
        plain Mock returns trigger a jsonify recursion."""
        from database import get_async_db

        async def override_async_db():
            mock_db = AsyncMock()
            # Sequence returns: two SELECTs return plain Mocks (unused),
            # then statement_timeout and application_name with real values.
            row_with_scalar = Mock()
            row_with_scalar.scalar = Mock(return_value="15000")
            row_app_name = Mock()
            row_app_name.scalar = Mock(return_value="benger-api-async")
            mock_db.execute = AsyncMock(
                side_effect=[Mock(), Mock(), row_with_scalar, row_app_name]
            )
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db
        try:
            response = client.get("/health/schema")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "healthy"
            assert data["schema"] == "validated"
        finally:
            app.dependency_overrides.clear()

    def test_health_schema_check_failure(self, client):
        """Test /health/schema with schema error. See success-case test
        for the get_async_db override rationale."""
        from database import get_async_db

        async def override_async_db():
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=Exception("Missing column"))
            yield mock_db

        app.dependency_overrides[get_async_db] = override_async_db
        try:
            response = client.get("/health/schema")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "error"
            assert data["schema"] == "invalid"
        finally:
            app.dependency_overrides.clear()

    def test_email_health_check_success(self, client, mock_superadmin):
        """Test /health/email with healthy email service."""
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        mock_email_service = Mock()
        mock_email_service.mail_enabled = True
        mock_email_service.from_email = "noreply@test.com"
        mock_email_service.from_name = "BenGER"
        mock_email_service.test_connection = AsyncMock(return_value=True)

        with patch("email_service.email_service", mock_email_service):
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            try:
                response = client.get("/health/email")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["configured"] is True
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_with_test_email(self, client, mock_superadmin):
        """Test /health/email with test email sending."""
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        mock_email_service = Mock()
        mock_email_service.mail_enabled = True
        mock_email_service.from_email = "noreply@test.com"
        mock_email_service.from_name = "BenGER"
        mock_email_service.test_connection = AsyncMock(return_value=True)
        mock_email_service.send_test_email = AsyncMock(return_value=True)

        with patch("email_service.email_service", mock_email_service):
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            try:
                response = client.get("/health/email?test_email=admin@test.com")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["test_send"]["success"] is True
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_unhealthy(self, client, mock_superadmin):
        """Test /health/email with unhealthy email service."""
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        mock_email_service = Mock()
        mock_email_service.mail_enabled = False
        mock_email_service.from_email = None
        mock_email_service.from_name = None
        mock_email_service.test_connection = AsyncMock(return_value=False)

        with patch("email_service.email_service", mock_email_service):
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            try:
                response = client.get("/health/email")
                assert response.status_code == 503
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_exception(self, client, mock_superadmin):
        """Test /health/email with exception."""
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        with patch("email_service.email_service", side_effect=Exception("Service unavailable")):
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            try:
                response = client.get("/health/email")
                assert response.status_code == 503
            finally:
                app.dependency_overrides.clear()

    def test_performance_stats(self, client, mock_superadmin):
        """Test /performance/stats endpoint."""
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        with patch("routers.health.rate_limiter", create=True) as mock_rl:
            mock_rl.clients = {}
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            try:
                with patch("rate_limiter.rate_limiter") as mock_rl_inner:
                    mock_rl_inner.clients = {}
                    response = client.get("/performance/stats")
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "timestamp" in data
                    assert "database" in data
                    assert "cache" in data
            finally:
                app.dependency_overrides.clear()
