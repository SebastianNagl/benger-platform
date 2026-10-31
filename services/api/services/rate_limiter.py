"""
Rate limiting middleware for BenGER API
Provides configurable rate limiting for different endpoints and user types
"""

import asyncio
import logging
import math
import time
from functools import wraps
from typing import Dict, Optional, Tuple

import redis
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from models import User

logger = logging.getLogger(__name__)

#: Memory-fallback size above which expired entries are swept.
_MEMORY_PRUNE_THRESHOLD = 10000


class RateLimiterUnavailable(Exception):
    """Redis is unreachable and the caller asked to fail closed."""


def _trusted_proxy_hops() -> int:
    """``TRUSTED_PROXY_HOPS``: how many proxies sit in front of the one that
    talks to the API (default 0: Traefik is the only one). Read per call so
    tests and a redeploy can change it without an import-time freeze."""
    import os

    try:
        return max(0, int(os.environ.get("TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        return 0


def client_ip_from_forwarded(forwarded_for: Optional[str], peer: Optional[str]) -> Optional[str]:
    """The client address from an ``X-Forwarded-For`` value and the socket peer.

    Each proxy APPENDS the address it received the connection from, so only
    the right end of the list is written by infrastructure we run. The left
    end is whatever the client sent in its own header: taking the leftmost
    entry (as this module did before) lets any caller pick its own bucket
    and walk around every per-IP limit. We therefore take the rightmost
    entry, skipping ``TRUSTED_PROXY_HOPS`` further proxies in front of
    Traefik (a CDN or load balancer adds one entry each). When the header is
    absent or shorter than the configured hops it was not written by our
    proxies, so the socket peer is used instead.
    """
    if isinstance(forwarded_for, str) and forwarded_for:
        entries = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        index = len(entries) - 1 - _trusted_proxy_hops()
        if entries and index >= 0:
            return entries[index]
    return peer


def get_client_ip(request: Request) -> Optional[str]:
    """Client IP of a request, see :func:`client_ip_from_forwarded`."""
    peer = request.client.host if getattr(request, "client", None) else None
    return client_ip_from_forwarded(request.headers.get("X-Forwarded-For"), peer)


class RateLimiter:
    def __init__(self, redis_url: str = "redis://redis:6379"):
        """Initialize rate limiter with Redis backend"""
        self._redis_url = redis_url
        self._memory_store: Dict[str, Dict] = {}
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()  # Test connection
            logger.info("Rate limiter connected to Redis")
        except Exception as e:
            logger.warning(f"Redis connection failed, using memory fallback: {e}")
            self.redis_client = None

    def _get_client_id(self, request: Request, user: Optional[User] = None) -> str:
        """Get unique client identifier for rate limiting"""
        if user:
            return f"user:{user.id}"

        # Fallback to IP address (rightmost X-Forwarded-For hop, see
        # client_ip_from_forwarded for why never the leftmost)
        return f"ip:{get_client_ip(request)}"

    def require_redis(self):
        """The Redis client for fail-closed callers.

        A limiter that came up while Redis was down runs on the per-process
        memory fallback forever; fail-closed buckets must not, so they retry
        the connection here and raise :class:`RateLimiterUnavailable` when
        Redis is still unreachable.
        """
        if self.redis_client is not None:
            return self.redis_client
        try:
            client = redis.from_url(
                self._redis_url, decode_responses=True, socket_connect_timeout=2
            )
            client.ping()
        except Exception as e:
            raise RateLimiterUnavailable(str(e)) from e
        self.redis_client = client
        logger.info("Rate limiter reconnected to Redis")
        return client

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

    def _increment_count_sync(self, key: str, ttl: int, fail_closed: bool = False) -> int:
        """Increment request count with TTL (blocking on Redis).

        On a Redis error the count reads as 1 (the request passes) unless
        ``fail_closed`` is set, which raises :class:`RateLimiterUnavailable`.
        """
        try:
            if self.redis_client:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl)
                results = pipe.execute()
                return results[0]
            else:
                # Memory fallback
                current_time = time.time()
                if len(self._memory_store) > _MEMORY_PRUNE_THRESHOLD:
                    self._prune_memory(current_time)
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
            if fail_closed:
                raise RateLimiterUnavailable(str(e)) from e
            return 1

    async def _increment_count(self, key: str, ttl: int, fail_closed: bool = False) -> int:
        """Async twin of :meth:`_increment_count_sync` (runs it off the loop)."""
        return await asyncio.to_thread(self._increment_count_sync, key, ttl, fail_closed)

    def _prune_memory(self, now: float) -> None:
        """Drop expired memory-fallback entries (window-indexed keys would
        otherwise accumulate one entry per client and window forever)."""
        expired = [k for k, v in self._memory_store.items() if v.get("expires", 0) < now]
        for k in expired:
            self._memory_store.pop(k, None)

    def check_rate_limit_sync(
        self,
        request: Request,
        endpoint: str,
        # {window: (max_requests, seconds)}
        limits: Dict[str, Tuple[int, int]],
        user: Optional[User] = None,
        client_id: Optional[str] = None,
        state: Optional[Dict] = None,
        fail_closed: bool = False,
    ) -> Optional[Dict]:
        """
        Check if request should be rate limited (blocking on Redis; async
        callers use :meth:`check_rate_limit`, which runs this off the loop)

        Windows are fixed: each window's counter key carries the window's
        index (``int(now // seconds)``), so a counter always resets at the
        window boundary. (Before, the TTL was refreshed on every request, so
        a client that kept calling more often than once per window never saw
        its counter reset.)

        Args:
            request: FastAPI request object
            endpoint: Endpoint identifier (e.g., "tasks", "eval")
            limits: Rate limit configuration
            user: Authenticated user (if any)
            client_id: bucket owner, overriding the user/IP derivation
                (access keys use ``apikey:<id>``)
            state: when given, filled with ``limit``, ``remaining``,
                ``reset`` (epoch seconds) and ``window`` of the tightest
                window, for X-RateLimit-* response headers
            fail_closed: when Redis is unreachable, raise
                :class:`RateLimiterUnavailable` instead of letting the request
                through (and never count on the per-process memory fallback).
                The auth buckets use this; the default stays fail-open.

        Returns:
            None if allowed, error dict if rate limited
        """
        # Skip rate limiting during tests
        import os

        if os.environ.get("TESTING") == "true":
            return None

        if fail_closed:
            self.require_redis()

        client_id = client_id or self._get_client_id(request, user)
        now = time.time()
        tightest: Optional[Dict] = None

        for window_type, (max_requests, window_seconds) in limits.items():
            window_index = int(now // window_seconds)
            reset_at = (window_index + 1) * window_seconds
            key = f"{self._get_key(client_id, endpoint, window_type)}:{window_index}"

            current_count = self._increment_count_sync(
                key, window_seconds, fail_closed=fail_closed
            )
            info = {
                "limit": max_requests,
                "remaining": max(0, max_requests - current_count),
                "reset": int(reset_at),
                "window": window_seconds,
            }
            if tightest is None or info["remaining"] < tightest["remaining"]:
                tightest = info

            if current_count > max_requests:
                logger.warning(
                    f"Rate limit exceeded: {client_id} on {endpoint} ({current_count}/{max_requests})"
                )
                if state is not None:
                    state.update(info)

                # Seconds until this window resets
                retry_after = max(1, int(math.ceil(reset_at - now)))

                return {
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds.",
                    "retry_after": retry_after,
                    "limit": max_requests,
                    "window": window_seconds,
                    "current": current_count,
                    "remaining": 0,
                    "reset": int(reset_at),
                }

        if state is not None and tightest is not None:
            state.update(tightest)
        return None

    async def check_rate_limit(
        self,
        request: Request,
        endpoint: str,
        # {window: (max_requests, seconds)}
        limits: Dict[str, Tuple[int, int]],
        user: Optional[User] = None,
        client_id: Optional[str] = None,
        state: Optional[Dict] = None,
        fail_closed: bool = False,
    ) -> Optional[Dict]:
        """Async twin of :meth:`check_rate_limit_sync`; same arguments and
        result, with the Redis round trips in a worker thread."""
        import os

        if os.environ.get("TESTING") == "true":
            return None
        return await asyncio.to_thread(
            self.check_rate_limit_sync,
            request,
            endpoint,
            limits,
            user,
            client_id,
            state,
            fail_closed,
        )


# Global rate limiter instance
# Use REDIS_URI from environment if available (production), otherwise use default
import os  # noqa: E402

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

    # ``role`` lives on OrganizationMembership, not on the ORM/Pydantic User —
    # use getattr so a role-less user object falls through to base limits
    # instead of AttributeError-500ing this path.
    user_role = getattr(user, "role", None) if user else None
    if user_role in USER_ROLE_MULTIPLIERS:
        multiplier = USER_ROLE_MULTIPLIERS[user_role]

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


# Access keys (/api/v1): per-key buckets, per minute and per day.

API_KEY_RATE_ENDPOINT = "apikey"


def api_key_limits(principal) -> Dict[str, Tuple[int, int]]:
    """The key's own limits, falling back to API_KEY_DEFAULT_RPM/RPD."""
    from app.core.config import settings

    rpm, rpd = getattr(principal, "rate_limit", (None, None)) or (None, None)
    return {
        "minute": (int(rpm or settings.api_key_default_rpm), 60),
        "day": (int(rpd or settings.api_key_default_rpd), 86400),
    }


async def enforce_key_rate_limit(request: Request, principal) -> Optional[Dict]:
    """Count one request against the key's buckets (``apikey:<id>``).

    Stores ``{"limit", "remaining", "reset", "window"}`` on
    ``request.state.rate_limit`` (the usage middleware turns it into
    X-RateLimit-* headers) and raises 429 with ``Retry-After`` when a
    bucket is exhausted. Sessions are not limited here.
    """
    if principal is None or not getattr(principal, "is_api_key", False):
        return None
    info: Dict = {}
    error = await rate_limiter.check_rate_limit(
        request,
        API_KEY_RATE_ENDPOINT,
        api_key_limits(principal),
        client_id=f"apikey:{principal.api_key_id}",
        state=info,
    )
    if info:
        try:
            request.state.rate_limit = info
        except Exception:  # pragma: no cover - requests without state
            pass
    if error:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": error["message"],
                "retry_after": error["retry_after"],
            },
            headers={
                "Retry-After": str(error["retry_after"]),
                "X-RateLimit-Limit": str(error["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(error["reset"]),
            },
        )
    return info
