"""Brute-force limits for the public auth routes.

Two kinds of buckets, both in Redis:

* per client IP (rightmost ``X-Forwarded-For`` hop, see
  ``services.rate_limiter.client_ip_from_forwarded``): fixed windows that count
  every request. They are a coarse flood guard, not the guessing defence: a
  campus NAT puts a whole lecture hall behind one address, and until it is
  confirmed that Traefik sees real client addresses behind the K3s service
  load balancer, every visitor may even share one. So the defaults are
  generous and each one can be changed per deployment through an
  ``AUTH_IP_LIMIT_<ROUTE>`` environment variable (requests per window, see
  ``IP_LIMITS``), read on every request. When the resolved address is
  loopback, link-local or private (RFC 1918, ``fc00::/7``), it is the address
  of our own infrastructure rather than the client (prod Traefik runs behind
  the K3s service load balancer with ``externalTrafficPolicy: Cluster``, which
  rewrites the source address), so the per-IP buckets skip the request
  entirely: one shared bucket for every visitor would turn the limit into a
  platform-wide outage. The per-account buckets still apply.
* per account, keyed by a hash of the submitted login or email, lowercased:
  login counts only FAILED attempts, the mail-sending routes count every
  request.

Login uses a throttle, not a lockout. Once a login has
``LOGIN_FREE_FAILURES`` failed attempts inside the sliding
``LOGIN_FAILURE_WINDOW_SECONDS`` window, every further attempt within
``LOGIN_COOLDOWN_SECONDS`` of the last failure answers 429 without checking
the password; after the cooldown one attempt is checked again, and a correct
password clears the counter. Attempts refused during the cooldown do not
extend it. This bounds online guessing to about one try per minute per
account, while a burst of wrong passwords (from a classmate in the same exam
room, say) can no longer keep the owner out for a quarter of an hour: the
owner waits at most a minute and then gets in with the right password. A
lockout would have turned every known username into a denial-of-service
lever at exam start.

Every bucket here fails CLOSED: when Redis is unreachable the route answers
503 ``rate_limiter_unavailable`` instead of letting unlimited guesses through.
Redis is already a hard dependency (``/health`` returns 503 without it).

A limited request gets 429 with a ``Retry-After`` header and
``detail={"code": "rate_limited", "retry_after": <seconds>}``.

Every function here is synchronous and blocks on Redis: call it directly from
a sync (``def``) handler, which FastAPI already runs in its threadpool, and
through ``await asyncio.to_thread(...)`` from an ``async def`` handler.

Like the rest of the limiter, the buckets are skipped when ``TESTING=true``
so the suites can log in as often as they like; the unit tests switch the
bypass off.
"""

import hashlib
import ipaddress
import logging
import os
import time
import uuid
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from services.rate_limiter import RateLimiterUnavailable, get_client_ip, rate_limiter

logger = logging.getLogger(__name__)

#: (max requests, window seconds)
Limit = Tuple[int, int]

# Bucket names (part of the Redis key).
LOGIN = "auth_login"
PASSWORD_RESET_MAIL = "auth_reset_mail"
VERIFICATION_MAIL = "auth_verify_mail"
PASSWORD_RESET_TOKEN = "auth_reset_token"
ACCOUNT_ACTIVATION = "auth_activate"
SIGNUP = "auth_signup"

#: Per-IP limits: bucket -> (environment variable, default max, window seconds).
IP_LIMITS: Dict[str, Tuple[str, int, int]] = {
    LOGIN: ("AUTH_IP_LIMIT_LOGIN", 1000, 15 * 60),
    PASSWORD_RESET_MAIL: ("AUTH_IP_LIMIT_RESET_MAIL", 60, 60 * 60),
    VERIFICATION_MAIL: ("AUTH_IP_LIMIT_VERIFY_MAIL", 60, 60 * 60),
    PASSWORD_RESET_TOKEN: ("AUTH_IP_LIMIT_RESET_PASSWORD", 40, 60 * 60),
    ACCOUNT_ACTIVATION: ("AUTH_IP_LIMIT_ACTIVATE", 40, 60 * 60),
    SIGNUP: ("AUTH_IP_LIMIT_SIGNUP", 40, 60 * 60),
}

LOGIN_FREE_FAILURES = 10
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_COOLDOWN_SECONDS = 60

MAIL_ACCOUNT_LIMIT: Limit = (3, 60 * 60)

#: Retry-After sent with a fail-closed 503.
UNAVAILABLE_RETRY_AFTER = 30


def _bypassed() -> bool:
    return os.environ.get("TESTING") == "true"


#: Addresses that name our own infrastructure, never a real client.
_INFRA_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "::1/128",
        "169.254.0.0/16",
        "fe80::/10",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)

_unknown_client_logged = False


def client_ip_is_unknown(ip: Optional[str]) -> bool:
    """True when ``ip`` cannot be a client's own address: missing, loopback,
    link-local or private. An unparsable value counts as known (it still
    keys a bucket of its own)."""
    if not ip:
        return True
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr in net for net in _INFRA_NETWORKS)


def _log_unknown_client_once(ip: Optional[str]) -> None:
    global _unknown_client_logged
    if _unknown_client_logged:
        return
    _unknown_client_logged = True
    logger.debug(
        f"Auth per-IP limits skipped: the resolved client address {ip!r} is "
        "loopback, link-local or private, so the real client address is not "
        "known (load balancer SNAT or missing X-Forwarded-For). Per-account "
        "limits still apply. Logged once per process."
    )


