"""Feature flag evaluation, caching and the lazy registry sync (core 2.42).

Persistence is ``models.FeatureFlag`` / ``models.FeatureFlagTarget``.

Snapshot
    One JSON document holding every registered flag with its state and
    allowlist: ``{name: {"state": ..., "users": [...], "orgs": [...]}}``.
    It is cached in Redis under :data:`SNAPSHOT_KEY` for
    :data:`SNAPSHOT_TTL` seconds and dropped on every write
    (:func:`invalidate_cache`, which also drops the pre-2.42 key
    :data:`LEGACY_SNAPSHOT_KEY`). Redis being down only costs a DB read. A
    registered flag without a row (not synced yet) evaluates with its
    registered default, so a missing row never flips a feature.

Evaluation
    ``off`` -> False, ``everyone`` -> True (anonymous callers included),
    ``allowlist`` -> True when the user is listed or any organization the
    user is an active member of is listed (every membership counts, the core
    2.21 rule). An unknown flag name -> False. A flag owned by a package
    with a master flag also needs that master flag on for the same caller
    (owner coupling, ``registry.coupled_master``).

Lazy registry sync (:func:`sync_registry` / :func:`sync_registry_sync`)
    Runs on the first DB snapshot load per process: inserts missing
    registered flags with their default state (``ON CONFLICT (name) DO
    NOTHING``, so an admin-changed state is never overwritten) and refreshes
    descriptions. Since core 2.42 it never deletes: a row whose name nobody
    registered (a package that is not installed in this process, or a
    retired flag) stays, is listed as ``registered: false`` in the admin
    console and can be deleted there by a superadmin. Every statement is
    idempotent, so concurrent API replicas may run it at the same time. It
    commits the session it is given, so callers load the snapshot before any
    writes of their own.

Sync and async twins share the statement builders (dual-mode pattern).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .registry import (
    PUBLIC_API,
    STATE_ALLOWLIST,
    STATE_EVERYONE,
    STATE_OFF,
    all_flags,
    coupled_master,
    flag,
    master_extension_ids,
)

logger = logging.getLogger(__name__)

SNAPSHOT_KEY = "feature_flags:snapshot"
LEGACY_SNAPSHOT_KEY = "ext:feature_flags:snapshot"
SNAPSHOT_TTL = 300

# Set once the registry sync committed in this process.
_registry_synced = False


def reset_registry_sync_state() -> None:
    """Forget that this process synced the registry (tests)."""
    global _registry_synced
    _registry_synced = False


# ---------------------------------------------------------------------------
# Statement builders (shared by the sync and async lanes)
# ---------------------------------------------------------------------------


def _models():
    from models import FeatureFlag, FeatureFlagTarget

    return FeatureFlag, FeatureFlagTarget


def _select_flags():
    FeatureFlag, _ = _models()
    return select(FeatureFlag.id, FeatureFlag.name, FeatureFlag.state)


def _select_targets():
    _, FeatureFlagTarget = _models()
    return select(
        FeatureFlagTarget.flag_id,
        FeatureFlagTarget.user_id,
        FeatureFlagTarget.organization_id,
    )


def select_membership_org_ids(user_id: str):
    from models import OrganizationMembership

    return select(OrganizationMembership.organization_id).where(
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.is_active.is_(True),
    )


def _sync_statements() -> List[Any]:
    """INSERT missing, refresh descriptions. Never deletes.

    Updates run in registry order, so two replicas syncing at once lock the
    rows in the same order and cannot deadlock each other.
    """
    FeatureFlag, _ = _models()
    registered = all_flags()
    if not registered:
        return []
    statements: List[Any] = [
        pg_insert(FeatureFlag)
        .values(
            [
                {
                    "id": str(uuid.uuid4()),
                    "name": definition.name,
                    "description": definition.description,
                    "state": definition.default_state,
                }
                for definition in registered
            ]
        )
        .on_conflict_do_nothing(index_elements=["name"])
    ]
    for definition in registered:
        statements.append(
            update(FeatureFlag)
            .where(
                FeatureFlag.name == definition.name,
                FeatureFlag.description.is_distinct_from(definition.description),
            )
            .values(description=definition.description)
        )
    return statements


# ---------------------------------------------------------------------------
# Snapshot building + cache
# ---------------------------------------------------------------------------


def default_entry(name: str) -> Optional[Dict]:
    definition = flag(name)
    if definition is None:
        return None
    return {"state": definition.default_state, "users": [], "orgs": []}


def defaults_snapshot() -> Dict[str, Dict]:
    """Every registered flag at its registered default (no DB, no cache)."""
    return {d.name: {"state": d.default_state, "users": [], "orgs": []} for d in all_flags()}


def build_snapshot(flag_rows: Iterable, target_rows: Iterable) -> Dict[str, Dict]:
    """Registered flags only; a registered flag without a row gets its default."""
    by_id: Dict[str, str] = {}
    snapshot: Dict[str, Dict] = {}
    for row in flag_rows:
        if flag(row.name) is None:
            continue
        by_id[row.id] = row.name
        snapshot[row.name] = {"state": row.state, "users": [], "orgs": []}
    for definition in all_flags():
        snapshot.setdefault(
            definition.name,
            {"state": definition.default_state, "users": [], "orgs": []},
        )
    for row in target_rows:
        name = by_id.get(row.flag_id)
        if name is None:
            continue
        if row.user_id:
            snapshot[name]["users"].append(str(row.user_id))
        if row.organization_id:
            snapshot[name]["orgs"].append(str(row.organization_id))
    return snapshot


class _RedisUrlCache:
    """Minimal JSON cache over ``REDIS_URI`` for processes without the API's
    ``redis_cache`` (the workers). Read and delete only need the same
    serialization the API uses (JSON strings)."""

    def __init__(self, url: str):
        import redis

        self._client = redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )

    def get(self, key):
        raw = self._client.get(key)
        return json.loads(raw) if raw else None

    def set(self, key, value, ttl=300):
        self._client.setex(key, ttl, json.dumps(value, default=str))
        return True

    def delete(self, key):
        self._client.delete(key)
        return True


_url_cache = None


def _cache():
    try:
        from redis_cache import cache

        return cache
    except ImportError:
        pass
    except Exception:  # pragma: no cover - redis_cache failed to initialize
        logger.warning("feature flags: redis_cache import failed", exc_info=True)
        return None
    global _url_cache
    if _url_cache is None:
        url = os.environ.get("REDIS_URI")
        if not url:
            return None
        try:
            _url_cache = _RedisUrlCache(url)
        except Exception:
            logger.warning("feature flags: no Redis client", exc_info=True)
            return None
    return _url_cache


def cache_get() -> Optional[Dict[str, Dict]]:
    cache = _cache()
    if cache is None:
        return None
    try:
        value = cache.get(SNAPSHOT_KEY)
    except Exception:
        logger.warning("feature flags: could not read the cached snapshot", exc_info=True)
        return None
    return value if isinstance(value, dict) else None


def cache_set(snapshot: Dict[str, Dict]) -> None:
    cache = _cache()
    if cache is None:
        return
    try:
        cache.set(SNAPSHOT_KEY, snapshot, ttl=SNAPSHOT_TTL)
    except Exception:
        logger.warning("feature flags: could not cache the snapshot", exc_info=True)


def invalidate_cache() -> None:
    """Drop the cached snapshot (call after every flag or target write).
    Also drops the pre-2.42 key so an older replica cannot serve stale state
    during a rollout."""
    cache = _cache()
    if cache is None:
        return
    for key in (SNAPSHOT_KEY, LEGACY_SNAPSHOT_KEY):
        try:
            cache.delete(key)
        except Exception:
            logger.warning("feature flags: could not drop %s", key, exc_info=True)


# ---------------------------------------------------------------------------
# Registry sync
# ---------------------------------------------------------------------------


def sync_registry_sync(db) -> None:
    """Align the table with the registry (sync lane). Commits ``db``."""
    for stmt in _sync_statements():
        db.execute(stmt)
    db.commit()


async def sync_registry(db) -> None:
    """Align the table with the registry (async lane). Commits ``db``."""
    for stmt in _sync_statements():
        await db.execute(stmt)
    await db.commit()


def _maybe_sync_sync(db) -> None:
    global _registry_synced
    if _registry_synced:
        return
    try:
        sync_registry_sync(db)
    except Exception:
        logger.exception("feature flags: registry sync failed, retrying later")
        db.rollback()
        return
    _registry_synced = True
    invalidate_cache()


async def _maybe_sync(db) -> None:
    global _registry_synced
    if _registry_synced:
        return
    try:
        await sync_registry(db)
    except Exception:
        logger.exception("feature flags: registry sync failed, retrying later")
        await db.rollback()
        return
    _registry_synced = True
    invalidate_cache()


# ---------------------------------------------------------------------------
# Snapshot loading
# ---------------------------------------------------------------------------


def load_snapshot_sync(db, *, use_cache: bool = True, sync: bool = True) -> Dict[str, Dict]:
    """The flag snapshot (sync lane): Redis first, then the database.

    ``use_cache=False, sync=False`` is the worker read: a direct DB read
    that neither touches Redis nor writes.
    """
    if use_cache:
        cached = cache_get()
        if cached is not None:
            return cached
    if sync:
        _maybe_sync_sync(db)
    snapshot = build_snapshot(
        db.execute(_select_flags()).all(), db.execute(_select_targets()).all()
    )
    if use_cache:
        cache_set(snapshot)
    return snapshot


async def load_snapshot(db, *, sync: bool = True) -> Dict[str, Dict]:
    """The flag snapshot (async lane): Redis first, then the database.

    ``sync=False`` never writes (the router gates run it before handlers
    that own the session's transaction)."""
    cached = cache_get()
    if cached is not None:
        return cached
    if sync:
        await _maybe_sync(db)
    flags = (await db.execute(_select_flags())).all()
    targets = (await db.execute(_select_targets())).all()
    snapshot = build_snapshot(flags, targets)
    cache_set(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def user_id_of(user) -> Optional[str]:
    if user is None:
        return None
    if isinstance(user, str):
        return user or None
    uid = getattr(user, "id", None)
    return str(uid) if uid else None


def entry_of(snapshot: Dict[str, Dict], name: str) -> Optional[Dict]:
    """The snapshot entry of a registered flag; a registered flag the
    snapshot does not know yet (registered after it was cached) gets its
    default. Unregistered names -> None."""
    if flag(name) is None:
        return None
    entry = snapshot.get(name)
    return entry if entry else default_entry(name)


def entry_allows(
    entry: Optional[Dict],
    user_id: Optional[str],
    org_ids: Callable[[], Set[str]],
) -> bool:
    """One entry for one caller. Anonymous callers pass only ``everyone``,
    unless ``org_ids`` (an organization key, a project's organizations)
    names a listed organization."""
    if not entry:
        return False
    state = entry.get("state")
    if state == STATE_EVERYONE:
        return True
    if state != STATE_ALLOWLIST:
        return False
    if user_id and user_id in (entry.get("users") or ()):
        return True
    listed_orgs = entry.get("orgs") or ()
    if not listed_orgs:
        return False
    return bool(org_ids() & {str(o) for o in listed_orgs})


def entry_on_globally(entry: Optional[Dict]) -> bool:
    """The POLICY_GLOBAL reading: anything but ``off``."""
    return bool(entry) and entry.get("state", STATE_OFF) != STATE_OFF


def needs_orgs(snapshot: Dict[str, Dict], names: Iterable[str], user_id: Optional[str]) -> bool:
    """Whether evaluating ``names`` (and their coupled masters) for
    ``user_id`` can depend on the user's memberships."""
    if not user_id:
        return False
    for name in _with_masters(names):
        entry = entry_of(snapshot, name) or {}
        if (
            entry.get("state") == STATE_ALLOWLIST
            and entry.get("orgs")
            and user_id not in (entry.get("users") or ())
        ):
            return True
    return False


def _with_masters(names: Iterable[str]) -> List[str]:
    out: List[str] = []
    for name in names:
        out.append(name)
        master = coupled_master(name)
        if master:
            out.append(master)
    return out


def evaluate_names(
    snapshot: Dict[str, Dict],
    names: Iterable[str],
    user_id: Optional[str],
    org_ids: Callable[[], Set[str]],
) -> Dict[str, bool]:
    """``{name: bool}`` with owner coupling applied."""
    result: Dict[str, bool] = {}
    for name in names:
        ok = entry_allows(entry_of(snapshot, name), user_id, org_ids)
        if ok:
            master = coupled_master(name)
            if master:
                ok = entry_allows(entry_of(snapshot, master), user_id, org_ids)
        result[name] = ok
    return result


def evaluate_snapshot_sync(db, snapshot: Dict[str, Dict], user, names: Iterable[str]) -> Dict[str, bool]:
    """Evaluate ``names`` against a loaded snapshot (sync lane)."""
    names = list(names)
    uid = user_id_of(user)
    orgs: Set[str] = set()
    if needs_orgs(snapshot, names, uid):
        orgs = {str(r[0]) for r in db.execute(select_membership_org_ids(uid)).all()}
    return evaluate_names(snapshot, names, uid, lambda: orgs)


async def evaluate_snapshot(db, snapshot: Dict[str, Dict], user, names: Iterable[str]) -> Dict[str, bool]:
    """Evaluate ``names`` against a loaded snapshot (async lane)."""
    names = list(names)
    uid = user_id_of(user)
    orgs: Set[str] = set()
    if needs_orgs(snapshot, names, uid):
        rows = (await db.execute(select_membership_org_ids(uid))).all()
        orgs = {str(r[0]) for r in rows}
    return evaluate_names(snapshot, names, uid, lambda: orgs)


def is_enabled_for_sync(db, user, name: str) -> bool:
    """Whether ``name`` is on for ``user`` (sync lane); ``user`` may be None
    (anonymous). An unregistered name is off."""
    if flag(name) is None:
        return False
    snapshot = load_snapshot_sync(db)
    return evaluate_snapshot_sync(db, snapshot, user, [name])[name]


async def is_enabled_for(db, user, name: str) -> bool:
    """Whether ``name`` is on for ``user`` (async lane); ``user`` may be None
    (anonymous). An unregistered name is off."""
    if flag(name) is None:
        return False
    snapshot = await load_snapshot(db)
    return (await evaluate_snapshot(db, snapshot, user, [name]))[name]


def registered_names() -> List[str]:
    return [d.name for d in all_flags()]


def evaluate_all_for_sync(db, user) -> Dict[str, bool]:
    """``{name: bool}`` for every registered flag, all owners (sync lane)."""
    return evaluate_snapshot_sync(db, load_snapshot_sync(db), user, registered_names())


async def evaluate_all_for(db, user) -> Dict[str, bool]:
    """``{name: bool}`` for every registered flag, all owners (async lane)."""
    return await evaluate_snapshot(db, await load_snapshot(db), user, registered_names())


def extensions_view(flags: Dict[str, bool]) -> Dict[str, bool]:
    """``{EXTENSION_ID: bool}`` of every master flag in ``flags``."""
    return {
        ext_id: bool(flags.get(name, False))
        for name, ext_id in master_extension_ids().items()
    }


async def public_api_enabled(db, user, *, organization_id=None) -> bool:
    """The platform ``public_api`` flag for one caller.

    ``everyone`` opens it for every caller, anonymous ones included. With
    ``allowlist``, an organization key passes when its organization is
    listed; any other caller is evaluated like every flag (listed user, or
    member of a listed organization). ``off`` closes it.
    """
    snapshot = await load_snapshot(db)
    entry = entry_of(snapshot, PUBLIC_API) or {}
    state = entry.get("state")
    if state == STATE_EVERYONE:
        return True
    if state != STATE_ALLOWLIST:
        return False
    if organization_id and str(organization_id) in {
        str(org) for org in (entry.get("orgs") or ())
    }:
        return True
    if user_id_of(user) is None:
        return False
    return (await evaluate_snapshot(db, snapshot, user, [PUBLIC_API]))[PUBLIC_API]
