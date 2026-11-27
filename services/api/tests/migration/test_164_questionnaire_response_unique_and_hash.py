"""Migration 164: unique questionnaire response per annotation, config hash.

The shared test DB is built by ``Base.metadata.create_all``, so it already
has the column and the unique index; on it ``upgrade()`` must be a no-op. The
tests that need a deployed database first reshape the table the way
production has it before this release (015's non-unique
``ix_par_annotation_id``, no ``config_hash``). Every test runs inside the
``test_db`` transaction, which rolls back.
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
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "164_questionnaire_response_unique_and_hash.py",
    )
)

TABLE = "post_annotation_responses"
UNIQUE = "ix_post_annotation_responses_annotation_id"
OLD = "ix_par_annotation_id"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_164", MIGRATION_PATH)
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


def _indexes(conn) -> dict:
    return {ix["name"]: ix for ix in inspect(conn).get_indexes(TABLE)}


def _columns(conn) -> set:
    return {c["name"] for c in inspect(conn).get_columns(TABLE)}


def _as_deployed_before(conn) -> None:
    conn.execute(text(f"DROP INDEX IF EXISTS {UNIQUE}"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {OLD} ON {TABLE} (annotation_id)"))
    conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS config_hash"))


def _seed_annotation(db: Session) -> dict:
    from models import User
    from project_models import Annotation, Project, Task

    uid = lambda: str(uuid.uuid4())  # noqa: E731
    user = User(
        id=uid(), username=f"m-{uid()[:8]}", email=f"{uid()[:8]}@example.com",
        name="Migration User", is_active=True, email_verified=True,
    )
    db.add(user)
    db.flush()
    project = Project(id=uid(), title="Migration 164", created_by=user.id)
    db.add(project)
    db.flush()
    task = Task(id=uid(), project_id=project.id, data={}, inner_id=1)
    db.add(task)
    db.flush()
    annotation = Annotation(
        id=uid(), task_id=task.id, project_id=project.id, completed_by=user.id, result=[]
    )
    db.add(annotation)
    db.flush()
    return {
        "annotation_id": annotation.id,
        "task_id": task.id,
        "project_id": project.id,
        "user_id": user.id,
    }


def _insert_response(conn, ids: dict) -> None:
    conn.execute(
        text(
            f"INSERT INTO {TABLE} (id, annotation_id, task_id, project_id, user_id, result) "
            "VALUES (:id, :annotation_id, :task_id, :project_id, :user_id, '[]'::jsonb)"
        ),
        {"id": str(uuid.uuid4()), **ids},
    )


class TestMigration164:
    def test_revision_chains_after_163(self):
        mig = _load_migration()
        assert mig.revision == "164_questionnaire_response_unique_and_hash"
        assert mig.down_revision == "163_llm_model_display_order"

    def test_upgrade_is_a_noop_on_a_current_schema(self, test_db: Session):
        conn = test_db.get_bind()
        assert _indexes(conn)[UNIQUE]["unique"]
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert _indexes(conn)[UNIQUE]["unique"]
        assert "config_hash" in _columns(conn)

    def test_upgrade_replaces_the_015_index_with_a_unique_one(self, test_db: Session):
        conn = test_db.get_bind()
        _as_deployed_before(conn)
        ids = _seed_annotation(test_db)
        _insert_response(conn, ids)

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # idempotent

        indexes = _indexes(conn)
        assert indexes[UNIQUE]["unique"]
        assert indexes[UNIQUE]["column_names"] == ["annotation_id"]
        assert OLD not in indexes
        assert "config_hash" in _columns(conn)

    def test_existing_duplicates_keep_the_rows_and_skip_the_index(
        self, test_db: Session
    ):
        conn = test_db.get_bind()
        _as_deployed_before(conn)
        ids = _seed_annotation(test_db)
        _insert_response(conn, ids)
        _insert_response(conn, ids)

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()

        indexes = _indexes(conn)
        assert UNIQUE not in indexes
        assert OLD in indexes
        assert "config_hash" in _columns(conn)
        count = conn.execute(
            text(f"SELECT count(*) FROM {TABLE} WHERE annotation_id = :a"),
            {"a": ids["annotation_id"]},
        ).scalar()
        assert count == 2

    def test_downgrade_restores_the_015_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.downgrade()  # idempotent
            indexes = _indexes(conn)
            assert UNIQUE not in indexes
            assert not indexes[OLD]["unique"]
            assert "config_hash" not in _columns(conn)
            mig.upgrade()
        assert _indexes(conn)[UNIQUE]["unique"]
        assert "config_hash" in _columns(conn)
