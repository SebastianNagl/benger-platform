"""Every migration applies to an empty PostgreSQL database, up to the one head.

The test suites build their schema from the models (``create_all`` in
tests/fixtures/database.py), so no other test runs the migration chain. The
API runs ``alembic upgrade head`` in its startup and only logs a failure as a
warning (main.py lifespan), so a migration that breaks would otherwise first
show as a pod serving an old schema after a deploy. This test runs the real
CLI against a fresh database, the way a new installation does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.smoke


def _admin_connection(url: str):
    connection = psycopg2.connect(urlunsplit(urlsplit(url)._replace(path="/postgres")))
    connection.autocommit = True
    return connection


@pytest.fixture
def empty_database_url():
    """A database of its own, created empty and dropped afterwards."""
    base = os.environ["DATABASE_URL"]
    parts = urlsplit(base)
    name = f"{parts.path.lstrip('/')}_migrate_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"
    admin = _admin_connection(base)
    try:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cur.execute(f'CREATE DATABASE "{name}"')
        yield urlunsplit(parts._replace(path=f"/{name}"))
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        admin.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url, "DATABASE_URI": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_upgrade_head_on_an_empty_database(empty_database_url):
    head = ScriptDirectory.from_config(Config(os.path.join(API_DIR, "alembic.ini"))).get_current_head()

    upgrade = _alembic(empty_database_url, "upgrade", "head")
    assert upgrade.returncode == 0, f"alembic upgrade head failed:\n{upgrade.stdout[-3000:]}\n{upgrade.stderr[-5000:]}"

    connection = psycopg2.connect(empty_database_url)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            versions = [row[0] for row in cur.fetchall()]
    finally:
        connection.close()
    assert versions == [head], f"database is at {versions}, the head is {head}"
