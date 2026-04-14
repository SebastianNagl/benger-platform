"""
Simplified Feature Flag Service

Only superadmins can control feature flags globally for all users and organizations.
No user or organization-specific overrides.
"""

import json
import logging
import os
from typing import Optional

import redis
from sqlalchemy.orm import Session

from models import FeatureFlag, User
from redis_cache import get_redis_client

logger = logging.getLogger(__name__)

# Environment detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Cache configuration
CACHE_PREFIX = "feature_flag"
CACHE_TTL = 300  # 5 minutes


class FeatureFlagService:
    """Simplified service for managing and checking feature flags"""

    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None):
        self.db = db
        self.redis_client = redis_client or get_redis_client()

    def _get_cache_key(self, flag_name: str) -> str:
        """Generate cache key for feature flag lookup"""
        return f"{CACHE_PREFIX}:{flag_name}"

    def _get_feature_flag_from_db(self, flag_name: str) -> Optional[FeatureFlag]:
        """Get feature flag from database"""
        return self.db.query(FeatureFlag).filter(FeatureFlag.name == flag_name).first()

    def is_enabled(
        self,
        flag_name: str,
        user: Optional[User] = None,
        organization_id: Optional[str] = None,  # Kept for API compatibility but ignored
    ) -> bool:
        """
        Check if feature flag is enabled globally.

        Only checks the global flag settings - no user or org overrides.
        Superadmins control all flags globally.
        """
        try:
            # Generate cache key
            cache_key = self._get_cache_key(flag_name)

            # Try cache first
            if self.redis_client:
                try:
                    cached_result = self.redis_client.get(cache_key)
                    if cached_result is not None:
                        return json.loads(cached_result)
                except Exception as e:
                    logger.warning(f"Redis cache read failed: {e}")

            # Get feature flag from database
            flag = self._get_feature_flag_from_db(flag_name)

            if not flag:
                # Flag doesn't exist - default to disabled
                result = False
            else:
                # Simple binary check - flag is either enabled or disabled globally
                result = flag.is_enabled

            # Cache the result
            if self.redis_client:
                try:
                    self.redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
                except Exception as e:
                    logger.warning(f"Redis cache write failed: {e}")

            return result

        except Exception as e:
            logger.error(f"Error checking feature flag {flag_name}: {e}")
            # Default to disabled on error
            return False

    def get_feature_flags(self) -> dict:
        """
        Get all feature flags as a simple enabled/disabled mapping.

        Feature flags are global and apply to all users the same way.
        """
        try:
            flags = self.db.query(FeatureFlag).all()
            result = {}

            for flag in flags:
                # Simple binary check - flag is either enabled or disabled globally
                result[flag.name] = flag.is_enabled

            return result

        except Exception as e:
            logger.error(f"Error getting feature flags: {e}")
            return {}

    def get_all_flags(self, user: Optional[User] = None) -> dict:
        """
        Get all feature flags and their states.

        Only returns global flag states - no user or org overrides.
        """
        try:
            flags = self.db.query(FeatureFlag).all()
            result = {}

            for flag in flags:
                result[flag.name] = {
                    "enabled": flag.is_enabled,
                    "description": flag.description,
                }

            return result

        except Exception as e:
            logger.error(f"Error getting all feature flags: {e}")
            return {}

    def update_flag(self, flag_id: str, updates: dict) -> FeatureFlag:
        """
        Update a feature flag.

        Args:
            flag_id: UUID of the feature flag to update
            updates: Dictionary of fields to update (description, is_enabled, etc.)

        Returns:
            Updated FeatureFlag object

        Raises:
            ValueError: If flag not found
        """
        try:
            # Get the flag by ID
            flag = self.db.query(FeatureFlag).filter(FeatureFlag.id == flag_id).first()

            if not flag:
                raise ValueError(f"Feature flag with ID {flag_id} not found")

            # Update the flag fields from the updates dict
            for field, value in updates.items():
                if hasattr(flag, field):
                    setattr(flag, field, value)

            self.db.commit()

            # Invalidate cache for this flag
            self.invalidate_cache(flag.name)

            logger.info(f"Updated feature flag {flag.name}: {updates}")
            return flag

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating feature flag {flag_id}: {e}")
            raise

    def invalidate_cache(self, flag_name: Optional[str] = None):
        """
        Invalidate cache for feature flags.

        If flag_name is provided, only that flag's cache is cleared.
        Otherwise, all feature flag caches are cleared.
        """
        if not self.redis_client:
            return

        try:
            if flag_name:
                # Clear specific flag cache
                cache_key = self._get_cache_key(flag_name)
                self.redis_client.delete(cache_key)
            else:
                # Clear all feature flag caches
                pattern = f"{CACHE_PREFIX}:*"
                for key in self.redis_client.scan_iter(match=pattern):
                    self.redis_client.delete(key)

        except Exception as e:
            logger.error(f"Error invalidating feature flag cache: {e}")
