"""Migration 112: LTI resource links can be bound to one task.

The shared test DB is built by ``Base.metadata.create_all`` (post-112
shape). The tests check the model and the live column (nullable, FK to
``tasks.id`` ON DELETE SET NULL, index), then ``downgrade()`` drops the
column, seeded pre-112 links are upgraded again and the backfill is checked:
a link on a one-task exam is bound to that task, links on a two-task exam,
an empty exam and an unbound activity stay NULL. Every test runs inside the
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


def _task_ids(conn, link_ids) -> dict:
    return dict(
        conn.execute(
            text("SELECT id, task_id FROM lti_resource_links WHERE id = ANY(:ids)"),
            {"ids": list(link_ids)},
        ).all()
    )


class TestMigration112Chain:
    def test_revision_chains_after_111(self):
        mig = _load_migration()
        assert mig.revision == "112_lti_resource_link_task"
        assert mig.down_revision == "111_group_membership_roles"

    def test_model_column_and_index(self):
        from models import LtiResourceLink

        column = LtiResourceLink.__table__.columns["task_id"]
        assert column.nullable is True
        (fk,) = column.foreign_keys
        assert fk.target_fullname == "tasks.id"
        assert fk.ondelete == "SET NULL"
        indexes = {ix.name: ix for ix in LtiResourceLink.__table__.indexes}
        assert [c.name for c in indexes["ix_lti_resource_links_task"].columns] == [
            "task_id"
        ]


class TestMigration112UpDown:
    def test_upgrade_is_idempotent_on_current_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert _columns(conn)["task_id"]["nullable"] is True
        assert _indexes(conn)["ix_lti_resource_links_task"]["column_names"] == [
            "task_id"
        ]
        (fk,) = _task_fks(conn)
        assert fk["referred_table"] == "tasks"
        assert fk["referred_columns"] == ["id"]
        assert fk["options"].get("ondelete") == "SET NULL"

    def test_downgrade_then_upgrade_backfills_single_task_exams(
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
            assert "task_id" not in _columns(conn)
            assert "ix_lti_resource_links_task" not in _indexes(conn)
            assert _task_fks(conn) == []

            links = {
                "single": _link(conn, reg, single),
                "single_second": _link(conn, reg, single),
                "collection": _link(conn, reg, collection),
                "empty": _link(conn, reg, empty),
                "unbound": _link(conn, reg, None),
            }
            mig.upgrade()

        bound = _task_ids(conn, links.values())
        assert bound == {
            links["single"]: only_task,
            links["single_second"]: only_task,
            links["collection"]: None,
            links["empty"]: None,
            links["unbound"]: None,
        }
        assert _columns(conn)["task_id"]["nullable"] is True
        assert "ix_lti_resource_links_task" in _indexes(conn)
        (fk,) = _task_fks(conn)
        assert fk["options"].get("ondelete") == "SET NULL"

    def test_backfill_keeps_existing_bindings(self, test_db: Session):
        """A link already bound (here to the first task of what is now a
        two-task exam) is never rewritten by a re-run."""
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (first, _second) = _exam(test_db, tasks=2)
        link = _link(conn, reg, project)
        conn.execute(
            text("UPDATE lti_resource_links SET task_id = :t WHERE id = :id"),
            {"t": first, "id": link},
        )
        conn.execute(text(mig.BACKFILL_SQL))
        assert _task_ids(conn, [link]) == {link: first}

    def test_deleting_the_task_turns_the_link_whole_exam(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        reg = _registration(test_db)
        project, (only_task,) = _exam(test_db, tasks=1)
        link = _link(conn, reg, project)
        conn.execute(text(mig.BACKFILL_SQL))
        assert _task_ids(conn, [link]) == {link: only_task}

        conn.execute(text("DELETE FROM tasks WHERE id = :t"), {"t": only_task})
        assert _task_ids(conn, [link]) == {link: None}
