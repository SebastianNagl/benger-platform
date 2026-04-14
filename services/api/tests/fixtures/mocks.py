"""Mock fixtures for BenGER API tests.

Provides centralized mocking for Celery, Redis, and other external services.
"""

from unittest.mock import AsyncMock, patch

import fakeredis
import pytest


@pytest.fixture(scope="function")
def mock_celery() -> AsyncMock:
    """Mock Celery task execution."""
    mock = AsyncMock()
    mock.delay.return_value.id = "test-task-id"
    mock.delay.return_value.status = "SUCCESS"
    return mock


@pytest.fixture(scope="function", autouse=True)
def mock_redis():
    """Centralized Redis mock using fakeredis for consistent testing

    This fixture replaces Redis connections throughout the application
    with a fake Redis instance that behaves like real Redis but doesn't
    require a running Redis server.

    Issue #179: Standardized Redis mocking pattern
    """
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    fake_async_redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    # Import the redis_cache module to access the global cache instance
    import redis_cache

    # Mock the global cache instance
    original_redis_client = redis_cache.cache.redis_client
    original_is_available = redis_cache.cache.is_available

    redis_cache.cache.redis_client = fake_redis
    redis_cache.cache.is_available = True

    # Also mock websocket_clustering to prevent Redis connection errors
    import websocket_clustering

    original_cluster_redis = websocket_clustering.cluster_manager.redis_client
    websocket_clustering.cluster_manager.redis_client = None  # Disable clustering in tests

    try:
        yield fake_redis
    finally:
        # Restore original values
        redis_cache.cache.redis_client = original_redis_client
        redis_cache.cache.is_available = original_is_available
        websocket_clustering.cluster_manager.redis_client = original_cluster_redis


@pytest.fixture(scope="function")
def mock_redis_async():
    """Async Redis mock for testing async Redis operations"""
    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    with (
        patch("websocket_clustering.redis_client", fake_redis),
        patch("main.async_redis_client", fake_redis),
    ):
        yield fake_redis
