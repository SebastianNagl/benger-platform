"""Shape tests for migration 089: lms_family on lti_platform_registrations.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guards — twice. ``downgrade()`` must remove the column and its
CHECK constraint; a re-run ``upgrade()`` must rebuild both.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

from sqlalchemy import inspect
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "089_add_lti_lms_family.py",
    )
)

TABLE = "lti_platform_registrations"
COLUMN = "lms_family"
CHECK = "ck_lti_platform_registrations_lms_family"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_089", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    """Install the alembic ``op`` proxy bound to the test connection."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _columns(conn) -> set:
    return {c["name"] for c in inspect(conn).get_columns(TABLE)}


def _checks(conn) -> set:
    return {c["name"] for c in inspect(conn).get_check_constraints(TABLE)}


class TestMigration089Shape:
    def test_revision_chains_after_087(self):
        mig = _load_migration()
        assert mig.revision == "089_add_lti_lms_family"
        assert mig.down_revision == "087_task_evaluations_metrics_jsonb"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Second run — the column/constraint guards must make this a no-op.
            mig.upgrade()
        assert COLUMN in _columns(conn)
        assert CHECK in _checks(conn)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert COLUMN not in _columns(conn)
        assert CHECK not in _checks(conn)

        with _op_context(conn):
            mig.upgrade()
        assert COLUMN in _columns(conn)
        assert CHECK in _checks(conn)

    def test_check_constraint_enforces_known_families(self, test_db: Session):
        """NULL and known vendors pass; anything else is rejected by the DB."""
        import uuid

        import pytest
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        from models import LtiPlatformRegistration, Organization

        org = Organization(
            id="org-089-test",
            name="org-089",
            display_name="org-089",
            slug=f"org-089-{uuid.uuid4().hex[:6]}",
        )
        test_db.add(org)
        test_db.flush()

        def _insert(lms_family):
            test_db.add(
                LtiPlatformRegistration(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    name="n",
                    issuer=f"https://lms-{uuid.uuid4().hex[:8]}.example.com",
                    client_id=uuid.uuid4().hex[:12],
                    auth_login_url="https://x/a",
                    auth_token_url="https://x/t",
                    jwks_uri="https://x/j",
                    lms_family=lms_family,
                )
            )
            test_db.flush()

        _insert(None)
        _insert("moodle")
        _insert("ilias")

        conn = test_db.get_bind()
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO lti_platform_registrations "
                        "(id, organization_id, name, issuer, client_id, "
                        " auth_login_url, auth_token_url, jwks_uri, lms_family) "
                        "VALUES (:id, :oid, 'n', :iss, :cid, "
                        " 'https://x/a', 'https://x/t', 'https://x/j', 'blackboard')"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "oid": org.id,
                        "iss": f"https://lms-{uuid.uuid4().hex[:8]}.example.com",
                        "cid": uuid.uuid4().hex[:12],
                    },
                )
