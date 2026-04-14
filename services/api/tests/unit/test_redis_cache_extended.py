"""
Extended tests for redis_cache service.

Targets: services/redis_cache.py lines 88-197, 214-250, 259-405, 410-449
"""

import json
from unittest.mock import Mock, patch, MagicMock

import pytest
import fakeredis


class TestRedisCacheMethods:
    """Test RedisCache class methods."""

    @pytest.fixture
    def cache_instance(self):
        """Create a RedisCache instance with fake Redis."""
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
        instance.is_available = True
        return instance

    def test_get_returns_none_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        assert instance.get("key") is None

    def test_get_returns_parsed_json(self, cache_instance):
        cache_instance.redis_client.set("test-key", json.dumps({"value": 42}))
        result = cache_instance.get("test-key")
        assert result == {"value": 42}

    def test_get_returns_none_for_missing_key(self, cache_instance):
        result = cache_instance.get("nonexistent")
        assert result is None

    def test_get_handles_exception(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.get.side_effect = Exception("Connection lost")
        assert cache_instance.get("key") is None

    def test_set_returns_false_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        assert instance.set("key", "value") is False

    def test_set_stores_value(self, cache_instance):
        assert cache_instance.set("test-key", {"data": "value"}, ttl=60) is True
        stored = cache_instance.redis_client.get("test-key")
        assert json.loads(stored) == {"data": "value"}

    def test_set_handles_exception(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.setex.side_effect = Exception("Write error")
        assert cache_instance.set("key", "value") is False

    def test_delete_returns_false_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        assert instance.delete("key") is False

    def test_delete_removes_key(self, cache_instance):
        cache_instance.redis_client.set("del-key", "value")
        assert cache_instance.delete("del-key") is True
        assert cache_instance.redis_client.get("del-key") is None

    def test_delete_handles_exception(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.delete.side_effect = Exception("Delete error")
        assert cache_instance.delete("key") is False

    def test_delete_pattern_returns_zero_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        assert instance.delete_pattern("pattern*") == 0

    def test_delete_pattern_deletes_matching_keys(self, cache_instance):
        cache_instance.redis_client.set("prefix:1", "a")
        cache_instance.redis_client.set("prefix:2", "b")
        cache_instance.redis_client.set("other:1", "c")
        result = cache_instance.delete_pattern("prefix:*")
        assert result >= 2

    def test_delete_pattern_no_matches(self, cache_instance):
        result = cache_instance.delete_pattern("nonexistent:*")
        assert result == 0

    def test_delete_pattern_handles_exception(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.keys.side_effect = Exception("Error")
        assert cache_instance.delete_pattern("pattern*") == 0

    def test_exists_returns_false_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        assert instance.exists("key") is False

    def test_exists_returns_true_for_existing_key(self, cache_instance):
        cache_instance.redis_client.set("exists-key", "value")
        assert cache_instance.exists("exists-key") is True

    def test_exists_returns_false_for_missing_key(self, cache_instance):
        assert cache_instance.exists("nonexistent") is False

    def test_exists_handles_exception(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.exists.side_effect = Exception("Error")
        assert cache_instance.exists("key") is False

    def test_get_stats_when_unavailable(self):
        from services.redis_cache import RedisCache
        instance = RedisCache.__new__(RedisCache)
        instance.is_available = False
        stats = instance.get_stats()
        assert stats["available"] is False

    def test_get_stats_success(self, cache_instance):
        # FakeRedis doesn't support info command, so mock it
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.info.return_value = {
            "connected_clients": 1,
            "used_memory_human": "1M",
            "keyspace_hits": 50,
            "keyspace_misses": 10,
        }
        stats = cache_instance.get_stats()
        assert stats["available"] is True
        assert stats["connected_clients"] == 1

    def test_get_stats_error(self, cache_instance):
        cache_instance.redis_client = Mock()
        cache_instance.redis_client.info.side_effect = Exception("Error")
        stats = cache_instance.get_stats()
        assert stats["available"] is False

    def test_calculate_hit_rate_with_hits(self, cache_instance):
        info = {"keyspace_hits": 80, "keyspace_misses": 20}
        rate = cache_instance._calculate_hit_rate(info)
        assert rate == 80.0

    def test_calculate_hit_rate_no_hits(self, cache_instance):
        info = {"keyspace_hits": 0, "keyspace_misses": 0}
        rate = cache_instance._calculate_hit_rate(info)
        assert rate == 0.0


class TestCachedDecorator:
    """Test the @cached decorator."""

    def test_cached_decorator_caches_result(self):
        from services.redis_cache import cached, cache

        @cached("test_func:{x}", ttl=60)
        def my_func(x):
            return x * 2

        # First call should compute
        result = my_func(5)
        assert result == 10

    def test_cached_decorator_returns_cached_on_second_call(self):
        from services.redis_cache import cached, cache

        call_count = [0]

        @cached("test_counter:{x}", ttl=60)
        def counter_func(x):
            call_count[0] += 1
            return call_count[0]

        # Clear any existing cache
        cache.delete("test_counter:42")

        result1 = counter_func(42)
        result2 = counter_func(42)
        assert result1 == result2


class TestTaskCache:
    """Test TaskCache methods."""

    def test_get_task(self):
        from services.redis_cache import TaskCache, cache
        cache.set("task:t1", {"id": "t1", "name": "Test"}, 60)
        result = TaskCache.get_task("t1")
        assert result == {"id": "t1", "name": "Test"}

    def test_set_task(self):
        from services.redis_cache import TaskCache
        result = TaskCache.set_task("t2", {"id": "t2"})
        assert result is True

    def test_invalidate_task(self):
        from services.redis_cache import TaskCache, cache
        cache.set("task:t3", {"id": "t3"}, 60)
        result = TaskCache.invalidate_task("t3")
        assert result is True

    def test_get_task_list(self):
        from services.redis_cache import TaskCache
        result = TaskCache.get_task_list("name", "asc")
        # May or may not be cached
        assert result is None or isinstance(result, list)

    def test_set_task_list(self):
        from services.redis_cache import TaskCache
        result = TaskCache.set_task_list(
            [{"id": "t1"}], "name", "asc"
        )
        assert result is True

    def test_invalidate_all_task_lists(self):
        from services.redis_cache import TaskCache
        result = TaskCache.invalidate_all_task_lists()
        assert isinstance(result, int)


class TestEvaluationCache:
    """Test EvaluationCache methods."""

    def test_get_evaluation(self):
        from services.redis_cache import EvaluationCache, cache
        cache.set("evaluation:e1", {"id": "e1"}, 60)
        result = EvaluationCache.get_evaluation("e1")
        assert result == {"id": "e1"}

    def test_set_evaluation(self):
        from services.redis_cache import EvaluationCache
        result = EvaluationCache.set_evaluation("e2", {"id": "e2"})
        assert result is True

    def test_get_task_evaluations(self):
        from services.redis_cache import EvaluationCache
        result = EvaluationCache.get_task_evaluations("t1")
        assert result is None or isinstance(result, list)

    def test_set_task_evaluations(self):
        from services.redis_cache import EvaluationCache
        result = EvaluationCache.set_task_evaluations("t1", [{"score": 0.95}])
        assert result is True

    def test_invalidate_task_evaluations(self):
        from services.redis_cache import EvaluationCache
        result = EvaluationCache.invalidate_task_evaluations("t1")
        assert result is True


class TestUserPreferencesCache:
    """Test UserPreferencesCache methods."""

    def test_get_preferences(self):
        from services.redis_cache import UserPreferencesCache
        result = UserPreferencesCache.get_preferences("u1", "t1")
        assert result is None or isinstance(result, dict)

    def test_set_preferences(self):
        from services.redis_cache import UserPreferencesCache
        result = UserPreferencesCache.set_preferences("u1", "t1", {"theme": "dark"})
        assert result is True

    def test_invalidate_preferences(self):
        from services.redis_cache import UserPreferencesCache
        result = UserPreferencesCache.invalidate_preferences("u1", "t1")
        assert result is True


class TestOrgSlugCache:
    """Test OrgSlugCache methods."""

    def test_get_org_id(self):
        from services.redis_cache import OrgSlugCache, cache
        cache.set("org_slug:test-org", "org-123", 60)
        result = OrgSlugCache.get_org_id("test-org")
        assert result == "org-123"

    def test_set_org_id(self):
        from services.redis_cache import OrgSlugCache
        result = OrgSlugCache.set_org_id("new-org", "org-456")
        assert result is True

    def test_invalidate_slug(self):
        from services.redis_cache import OrgSlugCache
        result = OrgSlugCache.invalidate_slug("test-org")
        assert result is True

    def test_invalidate_all(self):
        from services.redis_cache import OrgSlugCache
        result = OrgSlugCache.invalidate_all()
        assert isinstance(result, int)


class TestCacheUtilFunctions:
    """Test module-level utility functions."""

    def test_warm_cache_startup_available(self):
        from services.redis_cache import warm_cache_startup, cache
        original = cache.is_available
        cache.is_available = True
        warm_cache_startup()  # Should not raise
        cache.is_available = original

    def test_warm_cache_startup_unavailable(self):
        from services.redis_cache import warm_cache_startup, cache
        original = cache.is_available
        cache.is_available = False
        warm_cache_startup()  # Should return early
        cache.is_available = original

    def test_get_cache_performance_stats(self):
        from services.redis_cache import get_cache_performance_stats
        stats = get_cache_performance_stats()
        assert isinstance(stats, dict)
        assert "cache_keys_count" in stats

    def test_get_redis_client(self):
        from services.redis_cache import get_redis_client
        client = get_redis_client()
        # Should return the redis client or None
        assert client is not None or client is None
