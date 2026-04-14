"""
Unit tests for RateLimiter

Tests comprehensive rate limiting functionality including:
- Redis and memory fallback implementations
- Rate limit enforcement for different endpoints
- User role-based rate limit multipliers
- Request counting and TTL management
- Client identification (user ID vs IP)
- Rate limit decorator and middleware
"""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from models import User
from rate_limiter import (
    RATE_LIMITS,
    USER_ROLE_MULTIPLIERS,
    RateLimiter,
    get_rate_limits_for_user,
    rate_limit,
    rate_limit_middleware,
    rate_limiter,
)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    client = Mock()
    client.ping.return_value = True
    client.get.return_value = None
    client.pipeline.return_value = Mock()
    return client


@pytest.fixture
def rate_limiter_with_redis(mock_redis_client):
    """RateLimiter instance with mocked Redis"""
    with patch("services.rate_limiter.redis.from_url", return_value=mock_redis_client):
        limiter = RateLimiter("redis://test:6379")
        return limiter


@pytest.fixture
def rate_limiter_memory_only():
    """RateLimiter instance using memory fallback"""
    with patch("services.rate_limiter.redis.from_url", side_effect=Exception("Connection failed")):
        limiter = RateLimiter("redis://test:6379")
        return limiter


@pytest.fixture
def mock_request():
    """Mock FastAPI request"""
    request = Mock(spec=Request)
    request.client.host = "192.168.1.1"
    request.headers = {}
    request.url.path = "/api/test"
    return request


@pytest.fixture
def mock_user():
    """Mock user object"""
    user = Mock(spec=User)
    user.id = "user-123"
    user.is_superadmin = False
    return user


@pytest.mark.unit
class TestRateLimiterInitialization:
    """Test RateLimiter initialization"""

    def test_initialization_with_redis_success(self, mock_redis_client):
        """Test successful Redis connection"""
        with patch("services.rate_limiter.redis.from_url", return_value=mock_redis_client):
            limiter = RateLimiter("redis://test:6379")

            assert limiter.redis_client == mock_redis_client
            mock_redis_client.ping.assert_called_once()

    def test_initialization_with_redis_failure(self):
        """Test fallback to memory when Redis fails"""
        with patch("services.rate_limiter.redis.from_url", side_effect=Exception("Connection failed")):
            limiter = RateLimiter("redis://test:6379")

            assert limiter.redis_client is None
            assert limiter._memory_store == {}

    def test_initialization_with_invalid_redis_url(self):
        """Test handling of invalid Redis URL"""
        with patch("services.rate_limiter.redis.from_url", side_effect=ValueError("Invalid URL")):
            limiter = RateLimiter("invalid-url")

            assert limiter.redis_client is None
            assert isinstance(limiter._memory_store, dict)


@pytest.mark.unit
class TestClientIdentification:
    """Test client ID generation"""

    def test_get_client_id_with_user(self, rate_limiter_with_redis, mock_request, mock_user):
        """Test client ID generation for authenticated user"""
        client_id = rate_limiter_with_redis._get_client_id(mock_request, mock_user)
        assert client_id == "user:user-123"

    def test_get_client_id_without_user(self, rate_limiter_with_redis, mock_request):
        """Test client ID generation using IP address"""
        client_id = rate_limiter_with_redis._get_client_id(mock_request, None)
        assert client_id == "ip:192.168.1.1"

    def test_get_client_id_with_forwarded_ip(self, rate_limiter_with_redis, mock_request):
        """Test client ID with X-Forwarded-For header"""
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        client_id = rate_limiter_with_redis._get_client_id(mock_request, None)
        assert client_id == "ip:10.0.0.1"

    def test_get_key_generation(self, rate_limiter_with_redis):
        """Test Redis key generation"""
        key = rate_limiter_with_redis._get_key("user:123", "tasks", "minute")
        assert key == "ratelimit:user:123:tasks:minute"


