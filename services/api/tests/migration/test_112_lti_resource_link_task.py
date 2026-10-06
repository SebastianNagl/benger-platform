"""Migration 112: LTI links bound to one task or to a whole collection.

The shared test DB is built by ``Base.metadata.create_all`` (post-112
shape). The tests check the models and the live schema:

- ``lti_resource_links.task_id`` (FK ``tasks.id`` ON DELETE SET NULL, index)
  and ``grade_scope`` (NOT NULL, default ``'exam'``, CHECK);
- ``lti_grade_syncs.task_id`` (FK ON DELETE CASCADE, index) and
  ``uq_lti_grade_sync`` as ``UNIQUE NULLS NOT DISTINCT (resource_link_id,
  user_id, kind, task_id)``;
- the new ``lti_task_lineitems`` table with its uniqueness, checks and
  cascades.

``downgrade()`` removes all of it; seeded pre-112 links are upgraded again
and the backfills are checked: a link on a one-task exam is bound to that
task with scope ``'task'``, links on a two-task exam, an empty exam and an
unbound activity stay ``'exam'`` with NULL ``task_id``. Every test runs
inside the ``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "112_lti_resource_link_task.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_112", MIGRATION_PATH)
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


def _uid() -> str:
    return str(uuid.uuid4())


def _columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns("lti_resource_links")}


def _indexes(conn) -> dict:
    return {
        ix["name"]: ix for ix in inspect(conn).get_indexes("lti_resource_links")
    }


def _task_fks(conn) -> list:
    return [
        fk
        for fk in inspect(conn).get_foreign_keys("lti_resource_links")
        if fk["constrained_columns"] == ["task_id"]
    ]


def _registration(db: Session) -> str:
    from models import LtiPlatformRegistration, Organization

    org = _uid()
    db.add(Organization(id=org, name=org, display_name=org, slug=f"org-{org[:8]}"))
    db.flush()
    reg = _uid()
    db.add(
        LtiPlatformRegistration(
            id=reg,
            organization_id=org,
            name="Moodle",
            issuer=f"https://moodle-{reg[:8]}.example",
            client_id="c-1",
            auth_login_url="https://x/a",
            auth_token_url="https://x/t",
            jwks_uri="https://x/j",
            status="active",
        )
    )
    db.flush()
    return reg


def _exam(db: Session, tasks: int) -> tuple:
    from models import User
    from project_models import Project, Task

    owner = _uid()
    db.add(User(id=owner, username=owner, email=f"{owner[:8]}@example.com", name="U"))
    db.flush()
    project = Project(id=_uid(), title="Klausur", created_by=owner, kind="exam")
    db.add(project)
    db.flush()
    task_ids = []
    for index in range(tasks):
        task_ids.append(_uid())
        db.add(
            Task(
                id=task_ids[-1],
                project_id=project.id,
                inner_id=index + 1,
                data={"text": "S"},
            )
        )
    db.flush()
    return project.id, task_ids


def _link(conn, reg: str, project_id) -> str:
    link = _uid()
    conn.execute(
        text(
            "INSERT INTO lti_resource_links (id, registration_id, deployment_id, "
            "resource_link_id, project_id, sync_ai_grades, created_at) "
            "VALUES (:id, :r, '1', :rl, :p, true, now())"
        ),
        {"id": link, "r": reg, "rl": f"rl-{link[:8]}", "p": project_id},
    )
    return link




def _scopes(conn, link_ids) -> dict:
    return {
        row.id: (row.task_id, row.grade_scope)
        for row in conn.execute(
            text(
                "SELECT id, task_id, grade_scope FROM lti_resource_links "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": list(link_ids)},
        )
    }


def _table_columns(conn, table) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _table_indexes(conn, table) -> dict:
    return {ix["name"]: ix for ix in inspect(conn).get_indexes(table)}


def _checks(conn, table) -> set:
    return {ck["name"] for ck in inspect(conn).get_check_constraints(table)}


def _fks(conn, table) -> dict:
    return {
        tuple(fk["constrained_columns"]): fk
        for fk in inspect(conn).get_foreign_keys(table)
    }


def _sync_unique(conn):
    """(columns, nulls_not_distinct) of uq_lti_grade_sync, or None."""
    row = conn.execute(
        text(
            "SELECT array_agg(a.attname ORDER BY k.ord) AS cols, "
            "       i.indnullsnotdistinct AS nnd "
            "  FROM pg_constraint c "
            "  JOIN pg_index i ON i.indexrelid = c.conindid "
            "  CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) "
            "  JOIN pg_attribute a "
            "    ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
            " WHERE c.conrelid = 'lti_grade_syncs'::regclass "
            "   AND c.conname = 'uq_lti_grade_sync' "
            " GROUP BY i.indnullsnotdistinct"
        )
    ).first()
    return None if row is None else (list(row.cols), row.nnd)


def _user(db: Session) -> str:
    from models import User

    user = _uid()
    db.add(User(id=user, username=user, email=f"{user[:8]}@example.com", name="S"))
    db.flush()
    return user


def _sync(conn, link: str, user: str, kind: str = "final", task=None) -> str:
    row = _uid()
    conn.execute(
        text(
            "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind, "
            "task_id) VALUES (:i, :l, :u, :k, :t)"
        ),
        {"i": row, "l": link, "u": user, "k": kind, "t": task},
    )
    return row


def _lineitem(conn, link: str, task: str, kind: str = "final", status=None) -> str:
    row = _uid()
    conn.execute(
        text(
            "INSERT INTO lti_task_lineitems (id, resource_link_id, task_id, kind, "
            "lineitem_url, status) VALUES (:i, :l, :t, :k, :u, :s)"
        ),
        {
            "i": row,
            "l": link,
            "t": task,
            "k": kind,
            "u": f"https://lms.example/li/{row[:8]}",
            "s": status,
        },
    )
    return row


def _ids(conn, table: str, ids) -> set:
    return set(
        conn.execute(
            text(f"SELECT id FROM {table} WHERE id = ANY(:ids)"), {"ids": list(ids)}
        ).scalars()
    )


def _rejects(conn, sql: str, params: dict) -> None:
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(text(sql), params)


class TestMigration112Chain:
    def test_revision_chains_after_111(self):
        mig = _load_migration()
        assert mig.revision == "112_lti_resource_link_task"
        assert mig.down_revision == "111_group_membership_roles"
        assert mig.GRADE_SCOPES == ("exam", "task", "collection")


class TestMigration112Models:
    def test_resource_link_task_and_scope(self):
        from models import LtiResourceLink
        from sqlalchemy import CheckConstraint

        table = LtiResourceLink.__table__
        column = table.columns["task_id"]
        assert column.nullable is True
        (fk,) = column.foreign_keys
        assert fk.target_fullname == "tasks.id"
        assert fk.ondelete == "SET NULL"
        indexes = {ix.name: ix for ix in table.indexes}
        assert [c.name for c in indexes["ix_lti_resource_links_task"].columns] == [
            "task_id"
        ]

        scope = table.columns["grade_scope"]
        assert scope.nullable is False
        assert scope.type.length == 16
        assert scope.server_default.arg == "exam"
        checks = {
            c.name: str(c.sqltext)
            for c in table.constraints
            if isinstance(c, CheckConstraint)
        }
        assert "ck_lti_resource_links_grade_scope" in checks
        for value in ("exam", "task", "collection"):
            assert f"'{value}'" in checks["ck_lti_resource_links_grade_scope"]

    def test_grade_sync_task_and_uniqueness(self):
        from models import LtiGradeSync
        from sqlalchemy import UniqueConstraint

        table = LtiGradeSync.__table__
        column = table.columns["task_id"]
        assert column.nullable is True
        (fk,) = column.foreign_keys
        assert fk.target_fullname == "tasks.id"
        assert fk.ondelete == "CASCADE"
        indexes = {ix.name: ix for ix in table.indexes}
        assert [c.name for c in indexes["ix_lti_grade_syncs_task"].columns] == [
            "task_id"
        ]
        (unique,) = [
            c
            for c in table.constraints
            if isinstance(c, UniqueConstraint) and c.name == "uq_lti_grade_sync"
        ]
        assert [c.name for c in unique.columns] == [
            "resource_link_id",
            "user_id",
            "kind",
            "task_id",
        ]
        assert unique.dialect_options["postgresql"]["nulls_not_distinct"] is True

    def test_task_lineitem_model(self):
        from models import LtiTaskLineitem
        from sqlalchemy import UniqueConstraint

        table = LtiTaskLineitem.__table__
        assert table.name == "lti_task_lineitems"
        columns = table.columns
        assert set(columns.keys()) == {
            "id",
            "resource_link_id",
            "task_id",
            "kind",
            "lineitem_url",
            "status",
            "error",
            "created_at",
            "updated_at",
        }
        for name, target in (
            ("resource_link_id", "lti_resource_links.id"),
            ("task_id", "tasks.id"),
        ):
            (fk,) = columns[name].foreign_keys
            assert fk.target_fullname == target
            assert fk.ondelete == "CASCADE"
            assert columns[name].nullable is False
        assert columns["kind"].nullable is False
        for name in ("lineitem_url", "status", "error", "updated_at"):
            assert columns[name].nullable is True
        (unique,) = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
        assert unique.name == "uq_lti_task_lineitem"
        assert [c.name for c in unique.columns] == [
            "resource_link_id",
            "task_id",
            "kind",
        ]
        indexes = {ix.name: [c.name for c in ix.columns] for ix in table.indexes}
        assert indexes["ix_lti_task_lineitems_resource_link"] == ["resource_link_id"]
        assert indexes["ix_lti_task_lineitems_task"] == ["task_id"]
        names = {c.name for c in table.constraints if c.name}
        assert {"ck_lti_task_lineitems_kind", "ck_lti_task_lineitems_status"} <= names


def _assert_full_shape(conn):
    links = _table_columns(conn, "lti_resource_links")
    assert links["task_id"]["nullable"] is True
    assert links["grade_scope"]["nullable"] is False
    assert "exam" in str(links["grade_scope"]["default"])
    assert "ck_lti_resource_links_grade_scope" in _checks(conn, "lti_resource_links")
    assert _table_indexes(conn, "lti_resource_links")["ix_lti_resource_links_task"][
        "column_names"
    ] == ["task_id"]
    link_fk = _fks(conn, "lti_resource_links")[("task_id",)]
    assert link_fk["referred_table"] == "tasks"
    assert link_fk["options"].get("ondelete") == "SET NULL"

    syncs = _table_columns(conn, "lti_grade_syncs")
    assert syncs["task_id"]["nullable"] is True
    assert _table_indexes(conn, "lti_grade_syncs")["ix_lti_grade_syncs_task"][
        "column_names"
    ] == ["task_id"]
    sync_fk = _fks(conn, "lti_grade_syncs")[("task_id",)]
    assert sync_fk["referred_table"] == "tasks"
    assert sync_fk["options"].get("ondelete") == "CASCADE"
    assert _sync_unique(conn) == (
        ["resource_link_id", "user_id", "kind", "task_id"],
        True,
    )

    assert "lti_task_lineitems" in inspect(conn).get_table_names()
    lineitems = _table_columns(conn, "lti_task_lineitems")
    assert set(lineitems) == {
        "id",
        "resource_link_id",
        "task_id",
        "kind",
        "lineitem_url",
        "status",
        "error",
        "created_at",
        "updated_at",
    }
    fks = _fks(conn, "lti_task_lineitems")
    assert fks[("resource_link_id",)]["referred_table"] == "lti_resource_links"
    assert fks[("resource_link_id",)]["options"].get("ondelete") == "CASCADE"
    assert fks[("task_id",)]["referred_table"] == "tasks"
    assert fks[("task_id",)]["options"].get("ondelete") == "CASCADE"
    uniques = {
        uq["name"]: uq["column_names"]
        for uq in inspect(conn).get_unique_constraints("lti_task_lineitems")
    }
    assert uniques["uq_lti_task_lineitem"] == ["resource_link_id", "task_id", "kind"]
    indexes = _table_indexes(conn, "lti_task_lineitems")
    assert indexes["ix_lti_task_lineitems_resource_link"]["column_names"] == [
        "resource_link_id"
    ]
    assert indexes["ix_lti_task_lineitems_task"]["column_names"] == ["task_id"]
    assert {
        "ck_lti_task_lineitems_kind",
        "ck_lti_task_lineitems_status",
    } <= _checks(conn, "lti_task_lineitems")


class TestMigration112UpDown:
    def test_upgrade_is_idempotent_on_current_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        _assert_full_shape(conn)
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_full_shape(conn)

    def test_downgrade_removes_everything_then_upgrade_backfills(
        self, test_db: Session
    ):
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        single, (only_task,) = _exam(test_db, tasks=1)
        collection, _ = _exam(test_db, tasks=2)
        empty, _ = _exam(test_db, tasks=0)
        with _op_context(conn):
            mig.downgrade()
            assert not {"task_id", "grade_scope"} & set(
                _table_columns(conn, "lti_resource_links")
            )
            assert "ix_lti_resource_links_task" not in _table_indexes(
                conn, "lti_resource_links"
            )
            assert "ck_lti_resource_links_grade_scope" not in _checks(
                conn, "lti_resource_links"
            )
            assert ("task_id",) not in _fks(conn, "lti_resource_links")
            assert "task_id" not in _table_columns(conn, "lti_grade_syncs")
            assert "ix_lti_grade_syncs_task" not in _table_indexes(
                conn, "lti_grade_syncs"
            )
            assert _sync_unique(conn) == (
                ["resource_link_id", "user_id", "kind"],
                False,
            )
            assert "lti_task_lineitems" not in inspect(conn).get_table_names()
            # A second downgrade finds nothing left to remove.
            mig.downgrade()

            links = {
                "single": _link(conn, reg, single),
                "single_second": _link(conn, reg, single),
                "collection": _link(conn, reg, collection),
                "empty": _link(conn, reg, empty),
                "unbound": _link(conn, reg, None),
            }
            mig.upgrade()

        assert _scopes(conn, links.values()) == {
            links["single"]: (only_task, "task"),
            links["single_second"]: (only_task, "task"),
            links["collection"]: (None, "exam"),
            links["empty"]: (None, "exam"),
            links["unbound"]: (None, "exam"),
        }
        _assert_full_shape(conn)

    def test_downgrade_drops_per_task_sync_rows_only(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (first, second) = _exam(test_db, tasks=2)
        student = _user(test_db)
        link = _link(conn, reg, project)
        main = _sync(conn, link, student)
        ai = _sync(conn, link, student, kind="ai")
        per_task = {
            _sync(conn, link, student, task=first),
            _sync(conn, link, student, task=second),
            _sync(conn, link, student, kind="ai", task=first),
        }
        with _op_context(conn):
            mig.downgrade()
        assert _ids(conn, "lti_grade_syncs", per_task | {main, ai}) == {main, ai}
        with _op_context(conn):
            mig.upgrade()
        _assert_full_shape(conn)

    def test_backfills_keep_existing_bindings_and_scopes(self, test_db: Session):
        """A re-run never rewrites a bound link or a chosen scope."""
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (first, _second) = _exam(test_db, tasks=2)
        _single, (only_task,) = _exam(test_db, tasks=1)
        bound = _link(conn, reg, project)
        whole = _link(conn, reg, project)
        collection = _link(conn, reg, project)
        conn.execute(
            text(
                "UPDATE lti_resource_links SET task_id = :t, grade_scope = 'task' "
                "WHERE id = :id"
            ),
            {"t": first, "id": bound},
        )
        conn.execute(
            text(
                "UPDATE lti_resource_links SET grade_scope = 'collection' "
                "WHERE id = :id"
            ),
            {"id": collection},
        )
        conn.execute(text(mig.BACKFILL_SQL))
        conn.execute(text(mig.SCOPE_BACKFILL_SQL))
        assert _scopes(conn, [bound, whole, collection]) == {
            bound: (first, "task"),
            whole: (None, "exam"),
            collection: (None, "collection"),
        }
        assert only_task


class TestMigration112ResourceLinks:
    def test_new_links_default_to_exam_scope(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, _ = _exam(test_db, tasks=2)
        link = _link(conn, reg, project)
        assert _scopes(conn, [link]) == {link: (None, "exam")}

    def test_check_rejects_unknown_scope(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        link = _link(conn, reg, None)
        _rejects(
            conn,
            "UPDATE lti_resource_links SET grade_scope = 'course' WHERE id = :id",
            {"id": link},
        )
        _rejects(
            conn,
            "UPDATE lti_resource_links SET grade_scope = NULL WHERE id = :id",
            {"id": link},
        )

    def test_collection_scope_keeps_task_null(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, _ = _exam(test_db, tasks=3)
        link = _link(conn, reg, project)
        conn.execute(
            text(
                "UPDATE lti_resource_links SET grade_scope = 'collection' "
                "WHERE id = :id"
            ),
            {"id": link},
        )
        assert _scopes(conn, [link]) == {link: (None, "collection")}

    def test_deleting_the_task_keeps_the_task_scope(self, test_db: Session):
        """ON DELETE SET NULL works although the scope stays 'task': no
        constraint ties the scope to task_id (the link goes idle with
        task_missing in extended)."""
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (only_task,) = _exam(test_db, tasks=1)
        link = _link(conn, reg, project)
        conn.execute(text(mig.BACKFILL_SQL))
        conn.execute(text(mig.SCOPE_BACKFILL_SQL))
        assert _scopes(conn, [link]) == {link: (only_task, "task")}

        conn.execute(text("DELETE FROM tasks WHERE id = :t"), {"t": only_task})
        assert _scopes(conn, [link]) == {link: (None, "task")}


class TestMigration112GradeSyncs:
    def test_null_task_counts_as_one_value(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, (first, second) = _exam(test_db, tasks=2)
        student = _user(test_db)
        link = _link(conn, reg, project)

        _sync(conn, link, student)
        # Two NULL-task rows for the same link, user and kind conflict.
        _rejects(
            conn,
            "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind) "
            "VALUES (:i, :l, :u, 'final')",
            {"i": _uid(), "l": link, "u": student},
        )
        # Different tasks (and the other kind) do not.
        _sync(conn, link, student, kind="ai")
        _sync(conn, link, student, task=first)
        _sync(conn, link, student, task=second)
        _sync(conn, link, student, kind="ai", task=first)
        # The same task twice does.
        _rejects(
            conn,
            "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind, "
            "task_id) VALUES (:i, :l, :u, 'final', :t)",
            {"i": _uid(), "l": link, "u": student, "t": first},
        )
        count = conn.execute(
            text("SELECT count(*) FROM lti_grade_syncs WHERE resource_link_id = :l"),
            {"l": link},
        ).scalar()
        assert count == 5

    @pytest.mark.parametrize("task_index", [None, 0])
    def test_upsert_targets_the_constraint(self, test_db: Session, task_index):
        """``on_conflict_do_*(constraint="uq_lti_grade_sync")`` is the upsert
        target, also for the NULL-task row."""
        from models import LtiGradeSync

        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, tasks = _exam(test_db, tasks=2)
        task = None if task_index is None else tasks[task_index]
        student = _user(test_db)
        link = _link(conn, reg, project)
        first = _sync(conn, link, student, task=task)

        values = {
            "resource_link_id": link,
            "user_id": student,
            "kind": "final",
            "task_id": task,
            "status": "pending",
        }
        conn.execute(
            insert(LtiGradeSync)
            .values(id=_uid(), **values)
            .on_conflict_do_nothing(constraint="uq_lti_grade_sync")
        )
        conn.execute(
            insert(LtiGradeSync)
            .values(id=_uid(), **values)
            .on_conflict_do_update(
                constraint="uq_lti_grade_sync", set_={"status": "synced"}
            )
        )
        rows = conn.execute(
            text(
                "SELECT id, status FROM lti_grade_syncs WHERE resource_link_id = :l"
            ),
            {"l": link},
        ).all()
        assert [(row.id, row.status) for row in rows] == [(first, "synced")]

    def test_task_delete_cascades_to_its_rows(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, (first, second) = _exam(test_db, tasks=2)
        student = _user(test_db)
        link = _link(conn, reg, project)
        main = _sync(conn, link, student)
        on_first = _sync(conn, link, student, task=first)
        on_second = _sync(conn, link, student, task=second)

        conn.execute(text("DELETE FROM tasks WHERE id = :t"), {"t": first})
        assert _ids(conn, "lti_grade_syncs", [main, on_first, on_second]) == {
            main,
            on_second,
        }


class TestMigration112TaskLineitems:
    def test_one_column_per_link_task_and_kind(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, (first, second) = _exam(test_db, tasks=2)
        link = _link(conn, reg, project)
        other = _link(conn, reg, project)

        _lineitem(conn, link, first)
        _lineitem(conn, link, first, kind="ai", status="ready")
        _lineitem(conn, link, second, status="error")
        _lineitem(conn, other, first)
        _rejects(
            conn,
            "INSERT INTO lti_task_lineitems (id, resource_link_id, task_id, kind) "
            "VALUES (:i, :l, :t, 'final')",
            {"i": _uid(), "l": link, "t": first},
        )

    def test_checks_and_defaults(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, (task,) = _exam(test_db, tasks=1)
        link = _link(conn, reg, project)

        row = _lineitem(conn, link, task)
        created = conn.execute(
            text("SELECT status, created_at FROM lti_task_lineitems WHERE id = :i"),
            {"i": row},
        ).one()
        assert created.status is None and created.created_at is not None
        for status in ("ready", "unavailable", "error", "deleted"):
            conn.execute(
                text("UPDATE lti_task_lineitems SET status = :s WHERE id = :i"),
                {"s": status, "i": row},
            )
        _rejects(
            conn,
            "UPDATE lti_task_lineitems SET status = 'pending' WHERE id = :i",
            {"i": row},
        )
        _rejects(
            conn,
            "UPDATE lti_task_lineitems SET kind = 'main' WHERE id = :i",
            {"i": row},
        )
        _rejects(
            conn,
            "INSERT INTO lti_task_lineitems (id, resource_link_id, task_id) "
            "VALUES (:i, :l, :t)",
            {"i": _uid(), "l": link, "t": task},
        )

    def test_link_and_task_deletes_cascade(self, test_db: Session):
        conn = test_db.get_bind()
        reg = _registration(test_db)
        project, (first, second) = _exam(test_db, tasks=2)
        link = _link(conn, reg, project)
        other = _link(conn, reg, project)
        on_first = _lineitem(conn, link, first)
        on_second = _lineitem(conn, link, second)
        other_first = _lineitem(conn, other, first)
        other_second = _lineitem(conn, other, second)

        conn.execute(text("DELETE FROM tasks WHERE id = :t"), {"t": first})
        assert _ids(
            conn, "lti_task_lineitems", [on_first, on_second, other_first, other_second]
        ) == {on_second, other_second}

        conn.execute(text("DELETE FROM lti_resource_links WHERE id = :l"), {"l": link})
        assert _ids(conn, "lti_task_lineitems", [on_second, other_second]) == {
            other_second
        }


class TestMigration112ProdCompatibility:
    """The prod state before 112: links on single-task exams with sent
    ``final`` rows. The upgrade binds the links, never touches the rows."""

    _SYNC_COLUMNS = (
        "id, resource_link_id, user_id, kind, status, attempts, next_retry_at, "
        "last_synced_at, last_synced_score, last_synced_hash, "
        "last_synced_source, last_checked_at, source_task_evaluation_id, "
        "last_error, created_at, updated_at"
    )

    def _sync_row(self, conn, row_id):
        return conn.execute(
            text(f"SELECT {self._SYNC_COLUMNS} FROM lti_grade_syncs WHERE id = :i"),
            {"i": row_id},
        ).one()

    def test_upgrade_binds_links_and_keeps_sent_rows(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        single, (only_task,) = _exam(test_db, tasks=1)
        legacy, _ = _exam(test_db, tasks=2)
        student = _user(test_db)

        with _op_context(conn):
            mig.downgrade()
        single_link = _link(conn, reg, single)
        legacy_link = _link(conn, reg, legacy)
        sent = _uid()
        conn.execute(
            text(
                "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind, "
                "status, attempts, last_synced_at, last_synced_score, "
                "last_synced_hash, last_synced_source, last_checked_at) "
                "VALUES (:i, :l, :u, 'final', 'synced', 1, now(), 14.0, "
                "'h-1', 'human', now())"
            ),
            {"i": sent, "l": single_link, "u": student},
        )
        before = self._sync_row(conn, sent)

        with _op_context(conn):
            mig.upgrade()

        assert _scopes(conn, [single_link, legacy_link]) == {
            single_link: (only_task, "task"),
            legacy_link: (None, "exam"),
        }
        assert self._sync_row(conn, sent) == before
        task_id = conn.execute(
            text("SELECT task_id FROM lti_grade_syncs WHERE id = :i"), {"i": sent}
        ).scalar()
        assert task_id is None
        # An old writer (no task_id) still hits the same row through the
        # kept constraint name.
        conn.execute(
            text(
                "INSERT INTO lti_grade_syncs (id, resource_link_id, user_id, kind) "
                "VALUES (:i, :l, :u, 'final') "
                "ON CONFLICT ON CONSTRAINT uq_lti_grade_sync DO NOTHING"
            ),
            {"i": _uid(), "l": single_link, "u": student},
        )
        count = conn.execute(
            text(
                "SELECT count(*) FROM lti_grade_syncs WHERE resource_link_id = :l"
            ),
            {"l": single_link},
        ).scalar()
        assert count == 1

    def test_downgrade_keeps_null_task_rows_unchanged(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (task,) = _exam(test_db, tasks=1)
        student = _user(test_db)
        link = _link(conn, reg, project)
        row = _sync(conn, link, student)
        before = self._sync_row(conn, row)
        with _op_context(conn):
            mig.downgrade()
        assert self._sync_row(conn, row) == before
        assert task
