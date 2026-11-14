"""Concurrency limit per custom (BYOM) model endpoint.

A generation run queues one Celery job per cell at once. Against a custom
endpoint that serves only a few requests at a time, every job a worker picks
up sends its request anyway and waits in the provider's queue, and that wait
counts toward the job's Celery time limit: a 581-job run against a server
handling 2 requests at a time lost 9 jobs to ``SoftTimeLimitExceeded``.

So a generation job for a custom model first takes one of the model's slots
(``llm_models.max_concurrent_requests``, default
:data:`DEFAULT_MAX_CONCURRENT_REQUESTS`). When all slots are taken, the job
goes back to the queue for a few seconds instead of waiting while it runs, so
the time limit only ever covers the job's own request.

The slots are a Redis sorted set per model: one member per running job, scored
with the time its lease runs out. A lease outlives the job's hard time limit,
so a worker killed mid-request frees its slot by expiry; the job's own task id
is the member, so a redelivered job takes its old slot back instead of
counting twice. Official catalog models are not limited here. Without Redis
the job runs unlimited, as before (logged).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: Requests a custom model may have in flight when its row sets no limit.
#: Low on purpose: a limit above what the server serves costs failed jobs,
#: one below it only costs speed.
DEFAULT_MAX_CONCURRENT_REQUESTS = 2

#: Seconds a waiting job stays out of the queue, drawn per attempt.
RETRY_DELAY_RANGE = (5.0, 15.0)

#: How long a looked-up limit is reused before the row is read again.
_LIMIT_CACHE_SECONDS = 30.0

_KEY_PREFIX = "benger:endpoint-slots:"

# KEYS[1] = slot set; ARGV = limit, member, lease seconds.
# Drops expired leases, then takes (or renews) the member's slot if it already
# holds one or a slot is free. Returns 1 when the slot is held.
_ACQUIRE_LUA = """
local now = redis.call('TIME')
local now_s = tonumber(now[1]) + tonumber(now[2]) / 1000000
local limit = tonumber(ARGV[1])
local lease = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_s)
if redis.call('ZSCORE', KEYS[1], ARGV[2]) or redis.call('ZCARD', KEYS[1]) < limit then
  redis.call('ZADD', KEYS[1], now_s + lease, ARGV[2])
  redis.call('EXPIRE', KEYS[1], math.ceil(lease) + 60)
  return 1
end
return 0
"""


def is_custom_model_id(model_id: Optional[str]) -> bool:
    return isinstance(model_id, str) and model_id.startswith("custom-")


def slot_key(model_id: str) -> str:
    return f"{_KEY_PREFIX}{model_id}"


@dataclass
class Slot:
    """A held slot; :meth:`release` frees it (idempotent)."""

    client: object
    key: str
    member: str
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            self.client.zrem(self.key, self.member)
        except Exception as e:  # expiry frees it anyway
            logger.warning("endpoint slot release failed for %s: %s", self.key, e)


class EndpointBusy(Exception):
    """Every slot of the model is taken; retry the job after ``retry_in`` s."""

    def __init__(self, model_id: str, limit: int, retry_in: float):
        super().__init__(
            f"custom model {model_id} has {limit} request(s) in flight; "
            f"retrying in {retry_in:.0f}s"
        )
        self.model_id = model_id
        self.limit = limit
        self.retry_in = retry_in


_limit_cache: Dict[str, Tuple[float, int]] = {}


def clamp_limit(value) -> int:
    """The row's limit, or the default for NULL and anything not a positive int."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_MAX_CONCURRENT_REQUESTS
    return value


def model_limit(model_id: str, session_factory: Callable) -> int:
    """``max_concurrent_requests`` of the custom model, cached briefly."""
    now = time.monotonic()
    cached = _limit_cache.get(model_id)
    if cached and now - cached[0] < _LIMIT_CACHE_SECONDS:
        return cached[1]
    from models import LLMModel

    db = session_factory()
    try:
        row = (
            db.query(LLMModel.max_concurrent_requests)
            .filter(LLMModel.id == model_id)
            .first()
        )
    finally:
        db.close()
    limit = clamp_limit(row[0] if row else None)
    _limit_cache[model_id] = (now, limit)
    return limit


def acquire(
    client,
    model_id: str,
    member: str,
    *,
    limit: int,
    lease_seconds: float,
) -> Slot:
    """Take one of ``limit`` slots of ``model_id`` for ``member``.

    Raises :class:`EndpointBusy` when all are taken.
    """
    key = slot_key(model_id)
    held = client.eval(_ACQUIRE_LUA, 1, key, limit, member, lease_seconds)
    if int(held) != 1:
        raise EndpointBusy(model_id, limit, random.uniform(*RETRY_DELAY_RANGE))
    return Slot(client=client, key=key, member=member)


def acquire_for_job(
    model_id: str,
    member: Optional[str],
    *,
    redis_client_factory: Callable,
    session_factory: Callable,
    lease_seconds: float,
) -> Optional[Slot]:
    """The slot a generation job needs before it calls ``model_id``.

    ``None`` when the model is not limited here (an official model) or the
    limit cannot be checked (no Redis, a lookup error); the job then runs
    unlimited. Raises :class:`EndpointBusy` when the job has to wait.
    """
    if not is_custom_model_id(model_id):
        return None
    member = member or f"direct-{random.getrandbits(64):x}"
    try:
        limit = model_limit(model_id, session_factory)
        client = redis_client_factory()
        if client is None:
            raise RuntimeError("no redis client")
        return acquire(
            client, model_id, member, limit=limit, lease_seconds=lease_seconds
        )
    except EndpointBusy:
        raise
    except Exception as e:
        logger.warning(
            "endpoint slot for %s not checked, running without a limit: %s",
            model_id,
            e,
        )
        return None