@pytest.mark.unit
class TestRedisOperations:
    """Test Redis-based rate limiting operations"""

    @pytest.mark.asyncio
    async def test_get_count_with_redis(self, rate_limiter_with_redis):
        """Test getting count from Redis"""
        rate_limiter_with_redis.redis_client.get.return_value = "5"

        count = await rate_limiter_with_redis._get_count("test-key")

        assert count == 5
        rate_limiter_with_redis.redis_client.get.assert_called_with("test-key")

    @pytest.mark.asyncio
    async def test_get_count_redis_empty(self, rate_limiter_with_redis):
        """Test getting count when Redis key doesn't exist"""
        rate_limiter_with_redis.redis_client.get.return_value = None

        count = await rate_limiter_with_redis._get_count("test-key")

        assert count == 0

    @pytest.mark.asyncio
    async def test_increment_count_with_redis(self, rate_limiter_with_redis):
        """Test incrementing count in Redis with TTL"""
        mock_pipe = Mock()
        mock_pipe.execute.return_value = [1, True]
        rate_limiter_with_redis.redis_client.pipeline.return_value = mock_pipe

        count = await rate_limiter_with_redis._increment_count("test-key", 60)

        assert count == 1
        mock_pipe.incr.assert_called_with("test-key")
        mock_pipe.expire.assert_called_with("test-key", 60)

    @pytest.mark.asyncio
    async def test_redis_error_handling(self, rate_limiter_with_redis):
        """Test error handling for Redis operations"""
        rate_limiter_with_redis.redis_client.get.side_effect = Exception("Redis error")

        count = await rate_limiter_with_redis._get_count("test-key")

        assert count == 0  # Should return 0 on error


@pytest.mark.unit
class TestMemoryFallback:
    """Test memory-based rate limiting operations"""

    @pytest.mark.asyncio
    async def test_get_count_memory_fallback(self, rate_limiter_memory_only):
        """Test getting count from memory store"""
        rate_limiter_memory_only._memory_store = {
            "test-key": {"count": 3, "expires": time.time() + 60}
        }

        count = await rate_limiter_memory_only._get_count("test-key")

        assert count == 3

    @pytest.mark.asyncio
    async def test_increment_count_memory_fallback(self, rate_limiter_memory_only):
        """Test incrementing count in memory store"""
        count = await rate_limiter_memory_only._increment_count("test-key", 60)

        assert count == 1
        assert "test-key" in rate_limiter_memory_only._memory_store
        assert rate_limiter_memory_only._memory_store["test-key"]["count"] == 1

    @pytest.mark.asyncio
    async def test_memory_ttl_expiration(self, rate_limiter_memory_only):
        """Test TTL expiration in memory store"""
        # Set expired entry
        rate_limiter_memory_only._memory_store = {
            "test-key": {"count": 10, "expires": time.time() - 1}
        }

        count = await rate_limiter_memory_only._increment_count("test-key", 60)

        assert count == 1  # Should reset after expiration


