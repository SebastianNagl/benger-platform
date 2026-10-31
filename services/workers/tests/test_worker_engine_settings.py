"""Postgres session settings of the worker engine (audit A4).

The worker lane used to connect with a blank application_name and no
timeouts, so idle-in-transaction worker sessions were indistinguishable in
pg_stat_activity and could hold locks indefinitely (2026-10-15 migration
lock incident).
"""

import importlib.util
import os

WORKERS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_database(monkeypatch, **env):
    """Execute workers/database.py fresh under a private module name.

    Loaded by file path: ``import database`` may resolve to the API's module
    once ``tasks`` has put services/api on sys.path, and ``importlib.reload``
    re-resolves through sys.path as well.
    """
    for key in ("WORKER_IDLE_IN_TX_TIMEOUT_MS", "WORKER_LOCK_TIMEOUT_MS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(
        "_workers_database_under_test", os.path.join(WORKERS_ROOT, "database.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_defaults(monkeypatch):
    database = _load_database(monkeypatch)
    args = database.connect_args
    assert args["application_name"] == "benger-workers"
    assert "-c idle_in_transaction_session_timeout=1800000" in args["options"]
    assert "-c lock_timeout=30000" in args["options"]
    assert "statement_timeout" not in args["options"]
    # The keepalives stay in place.
    assert args["keepalives"] == 1


def test_env_overrides(monkeypatch):
    database = _load_database(
        monkeypatch,
        WORKER_IDLE_IN_TX_TIMEOUT_MS="0",
        WORKER_LOCK_TIMEOUT_MS="not-a-number",
    )
    assert "-c idle_in_transaction_session_timeout=0" in database.connect_args["options"]
    assert "-c lock_timeout=30000" in database.connect_args["options"]
