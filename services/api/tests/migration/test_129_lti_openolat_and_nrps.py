"""Shape tests for migration 129: OpenOlat vendor tag and the NRPS URL.

The shared test DB is built from the models, so it already has the widened
CHECK and the column: ``upgrade()`` must be a clean no-op twice. A downgrade
must restore the old two-vendor CHECK (untagging OpenOlat rows first) and drop
the column; a re-run upgrade must rebuild both.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "129_lti_openolat_and_nrps.py",
    )
)

REG_TABLE = "lti_platform_registrations"
LINK_TABLE = "lti_resource_links"
COLUMN = "context_memberships_url"
CHECK = "ck_lti_platform_registrations_lms_family"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_129", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _link_columns(conn) -> set:
    return {c["name"] for c in inspect(conn).get_columns(LINK_TABLE)}


def _family_check(conn) -> str:
    for ck in inspect(conn).get_check_constraints(REG_TABLE):
        if ck["name"] == CHECK:
            return ck["sqltext"]
    raise AssertionError("lms_family CHECK missing")


def _org(test_db: Session):
    from models import Organization

    org = Organization(
        id=f"org-129-{uuid.uuid4().hex[:6]}",
        name="org-129",
        display_name="org-129",
        slug=f"org-129-{uuid.uuid4().hex[:6]}",
    )
    test_db.add(org)
    test_db.flush()
    return org


def _insert_registration(conn, org_id: str, lms_family) -> str:
    reg_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO lti_platform_registrations "
            "(id, organization_id, name, issuer, client_id, "
            " auth_login_url, auth_token_url, jwks_uri, lms_family) "
            "VALUES (:id, :oid, 'n', :iss, :cid, "
            " 'https://x/a', 'https://x/t', 'https://x/j', :fam)"
        ),
        {
            "id": reg_id,
            "oid": org_id,
            "iss": f"https://lms-{uuid.uuid4().hex[:8]}.example.com",
            "cid": uuid.uuid4().hex[:12],
            "fam": lms_family,
        },
    )
    return reg_id


class TestMigration129Shape:
    def test_revision_chains_after_128(self):
        mig = _load_migration()
        assert mig.revision == "129_lti_openolat_and_nrps"
        assert mig.down_revision == "128_feedback_value_follows_release"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert COLUMN in _link_columns(conn)
        assert "openolat" in _family_check(conn)

    def test_check_accepts_openolat_and_rejects_unknown(self, test_db: Session):
        conn = test_db.get_bind()
        org = _org(test_db)
        for family in (None, "moodle", "ilias", "openolat"):
            _insert_registration(conn, org.id, family)
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_registration(conn, org.id, "blackboard")

    def test_downgrade_untags_openolat_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        org = _org(test_db)
        reg_id = _insert_registration(conn, org.id, "openolat")
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert COLUMN not in _link_columns(conn)
        assert "openolat" not in _family_check(conn)
        assert (
            conn.execute(
                text("SELECT lms_family FROM lti_platform_registrations WHERE id = :id"),
                {"id": reg_id},
            ).scalar_one()
            is None
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_registration(conn, org.id, "openolat")

        with _op_context(conn):
            mig.upgrade()
        assert COLUMN in _link_columns(conn)
        assert "openolat" in _family_check(conn)
        _insert_registration(conn, org.id, "openolat")
