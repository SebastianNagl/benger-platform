"""
Pytest configuration for workers tests.

Handles platform-specific setup, particularly disabling MKL-DNN on ARM64
where Intel-specific instructions cause "Illegal instruction" errors.

Also configures timeouts to prevent tests from hanging indefinitely.
"""

import os
import platform
import sys
from unittest.mock import MagicMock

import pytest

# Sentinel for /shared/encryption_service.py — module-level
# `encryption_service = EncryptionService()` runs at first import, BEFORE
# pytest sets PYTEST_CURRENT_TEST. Without this, every worker test file
# that transitively imports the module raises RuntimeError at collection
# time. Mirrors what the API conftest does via JWT_SECRET_KEY / SECRET_KEY.
os.environ.setdefault("BENGER_TEST_MODE", "1")

# pytest-xdist (`pytest -n auto`, set in pytest.ini): give every xdist worker
# its own Postgres database, the same pattern the API suite uses. The
# integration harness (tests/integration/conftest.py) commits real rows and
# runs `create_all` plus `ALTER TYPE ... ADD VALUE` once per session, so
# several workers sharing one database would race on that DDL and see each
# other's rows in the leaderboard aggregation tests. The worker database is
# derived from DATABASE_URI (or DATABASE_URL) as `<name>_workers_gwN`
# (distinct from the API suite's `<name>_gwN`, so both suites can run against
# the same test-db at once), created empty if missing, and the env var is rewritten BEFORE anything imports the
# workers `database` module, which builds its engine from the env at import
# time. When Postgres is unreachable (bare host runs without the test stack)
# the URL is left alone, so DB-free tests still run and the integration
# harness reports the missing database exactly as before.
#
# Redis stays shared on purpose: every key the suite writes is scoped by a
# fresh UUID (chord results by Celery task id, poison-cell counters by
# run id + cell id), nothing flushes or counts keys, and Redis only has 16
# logical databases, too few for one pair per worker on large machines.
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
_db_env_key = next(
    (k for k in ("DATABASE_URI", "DATABASE_URL") if os.environ.get(k)), None
)
if _xdist_worker and _db_env_key:
    from urllib.parse import urlsplit, urlunsplit

    _parts = urlsplit(os.environ[_db_env_key])
    _worker_db = f"{_parts.path.lstrip('/')}_workers_{_xdist_worker}"
    import psycopg2

    try:
        _admin = psycopg2.connect(
            urlunsplit(_parts._replace(path="/postgres")), connect_timeout=5
        )
    except psycopg2.OperationalError:
        _admin = None
    if _admin is not None:
        _admin.autocommit = True
        with _admin.cursor() as _cur:
            _cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_worker_db,))
            if not _cur.fetchone():
                _cur.execute(f'CREATE DATABASE "{_worker_db}"')
        _admin.close()
        os.environ[_db_env_key] = urlunsplit(_parts._replace(path=f"/{_worker_db}"))

# Point Celery's broker + result backend at the reachable test Redis BEFORE
# anything imports `tasks` (this root conftest is the FIRST thing pytest
# loads in the workers suite, so it precedes every `import tasks`). The
# mounted `services/workers/.env` sets CELERY_BROKER_URL / CELERY_RESULT_BACKEND
# to the dev host `redis:6379` (unresolvable on the test network) and
# `tasks.py` reads them at import time via a direct `app.conf.broker_url =`
# assignment that Celery's config layering makes UN-overridable at runtime
# (a later conf.update / conf.changes write is silently shadowed). So the
# only place to win is here, before import: `setdefault` is enough because
# the runner env doesn't set these and `load_dotenv()` (called inside
# tasks.py) doesn't override an already-set var. The integration eval-chord
# harness needs the result backend reachable so a REAL `chord(header)(callback)`
# barrier fires; other worker tests just benefit from a reachable broker
# instead of a dead host. Distinct DBs (/1 result, /2 broker) keep the chord
# result keyspace off the poison-cell counter / progress pub-sub keyspace.
_test_redis = os.environ.get("REDIS_URL") or os.environ.get("REDIS_URI") \
    or "redis://test-redis:6379"
