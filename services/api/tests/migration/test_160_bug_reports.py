"""Migration 160: the ``bug_reports`` table.

The shared test DB is built by ``Base.metadata.create_all``, so it already has
the table; on it ``upgrade()`` must be a no-op. The shape tests drop the table
first, the way production is before this release. Every test runs inside the
``test_db`` transaction, which rolls back.
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
        os.path.dirname(__file__), "..", "..", "alembic", "versions", "160_bug_reports.py"
    )
)

TABLE = "bug_reports"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_160", MIGRATION_PATH)
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


def _shape(conn):
    insp = inspect(conn)
    if not insp.has_table(TABLE):
        return None
    return {
        "columns": {
            c["name"]: {"nullable": c["nullable"], "default": c.get("default")}
            for c in insp.get_columns(TABLE)
        },
        "checks": {c["name"] for c in insp.get_check_constraints(TABLE)},
        "indexes": {i["name"] for i in insp.get_indexes(TABLE)},
        "fk_rules": {
            tuple(fk["constrained_columns"]): (fk.get("options") or {}).get("ondelete")
            for fk in insp.get_foreign_keys(TABLE)
        },
    }


def _user(db: Session):
    from models import User

    user = User(
        id=str(uuid.uuid4()),
        username=f"mig160-{uuid.uuid4().hex[:8]}",
        email=f"mig160-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 160",
    )
    db.add(user)
    db.flush()
    return user


class TestMigration160:
    def test_revision_chains_after_159(self):
        mig = _load_migration()
        assert mig.revision == "160_bug_reports"
        assert mig.down_revision == "159_annotation_original_result"

    def test_upgrade_is_a_no_op_on_the_existing_table(self, test_db: Session):
        conn = test_db.get_bind()
        before = _shape(conn)
        assert before is not None
        with _op_context(conn):
            _load_migration().upgrade()
        assert _shape(conn) == before

    def test_downgrade_then_upgrade_builds_the_table(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert _shape(conn) is None
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        shape = _shape(conn)
        assert shape is not None
        columns = shape["columns"]
        assert {
            "id",
            "reporter_id",
            "contact_email",
            "title",
            "description",
            "expected",
            "context",
            "screenshot_key",
            "screenshot_content_type",
            "screenshot_size",
            "status",
            "delivery_attempts",
            "delivery_error",
            "issue_url",
            "issue_number",
            "delivered_at",
            "created_at",
            "updated_at",
        } == set(columns)
        assert columns["title"]["nullable"] is False
        assert columns["reporter_id"]["nullable"] is True
        assert "pending" in str(columns["status"]["default"])
        assert shape["checks"] == {"ck_bug_reports_status"}
        assert {
            "ix_bug_reports_created",
            "ix_bug_reports_status_created",
            "ix_bug_reports_reporter",
        } <= shape["indexes"]
        assert shape["fk_rules"] == {("reporter_id",): "SET NULL"}

    def test_defaults_and_status_check(self, test_db: Session):
        user = _user(test_db)
        test_db.execute(
            text(
                "INSERT INTO bug_reports (id, reporter_id, title, description)"
                " VALUES ('mig160-a', :u, 't', 'd')"
            ),
            {"u": user.id},
        )
        row = test_db.execute(
            text(
                "SELECT status, delivery_attempts, context FROM bug_reports"
                " WHERE id = 'mig160-a'"
            )
        ).one()
        assert row.status == "pending"
        assert row.delivery_attempts == 0
        assert row.context == {}
        with pytest.raises(IntegrityError):
            test_db.execute(
                text(
                    "INSERT INTO bug_reports (id, title, description, status)"
                    " VALUES ('mig160-b', 't', 'd', 'lost')"
                )
            )
        test_db.rollback()

    def test_deleting_the_reporter_keeps_the_report(self, test_db: Session):
        from models import BugReport, User

        user = _user(test_db)
        report = BugReport(reporter_id=user.id, title="t", description="d")
        test_db.add(report)
        test_db.flush()
        report_id, user_id = report.id, user.id
        test_db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        test_db.expunge_all()
        kept = test_db.get(BugReport, report_id)
        assert kept is not None and kept.reporter_id is None
        assert test_db.query(User).filter(User.id == user_id).first() is None
