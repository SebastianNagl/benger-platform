"""Bounded retry for migrations that lose the race for a table lock.

Migrations that ALTER hot tables set ``SET LOCAL lock_timeout = '5s'`` so a
blocked ALTER fails fast instead of queueing every request behind it. Before
this helper one such timeout failed the whole ``alembic upgrade`` (the Helm
migration Job and the API lifespan both run it), which sank the deploy even
when the blocking transaction ended a few seconds later (2026-10-15: idle
worker transactions held AccessShareLock on ``users``).

``run_with_lock_retry`` re-runs the upgrade a few times with a pause in
between. That is safe because each attempt runs in its own transaction: a
lock timeout rolls the attempt back, and the next attempt starts from the
revision recorded in ``alembic_version``. Only lock-timeout and deadlock
errors are retried; anything else propagates on the first failure.

Plain module (no alembic import) so it can be unit tested without an alembic
context. Used by ``alembic/env.py``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, List, Optional, TypeVar

logger = logging.getLogger("alembic.lock_retry")

T = TypeVar("T")

# 55P03 lock_not_available (lock_timeout fired), 40P01 deadlock_detected.
RETRYABLE_PGCODES = frozenset({"55P03", "40P01"})

DEFAULT_ATTEMPTS = 6
DEFAULT_DELAY_S = 20.0

# Sessions that hold a relation lock while idle in a transaction, or whose
# transaction is older than 30 s. The query runs on a fresh connection after
# our own attempt has rolled back, so it lists who held the table at that
# moment (pg_blocking_pids needs a still-waiting backend, which no longer
# exists by then).
LOCK_HOLDERS_SQL = """
SELECT a.pid,
       COALESCE(NULLIF(a.application_name, ''), '<blank>') AS application_name,
       a.state,
       EXTRACT(EPOCH FROM (now() - a.xact_start))::int AS xact_age_s,
       string_agg(DISTINCT c.relname || ':' || l.mode, ', ') AS locks
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
LEFT JOIN pg_class c ON c.oid = l.relation
WHERE l.granted
  AND l.locktype = 'relation'
  AND a.pid <> pg_backend_pid()
  AND a.datname = current_database()
  AND (a.state LIKE 'idle in transaction%'
       OR a.xact_start < now() - interval '30 seconds')
GROUP BY a.pid, a.application_name, a.state, a.xact_start
ORDER BY a.xact_start
LIMIT 20
"""


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, default)), 1)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(float(os.getenv(name, default)), 0.0)
    except (TypeError, ValueError):
        return default


def retry_settings() -> tuple[int, float]:
    """``(attempts, delay_s)``, overridable via the environment."""
    return (
        _env_int("MIGRATION_LOCK_RETRY_ATTEMPTS", DEFAULT_ATTEMPTS),
        _env_float("MIGRATION_LOCK_RETRY_DELAY_S", DEFAULT_DELAY_S),
    )


def pgcode_of(exc: BaseException) -> Optional[str]:
    """The SQLSTATE of a DBAPI error, also when wrapped by SQLAlchemy."""
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("pgcode", "sqlstate"):
            code = getattr(current, attr, None)
            if isinstance(code, str) and code:
                return code
        current = getattr(current, "orig", None) or current.__cause__
    return None


def is_retryable_lock_error(exc: BaseException) -> bool:
    return pgcode_of(exc) in RETRYABLE_PGCODES


def describe_lock_holders(engine) -> List[str]:
    """Readable lines for the sessions that likely blocked the migration.

    Best effort: any error yields an empty list, the retry must not fail on
    its own diagnostics.
    """
    if engine is None or engine.dialect.name != "postgresql":
        return []
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            rows = conn.execute(text(LOCK_HOLDERS_SQL)).fetchall()
    except Exception as diag_err:  # pragma: no cover - diagnostics only
        logger.debug("lock holder query failed: %s", diag_err)
        return []
    return [
        f"pid={r.pid} app={r.application_name} state={r.state} "
        f"xact_age={r.xact_age_s}s locks=[{r.locks}]"
        for r in rows
    ]


def run_with_lock_retry(
    fn: Callable[[], T],
    *,
    attempts: Optional[int] = None,
    delay_s: Optional[float] = None,
    describe_holders: Optional[Callable[[], List[str]]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` and retry it on lock timeouts and deadlocks.

    ``attempts`` counts calls in total (6 means one try plus five retries).
    The last failure is re-raised unchanged.
    """
    default_attempts, default_delay = retry_settings()
    attempts = attempts if attempts is not None else default_attempts
    delay_s = delay_s if delay_s is not None else default_delay

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable_lock_error(exc) or attempt >= attempts:
                if is_retryable_lock_error(exc):
                    logger.error(
                        "Migration lock wait failed %d times; giving up: %s",
                        attempt,
                        exc,
                    )
                raise
            holders = describe_holders() if describe_holders else []
            logger.warning(
                "Migration attempt %d/%d could not get a lock (%s, SQLSTATE %s); "
                "retrying in %.0f s. Sessions holding relation locks: %s",
                attempt,
                attempts,
                str(exc).splitlines()[0] if str(exc) else type(exc).__name__,
                pgcode_of(exc),
                delay_s,
                "; ".join(holders) if holders else "none found",
            )
            sleep(delay_s)
    raise RuntimeError("unreachable")  # pragma: no cover