def ip_limit(bucket: str) -> Limit:
    """The per-IP limit of a bucket: its ``AUTH_IP_LIMIT_*`` value when that
    is a positive integer, the default otherwise."""
    env_name, default, window = IP_LIMITS[bucket]
    raw = os.environ.get(env_name)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value, window
        except ValueError:
            pass
        logger.warning(f"Ignoring {env_name}={raw!r}: not a positive integer")
    return default, window


def account_key(login: Optional[str]) -> str:
    """Bucket id for a submitted login or email. Hashed so Redis key names
    carry no addresses; lowercased so ``A@x.de`` and ``a@x.de`` share it."""
    normalized = (login or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def rate_limited(retry_after: int) -> HTTPException:
    retry_after = max(1, int(retry_after))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "rate_limited", "retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def limiter_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "rate_limiter_unavailable"},
        headers={"Retry-After": str(UNAVAILABLE_RETRY_AFTER)},
    )


def _unavailable(bucket: str, error: Exception) -> HTTPException:
    logger.error(f"Auth rate limiter unavailable on {bucket}, refusing: {error}")
    return limiter_unavailable()


def _hit(request: Optional[Request], client_id: str, bucket: str, limit: Limit) -> None:
    try:
        error = rate_limiter.check_rate_limit_sync(
            request,
            bucket,
            {"window": limit},
            client_id=client_id,
            fail_closed=True,
        )
    except RateLimiterUnavailable as e:
        raise _unavailable(bucket, e)
    if error:
        raise rate_limited(error["retry_after"])


def enforce_ip_limit(
    request: Optional[Request], bucket: str, limit: Optional[Limit] = None
) -> None:
    """Count one request against the caller's IP bucket; 429 when full.

    ``limit`` defaults to the bucket's configured :func:`ip_limit`. Without a
    request (handlers called directly), or when the client address is not
    known (:func:`client_ip_is_unknown`), the request is not counted.
    """
    if _bypassed() or request is None:
        return
    ip = get_client_ip(request)
    if client_ip_is_unknown(ip):
        # Our own infrastructure's address: counting it would put every
        # visitor into one bucket. No count, no limit.
        _log_unknown_client_once(ip)
        return
    _hit(request, f"ip:{ip}", bucket, limit or ip_limit(bucket))


def enforce_account_limit(
    request: Optional[Request], login: Optional[str], bucket: str, limit: Limit
) -> None:
    """Count one request against the submitted account's bucket; 429 when full."""
    if _bypassed():
        return
    _hit(request, f"acct:{account_key(login)}", bucket, limit)


# Login throttle -------------------------------------------------------------


def _failures_key(account: str) -> str:
    """Sorted set of failure timestamps (the sliding window)."""
    return f"authfail:{LOGIN}:{account}"


def _cooldown_key(account: str) -> str:
    return f"authcool:{LOGIN}:{account}"


def _redis():
    try:
        return rate_limiter.require_redis()
    except RateLimiterUnavailable as e:
        raise _unavailable(LOGIN, e)


def check_login_throttle(login: Optional[str]) -> None:
    """429 while the login is in its cooldown. Counts nothing and runs before
    the password check, so a throttled attempt gives no password oracle."""
    if _bypassed():
        return
    client = _redis()
    try:
        ttl = client.ttl(_cooldown_key(account_key(login)))
    except Exception as e:
        raise _unavailable(LOGIN, e)
    if ttl is None or ttl == -2:
        return
    # -1: the key lost its expiry somehow; treat it as a fresh cooldown.
    raise rate_limited(ttl if ttl > 0 else LOGIN_COOLDOWN_SECONDS)


def record_login_failure(login: Optional[str]) -> int:
    """Count a failed password check in the sliding window and start the
    cooldown once the window holds ``LOGIN_FREE_FAILURES`` or more.
    Returns the number of failures in the window."""
    if _bypassed():
        return 0
    client = _redis()
    account = account_key(login)
    failures_key = _failures_key(account)

    def _count() -> int:
        now = time.time()
        pipe = client.pipeline()
        pipe.zremrangebyscore(failures_key, 0, now - LOGIN_FAILURE_WINDOW_SECONDS)
        pipe.zadd(failures_key, {f"{now:.6f}:{uuid.uuid4().hex[:8]}": now})
        pipe.zcard(failures_key)
        pipe.expire(failures_key, LOGIN_FAILURE_WINDOW_SECONDS)
        return int(pipe.execute()[2])

    try:
        count = _count()
        if count >= LOGIN_FREE_FAILURES:
            client.set(_cooldown_key(account), 1, ex=LOGIN_COOLDOWN_SECONDS)
            logger.warning(
                f"Login throttled for {LOGIN_COOLDOWN_SECONDS}s after {count} failed "
                f"attempts in {LOGIN_FAILURE_WINDOW_SECONDS}s (account bucket {account[:8]})"
            )
        return count
    except Exception as e:
        raise _unavailable(LOGIN, e)


def reset_login_failures(login: Optional[str]) -> None:
    """A correct password clears the failure window and any cooldown. Best
    effort: the throttle check already passed, so a Redis error only logs."""
    if _bypassed():
        return
    try:
        client = rate_limiter.require_redis()
        account = account_key(login)
        client.delete(_failures_key(account), _cooldown_key(account))
    except Exception as e:
        logger.warning(f"Could not reset login failures: {e}")
