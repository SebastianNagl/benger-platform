"""Flag checks for Celery tasks.

Workers never sync the registry and never write: they read the cached
snapshot when Redis is reachable (``REDIS_URI``) and fall back to a direct
database read. A registered flag without a row evaluates with its
registered default, like everywhere else.
"""

from __future__ import annotations

from .registry import FEATURE_DISABLED, FEATURE_DISABLED_MESSAGE, flag
from .service import cache_get, evaluate_snapshot_sync, load_snapshot_sync


def worker_snapshot(db):
    """The snapshot for a worker: the Redis copy, else a read-only DB read."""
    cached = cache_get()
    if cached is not None:
        return cached
    return load_snapshot_sync(db, use_cache=False, sync=False)


def flag_enabled_sync(db, user_id, name: str) -> bool:
    """Whether ``name`` is on for ``user_id`` (None: anonymous/system, which
    passes only ``everyone``). An unregistered name is off."""
    if flag(name) is None:
        return False
    snapshot = worker_snapshot(db)
    uid = str(user_id) if user_id else None
    return evaluate_snapshot_sync(db, snapshot, uid, [name])[name]


def feature_disabled_result(name: str) -> dict:
    """The task result for a job whose flag was switched off after dispatch."""
    return {
        "status": "error",
        "error": FEATURE_DISABLED_MESSAGE,
        "reason": FEATURE_DISABLED,
        "flag": name,
    }
