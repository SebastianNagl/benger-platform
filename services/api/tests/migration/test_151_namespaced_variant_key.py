"""Migration 151: variant assignments move to ``meta.benger_variant``.

A database that ran the first version of migration 142 reserved
``meta.variant`` and kept users' own values in ``meta.variant_legacy``. The
upgrade moves the assignments to the namespaced key, puts the plain values
back into ``meta.variant``, keeps the derived columns, and installs the
function reading the new key. A database that came from main (the shared test
DB, built from the models) is left as it is. The downgrade restores the first
shape, and migration 142's downgrade then returns the plain values to
``meta.variant``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "151_namespaced_variant_key"


def _load(name: str = NAME):
    spec = importlib.util.spec_from_file_location(f"mig_{name}", os.path.join(VERSIONS, f"{name}.py"))
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


_INSERT_TASK = text(
    "INSERT INTO tasks (id, project_id, data, meta, inner_id, is_labeled, "
    "total_annotations, cancelled_annotations, comment_count, "
    "unresolved_comment_count, korrektur_count, unresolved_korrektur_count) "
    "VALUES (:t, :p, CAST(:d AS json), CAST(:m AS json), :n, false, 0, 0, 0, 0, 0, 0)"
)

_SPEC = {
    "schema_version": 1,
    "unit": {"name": "case"},
    "factors": [{"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]}],
}


def _project(test_db, test_users) -> str:
    from project_models import Project

    project_id = str(uuid.uuid4())
    test_db.add(Project(id=project_id, title="m151", created_by=test_users[0].id))
    test_db.flush()
    return project_id


def _design(conn, project_id, key="swap", frozen=False):
    conn.execute(
        text(
            "INSERT INTO variant_designs (id, project_id, key, version, spec, status, "
            "content_hash, frozen_at) VALUES (:i, :p, :k, 1, CAST(:s AS jsonb), :st, :h, "
            "CASE WHEN :st = 'frozen' THEN now() END)"
        ),
        {
            "i": str(uuid.uuid4()),
            "p": project_id,
            "k": key,
            "s": json.dumps(_SPEC),
            "st": "frozen" if frozen else "draft",
            "h": "0" * 64 if frozen else None,
        },
    )


def _insert(conn, project_id, n, meta) -> str:
    task_id = str(uuid.uuid4())
    conn.execute(
        _INSERT_TASK,
        {"t": task_id, "p": project_id, "d": json.dumps({"facts": n}), "m": json.dumps(meta), "n": n},
    )
    return task_id


def _row(conn, task_id):
    return conn.execute(
        text("SELECT meta, variant_design, variant_unit, variant_cell FROM tasks WHERE id = :t"),
        {"t": task_id},
    ).one()


def _function_source(conn) -> str:
    return conn.execute(
        text("SELECT prosrc FROM pg_proc WHERE proname = 'tasks_variant_sync'")
    ).scalar_one()


def _install_first_142_function(conn):
    """The database state the first version of migration 142 left."""
    conn.execute(text(_load()._FUNCTION_OLD))


def _assignment(unit="u1", role="claimant", design="swap"):
    return {"design": design, "unit": unit, "factors": {"role": role}}


class TestMigration151:
    def test_revision_chains_after_150(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "150_handwriting_ocr_default_on"

    def test_function_texts_match_the_models(self):
        from project_models import TASKS_VARIANT_FUNCTION

        mig = _load()
        assert mig._FUNCTION_NEW.strip() == TASKS_VARIANT_FUNCTION.strip()
        assert "'benger_variant'" not in mig._FUNCTION_OLD
        assert "-> 'variant'" in mig._FUNCTION_OLD

    def test_database_from_main_is_left_alone(self, test_db: Session, test_users):
        conn = test_db.get_bind()
        project_id = _project(test_db, test_users)
        _design(conn, project_id)
        plain = _insert(conn, project_id, 1, {"variant": {"design": "mine"}, "variant_legacy": 1})
        assigned = _insert(conn, project_id, 2, {"benger_variant": _assignment()})
        before = [_row(conn, plain), _row(conn, assigned)]
        with _op_context(conn):
            _load().upgrade()
        assert [_row(conn, plain), _row(conn, assigned)] == before
        assert "'benger_variant'" in _function_source(conn)

    def test_first_142_database_is_converted(self, test_db: Session, test_users):
        conn = test_db.get_bind()
        project_id = _project(test_db, test_users)
        _design(conn, project_id)
        _install_first_142_function(conn)
        # Written while meta.variant was reserved: derived columns are set.
        assigned = _insert(conn, project_id, 1, {"tags": ["a"], "variant": _assignment()})
        # A user's value the first 142 moved aside.
        legacy = _insert(conn, project_id, 2, {"variant_legacy": {"design": "own"}})
        # Both on one task (assigned after the move).
        both = _insert(
            conn, project_id, 3, {"variant": _assignment("u2"), "variant_legacy": "kept"}
        )
        derived = _row(conn, assigned)[1:]
        assert derived == ("swap", "u1", {"role": "claimant"})

        with _op_context(conn):
            _load().upgrade()

        assert _row(conn, assigned) == (
            {"tags": ["a"], "benger_variant": _assignment()},
            "swap",
            "u1",
            {"role": "claimant"},
        )
        assert _row(conn, legacy)[0] == {"variant": {"design": "own"}}
        assert _row(conn, legacy)[1] is None
        assert _row(conn, both)[0] == {"benger_variant": _assignment("u2"), "variant": "kept"}
        assert _row(conn, both)[1:3] == ("swap", "u2")
        assert "'benger_variant'" in _function_source(conn)
        # The new function derives from the new key and ignores a plain one.
        fresh = _insert(conn, project_id, 4, {"benger_variant": _assignment("u3")})
        assert _row(conn, fresh)[1:3] == ("swap", "u3")
        plain = _insert(conn, project_id, 5, {"variant": _assignment("u4")})
        assert _row(conn, plain)[1] is None

    def test_conversion_moves_tasks_of_frozen_designs(self, test_db: Session, test_users):
        conn = test_db.get_bind()
        project_id = _project(test_db, test_users)
        _design(conn, project_id)
        _install_first_142_function(conn)
        task = _insert(conn, project_id, 1, {"variant": _assignment()})
        conn.execute(
            text(
                "UPDATE variant_designs SET status = 'frozen', content_hash = :h, "
                "frozen_at = now() WHERE project_id = :p"
            ),
            {"h": "0" * 64, "p": project_id},
        )
        with _op_context(conn):
            _load().upgrade()
        assert _row(conn, task)[0] == {"benger_variant": _assignment()}
        assert _row(conn, task)[1] == "swap"

    def test_downgrade_restores_the_first_shape_and_upgrade_returns(
        self, test_db: Session, test_users
    ):
        conn = test_db.get_bind()
        project_id = _project(test_db, test_users)
        _design(conn, project_id)
        assigned = _insert(conn, project_id, 1, {"benger_variant": _assignment()})
        plain = _insert(conn, project_id, 2, {"variant": {"design": "own"}})
        blocked = _insert(conn, project_id, 3, {"variant": "own", "variant_legacy": "x"})
        after_upgrade = [_row(conn, t) for t in (assigned, plain, blocked)]
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert _row(conn, assigned)[0] == {"variant": _assignment()}
        assert _row(conn, assigned)[1] == "swap"
        assert _row(conn, plain)[0] == {"variant_legacy": {"design": "own"}}
        # Nothing overwritten: the plain value stays, so the assignment-free row
        # is unchanged.
        assert _row(conn, blocked)[0] == {"variant": "own", "variant_legacy": "x"}
        assert "'benger_variant'" not in _function_source(conn)
        with _op_context(conn):
            mig.upgrade()
        assert [_row(conn, t) for t in (assigned, plain, blocked)] == after_upgrade

    def test_full_downgrade_returns_plain_values_to_meta_variant(
        self, test_db: Session, test_users
    ):
        conn = test_db.get_bind()
        project_id = _project(test_db, test_users)
        _design(conn, project_id)
        assigned = _insert(conn, project_id, 1, {"benger_variant": _assignment()})
        plain = _insert(conn, project_id, 2, {"tags": ["t"], "variant": {"design": "own"}})
        with _op_context(conn):
            _load().downgrade()
            _load("142_variant_designs").downgrade()
        assert _row_meta(conn, plain) == {"tags": ["t"], "variant": {"design": "own"}}
        # The assignment stays as data under the namespaced key.
        assert _row_meta(conn, assigned) == {"benger_variant": _assignment()}


def _row_meta(conn, task_id):
    return conn.execute(text("SELECT meta FROM tasks WHERE id = :t"), {"t": task_id}).scalar_one()
