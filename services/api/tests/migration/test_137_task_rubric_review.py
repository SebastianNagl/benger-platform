"""Shape tests for migration 137: the check step of grading sheets.

The shared test DB already carries the columns, the table and (through the
model's ``after_create`` listener) the append-only trigger, so ``upgrade()``
must be a no-op through its guards, twice. ``downgrade()`` removes all of it
and a re-run ``upgrade()`` rebuilds it. The trigger refuses every UPDATE of a
``task_rubric_review_events`` row except the two ``ON DELETE SET NULL``
actions; DELETE (cascades included) stays allowed.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)


def _load(name: str = "137_task_rubric_review"):
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


def _columns(conn, table):
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _has_trigger(conn) -> bool:
    return conn.execute(
        text(
            "SELECT 1 FROM pg_trigger WHERE tgname = "
            "'trg_task_rubric_review_events_append_only' AND NOT tgisinternal"
        )
    ).first() is not None


def _seed(test_db: Session):
    from models import User
    from project_models import Project, Task, TaskRubric

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig137-{suffix}", email=f"mig137-{suffix}@example.com",
        hashed_password="x", name="Mig 137",
    )
    owner = User(
        id=str(uuid.uuid4()), username=f"mig137o-{suffix}", email=f"mig137o-{suffix}@example.com",
        hashed_password="x", name="Owner 137",
    )
    test_db.add_all([user, owner])
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig137", created_by=owner.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, inner_id=1)
    test_db.add(task)
    test_db.flush()
    rubric = TaskRubric(
        id=str(uuid.uuid4()), task_id=task.id, project_id=project.id,
        criteria={"s01": {"name": "A", "rubric": "r", "max_score": 10}}, total_points=10,
    )
    test_db.add(rubric)
    test_db.flush()
    return user, project, task, rubric


def _event(conn, project, task, rubric, actor, **extra) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO task_rubric_review_events "
            "(id, project_id, task_id, rubric_id, actor_id, event, notes, checklist) "
            "VALUES (:id, :p, :t, :r, :a, :event, :notes, CAST(:checklist AS jsonb))"
        ),
        {
            "id": event_id, "p": project.id, "t": task.id, "r": rubric.id, "a": actor.id,
            "event": extra.get("event", "confirmed"), "notes": extra.get("notes"),
            "checklist": extra.get("checklist", '{"steps_complete": true}'),
        },
    )
    return event_id


def _row(conn, event_id):
    return conn.execute(
        text("SELECT * FROM task_rubric_review_events WHERE id = :id"), {"id": event_id}
    ).mappings().first()


class TestMigration137Shape:
    def test_revision_chains_after_136(self):
        mig = _load()
        assert mig.revision == "137_task_rubric_review"
        assert mig.down_revision == "136_rubric_generation_jobs"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        flag = _columns(conn, "projects")["rubric_review_required"]
        assert flag["nullable"] is False
        rubrics = _columns(conn, "task_rubrics")
        assert {"review_state", "reviewed_at", "reviewed_by"} <= set(rubrics)
        assert all(rubrics[c]["nullable"] for c in ("review_state", "reviewed_at", "reviewed_by"))
        from project_models import TaskRubricReviewEvent

        events = _columns(conn, "task_rubric_review_events")
        assert set(events) == {c.name for c in TaskRubricReviewEvent.__table__.columns}
        assert {i["name"] for i in inspect(conn).get_indexes("task_rubric_review_events")} >= {
            "ix_task_rubric_review_events_project_created",
            "ix_task_rubric_review_events_rubric_id",
        }
        assert "ix_task_rubrics_project_review_state" in {
            i["name"] for i in inspect(conn).get_indexes("task_rubrics")
        }
        assert _has_trigger(conn)

    def test_existing_projects_keep_the_flag_off(self, test_db: Session):
        _, project, _, _ = _seed(test_db)
        conn = test_db.get_bind()
        value = conn.execute(
            text("SELECT rubric_review_required FROM projects WHERE id = :id"), {"id": project.id}
        ).scalar_one()
        assert value is False

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "task_rubric_review_events" not in inspect(conn).get_table_names()
        assert "rubric_review_required" not in _columns(conn, "projects")
        assert "review_state" not in _columns(conn, "task_rubrics")
        assert not _has_trigger(conn)
        assert conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'task_rubric_review_events_append_only'")
        ).first() is None
        with _op_context(conn):
            mig.upgrade()
        assert "task_rubric_review_events" in inspect(conn).get_table_names()
        assert "reviewed_by" in _columns(conn, "task_rubrics")
        assert _has_trigger(conn)


class TestAppendOnly:
    def test_update_of_a_logged_field_is_refused(self, test_db: Session):
        user, project, task, rubric = _seed(test_db)
        conn = test_db.get_bind()
        event_id = _event(conn, project, task, rubric, user, notes="ok")
        for statement in (
            "UPDATE task_rubric_review_events SET notes = 'changed' WHERE id = :id",
            "UPDATE task_rubric_review_events SET checklist = '{}'::jsonb WHERE id = :id",
            "UPDATE task_rubric_review_events SET event = 'rejected' WHERE id = :id",
            # Re-pointing to another row is not one of the SET NULL actions.
            "UPDATE task_rubric_review_events SET actor_id = :other WHERE id = :id",
        ):
            savepoint = conn.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(text(statement), {"id": event_id, "other": project.created_by})
            savepoint.rollback()
        assert _row(conn, event_id)["notes"] == "ok"

    def test_setting_the_references_to_null_is_allowed(self, test_db: Session):
        user, project, task, rubric = _seed(test_db)
        conn = test_db.get_bind()
        event_id = _event(conn, project, task, rubric, user)
        conn.execute(
            text(
                "UPDATE task_rubric_review_events SET rubric_id = NULL, actor_id = NULL "
                "WHERE id = :id"
            ),
            {"id": event_id},
        )
        row = _row(conn, event_id)
        assert row["rubric_id"] is None and row["actor_id"] is None

    def test_on_delete_set_null_passes_the_trigger(self, test_db: Session):
        user, project, task, rubric = _seed(test_db)
        conn = test_db.get_bind()
        event_id = _event(conn, project, task, rubric, user)
        conn.execute(text("DELETE FROM task_rubrics WHERE id = :id"), {"id": rubric.id})
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        row = _row(conn, event_id)
        assert row is not None
        assert row["rubric_id"] is None and row["actor_id"] is None
        assert row["checklist"] == {"steps_complete": True}
        test_db.expire_all()

    def test_delete_and_the_task_cascade_are_allowed(self, test_db: Session):
        user, project, task, rubric = _seed(test_db)
        conn = test_db.get_bind()
        direct = _event(conn, project, task, rubric, user)
        cascaded = _event(conn, project, task, rubric, user, event="recorded")
        conn.execute(text("DELETE FROM task_rubric_review_events WHERE id = :id"), {"id": direct})
        assert _row(conn, direct) is None
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task.id})
        assert _row(conn, cascaded) is None
        test_db.expire_all()

    def test_the_orm_cannot_rewrite_an_event(self, test_db: Session):
        from project_models import TaskRubricReviewEvent

        user, project, task, rubric = _seed(test_db)
        event = TaskRubricReviewEvent(
            id=str(uuid.uuid4()), project_id=project.id, task_id=task.id,
            rubric_id=rubric.id, actor_id=user.id, event="edited", verdict="minor_edits",
        )
        test_db.add(event)
        test_db.flush()
        savepoint = test_db.begin_nested()
        event.verdict = "unchanged"
        with pytest.raises(DBAPIError, match="append-only"):
            test_db.flush()
        savepoint.rollback()
