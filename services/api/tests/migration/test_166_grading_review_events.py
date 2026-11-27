"""Migration 166: the review history of gradings and its exact backfill.

The shared test DB already carries the table and (through the model's
``after_create`` listener) the append-only trigger, so ``upgrade()`` must be
a no-op through its guards, twice, apart from the backfill of the rows it
holds. ``downgrade()`` removes it and a re-run ``upgrade()`` rebuilds it.
The trigger refuses every UPDATE except the three ``ON DELETE SET NULL``
actions; DELETE (cascades included) stays allowed. The backfill turns what
each stored review records (times and people) into entries, nothing more.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)

T1 = "2026-11-20T09:00:00+00:00"
T2 = "2026-11-21T10:30:00+00:00"
T3 = "2026-11-22T12:15:00+00:00"


def _load():
    name = "166_grading_review_events"
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


def _has_trigger(conn) -> bool:
    return conn.execute(
        text(
            "SELECT 1 FROM pg_trigger WHERE tgname = "
            "'trg_grading_review_events_append_only' AND NOT tgisinternal"
        )
    ).first() is not None


def _user(db, tag="u"):
    from models import User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig166{tag}-{suffix}",
        email=f"mig166{tag}-{suffix}@example.com", hashed_password="x", name="Mig 166",
    )
    db.add(user)
    db.flush()
    return user


class _Seed:
    def __init__(self, db: Session):
        from models import EvaluationJudgeRun, EvaluationRun
        from project_models import Annotation, Project, Task

        self.db = db
        self.teacher = _user(db, "t")
        self.student = _user(db, "s")
        self.owner = _user(db, "o")
        self.project = Project(id=str(uuid.uuid4()), title="mig166", created_by=self.owner.id)
        db.add(self.project)
        db.flush()
        self.task = Task(id=str(uuid.uuid4()), project_id=self.project.id, data={"text": "x"}, inner_id=1)
        db.add(self.task)
        db.flush()
        self.annotation = Annotation(
            id=str(uuid.uuid4()), task_id=self.task.id, project_id=self.project.id,
            completed_by=self.student.id, result=[],
        )
        db.add(self.annotation)
        self.run = EvaluationRun(
            id=str(uuid.uuid4()), project_id=self.project.id, model_id="immediate",
            evaluation_type_ids=[], metrics={}, status="completed", created_by=self.owner.id,
        )
        db.add(self.run)
        db.flush()
        self.judge_run = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=self.run.id)
        db.add(self.judge_run)
        db.flush()

    def grading(self, metrics, *, updated_at=None, config_id="cfg"):
        from models import TaskEvaluation

        row = TaskEvaluation(
            id=str(uuid.uuid4()), evaluation_id=self.run.id, judge_run_id=self.judge_run.id,
            task_id=self.task.id, annotation_id=self.annotation.id,
            field_name=f"loesung-{uuid.uuid4().hex[:8]}",
            evaluation_config_id=config_id, answer_type="text", ground_truth="",
            prediction="", metrics=metrics, passed=True,
        )
        self.db.add(row)
        self.db.flush()
        if updated_at is not None:
            # As an update after insert stamps it (migration 106).
            self.db.execute(
                text("UPDATE task_evaluations SET updated_at = :at WHERE id = :id"),
                {"at": updated_at, "id": row.id},
            )
        return row


def _feedback(review):
    return {"llm_judge_feedback": {"value": None, "method": "llm_judge_feedback",
                                   "details": {"feedback_only": True, "review": review}}}


def _events(conn, row_id):
    return [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT * FROM grading_review_events WHERE task_evaluation_id = :id "
                "ORDER BY created_at"
            ),
            {"id": row_id},
        ).mappings()
    ]


class TestShape:
    def test_revision_chains_after_165(self):
        mig = _load()
        assert mig.revision == "166_grading_review_events"
        assert mig.down_revision == "165_project_questionnaires"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        from models import GradingReviewEvent

        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        columns = {c["name"]: c for c in inspect(conn).get_columns("grading_review_events")}
        assert set(columns) == {c.name for c in GradingReviewEvent.__table__.columns}
        assert columns["event"]["nullable"] is False
        assert columns["task_evaluation_id"]["nullable"] is True
        assert {i["name"] for i in inspect(conn).get_indexes("grading_review_events")} >= {
            name for name, _ in mig._INDEXES
        }
        assert _has_trigger(conn)

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "grading_review_events" not in inspect(conn).get_table_names()
        assert not _has_trigger(conn)
        assert conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'grading_review_events_append_only'")
        ).first() is None
        with _op_context(conn):
            mig.upgrade()
        assert "grading_review_events" in inspect(conn).get_table_names()
        assert _has_trigger(conn)


def _insert_event(conn, seed, row, actor, **extra) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO grading_review_events (id, project_id, task_id, task_evaluation_id, "
            "annotation_id, actor_id, event, review_after) VALUES (:id, :p, :t, :te, :a, "
            ":actor, :event, CAST(:after AS jsonb))"
        ),
        {
            "id": event_id, "p": seed.project.id, "t": seed.task.id, "te": row.id,
            "a": seed.annotation.id, "actor": actor.id, "event": extra.get("event", "released"),
            "after": '{"status": "released"}',
        },
    )
    return event_id


def _row(conn, event_id):
    return conn.execute(
        text("SELECT * FROM grading_review_events WHERE id = :id"), {"id": event_id}
    ).mappings().first()


class TestAppendOnly:
    def test_update_of_a_logged_field_is_refused(self, test_db: Session):
        seed = _Seed(test_db)
        row = seed.grading({"bleu": {"value": 0.4}})
        conn = test_db.get_bind()
        event_id = _insert_event(conn, seed, row, seed.teacher)
        for statement in (
            "UPDATE grading_review_events SET event = 'edited' WHERE id = :id",
            "UPDATE grading_review_events SET review_after = '{}'::jsonb WHERE id = :id",
            "UPDATE grading_review_events SET created_at = created_at - interval '1 day' "
            "WHERE id = :id",
            # Re-pointing to another row is not one of the SET NULL actions.
            "UPDATE grading_review_events SET actor_id = :other WHERE id = :id",
        ):
            savepoint = conn.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(text(statement), {"id": event_id, "other": seed.student.id})
            savepoint.rollback()
        assert _row(conn, event_id)["event"] == "released"

    def test_set_null_actions_pass_the_trigger(self, test_db: Session):
        seed = _Seed(test_db)
        row = seed.grading({"bleu": {"value": 0.4}})
        conn = test_db.get_bind()
        event_id = _insert_event(conn, seed, row, seed.teacher)
        conn.execute(text("DELETE FROM task_evaluations WHERE id = :id"), {"id": row.id})
        conn.execute(text("DELETE FROM annotations WHERE id = :id"), {"id": seed.annotation.id})
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": seed.teacher.id})
        kept = _row(conn, event_id)
        assert kept is not None
        assert kept["task_evaluation_id"] is None
        assert kept["annotation_id"] is None
        assert kept["actor_id"] is None
        assert kept["review_after"] == {"status": "released"}
        test_db.expire_all()

    def test_delete_and_the_task_cascade_are_allowed(self, test_db: Session):
        seed = _Seed(test_db)
        row = seed.grading({"bleu": {"value": 0.4}})
        conn = test_db.get_bind()
        direct = _insert_event(conn, seed, row, seed.teacher)
        cascaded = _insert_event(conn, seed, row, seed.teacher, event="checked")
        conn.execute(text("DELETE FROM grading_review_events WHERE id = :id"), {"id": direct})
        assert _row(conn, direct) is None
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": seed.task.id})
        assert _row(conn, cascaded) is None
        test_db.expire_all()

    def test_the_orm_cannot_rewrite_an_event(self, test_db: Session):
        from models import GradingReviewEvent

        seed = _Seed(test_db)
        row = seed.grading({"bleu": {"value": 0.4}})
        event = GradingReviewEvent(
            id=str(uuid.uuid4()), project_id=seed.project.id, task_id=seed.task.id,
            task_evaluation_id=row.id, actor_id=seed.teacher.id, event="edited",
            review_after={"status": "draft"},
        )
        test_db.add(event)
        test_db.flush()
        savepoint = test_db.begin_nested()
        event.event = "released"
        with pytest.raises(DBAPIError, match="append-only"):
            test_db.flush()
        savepoint.rollback()


class TestReviewEvents:
    """What one stored review records, as entries (pure)."""

    def test_a_teacher_release_names_the_teacher(self):
        mig = _load()
        review = {
            "status": "released", "released_at": T2, "released_by": "teacher",
            "checked_at": T2, "checked_by": "t1", "reviewed_by": "t1", "updated_at": T2,
            "markdown": "edited",
        }
        events = mig.review_events(review)
        assert [(e["event"], e["at"], e["actor_id"]) for e in events] == [("released", T2, "t1")]
        assert events[0]["context"] == {"backfill": True, "released_by": "teacher"}
        assert events[0]["review_after"] == review

    def test_a_judge_release_has_no_person(self):
        mig = _load()
        review = {"status": "released", "auto": True, "released_by": "judge", "released_at": T1}
        (event,) = mig.review_events(review)
        assert event["actor_id"] is None
        assert event["context"] == {"backfill": True, "released_by": "judge", "auto": True}
        assert event["review_after"] == review

    def test_a_check_and_a_later_change_are_their_own_entries(self):
        mig = _load()
        review = {
            "status": "draft", "reason": "regrade", "checked_at": T1, "checked_by": "t1",
            "reviewed_by": "t2", "updated_at": T3,
        }
        events = mig.review_events(review)
        assert [(e["event"], e["at"], e["actor_id"]) for e in events] == [
            ("checked", T1, "t1"),
            ("updated", T3, "t2"),
        ]
        assert all(e["context"]["reason"] == "regrade" for e in events)
        assert "review_after" not in events[0]
        assert events[1]["review_after"] == review

    def test_a_release_after_a_judge_release_of_a_regrading(self):
        """A teacher's release of a regrading the judge had released keeps the
        leftover ``auto`` mark: it is still the teacher's release."""
        mig = _load()
        review = {
            "status": "released", "auto": True, "released_by": "teacher", "released_at": T2,
            "checked_at": T2, "checked_by": "t1", "reviewed_by": "t1", "updated_at": T2,
        }
        (event,) = mig.review_events(review)
        assert event["actor_id"] == "t1"

    def test_a_release_without_released_by_uses_the_same_call(self):
        mig = _load()
        stamped = {"status": "released", "released_at": T2, "reviewed_by": "t1", "updated_at": T2}
        assert mig.review_events(stamped)[0]["actor_id"] == "t1"
        # A later call by someone else does not tell who released.
        later = {"status": "released", "released_at": T1, "reviewed_by": "t2", "updated_at": T3}
        released, updated = mig.review_events(later)
        assert (released["event"], released["actor_id"]) == ("released", None)
        assert (updated["event"], updated["actor_id"]) == ("updated", "t2")

    def test_nothing_recorded_gives_nothing(self):
        mig = _load()
        assert mig.review_events({"status": "draft", "reason": "regrade"}) == []
        assert mig.review_events({"status": "draft"}) == []
        assert mig.review_events(None) == []
        # A time that does not parse is left out.
        assert mig.review_events({"status": "released", "released_at": "gestern"}) == []