@pytest.mark.unit
class TestRateLimitChecking:
    """Test rate limit checking logic"""

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, rate_limiter_with_redis, mock_request):
        """Test request allowed within rate limit"""
        mock_pipe = Mock()
        mock_pipe.execute.return_value = [5, True]  # 5 requests
        rate_limiter_with_redis.redis_client.pipeline.return_value = mock_pipe

        limits = {"minute": (10, 60)}  # 10 requests per minute

        result = await rate_limiter_with_redis.check_rate_limit(mock_request, "test", limits)

        assert result is None  # Should be allowed

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, rate_limiter_with_redis, mock_request):
        """Test request blocked when rate limit exceeded"""
        mock_pipe = Mock()
        mock_pipe.execute.return_value = [11, True]  # 11 requests
        rate_limiter_with_redis.redis_client.pipeline.return_value = mock_pipe

        limits = {"minute": (10, 60)}  # 10 requests per minute

        # Disable TESTING bypass to actually test rate limiting
        with patch.dict("os.environ", {"TESTING": ""}):
            result = await rate_limiter_with_redis.check_rate_limit(mock_request, "test", limits)

        assert result is not None
        assert result["error"] == "rate_limit_exceeded"
        assert result["limit"] == 10
        assert result["current"] == 11
        assert result["retry_after"] == 60

    @pytest.mark.asyncio
    async def test_check_multiple_windows(self, rate_limiter_with_redis, mock_request):
        """Test checking multiple rate limit windows"""
        mock_pipe = Mock()
        # First window: 5 requests (under limit)
        # Second window: 51 requests (over limit)
        mock_pipe.execute.side_effect = [[5, True], [51, True]]
        rate_limiter_with_redis.redis_client.pipeline.return_value = mock_pipe

        limits = {
            "minute": (10, 60),  # 10 per minute
            "hour": (50, 3600),  # 50 per hour
        }

        # Disable TESTING bypass to actually test rate limiting
        with patch.dict("os.environ", {"TESTING": ""}):
            result = await rate_limiter_with_redis.check_rate_limit(mock_request, "test", limits)

        assert result is not None  # Should be blocked by hour limit
        assert result["limit"] == 50
        assert result["window"] == 3600

    @pytest.mark.asyncio
    async def test_skip_rate_limiting_in_tests(self, rate_limiter_with_redis, mock_request):
        """Test that rate limiting is skipped during tests"""
        with patch.dict("os.environ", {"TESTING": "true"}):
            limits = {"minute": (1, 60)}  # Very restrictive limit

            result = await rate_limiter_with_redis.check_rate_limit(mock_request, "test", limits)

            assert result is None  # Should be allowed due to TESTING flag


@pytest.mark.unit
class TestUserRoleLimits:
    """Test user role-based rate limit adjustments"""

    def test_get_rate_limits_for_admin(self):
        """Test rate limits for admin users"""
        admin_user = Mock(spec=User)
        admin_user.role = "admin"

        limits = get_rate_limits_for_user("tasks", admin_user)

        base_minute_limit = RATE_LIMITS["tasks"]["minute"][0]
        expected_limit = int(base_minute_limit * USER_ROLE_MULTIPLIERS["admin"])

        assert limits["minute"][0] == expected_limit

    def test_get_rate_limits_for_contributor(self):
        """Test rate limits for contributor users"""
        contributor_user = Mock(spec=User)
        contributor_user.role = "contributor"

        limits = get_rate_limits_for_user("tasks", contributor_user)

        base_minute_limit = RATE_LIMITS["tasks"]["minute"][0]
        expected_limit = int(base_minute_limit * USER_ROLE_MULTIPLIERS["contributor"])

        assert limits["minute"][0] == expected_limit

    def test_get_rate_limits_for_annotator(self):
        """Test rate limits for annotator users"""
        annotator_user = Mock(spec=User)
        annotator_user.role = "annotator"

        limits = get_rate_limits_for_user("tasks", annotator_user)

        assert limits == RATE_LIMITS["tasks"]  # Base limits

    def test_get_rate_limits_without_user(self):
        """Test rate limits for unauthenticated requests"""
        limits = get_rate_limits_for_user("tasks", None)

        assert limits == RATE_LIMITS["tasks"]  # Base limits

    def test_get_rate_limits_unknown_endpoint(self):
        """Test fallback to default API limits for unknown endpoint"""
        limits = get_rate_limits_for_user("unknown", None)

        assert limits == RATE_LIMITS["api"]


