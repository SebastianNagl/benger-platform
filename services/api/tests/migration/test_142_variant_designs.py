"""Shape tests for migration 142: variant designs.

The shared test DB already carries the table, the derived task columns, the
trigger, the unique cell index and the design key (built from the models),
so ``upgrade()`` must be a no-op through its guards, twice. ``downgrade()``
removes all of it, and a re-run ``upgrade()`` rebuilds the shape of the
models; an assignment stored before the key was reserved moves to
``meta.variant_legacy`` on that first run. The trigger the re-run installs
derives the cell from the within-unit task factors and guards frozen designs.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "142_variant_designs"


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py"))
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


def _assert_shape(conn):
    from project_models import VariantDesign

    insp = inspect(conn)
    assert {c["name"] for c in insp.get_columns("variant_designs")} == {
        c.name for c in VariantDesign.__table__.columns
    }
    uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("variant_designs")}
    assert uniques["uq_variant_designs_project_key"] == ["project_id", "key"]
    columns = {c["name"] for c in insp.get_columns("tasks")}
    assert {"variant_design", "variant_unit", "variant_cell"} <= columns
    index = {i["name"]: i for i in insp.get_indexes("tasks")}["uq_tasks_variant_cell"]
    assert index["unique"]
    assert index["column_names"] == ["project_id", "variant_design", "variant_unit", "variant_cell"]
    fks = {fk["name"]: fk for fk in insp.get_foreign_keys("tasks")}
    fk = fks["fk_tasks_variant_design"]
    assert fk["referred_table"] == "variant_designs"
    assert fk["referred_columns"] == ["project_id", "key"]
    deferred = conn.execute(
        text(
            "SELECT condeferrable, condeferred FROM pg_constraint "
            "WHERE conname = 'fk_tasks_variant_design'"
        )
    ).one()
    assert tuple(deferred) == (False, False)
    assert conn.execute(
        text("SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tasks_variant_sync'")
    ).scalar()


_INSERT_TASK = text(
    "INSERT INTO tasks (id, project_id, data, meta, inner_id, is_labeled, "
    "total_annotations, cancelled_annotations, comment_count, "
    "unresolved_comment_count, korrektur_count, unresolved_korrektur_count) "
    "VALUES (:t, :p, CAST(:d AS json), CAST(:m AS json), :n, false, 0, 0, 0, 0, 0, 0)"
)


def _insert_task(conn, project_id, inner_id, factors):
    task_id = str(uuid.uuid4())
    meta = {"variant": {"design": "swap", "unit": "u1", "factors": factors}}
    conn.execute(
        _INSERT_TASK,
        {"t": task_id, "p": project_id, "d": json.dumps({"facts": "x"}), "m": json.dumps(meta), "n": inner_id},
    )
    return task_id


def _assert_installed_trigger_behaves(conn, project_id):
    """The function the migration installed derives the cell from the
    within-unit task factors only and refuses edits of a frozen design."""
    spec = {
        "schema_version": 1,
        "unit": {"name": "case"},
        "factors": [
            {"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]},
            {"name": "level", "type": "numeric", "varies": "between_units"},
        ],
    }
    conn.execute(
        text(
            "INSERT INTO variant_designs (id, project_id, key, version, spec, status) "
            "VALUES (:i, :p, 'swap', 1, CAST(:s AS jsonb), 'draft')"
        ),
        {"i": str(uuid.uuid4()), "p": project_id, "s": json.dumps(spec)},
    )
    first = _insert_task(conn, project_id, 2, {"role": "claimant", "level": 1})
    cell = conn.execute(
        text("SELECT variant_cell FROM tasks WHERE id = :t"), {"t": first}
    ).scalar_one()
    assert cell == {"role": "claimant"}
    for n, factors in ((3, {"role": "claimant", "level": 2}), (4, {"level": 2, "role": "claimant"})):
        with pytest.raises(IntegrityError) as exc:
            with conn.begin_nested():
                _insert_task(conn, project_id, n, factors)
        assert "uq_tasks_variant_cell" in str(exc.value)
    conn.execute(
        text(
            "UPDATE variant_designs SET status = 'frozen', content_hash = :h, frozen_at = now() "
            "WHERE project_id = :p AND key = 'swap'"
        ),
        {"h": "0" * 64, "p": project_id},
    )
    with pytest.raises(DBAPIError) as exc:
        with conn.begin_nested():
            conn.execute(
                text("UPDATE tasks SET data = CAST(:d AS json) WHERE id = :t"),
                {"d": json.dumps({"facts": "changed"}), "t": first},
            )
    assert "variant_design_frozen" in str(exc.value)


class TestMigration142:
    def test_revision_chains_after_145(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "145_compliance_findings"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_shape(conn)

    def test_downgrade_then_upgrade_rebuilds_and_moves_legacy_keys(
        self, test_db: Session, test_users
    ):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "variant_designs" not in inspect(conn).get_table_names()
        assert "variant_design" not in {c["name"] for c in inspect(conn).get_columns("tasks")}

        # A task that used the key before it was reserved.
        from project_models import Project

        project_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
        test_db.add(Project(id=project_id, title="m142", created_by=test_users[0].id))
        test_db.flush()
        conn.execute(
            text(
                "INSERT INTO tasks (id, project_id, data, meta, inner_id, is_labeled, "
                "total_annotations, cancelled_annotations, comment_count, "
                "unresolved_comment_count, korrektur_count, unresolved_korrektur_count) "
                "VALUES (:t, :p, CAST('{}' AS json), CAST(:m AS json), 1, false, 0, 0, 0, 0, 0, 0)"
            ),
            {"t": task_id, "p": project_id, "m": json.dumps({"tags": ["a"], "variant": {"design": "x"}})},
        )
        with _op_context(conn):
            mig.upgrade()
        _assert_shape(conn)
        meta, design = conn.execute(
            text("SELECT meta, variant_design FROM tasks WHERE id = :t"), {"t": task_id}
        ).one()
        assert meta == {"tags": ["a"], "variant_legacy": {"design": "x"}}
        assert design is None
        _assert_installed_trigger_behaves(conn, project_id)