os.environ.setdefault("CELERY_BROKER_URL", f"{_test_redis}/2")
os.environ.setdefault("CELERY_RESULT_BACKEND", f"{_test_redis}/1")

# Ensure the workers source directory is at the front of sys.path
# so that local modules (email_service, ml_evaluation, etc.) are
# imported from workers, not from other services.
workers_root = os.path.dirname(os.path.dirname(__file__))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

# Add /shared to sys.path (where it lives in both Docker containers via
# the volume mount, and inside the test container the same path is
# available). The consolidation on 2026-05-19 moved models.py into
# /shared, so `from models import …` only resolves with /shared on the
# path. Fall back to a relative path for host-local pytest runs.
_shared_dir = (
    "/shared"
    if os.path.exists("/shared")
    else os.path.normpath(os.path.join(workers_root, "..", "shared"))
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

# Remove ALL paths that could resolve to the API's modules.
# On the self-hosted CI runner, the API directory ends up in sys.path
# (likely via .pth files or shared Python environment), causing
# 'import email_service' to resolve to services/api/email_service.py
# instead of services/workers/email_service.py.
_api_dir = os.path.normpath(os.path.join(workers_root, '..', 'api'))
sys.path = [
    p
    for p in sys.path
    if os.path.normpath(p) != _api_dir
    and not os.path.exists(os.path.join(p, 'email_service.py'))
    or os.path.normpath(p) == os.path.normpath(workers_root)
]

# Force-load email_service from the workers directory to guarantee
# the correct module is used, regardless of sys.path state.
import importlib.util as _ilu  # noqa: E402

_es_path = os.path.join(workers_root, 'email_service.py')
if os.path.exists(_es_path):
    _spec = _ilu.spec_from_file_location('email_service', _es_path)
    _mod = _ilu.module_from_spec(_spec)
    sys.modules['email_service'] = _mod
    _spec.loader.exec_module(_mod)


# Detect ARM64 platform
IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')

if IS_ARM64:
    # Disable MKL-DNN before torch is imported
    # MKL-DNN contains Intel-specific SIMD instructions that crash on ARM64
    os.environ['MKLDNN_VERBOSE'] = '0'

# Now import torch and disable MKL-DNN runtime
try:
    import torch

    if IS_ARM64:
        torch.backends.mkldnn.enabled = False
except ImportError:
    pass  # torch not installed


@pytest.fixture(autouse=True)
def _instant_ai_backoff_sleep(monkeypatch):
    """Make the AI-services retry backoff instant for every worker test.

    ``ai_services.deepinfra_service`` exposes its backoff sleep as a module
    seam (``_sleep = asyncio.sleep``), awaited by
    ``async_retry_with_exponential_backoff`` — the retry decorator shared by
    the DeepInfra and OpenAI-compatible (BYOM) clients. Left unpatched, any
    test that drives a retryable failure (429/5xx/timeout) would wait out
    real exponential delays (2s, 4s, ... capped at 60s, up to 5 retries).

    sys.modules-only on purpose: any test that can reach the backoff has
    the module imported at collection time (directly or via tasks.py), long
    before fixtures run — while importing it here would pull the whole
    ai_services package (and every provider SDK) into unrelated tests.
    Dedicated retry tests re-patch the same seam with a recording version;
    theirs wins because autouse fixtures are applied first.
    """
    di_mod = sys.modules.get("ai_services.deepinfra_service")
    if di_mod is None:
        return

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(di_mod, "_sleep", _no_sleep)


@pytest.fixture
def mock_api_client():
    """Mock API client for evaluation tasks.

    Provides a simple MagicMock that tests can configure for their
    specific API call expectations.

    Example usage in tests:
        mock_api_client.get.return_value.json.return_value = {"results": []}
    """
    return MagicMock()