@pytest.mark.unit
class TestRateLimitDecorator:
    """Test rate limit decorator functionality"""

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_allowed(self):
        """Test decorator allows request within limits"""
        mock_func = AsyncMock(return_value="success")
        decorated = rate_limit("test")(mock_func)

        mock_request = Mock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        with patch.object(rate_limiter, "check_rate_limit", return_value=None):
            result = await decorated(mock_request)

        assert result == "success"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_blocked(self):
        """Test decorator blocks request over limits"""
        mock_func = AsyncMock(return_value="success")
        decorated = rate_limit("test")(mock_func)

        mock_request = Mock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        error_response = {"error": "rate_limit_exceeded", "retry_after": 60}

        with patch.object(rate_limiter, "check_rate_limit", return_value=error_response):
            with pytest.raises(HTTPException) as exc_info:
                await decorated(mock_request)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == error_response
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_with_user(self):
        """Test decorator with authenticated user"""
        mock_func = AsyncMock(return_value="success")
        decorated = rate_limit("test")(mock_func)

        mock_request = Mock(spec=Request)
        mock_user = Mock(spec=User)
        mock_user.id = "user-123"
        mock_user.role = "admin"

        with patch.object(rate_limiter, "check_rate_limit", return_value=None) as mock_check:
            result = await decorated(mock_request, user=mock_user)

        assert result == "success"
        # Verify user was passed to rate limit check
        call_args = mock_check.call_args
        assert call_args[0][3] == mock_user  # user argument


@pytest.mark.unit
class TestRateLimitMiddleware:
    """Test rate limit middleware functionality"""

    @pytest.mark.asyncio
    async def test_middleware_skips_health_check(self):
        """Test middleware skips health check endpoint"""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/health"

        mock_call_next = AsyncMock(return_value="response")

        response = await rate_limit_middleware(mock_request, mock_call_next)

        assert response == "response"
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_middleware_allows_normal_request(self):
        """Test middleware allows request within limits"""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/tasks"
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        mock_call_next = AsyncMock(return_value="response")

        with patch.object(rate_limiter, "check_rate_limit", return_value=None):
            response = await rate_limit_middleware(mock_request, mock_call_next)

        assert response == "response"

    @pytest.mark.asyncio
    async def test_middleware_blocks_over_limit(self):
        """Test middleware blocks request over limits"""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/tasks"
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        mock_call_next = AsyncMock()

        error_response = {"error": "rate_limit_exceeded", "retry_after": 60}

        with patch.object(rate_limiter, "check_rate_limit", return_value=error_response):
            response = await rate_limit_middleware(mock_request, mock_call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        mock_call_next.assert_not_called()


@pytest.mark.unit
class TestRateLimitConfigurations:
    """Test different rate limit configurations"""

    def test_auth_endpoint_limits(self):
        """Test authentication endpoint has restrictive limits"""
        limits = RATE_LIMITS["auth"]
        assert limits["minute"][0] == 10  # 10 per minute
        assert limits["hour"][0] == 50  # 50 per hour

    def test_upload_endpoint_limits(self):
        """Test upload endpoint has very restrictive limits"""
        limits = RATE_LIMITS["upload"]
        assert limits["minute"][0] == 5  # 5 per minute
        assert limits["hour"][0] == 20  # 20 per hour

    def test_evaluation_endpoint_limits(self):
        """Test evaluation endpoint has restrictive limits"""
        limits = RATE_LIMITS["evaluation"]
        assert limits["minute"][0] == 5  # 5 per minute
        assert limits["hour"][0] == 50  # 50 per hour

    def test_general_api_limits(self):
        """Test general API endpoint limits"""
        limits = RATE_LIMITS["api"]
        assert limits["minute"][0] == 60  # 60 per minute
        assert limits["hour"][0] == 1000  # 1000 per hour


@pytest.mark.unit
class TestGlobalRateLimiterInstance:
    """Test global rate limiter instance"""

    def test_global_rate_limiter_exists(self):
        """Test that global rate limiter instance is available"""
        from rate_limiter import rate_limiter

        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_global_rate_limiter_uses_env_redis_uri(self):
        """Test global instance uses REDIS_URI from environment"""
        with patch.dict("os.environ", {"REDIS_URI": "redis://custom:6380"}):
            with patch("services.rate_limiter.redis.from_url") as mock_from_url:
                # Re-import to trigger initialization
                import importlib

                import services.rate_limiter as module

                importlib.reload(module)

                # Should use custom URI
                mock_from_url.assert_called_with("redis://custom:6380", decode_responses=True)
