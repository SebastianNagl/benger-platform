"""
Comprehensive tests for feature flag service.
Tests feature flag management and caching functionality.
"""

import json
from unittest.mock import Mock, patch

import pytest
import redis
from sqlalchemy.orm import Session

from feature_flag_service import FeatureFlagService
from models import FeatureFlag, User


class TestFeatureFlagService:
    """Test feature flag service functionality"""

    @pytest.fixture
    def test_db(self):
        """Create mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client"""
        return Mock(spec=redis.Redis)

    @pytest.fixture
    def mock_user(self):
        """Create mock user for testing"""
        user = Mock(spec=User)
        user.id = "test-user-123"
        user.username = "testuser"
        user.email = "test@example.com"
        user.is_superadmin = False
        return user

    @pytest.fixture
    def mock_feature_flag(self):
        """Create mock feature flag for testing"""
        flag = Mock(spec=FeatureFlag)
        flag.id = "flag-123"
        flag.name = "test_feature"
        flag.description = "Test feature flag"
        flag.is_enabled = True
        return flag

    @pytest.fixture
    def service(self, test_db, mock_redis):
        """Create FeatureFlagService instance"""
        return FeatureFlagService(test_db, mock_redis)

    def test_init_with_db_and_redis(self, test_db, mock_redis):
        """Test service initialization with database and Redis"""
        service = FeatureFlagService(test_db, mock_redis)
        assert service.db == test_db
        assert service.redis_client == mock_redis

    def test_init_with_db_only(self, test_db):
        """Test service initialization with database only"""
        with patch('services.feature_flag_service.get_redis_client') as mock_get_redis:
            mock_redis_client = Mock()
            mock_get_redis.return_value = mock_redis_client

            service = FeatureFlagService(test_db)
            assert service.db == test_db
            assert service.redis_client == mock_redis_client

    def test_get_cache_key(self, service):
        """Test cache key generation"""
        key = service._get_cache_key("test_feature")
        assert key == "feature_flag:test_feature"

    def test_get_feature_flag_from_db_success(self, service, mock_feature_flag):
        """Test getting feature flag from database successfully"""
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag

        result = service._get_feature_flag_from_db("test_feature")

        assert result == mock_feature_flag
        service.db.query.assert_called_once_with(FeatureFlag)

    def test_get_feature_flag_from_db_not_found(self, service):
        """Test getting feature flag from database when not found"""
        service.db.query.return_value.filter.return_value.first.return_value = None

        result = service._get_feature_flag_from_db("nonexistent_feature")

        assert result is None

    def test_is_enabled_flag_exists_and_enabled(self, service, mock_feature_flag):
        """Test is_enabled when flag exists and is enabled"""
        # Mock Redis cache miss
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature")

        assert result is True
        service.redis_client.setex.assert_called_once()

    def test_is_enabled_flag_exists_and_disabled(self, service, mock_feature_flag):
        """Test is_enabled when flag exists and is disabled"""
        # Mock Redis cache miss
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = False

        result = service.is_enabled("test_feature")

        assert result is False

    def test_is_enabled_flag_not_exists(self, service):
        """Test is_enabled when flag does not exist"""
        # Mock Redis cache miss
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = None

        result = service.is_enabled("nonexistent_feature")

        assert result is False

    def test_is_enabled_cached_result(self, service):
        """Test is_enabled with cached result"""
        # Mock Redis cache hit
        service.redis_client.get.return_value = json.dumps(True)

        result = service.is_enabled("test_feature")

        assert result is True
        # Should not query database
        service.db.query.assert_not_called()

    def test_is_enabled_with_user_parameter(self, service, mock_user, mock_feature_flag):
        """Test is_enabled with user parameter (should be ignored)"""
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature", user=mock_user)

        assert result is True

    def test_is_enabled_with_organization_parameter(self, service, mock_feature_flag):
        """Test is_enabled with organization parameter (should be ignored)"""
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature", organization_id="org-123")

        assert result is True

    def test_is_enabled_redis_read_error(self, service, mock_feature_flag):
        """Test is_enabled when Redis read fails"""
        service.redis_client.get.side_effect = Exception("Redis error")
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature")

        assert result is True

    def test_is_enabled_redis_write_error(self, service, mock_feature_flag):
        """Test is_enabled when Redis write fails"""
        service.redis_client.get.return_value = None
        service.redis_client.setex.side_effect = Exception("Redis write error")
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature")

        assert result is True

    def test_is_enabled_database_error(self, service):
        """Test is_enabled when database query fails"""
        service.redis_client.get.return_value = None
        service.db.query.side_effect = Exception("Database error")

        result = service.is_enabled("test_feature")

        assert result is False  # Default to disabled on error

    def test_is_enabled_no_redis_client(self, test_db, mock_feature_flag):
        """Test is_enabled when no Redis client available"""
        service = FeatureFlagService(test_db, redis_client=None)
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        result = service.is_enabled("test_feature")

        assert result is True

    def test_get_feature_flags_success(self, service):
        """Test get_feature_flags success"""
        # Create mock flags
        flag1 = Mock(spec=FeatureFlag)
        flag1.name = "feature1"
        flag1.is_enabled = True

        flag2 = Mock(spec=FeatureFlag)
        flag2.name = "feature2"
        flag2.is_enabled = False

        service.db.query.return_value.all.return_value = [flag1, flag2]

        result = service.get_feature_flags()

        assert result == {"feature1": True, "feature2": False}

    def test_get_feature_flags_empty(self, service):
        """Test get_feature_flags with no flags"""
        service.db.query.return_value.all.return_value = []

        result = service.get_feature_flags()

        assert result == {}

    def test_get_feature_flags_error(self, service):
        """Test get_feature_flags database error"""
        service.db.query.side_effect = Exception("Database error")

        result = service.get_feature_flags()

        assert result == {}

    def test_get_all_flags_success(self, service):
        """Test get_all_flags success"""
        # Create mock flags
        flag1 = Mock(spec=FeatureFlag)
        flag1.name = "feature1"
        flag1.is_enabled = True
        flag1.description = "Feature 1 description"

        flag2 = Mock(spec=FeatureFlag)
        flag2.name = "feature2"
        flag2.is_enabled = False
        flag2.description = "Feature 2 description"

        service.db.query.return_value.all.return_value = [flag1, flag2]

        result = service.get_all_flags()

        expected = {
            "feature1": {"enabled": True, "description": "Feature 1 description"},
            "feature2": {"enabled": False, "description": "Feature 2 description"},
        }
        assert result == expected

    def test_get_all_flags_with_user_parameter(self, service, mock_user):
        """Test get_all_flags with user parameter (should be ignored)"""
        service.db.query.return_value.all.return_value = []

        result = service.get_all_flags(user=mock_user)

        assert result == {}

    def test_get_all_flags_error(self, service):
        """Test get_all_flags database error"""
        service.db.query.side_effect = Exception("Database error")

        result = service.get_all_flags()

        assert result == {}

    def test_update_flag_success(self, service, mock_feature_flag):
        """Test update_flag success"""
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag

        updates = {"is_enabled": False, "description": "Updated description"}

        with patch.object(service, 'invalidate_cache') as mock_invalidate:
            result = service.update_flag("flag-123", updates)

            assert result == mock_feature_flag
            assert mock_feature_flag.is_enabled == False
            assert mock_feature_flag.description == "Updated description"
            service.db.commit.assert_called_once()
            mock_invalidate.assert_called_once_with(mock_feature_flag.name)

    def test_update_flag_not_found(self, service):
        """Test update_flag when flag not found"""
        service.db.query.return_value.filter.return_value.first.return_value = None

        updates = {"is_enabled": False}

        with pytest.raises(ValueError, match="Feature flag with ID flag-123 not found"):
            service.update_flag("flag-123", updates)

    def test_update_flag_invalid_field(self, service, mock_feature_flag):
        """Test update_flag with invalid field"""
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag

        updates = {"is_enabled": False, "invalid_field": "value"}  # This should be ignored

        with patch.object(service, 'invalidate_cache'):
            result = service.update_flag("flag-123", updates)

            assert result == mock_feature_flag
            assert mock_feature_flag.is_enabled == False
            # invalid_field should not be set
            assert not hasattr(mock_feature_flag, "invalid_field")

    def test_update_flag_database_error(self, service, mock_feature_flag):
        """Test update_flag database error"""
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        service.db.commit.side_effect = Exception("Database error")

        updates = {"is_enabled": False}

        with pytest.raises(Exception, match="Database error"):
            service.update_flag("flag-123", updates)

        service.db.rollback.assert_called_once()

    def test_invalidate_cache_specific_flag(self, service):
        """Test invalidate_cache for specific flag"""
        service.invalidate_cache("test_feature")

        expected_key = "feature_flag:test_feature"
        service.redis_client.delete.assert_called_once_with(expected_key)

    def test_invalidate_cache_all_flags(self, service):
        """Test invalidate_cache for all flags"""
        # Mock scan_iter to return some cache keys
        mock_keys = [b"feature_flag:feature1", b"feature_flag:feature2"]
        service.redis_client.scan_iter.return_value = mock_keys

        service.invalidate_cache()

        service.redis_client.scan_iter.assert_called_once_with(match="feature_flag:*")
        # Should delete each key
        assert service.redis_client.delete.call_count == len(mock_keys)

    def test_invalidate_cache_no_redis(self, test_db):
        """Test invalidate_cache when no Redis client"""
        service = FeatureFlagService(test_db, redis_client=None)

        # Should not raise error
        service.invalidate_cache("test_feature")
        service.invalidate_cache()

    def test_invalidate_cache_redis_error(self, service):
        """Test invalidate_cache when Redis operation fails"""
        service.redis_client.delete.side_effect = Exception("Redis error")

        # Should not raise error, just log
        service.invalidate_cache("test_feature")

    def test_invalidate_cache_scan_error(self, service):
        """Test invalidate_cache when Redis scan fails"""
        service.redis_client.scan_iter.side_effect = Exception("Redis scan error")

        # Should not raise error, just log
        service.invalidate_cache()

    def test_cache_key_format(self, service):
        """Test cache key format consistency"""
        key1 = service._get_cache_key("feature_name")
        key2 = service._get_cache_key("another_feature")

        assert key1.startswith("feature_flag:")
        assert key2.startswith("feature_flag:")
        assert key1 != key2

    def test_json_serialization_in_cache(self, service, mock_feature_flag):
        """Test JSON serialization/deserialization in cache operations"""
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        service.is_enabled("test_feature")

        # Check that setex was called with JSON-serialized value
        service.redis_client.setex.assert_called_once()
        args = service.redis_client.setex.call_args[0]
        assert args[0] == "feature_flag:test_feature"  # key
        assert args[1] == 300  # TTL
        assert args[2] == json.dumps(True)  # serialized value

    def test_concurrent_access_handling(self, service, mock_feature_flag):
        """Test handling of concurrent access scenarios"""
        # Simulate cache being updated between get and set
        service.redis_client.get.return_value = None
        service.db.query.return_value.filter.return_value.first.return_value = mock_feature_flag
        mock_feature_flag.is_enabled = True

        # First call should query DB and cache result
        result1 = service.is_enabled("test_feature")
        assert result1 is True

        # Second call should use cache
        service.redis_client.get.return_value = json.dumps(False)  # Simulate cache update
        result2 = service.is_enabled("test_feature")
        assert result2 is False
