"""
Unit tests for RateLimiter

Tests comprehensive rate limiting functionality including:
- Redis and memory fallback implementations
- Fixed-window and rolling-window enforcement
- Request counting and TTL management
- Client identification (user ID vs IP)
"""

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import Request

from models import User
from services.rate_limiter import RateLimiter


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

            assert limiter.redis_client == None  # noqa: E711
            assert limiter._memory_store == {}

    def test_initialization_with_invalid_redis_url(self):
        """Test handling of invalid Redis URL"""
        with patch("services.rate_limiter.redis.from_url", side_effect=ValueError("Invalid URL")):
            limiter = RateLimiter("invalid-url")

            assert limiter.redis_client == None  # noqa: E711
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
        # Rightmost hop: the leftmost entry is client-controlled.
        assert client_id == "ip:192.168.1.1"

    def test_get_key_generation(self, rate_limiter_with_redis):
        """Test Redis key generation"""
        key = rate_limiter_with_redis._get_key("user:123", "tasks", "minute")
        assert key == "ratelimit:user:123:tasks:minute"


@pytest.mark.unit
class TestRedisOperations:
    """Test Redis-based rate limiting operations"""

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
        """A Redis error counts the request as the first one (fail open)"""
        rate_limiter_with_redis.redis_client.pipeline.side_effect = Exception("Redis error")

        count = await rate_limiter_with_redis._increment_count("test-key", 60)

        assert count == 1


@pytest.mark.unit
class TestMemoryFallback:
    """Test memory-based rate limiting operations"""

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
        # Seconds until the fixed window resets.
        assert 1 <= result["retry_after"] <= 60

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


class _FakeSortedSets:
    """Just the sorted-set commands the rolling window uses."""

    def __init__(self):
        self.sets = {}

    def pipeline(self):
        return _FakePipeline(self)

    def zrem(self, key, member):
        self.sets.get(key, {}).pop(member, None)


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.ops.append((name, args, kwargs))

        return queue

    def execute(self):
        out = []
        for name, args, kwargs in self.ops:
            zset = self.redis.sets.setdefault(args[0], {})
            if name == "zremrangebyscore":
                low = float("-inf") if args[1] == "-inf" else float(args[1])
                gone = [m for m, score in zset.items() if low <= score <= float(args[2])]
                for m in gone:
                    del zset[m]
                out.append(len(gone))
            elif name == "zadd":
                zset.update(args[1])
                out.append(1)
            elif name == "zcard":
                out.append(len(zset))
            elif name == "zrange":
                ordered = sorted(zset.items(), key=lambda item: item[1])
                out.append(ordered[args[1] : args[2] + 1])
            else:  # expire
                out.append(True)
        return out


@pytest.mark.unit
class TestRollingLimit:
    """check_rolling_limit: the last N seconds, refused events not counted"""

    @pytest.fixture(params=["memory", "redis"])
    def limiter(self, request, monkeypatch):
        monkeypatch.setenv("TESTING", "false")
        with patch("services.rate_limiter.redis.from_url", side_effect=Exception("down")):
            limiter = RateLimiter("redis://test:6379")
        if request.param == "redis":
            limiter.redis_client = _FakeSortedSets()
        return limiter

    async def test_n_plus_first_event_is_refused(self, limiter):
        for _ in range(3):
            assert await limiter.check_rolling_limit("user:u1", "upload_url", 3, 86400) is None
        error = await limiter.check_rolling_limit("user:u1", "upload_url", 3, 86400)
        assert error is not None
        assert error["limit"] == 3 and error["window"] == 86400
        assert 86000 < error["retry_after"] <= 86400
        # Another client has its own window.
        assert await limiter.check_rolling_limit("user:u2", "upload_url", 3, 86400) is None

    async def test_window_rolls_and_refusals_do_not_extend_it(self, limiter, monkeypatch):
        clock = [1_000_000.0]
        monkeypatch.setattr("services.rate_limiter.time.time", lambda: clock[0])
        assert await limiter.check_rolling_limit("user:u1", "x", 2, 100) is None
        clock[0] += 50
        assert await limiter.check_rolling_limit("user:u1", "x", 2, 100) is None
        clock[0] += 10
        error = await limiter.check_rolling_limit("user:u1", "x", 2, 100)
        # The first event leaves the window 100 s after it was counted.
        assert error["retry_after"] == 40
        clock[0] += 39
        assert await limiter.check_rolling_limit("user:u1", "x", 2, 100) is not None
        clock[0] += 2  # first event is out now; the refused ones never counted
        assert await limiter.check_rolling_limit("user:u1", "x", 2, 100) is None
        assert await limiter.check_rolling_limit("user:u1", "x", 2, 100) is not None

    async def test_redis_error_fails_open(self, monkeypatch):
        monkeypatch.setenv("TESTING", "false")
        with patch("services.rate_limiter.redis.from_url", side_effect=Exception("down")):
            limiter = RateLimiter("redis://test:6379")
        limiter.redis_client = Mock()
        limiter.redis_client.pipeline.side_effect = Exception("Redis error")
        assert await limiter.check_rolling_limit("user:u1", "x", 1, 60) is None

    async def test_skipped_while_testing(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        with patch("services.rate_limiter.redis.from_url", side_effect=Exception("down")):
            limiter = RateLimiter("redis://test:6379")
        for _ in range(3):
            assert await limiter.check_rolling_limit("user:u1", "x", 1, 60) is None


@pytest.mark.unit
class TestGlobalRateLimiterInstance:
    """Test global rate limiter instance"""

    def test_global_rate_limiter_exists(self):
        """Test that global rate limiter instance is available"""
        from services.rate_limiter import rate_limiter

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
