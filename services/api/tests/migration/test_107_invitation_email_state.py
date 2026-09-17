"""Shape and backfill tests for migration 107: invitation mail state.

The shared test DB already carries the four columns (created from the model by
``Base.metadata.create_all``), so ``upgrade()`` must be a no-op through its
guards, twice. ``downgrade()`` drops them; a re-run ``upgrade()`` rebuilds
them with the right nullability and the ``0`` default on the counter.

The backfill case matters as much as the shape: an invitation that existed
before this migration must come back as *unknown*, never as *failed*. We
cannot tell after the fact which historical invitations were delivered, and a
false ``failed`` would cry wolf on every one of them.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "107_invitation_email_state.py",
    )
)

TABLE = "invitations"
COLUMNS = (
    "email_sent_at",
    "email_last_attempt_at",
    "email_attempts",
    "email_last_error",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_107", MIGRATION_PATH)
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


def _columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(TABLE)}


def _uid(prefix="x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _assert_full_shape(conn) -> None:
    cols = _columns(conn)
    for name in ("email_sent_at", "email_last_attempt_at"):
        assert cols[name]["nullable"] is True, name
        assert cols[name]["default"] is None, name
    assert cols["email_last_error"]["nullable"] is True
    attempts = cols["email_attempts"]
    assert attempts["nullable"] is False
    assert "0" in str(attempts["default"])


class TestMigration107Shape:
    def test_revision_chains_after_106(self):
        mig = _load_migration()
        assert mig.revision == "107_invitation_email_state"
        assert mig.down_revision == "106_users_anon_and_eval_updated_at"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_full_shape(conn)

    def test_downgrade_then_upgrade_rebuilds_the_columns(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        present = _columns(conn)
        for name in COLUMNS:
            assert name not in present, name

        with _op_context(conn):
            mig.upgrade()
        _assert_full_shape(conn)

    def test_partially_applied_migration_finishes(self, test_db: Session):
        """A migration killed between two ALTERs must complete on the retry,
        which is how a pod recovers from a lock_timeout mid-run."""
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
            # Put one column back by hand, as a half-finished run would leave it.
            conn.exec_driver_sql(
                f"ALTER TABLE {TABLE} ADD COLUMN email_sent_at TIMESTAMPTZ NULL"
            )
            mig.upgrade()
        _assert_full_shape(conn)


class TestMigration107Backfill:
    def test_existing_row_reads_unknown_not_failed(self, test_db: Session):
        """No backfill on purpose. An invitation from before the columns
        existed carries no timestamps, which the API reports as unknown."""
        from models import Invitation, Organization, OrganizationRole, User

        conn = test_db.get_bind()
        mig = _load_migration()

        org = Organization(
            id=_uid("org"), name="Uni", display_name="Uni", slug=_uid("u")
        )
        inviter = User(
            id=_uid("usr"),
            username=_uid("un"),
            email=f"{_uid('m')}@example.com",
            name="Inviter",
        )
        test_db.add_all([org, inviter])
        test_db.flush()
        invitation = Invitation(
            id=_uid("inv"),
            organization_id=org.id,
            email="invitee@example.com",
            role=OrganizationRole.ANNOTATOR,
            token=_uid("tok"),
            invited_by=inviter.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted=False,
        )
        test_db.add(invitation)
        test_db.flush()

        # Round-trip the columns away and back, as the real upgrade does on a
        # table that already holds rows.
        with _op_context(conn):
            mig.downgrade()
            mig.upgrade()

        row = conn.exec_driver_sql(
            "SELECT email_sent_at, email_last_attempt_at, email_attempts, "
            f"email_last_error FROM {TABLE} WHERE id = '{invitation.id}'"
        ).first()
        sent_at, last_attempt_at, attempts, last_error = row
        assert sent_at is None
        assert last_attempt_at is None
        assert last_error is None
        # The NOT NULL DEFAULT 0 is what keeps existing rows readable.
        assert attempts == 0
