"""Rate limiting for the BenGER API.

:class:`RateLimiter` keeps its counters in Redis (with a per-process memory
fallback) and offers two kinds of bucket: fixed windows
(:meth:`RateLimiter.check_rate_limit`, per minute/hour/day) and a rolling
window (:meth:`RateLimiter.check_rolling_limit`, the last N seconds). Users
of the fixed windows: the access-key limits below, the login and token
buckets (``services/auth_rate_limit.py``), the per-user ceilings
(``services/usage_limits.py``) and a few route-level buckets.
"""

import asyncio
import logging
import math
import time
import uuid
from typing import Dict, Optional, Tuple

import redis
from fastapi import HTTPException, Request

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

    def check_rolling_limit_sync(
        self, client_id: str, endpoint: str, max_events: int, window_seconds: int
    ) -> Optional[Dict]:
        """Count one event against a rolling window of ``window_seconds``.

        Unlike the fixed windows of :meth:`check_rate_limit_sync`, the window
        always covers the last ``window_seconds`` (a Redis sorted set of event
        times), so a client cannot spend the limit twice around a window
        boundary. A refused event is not recorded, so retrying while blocked
        does not push the block further out. Fails open on Redis errors.

        Returns None if allowed, else an error dict like
        :meth:`check_rate_limit_sync` (``retry_after`` is the time until the
        oldest counted event leaves the window).
        """
        import os

        if os.environ.get("TESTING") == "true":
            return None
        key = self._get_key(client_id, endpoint, "rolling")
        now = time.time()
        try:
            count, oldest = self._record_rolling_event(key, now, max_events, window_seconds)
        except Exception as e:
            logger.error(f"Error checking rolling rate limit: {e}")
            return None
        if count <= max_events:
            return None
        logger.warning(
            f"Rolling limit exceeded: {client_id} on {endpoint} ({max_events}/{window_seconds}s)"
        )
        reset_at = (oldest if oldest is not None else now) + window_seconds
        return {
            "error": "rate_limit_exceeded",
            "message": f"Limit exceeded. Maximum {max_events} per {window_seconds} seconds.",
            "retry_after": max(1, int(math.ceil(reset_at - now))),
            "limit": max_events,
            "window": window_seconds,
            "current": count,
            "remaining": 0,
            "reset": int(math.ceil(reset_at)),
        }

    def _record_rolling_event(
        self, key: str, now: float, max_events: int, window_seconds: int
    ) -> Tuple[int, Optional[float]]:
        """Add an event at ``now`` and return ``(count including it, time of
        the oldest event in the window)``; over ``max_events`` the event is
        taken back out again."""
        cutoff = now - window_seconds
        if self.redis_client:
            member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, "-inf", cutoff)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            pipe.expire(key, int(window_seconds) + 1)
            _, _, count, oldest, _ = pipe.execute()
            if count > max_events:
                self.redis_client.zrem(key, member)
            return int(count), (float(oldest[0][1]) if oldest else None)
        if len(self._memory_store) > _MEMORY_PRUNE_THRESHOLD:
            self._prune_memory(now)
        entry = self._memory_store.setdefault(key, {"events": [], "expires": 0.0})
        events = [t for t in entry.get("events", []) if t > cutoff]
        events.append(now)
        count = len(events)
        if count > max_events:
            events.pop()
        entry["events"] = events
        entry["expires"] = now + window_seconds
        return count, (events[0] if events else None)

    async def check_rolling_limit(
        self, client_id: str, endpoint: str, max_events: int, window_seconds: int
    ) -> Optional[Dict]:
        """Async twin of :meth:`check_rolling_limit_sync`."""
        import os

        if os.environ.get("TESTING") == "true":
            return None
        return await asyncio.to_thread(
            self.check_rolling_limit_sync, client_id, endpoint, max_events, window_seconds
        )


# Global rate limiter instance
# Use REDIS_URI from environment if available (production), otherwise use default
import os  # noqa: E402

redis_url = os.getenv("REDIS_URI", "redis://redis:6379")
rate_limiter = RateLimiter(redis_url)

# Access keys (/api/v1): per-key buckets, per minute and per day.

API_KEY_RATE_ENDPOINT = "apikey"


def api_key_limits(principal) -> Dict[str, Tuple[int, int]]:
    """The key's own limits, falling back to API_KEY_DEFAULT_RPM/RPD and
    clamped to API_KEY_MAX_RPM/RPD (a key stored before the maximum existed,
    or above a lowered one, never exceeds the deployment ceiling)."""
    from app.core.config import settings

    rpm, rpd = getattr(principal, "rate_limit", (None, None)) or (None, None)
    return {
        "minute": (
            min(int(rpm or settings.api_key_default_rpm), int(settings.api_key_max_rpm)),
            60,
        ),
        "day": (
            min(int(rpd or settings.api_key_default_rpd), int(settings.api_key_max_rpd)),
            86400,
        ),
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
        from services.limit_metrics import record_rate_limited

        record_rate_limited("api_key")
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
