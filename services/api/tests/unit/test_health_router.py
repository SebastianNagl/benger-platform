"""
Comprehensive tests for the health router endpoints.
Tests the current router architecture for health check endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestHealthRouter:
    """Test health router endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin_user(self):
        """Create mock superadmin user"""
        return User(
            id="admin-user-123",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_root_endpoint(self, client):
        """Test root endpoint at /"""
        response = client.get("/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "Willkommen bei der BenGER API" in data["message"]

    def test_healthz_endpoint(self, client):
        """Test Kubernetes health check at /healthz"""
        response = client.get("/healthz")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_endpoint(self, client):
        """Test Docker health check at /health"""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_cors_auth_test_endpoint(self, client, mock_superadmin_user):
        """Test CORS and auth test endpoint at /health/cors-auth"""
        from main import app
        from routers.health import require_user

        def override_require_user():
            return mock_superadmin_user

        app.dependency_overrides[require_user] = override_require_user

        try:
            headers = {"origin": "http://localhost:3000", "user-agent": "Mozilla/5.0 Test Browser"}

            response = client.get("/health/cors-auth", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert "CORS and authentication working correctly" in data["message"]
            assert data["user_id"] == mock_superadmin_user.id
            assert data["user_username"] == mock_superadmin_user.username
            assert "timestamp" in data
        finally:
            app.dependency_overrides.clear()

    def test_cors_auth_test_requires_authentication(self, client):
        """Test CORS auth test requires authentication"""
        response = client.get("/health/cors-auth")
        # Should require authentication
        assert response.status_code in [401, 403]

    def test_schema_health_check_success(self, client):
        """Test schema health check at /health/schema with healthy database"""
        from database import get_db
        from main import app

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.execute.return_value = Mock()
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/health/schema")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "healthy"
            assert data["schema"] == "validated"
            assert "timestamp" in data
        finally:
            app.dependency_overrides.clear()

    def test_schema_health_check_database_error(self, client):
        """Test schema health check with database error"""
        from database import get_db
        from main import app

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.execute.side_effect = Exception("Database connection failed")
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/health/schema")

            assert response.status_code == status.HTTP_200_OK  # Should not crash
            data = response.json()
            assert data["status"] == "error"
            assert data["schema"] == "invalid"
            assert "error" in data
            assert "Database connection failed" in data["error"]
        finally:
            app.dependency_overrides.clear()

    def test_email_health_check_success_as_superadmin(self, client, mock_superadmin_user):
        """Test email health check as superadmin at /health/email"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        with patch("email_service.email_service") as mock_email_service:
            # Mock email service configuration
            mock_email_service.mail_enabled = True
            mock_email_service.smtp_host = "mail"
            mock_email_service.smtp_port = 25
            mock_email_service.from_email = "noreply@test.com"
            mock_email_service.from_name = "Test"
            mock_email_service.test_connection = AsyncMock(return_value=True)

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                response = client.get("/health/email")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "healthy"
                assert data["configured"] is True
                assert data["service"] == "mail"
                assert data["smtp_host"] == "mail"
                assert data["connection"]["success"] is True
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_with_test_email(self, client, mock_superadmin_user):
        """Test email health check with test email sending"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        with patch("email_service.email_service") as mock_email_service:
            # Mock email service with proper attributes
            mock_email_service.mail_enabled = True
            mock_email_service.smtp_host = "smtp.example.com"
            mock_email_service.smtp_port = 587
            mock_email_service.from_email = "test@example.com"
            mock_email_service.from_name = "Test Sender"
            mock_email_service.test_connection = AsyncMock(return_value=True)
            mock_email_service.send_test_email = AsyncMock(return_value=True)

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                params = {"test_email": "test@example.com"}
                response = client.get("/health/email", params=params)

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "healthy"
                assert data["test_send"]["success"] is True
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_connection_failure(self, client, mock_superadmin_user):
        """Test email health check with connection failure"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        with patch("email_service.email_service") as mock_email_service:
            # Mock email service configuration
            mock_email_service.mail_enabled = True
            mock_email_service.smtp_host = "mail"
            mock_email_service.smtp_port = 25
            mock_email_service.from_email = "noreply@test.com"
            mock_email_service.from_name = "Test"
            mock_email_service.test_connection = AsyncMock(
                side_effect=Exception("Connection timeout")
            )

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                response = client.get("/health/email")

                # Should return 503 for unhealthy service
                assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                data = response.json()
                assert data["status"] == "unhealthy"
                assert data["connection"]["success"] is False
                assert "Connection timeout" in data["connection"]["error"]
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_not_configured(self, client, mock_superadmin_user):
        """Test email health check when email service is not configured"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        with patch("email_service.email_service") as mock_email_service:
            # Mock email service not configured
            # Mock email service configuration as disabled
            mock_email_service.mail_enabled = False
            mock_email_service.smtp_host = ""
            mock_email_service.smtp_port = 0
            mock_email_service.from_email = ""
            mock_email_service.from_name = ""
            mock_email_service.test_connection = AsyncMock(return_value=False)

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                response = client.get("/health/email")

                assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                data = response.json()
                assert data["status"] == "unhealthy"
                assert data["configured"] is False
            finally:
                app.dependency_overrides.clear()

    def test_email_health_check_requires_superadmin(self, client):
        """Test email health check requires superadmin role"""
        response = client.get("/health/email")
        # Should require superadmin authentication
        assert response.status_code in [401, 403]

    def test_email_health_check_service_error(self, client, mock_superadmin_user):
        """Test email health check with service initialization error"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        app.dependency_overrides[require_superadmin] = override_require_superadmin

        try:
            # Mock the specific import of email_service module
            import_orig = __builtins__['__import__']

            def mock_import(name, *args, **kwargs):
                if name == 'email_service':
                    raise ImportError("email_service not available")
                return import_orig(name, *args, **kwargs)

            with patch('builtins.__import__', side_effect=mock_import):
                response = client.get("/health/email")

                assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                data = response.json()
                assert data["status"] == "error"
        finally:
            app.dependency_overrides.clear()

    def test_performance_stats_success_as_superadmin(self, client, mock_superadmin_user):
        """Test performance stats endpoint as superadmin at /performance/stats"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        # Create a mock module for database_optimization
        mock_db_module = Mock()
        mock_db_module.get_query_performance_stats.return_value = {
            "avg_query_time": 15.2,
            "slow_queries": 3,
            "total_queries": 150,
        }

        with patch.dict('sys.modules', {'database_optimization': mock_db_module}), patch(
            "redis_cache.get_cache_performance_stats"
        ) as mock_cache_stats, patch("rate_limiter.rate_limiter") as mock_rate_limiter:
            mock_cache_stats.return_value = {
                "hit_rate": 0.85,
                "memory_usage": "128MB",
                "connected_clients": 5,
            }

            mock_rate_limiter.clients = {"client1": "data", "client2": "data"}

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                response = client.get("/performance/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "timestamp" in data
                assert "database" in data
                assert "cache" in data
                assert "rate_limiting" in data
                assert data["database"]["avg_query_time"] == 15.2
                assert data["cache"]["hit_rate"] == 0.85
                assert data["rate_limiting"]["active_clients"] == 2
            finally:
                app.dependency_overrides.clear()

    def test_performance_stats_partial_service_failure(self, client, mock_superadmin_user):
        """Test performance stats with some service failures"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        # Create a mock module for database_optimization
        mock_db_module = Mock()
        mock_db_module.get_query_performance_stats.return_value = {"avg_query_time": 10.5}

        with patch.dict('sys.modules', {'database_optimization': mock_db_module}), patch(
            "redis_cache.get_cache_performance_stats"
        ) as mock_cache_stats, patch("rate_limiter.rate_limiter") as mock_rate_limiter:
            # Mock cache stats failure
            mock_cache_stats.side_effect = Exception("Redis connection failed")

            # Mock rate limiter success
            mock_rate_limiter.clients = {}

            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                response = client.get("/performance/stats")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["database"]["avg_query_time"] == 10.5
                assert "error" in data["cache"]
                assert "Redis connection failed" in data["cache"]["error"]
                assert data["rate_limiting"]["active_clients"] == 0
            finally:
                app.dependency_overrides.clear()

    def test_performance_stats_complete_service_failure(self, client, mock_superadmin_user):
        """Test performance stats with complete service failure"""
        from main import app
        from routers.health import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        app.dependency_overrides[require_superadmin] = override_require_superadmin

        try:
            # Mock import errors for all services
            import_orig = __builtins__['__import__']

            def mock_import(name, *args, **kwargs):
                if name in ['rate_limiter', 'database_optimization', 'redis_cache']:
                    raise ImportError("Services not available")
                return import_orig(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                response = client.get("/performance/stats")

                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        finally:
            app.dependency_overrides.clear()

    def test_performance_stats_requires_superadmin(self, client):
        """Test performance stats requires superadmin role"""
        response = client.get("/performance/stats")
        # Should require superadmin authentication
        assert response.status_code in [401, 403]


@pytest.mark.integration
class TestHealthRouterIntegration:
    """Integration tests for health router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_basic_health_endpoints_always_available(self, client):
        """Test basic health endpoints are always available without dependencies"""
        endpoints = ["/", "/healthz", "/health"]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "status" in data or "message" in data

    # test_health_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.

    def test_health_endpoints_return_proper_content_types(self, client):
        """Test health endpoints return JSON responses"""
        endpoints = ["/", "/healthz", "/health", "/health/schema"]

        for endpoint in endpoints:
            response = client.get(endpoint)
            if response.status_code == 200:
                assert response.headers.get("content-type", "").startswith("application/json")
