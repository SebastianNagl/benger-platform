"""
Rate limiting middleware for BenGER API
Provides configurable rate limiting for different endpoints and user types
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Dict, Optional, Tuple

import redis
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from models import User

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_url: str = "redis://redis:6379"):
        """Initialize rate limiter with Redis backend"""
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()  # Test connection
            logger.info("Rate limiter connected to Redis")
        except Exception as e:
            logger.warning(f"Redis connection failed, using memory fallback: {e}")
            self.redis_client = None
            self._memory_store: Dict[str, Dict] = {}

    def _get_client_id(self, request: Request, user: Optional[User] = None) -> str:
        """Get unique client identifier for rate limiting"""
        if user:
            return f"user:{user.id}"

        # Fallback to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host

        return f"ip:{client_ip}"

    def _get_key(self, client_id: str, endpoint: str, window_type: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ratelimit:{client_id}:{endpoint}:{window_type}"

    async def _get_count(self, key: str) -> int:
        """Get current request count for key"""
        try:
            if self.redis_client:
                count = await asyncio.to_thread(self.redis_client.get, key)
                return int(count) if count else 0
            else:
                # Memory fallback
                return self._memory_store.get(key, {}).get("count", 0)
        except Exception as e:
            logger.error(f"Error getting rate limit count: {e}")
            return 0

    async def _increment_count(self, key: str, ttl: int) -> int:
        """Increment request count with TTL"""
        try:
            if self.redis_client:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl)
                results = await asyncio.to_thread(pipe.execute)
                return results[0]
            else:
                # Memory fallback
                current_time = time.time()
                if key not in self._memory_store:
                    self._memory_store[key] = {
                        "count": 0,
                        "expires": current_time + ttl,
                    }

                entry = self._memory_store[key]
                if current_time > entry["expires"]:
                    entry["count"] = 0
                    entry["expires"] = current_time + ttl

                entry["count"] += 1
                return entry["count"]
        except Exception as e:
            logger.error(f"Error incrementing rate limit count: {e}")
            return 1

    async def check_rate_limit(
        self,
        request: Request,
        endpoint: str,
        # {window: (max_requests, seconds)}
        limits: Dict[str, Tuple[int, int]],
        user: Optional[User] = None,
    ) -> Optional[Dict]:
        """
        Check if request should be rate limited

        Args:
            request: FastAPI request object
            endpoint: Endpoint identifier (e.g., "tasks", "eval")
            limits: Rate limit configuration
            user: Authenticated user (if any)

        Returns:
            None if allowed, error dict if rate limited
        """
        # Skip rate limiting during tests
        import os

        if os.environ.get("TESTING") == "true":
            return None

        client_id = self._get_client_id(request, user)

        for window_type, (max_requests, window_seconds) in limits.items():
            key = self._get_key(client_id, endpoint, window_type)

            current_count = await self._increment_count(key, window_seconds)

            if current_count > max_requests:
                logger.warning(
                    f"Rate limit exceeded: {client_id} on {endpoint} ({current_count}/{max_requests})"
                )

                # Calculate retry after time
                retry_after = window_seconds

                return {
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds.",
                    "retry_after": retry_after,
                    "limit": max_requests,
                    "window": window_seconds,
                    "current": current_count,
                }

        return None


# Global rate limiter instance
# Use REDIS_URI from environment if available (production), otherwise use default
import os

redis_url = os.getenv("REDIS_URI", "redis://redis:6379")
rate_limiter = RateLimiter(redis_url)

# Rate limit configurations for different endpoints
RATE_LIMITS = {
    # Authentication endpoints - more restrictive
    "auth": {
        "minute": (10, 60),  # 10 requests per minute
        "hour": (50, 3600),  # 50 requests per hour
    },
    # General API endpoints
    "api": {
        "minute": (60, 60),  # 60 requests per minute
        "hour": (1000, 3600),  # 1000 requests per hour
    },
    # Task operations - moderate limits
    "tasks": {
        "minute": (30, 60),  # 30 requests per minute
        "hour": (500, 3600),  # 500 requests per hour
    },
    # Evaluation endpoints - more restrictive due to compute cost
    "evaluation": {
        "minute": (5, 60),  # 5 requests per minute
        "hour": (50, 3600),  # 50 requests per hour
    },
    # File uploads - very restrictive
    "upload": {
        "minute": (5, 60),  # 5 uploads per minute
        "hour": (20, 3600),  # 20 uploads per hour
    },
    # Admin operations - restrictive
    "admin": {
        "minute": (20, 60),  # 20 requests per minute
        "hour": (200, 3600),  # 200 requests per hour
    },
}

# Enhanced rate limits for different user roles
USER_ROLE_MULTIPLIERS = {
    "admin": 2.0,  # Admins get 2x the limits
    "contributor": 1.5,  # Contributors get 1.5x the limits
    "annotator": 1.0,  # Annotators get base limits
}


def get_rate_limits_for_user(endpoint: str, user: Optional[User] = None) -> Dict:
    """Get rate limits adjusted for user role"""
    base_limits = RATE_LIMITS.get(endpoint, RATE_LIMITS["api"])

    if user and user.role in USER_ROLE_MULTIPLIERS:
        multiplier = USER_ROLE_MULTIPLIERS[user.role]

        # Apply multiplier to limits
        adjusted_limits = {}
        for window, (max_requests, seconds) in base_limits.items():
            adjusted_limits[window] = (int(max_requests * multiplier), seconds)

        return adjusted_limits

    return base_limits


def rate_limit(endpoint: str):
    """Decorator for rate limiting FastAPI endpoints"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request and user from function arguments
            request = None
            user = None

            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                elif isinstance(arg, User):
                    user = arg

            for value in kwargs.values():
                if isinstance(value, Request):
                    request = value
                elif isinstance(value, User):
                    user = value

            if not request:
                # If no request found, skip rate limiting (shouldn't happen in practice)
                return await func(*args, **kwargs)

            # Get appropriate rate limits
            limits = get_rate_limits_for_user(endpoint, user)

            # Check rate limit
            rate_limit_error = await rate_limiter.check_rate_limit(request, endpoint, limits, user)

            if rate_limit_error:
                raise HTTPException(
                    status_code=429,
                    detail=rate_limit_error,
                    headers={"Retry-After": str(rate_limit_error["retry_after"])},
                )

            # Execute original function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Middleware version for global rate limiting


async def rate_limit_middleware(request: Request, call_next):
    """Global rate limiting middleware"""

    # Skip rate limiting for health checks and static files
    if request.url.path in ["/health", "/docs", "/openapi.json", "/favicon.ico"]:
        return await call_next(request)

    # Apply general API rate limiting
    limits = get_rate_limits_for_user("api")

    rate_limit_error = await rate_limiter.check_rate_limit(request, "api", limits)

    if rate_limit_error:
        return JSONResponse(
            status_code=429,
            content=rate_limit_error,
            headers={"Retry-After": str(rate_limit_error["retry_after"])},
        )

    response = await call_next(request)
    return response
