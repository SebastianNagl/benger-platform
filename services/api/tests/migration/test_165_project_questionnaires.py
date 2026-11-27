"""Migration 165: project questionnaires and one answer store, exact backfill.

The shared test DB is built by ``Base.metadata.create_all``, so the new
tables exist; ``upgrade()`` then only runs the backfill over the rows a test
seeds into the #1208 columns and ``post_annotation_responses``. Every test
runs inside the ``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "165_project_questionnaires.py",
    )
)

CONFIG = (
    '<View><Rating name="confidence" toName="confidence" maxRating="5" '
    'required="true"/></View>'
)


def _uid() -> str:
    return str(uuid.uuid4())


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_165", MIGRATION_PATH)
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


def _user(db: Session):
    from models import User

    user = User(
        id=_uid(), username=f"m-{_uid()[:8]}", email=f"{_uid()[:8]}@example.com",
        name="Migration User", is_active=True, email_verified=True,
    )
    db.add(user)
    db.flush()
    return user


def _project(db: Session, user, *, enabled=False, config=None):
    from project_models import Project

    project = Project(
        id=_uid(), title="Migration 165", created_by=user.id,
        questionnaire_enabled=enabled, questionnaire_config=config,
    )
    db.add(project)
    db.flush()
    return project


def _annotation(db: Session, project, user, inner_id=1):
    from project_models import Annotation, Task

    task = Task(id=_uid(), project_id=project.id, data={}, inner_id=inner_id)
    db.add(task)
    db.flush()
    annotation = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id, completed_by=user.id, result=[]
    )
    db.add(annotation)
    db.flush()
    return task, annotation


def _old_answer(conn, project, task, annotation, user, *, result, config_hash=None, created_at):
    answer_id = _uid()
    conn.execute(
        text(
            "INSERT INTO post_annotation_responses "
            "(id, annotation_id, task_id, project_id, user_id, result, config_hash, created_at) "
            "VALUES (:id, :a, :t, :p, :u, CAST(:r AS JSONB), :h, :c)"
        ),
        {
            "id": answer_id, "a": annotation.id, "t": task.id, "p": project.id,
            "u": user.id, "r": json.dumps(result), "h": config_hash, "c": created_at,
        },
    )
    return answer_id


def _upgrade(conn, times=1):
    mig = _load_migration()
    with _op_context(conn):
        for _ in range(times):
            mig.upgrade()


def _questionnaires(conn, project_id):
    return conn.execute(
        text(
            "SELECT id, trigger, enabled, config, required, frequency, version "
            "FROM project_questionnaires WHERE project_id = :p"
        ),
        {"p": project_id},
    ).mappings().all()


def _answers(conn, project_id):
    return conn.execute(
        text(
            "SELECT * FROM questionnaire_responses WHERE project_id = :p ORDER BY created_at"
        ),
        {"p": project_id},
    ).mappings().all()


class TestMigration165:
    def test_revision_chains_after_164(self):
        mig = _load_migration()
        assert mig.revision == "165_project_questionnaires"
        assert mig.down_revision == "164_questionnaire_response_unique_and_hash"

    def test_tables_match_the_models(self, test_db: Session):
        names = set(inspect(test_db.get_bind()).get_table_names())
        assert {
            "project_questionnaires",
            "project_questionnaire_versions",
            "questionnaire_responses",
        } <= names

    def test_post_annotation_questionnaire_becomes_after_submit(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)

        _upgrade(conn)

        (q,) = _questionnaires(conn, project.id)
        assert q["trigger"] == "after_submit"
        assert q["enabled"] is True
        assert q["config"] == CONFIG
        # The old modal could not be dismissed and came after every submission.
        assert q["required"] is True
        assert q["frequency"] == "once_per_submission"
        assert q["version"] == 1
        version = conn.execute(
            text(
                "SELECT version, config, config_hash FROM project_questionnaire_versions "
                "WHERE questionnaire_id = :q"
            ),
            {"q": q["id"]},
        ).mappings().one()
        assert dict(version) == {"version": 1, "config": CONFIG, "config_hash": _sha(CONFIG)}

    def test_answers_are_copied_exactly(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)
        task1, ann1 = _annotation(test_db, project, user, 1)
        task2, ann2 = _annotation(test_db, project, user, 2)
        t0 = datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)
        result1 = [{"from_name": "confidence", "type": "rating", "value": {"rating": 4}}]
        result2 = [{"from_name": "confidence", "type": "rating", "value": {"rating": 2}}]
        # Answered the config being migrated (hash recorded since 164) ...
        id1 = _old_answer(
            conn, project, task1, ann1, user, result=result1,
            config_hash=_sha(CONFIG), created_at=t0,
        )
        # ... and one from before hashes existed: its text is not known.
        id2 = _old_answer(
            conn, project, task2, ann2, user, result=result2, created_at=t0 + timedelta(hours=1)
        )

        _upgrade(conn)

        (q,) = _questionnaires(conn, project.id)
        first, second = _answers(conn, project.id)
        assert first["id"] == id1 and second["id"] == id2
        for row, task, ann, result in ((first, task1, ann1, result1), (second, task2, ann2, result2)):
            assert row["questionnaire_id"] == q["id"]
            assert row["trigger"] == "after_submit"
            assert row["user_id"] == user.id
            assert row["task_id"] == task.id
            assert row["annotation_id"] == ann.id
            assert row["task_evaluation_id"] is None
            assert row["subject_key"] == f"annotation:{ann.id}"
            assert row["skipped"] is False
            assert row["result"] == result
        assert first["created_at"] == t0
        assert second["created_at"] == t0 + timedelta(hours=1)
        assert first["questionnaire_version"] == 1
        assert first["config_hash"] == _sha(CONFIG)
        assert second["questionnaire_version"] is None
        assert second["config_hash"] is None

    def test_hash_of_an_edited_config_keeps_the_version_unknown(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)
        task, ann = _annotation(test_db, project, user)
        _old_answer(
            conn, project, task, ann, user, result=[],
            config_hash=_sha("<View>an earlier text</View>"),
            created_at=datetime.now(timezone.utc),
        )

        _upgrade(conn)

        (row,) = _answers(conn, project.id)
        assert row["questionnaire_version"] is None
        assert row["config_hash"] == _sha("<View>an earlier text</View>")

    def test_switched_off_and_answered_projects_keep_their_state(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        configured_off = _project(test_db, user, enabled=False, config=CONFIG)
        # Switched on but never configured: shown to nobody, kept so.
        on_empty = _project(test_db, user, enabled=True, config=None)
        # Switched off and cleared after answers came in: the answers stay.
        answered = _project(test_db, user, enabled=False, config=None)
        task, ann = _annotation(test_db, answered, user)
        _old_answer(
            conn, answered, task, ann, user, result=[{"x": 1}],
            created_at=datetime.now(timezone.utc),
        )
        untouched = _project(test_db, user)

        _upgrade(conn)

        (q,) = _questionnaires(conn, configured_off.id)
        assert (q["enabled"], q["config"], q["version"]) == (False, CONFIG, 1)
        (q,) = _questionnaires(conn, on_empty.id)
        assert (q["enabled"], q["config"], q["version"]) == (True, None, 0)
        (q,) = _questionnaires(conn, answered.id)
        assert (q["enabled"], q["config"], q["version"]) == (False, None, 0)
        assert len(_answers(conn, answered.id)) == 1
        assert _questionnaires(conn, untouched.id) == []

    def test_idempotent(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)
        task, ann = _annotation(test_db, project, user)
        _old_answer(conn, project, task, ann, user, result=[], created_at=datetime.now(timezone.utc))

        _upgrade(conn, times=2)

        assert len(_questionnaires(conn, project.id)) == 1
        assert len(_answers(conn, project.id)) == 1

    def test_two_answers_for_one_annotation_are_both_kept(self, test_db: Session):
        conn = test_db.get_bind()
        conn.execute(text("DROP INDEX IF EXISTS ix_post_annotation_responses_annotation_id"))
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)
        task, ann = _annotation(test_db, project, user)
        t0 = datetime.now(timezone.utc)
        first = _old_answer(conn, project, task, ann, user, result=[{"n": 1}], created_at=t0)
        second = _old_answer(
            conn, project, task, ann, user, result=[{"n": 2}], created_at=t0 + timedelta(seconds=1)
        )

        _upgrade(conn)

        rows = _answers(conn, project.id)
        assert [r["id"] for r in rows] == [first, second]
        assert rows[0]["subject_key"] == f"annotation:{ann.id}"
        assert rows[1]["subject_key"] == f"annotation:{ann.id}#{second}"

    def test_downgrade_drops_the_new_tables_and_keeps_the_old_answers(self, test_db: Session):
        conn = test_db.get_bind()
        user = _user(test_db)
        project = _project(test_db, user, enabled=True, config=CONFIG)
        task, ann = _annotation(test_db, project, user)
        _old_answer(conn, project, task, ann, user, result=[], created_at=datetime.now(timezone.utc))
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.downgrade()
            mig.downgrade()  # idempotent
            names = set(inspect(conn).get_table_names())
            assert "questionnaire_responses" not in names
            assert "project_questionnaires" not in names
            kept = conn.execute(
                text("SELECT count(*) FROM post_annotation_responses WHERE project_id = :p"),
                {"p": project.id},
            ).scalar()
            assert kept == 1
            mig.upgrade()
        assert len(_answers(conn, project.id)) == 1
