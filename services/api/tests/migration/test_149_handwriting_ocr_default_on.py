"""Migration 149: handwritten uploads on by default.

``upgrade()`` gives ``projects.handwriting_ocr_enabled`` the server default
TRUE and switches on existing exam-shaped projects (a ``Loesung`` field with
``name`` and ``toName``) that are off, recording them; ``downgrade()``
switches exactly those back off and restores the FALSE default. Projects
without an answer field and switches a teacher set stay as they are.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "alembic", "versions",
        "149_handwriting_ocr_default_on.py",
    )
)

EXAM = (
    '<View><Angabe name="angabe" value="$sachverhalt"/>'
    '<Loesung name="loesung" toName="angabe"/></View>'
)
TEXTAREA = '<View><Text name="t" value="$text"/><TextArea name="a" toName="t"/></View>'
LOESUNG_WITHOUT_TONAME = '<View><Loesung name="loesung"/></View>'
MALFORMED = "<View><Loesung name='loesung' toName='a'>"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_149", MIGRATION_PATH)
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


def _server_default(conn):
    col = {c["name"]: c for c in inspect(conn).get_columns("projects")}["handwriting_ocr_enabled"]
    return str(col["default"]).lower()


def _projects(test_db: Session):
    """Projects keyed by role, each with its switch as the old default left it."""
    from models import User
    from project_models import Project

    owner = User(
        id=str(uuid.uuid4()),
        username=f"mig149-{uuid.uuid4().hex[:8]}",
        email=f"mig149-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 149",
    )
    test_db.add(owner)
    test_db.flush()
    specs = {
        "exam_off": (EXAM, False),
        "exam_on": (EXAM, True),
        "textarea": (TEXTAREA, False),
        "no_toname": (LOESUNG_WITHOUT_TONAME, False),
        "malformed": (MALFORMED, False),
        "no_config": (None, False),
    }
    ids = {}
    for key, (config, enabled) in specs.items():
        project = Project(
            id=str(uuid.uuid4()), title=f"mig149 {key}", created_by=owner.id,
            label_config=config, handwriting_ocr_enabled=enabled,
        )
        test_db.add(project)
        ids[key] = project.id
    test_db.flush()
    return ids


def _enabled(conn, ids):
    rows = conn.execute(
        text("SELECT id, handwriting_ocr_enabled FROM projects WHERE id = ANY(:ids)"),
        {"ids": list(ids.values())},
    ).fetchall()
    by_id = dict(rows)
    return {key: by_id[pid] for key, pid in ids.items()}


class TestMigration149:
    def test_revision_chains_after_148(self):
        mig = _load_migration()
        assert mig.revision == "149_handwriting_ocr_default_on"
        assert mig.down_revision == "148_analysis_lookup_tables"

    def test_answer_field_detection(self):
        mig = _load_migration()
        assert mig.has_answer_field(EXAM) is True
        for config in (TEXTAREA, LOESUNG_WITHOUT_TONAME, MALFORMED, None, ""):
            assert mig.has_answer_field(config) is False

    def test_upgrade_switches_on_exam_projects_and_downgrade_restores(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        # The models already carry the new default; start from the old one.
        with _op_context(conn):
            mig.downgrade()
        conn.execute(text("ALTER TABLE projects ALTER COLUMN handwriting_ocr_enabled SET DEFAULT false"))
        ids = _projects(test_db)
        before = _enabled(conn, ids)

        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # idempotent
        after = _enabled(conn, ids)
        assert after == {**before, "exam_off": True}
        assert "true" in _server_default(conn)
        recorded = conn.execute(
            text("SELECT project_id FROM handwriting_ocr_backfill_149 WHERE project_id = ANY(:ids)"),
            {"ids": list(ids.values())},
        ).scalars().all()
        assert recorded == [ids["exam_off"]]

        with _op_context(conn):
            mig.downgrade()
        assert _enabled(conn, ids) == before
        assert "false" in _server_default(conn)
        assert "handwriting_ocr_backfill_149" not in inspect(conn).get_table_names()

        with _op_context(conn):
            mig.upgrade()
        assert _enabled(conn, ids)["exam_off"] is True