class TestBackfill:
    def test_the_backfill_writes_what_the_reviews_record(self, test_db: Session):
        seed = _Seed(test_db)
        teacher = seed.teacher.id
        released = seed.grading(
            _feedback({
                "status": "released", "released_by": "teacher", "released_at": T2,
                "checked_at": T2, "checked_by": teacher, "reviewed_by": teacher,
                "updated_at": T2, "markdown": "Bien.",
            }),
            updated_at=datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc),
            config_id="feedback",
        )
        auto = seed.grading(
            _feedback({"status": "released", "auto": True, "released_by": "judge", "released_at": T1}),
            config_id="feedback",
        )
        # A flat re-graded score row a teacher checked; the row was updated.
        regraded = seed.grading(
            {
                "llm_judge_custom": 0.5,
                "llm_judge_custom_details": {"review": {
                    "status": "draft", "reason": "regrade", "checked_at": T1,
                    "checked_by": teacher, "reviewed_by": "someone-gone", "updated_at": T3,
                }},
            },
            updated_at=datetime(2026, 11, 22, 12, 15, tzinfo=timezone.utc),
            config_id="judge",
        )
        untouched = seed.grading(
            {"llm_judge_custom": {"value": 0.7, "details": {"review": {"status": "draft", "reason": "regrade"}}}},
            updated_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
        )
        plain = seed.grading({"bleu": {"value": 0.4, "details": {}}})
        test_db.flush()

        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # nothing twice

        (rel,) = _events(conn, released.id)
        assert rel["event"] == "released"
        assert rel["actor_id"] == teacher
        assert rel["created_at"] == datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc)
        assert rel["project_id"] == seed.project.id
        assert rel["task_id"] == seed.task.id
        assert rel["annotation_id"] == seed.annotation.id
        assert rel["evaluation_config_id"] == "feedback"
        assert rel["metric"] == "llm_judge_feedback"
        assert rel["review_after"]["markdown"] == "Bien."
        assert rel["review_before"] is None
        assert rel["context"] == {"backfill": True, "released_by": "teacher"}

        (judge,) = _events(conn, auto.id)
        assert judge["actor_id"] is None
        assert judge["context"]["released_by"] == "judge"

        checked, updated = _events(conn, regraded.id)
        assert (checked["event"], checked["actor_id"], checked["metric"]) == (
            "checked", teacher, "llm_judge_custom",
        )
        # An actor who is no longer a user stays empty, as SET NULL would.
        assert (updated["event"], updated["actor_id"]) == ("updated", None)
        assert updated["review_after"]["reason"] == "regrade"

        assert _events(conn, untouched.id) == []
        assert _events(conn, plain.id) == []

    def test_the_backfill_ids_are_stable(self):
        mig = _load()
        row = {
            "task_evaluation_id": "te1", "task_id": "t", "project_id": "p", "metric": "m",
            "review": {"status": "released", "released_at": T1, "released_by": "judge"},
        }
        first = mig.backfill_rows([row], [])
        assert [e["id"] for e in first] == [e["id"] for e in mig.backfill_rows([row], [])]
        assert first[0]["actor_id"] is None
