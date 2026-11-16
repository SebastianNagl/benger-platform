"""Concurrent project imports that share users (Kolibri-1 benchmark, K4).

Three full-project imports started within seconds of each other on one
deployment: two failed with ``LockNotAvailable ... "ix_users_email"``. Both
exports carried the same author, unknown on the importing deployment, so both
imports created the same placeholder account (its address is derived from the
source user id). The first import inserted it inside its own long import
transaction; the second insert waited for that uncommitted index entry until
the worker's ``lock_timeout`` ended it.

These tests run the imports on real, separately committing sessions (the
``test_db`` fixture shares one rolled-back connection, which cannot show a
lock between two transactions). The first import is held open right before
its commit while the second runs from start to finish, which is the overlap
the benchmark hit. Every row they commit is removed again afterwards.
"""

import io
import json
import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import User
from project_models import Annotation, Project, Task
from routers.projects._import_stream import (
    run_full_project_import,
    run_nested_import,
)

# The workers' session setting (services/workers/database.py), shortened so a
# regression fails in seconds instead of thirty.
_LOCK_TIMEOUT_MS = 2000
# How long the first import stays open waiting for the second one.
_OVERLAP_WAIT_S = 30


@pytest.fixture
def worker_like_sessions(test_db):
    """A session factory with the workers' lock_timeout, plus cleanup.

    ``test_db`` is requested only so the tables exist; nothing here runs in
    its rolled-back transaction.
    """
    engine = create_engine(
        os.environ["DATABASE_URL"],
        connect_args={"options": f"-c lock_timeout={_LOCK_TIMEOUT_MS}"},
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    created = {"users": set(), "titles": set(), "emails": set()}
    yield factory, created
    with engine.begin() as conn:
        project_ids = [
            row[0]
            for row in conn.execute(
                text("SELECT id FROM projects WHERE title = ANY(:t)"),
                {"t": list(created["titles"])},
            )
        ]
        if project_ids:
            conn.execute(
                text("DELETE FROM annotations WHERE project_id = ANY(:p)"),
                {"p": project_ids},
            )
            conn.execute(
                text("DELETE FROM tasks WHERE project_id = ANY(:p)"), {"p": project_ids}
            )
            conn.execute(
                text("DELETE FROM project_organizations WHERE project_id = ANY(:p)"),
                {"p": project_ids},
            )
            conn.execute(text("DELETE FROM projects WHERE id = ANY(:p)"), {"p": project_ids})
        conn.execute(
            text("DELETE FROM users WHERE id = ANY(:u) OR email = ANY(:e)"),
            {"u": list(created["users"]), "e": list(created["emails"])},
        )
    engine.dispose()


def _importer(factory, created) -> str:
    user_id = f"importer-{uuid.uuid4()}"
    with factory() as db:
        db.add(
            User(
                id=user_id,
                username=user_id,
                email=f"{user_id}@test.example",
                name="Importer",
                hashed_password="!",
                is_active=True,
                email_verified=True,
            )
        )
        db.commit()
    created["users"].add(user_id)
    return user_id


def _export(title: str, shared_users: list, pseudonym=None) -> bytes:
    """A comprehensive export whose single task carries one answer by each of
    ``shared_users`` (``(id, email)`` pairs unknown on this deployment)."""
    return json.dumps(
        {
            "format_version": "1.0.0",
            "project": {
                "title": title,
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            "users": [
                {"id": uid, "email": email, "name": "Source author", "pseudonym": pseudonym}
                for uid, email in shared_users
            ],
            "tasks": [{"id": "task-1", "data": {"text": "one"}}],
            "annotations": [
                {
                    "id": f"annotation-{n}",
                    "task_id": "task-1",
                    "completed_by": uid,
                    "result": [{"value": {"text": ["answer"]}, "from_name": "text"}],
                }
                for n, (uid, _email) in enumerate(shared_users)
            ],
        }
    ).encode("utf-8")


def _run_overlapping_imports(factory, created, shared_users, pseudonyms=(None, None)):
    """Import two exports sharing ``shared_users``; the first stays open right
    before its commit, with its rows written, until the second has finished. Returns both outcomes
    (a result dict or the exception) and the two project titles."""
    importer = _importer(factory, created)
    titles = [f"Concurrent import {n} {uuid.uuid4()}" for n in (1, 2)]
    created["titles"].update(titles)
    for uid, email in shared_users:
        created["users"].add(uid)
        created["emails"].update({email, f"{uid}@imported.invalid"})

    first_ready = threading.Event()
    second_done = threading.Event()
    outcomes = {}

    def hold_open(_result):
        first_ready.set()
        second_done.wait(_OVERLAP_WAIT_S)

    def run(name, title, pseudonym, before_commit):
        db = factory()
        try:
            outcomes[name] = run_full_project_import(
                db,
                io.BytesIO(_export(title, shared_users, pseudonym)),
                importer,
                before_commit=before_commit and (lambda r: (db.flush(), before_commit(r))),
            )
        except Exception as exc:  # noqa: BLE001 - the outcome is the assertion
            db.rollback()
            outcomes[name] = exc
        finally:
            db.close()

    first = threading.Thread(
        target=run, args=("first", titles[0], pseudonyms[0], hold_open)
    )
    first.start()
    try:
        assert first_ready.wait(_OVERLAP_WAIT_S), outcomes.get("first")
        run("second", titles[1], pseudonyms[1], None)
    finally:
        second_done.set()
        first.join(_OVERLAP_WAIT_S)
    return outcomes, titles


@pytest.mark.integration
def test_two_concurrent_imports_sharing_an_unknown_user_both_succeed(
    worker_like_sessions,
):
    factory, created = worker_like_sessions
    source_id = f"source-{uuid.uuid4()}"
    shared = [(source_id, f"{source_id}@source.example")]

    outcomes, titles = _run_overlapping_imports(factory, created, shared)

    for name in ("first", "second"):
        assert isinstance(outcomes.get(name), dict), f"{name} import: {outcomes.get(name)!r}"
    with factory() as db:
        projects = db.query(Project).filter(Project.title.in_(titles)).all()
        assert len(projects) == 2
        authors = {
            a.completed_by
            for a in db.query(Annotation).filter(
                Annotation.project_id.in_([p.id for p in projects])
            )
        }
        # Both copies attribute the answer to the same placeholder account.
        assert len(authors) == 1
        placeholder = db.get(User, authors.pop())
        assert placeholder.email.endswith("@imported.invalid")
        assert db.query(Task).filter(Task.project_id.in_([p.id for p in projects])).count() == 2
        created["users"].add(placeholder.id)
    # Exactly one of the two imports created the placeholder.
    assert sorted(
        o["statistics"]["placeholder_users_created"] for o in outcomes.values()
    ) == [0, 1]


@pytest.mark.integration
def test_pseudonym_take_over_does_not_wait_for_an_open_import_using_the_placeholder(
    worker_like_sessions,
):
    """The first export carries no pseudonym, so its placeholder gets a neutral
    label, and the open first import references it from its answer. The second
    export of the same author offers a pseudonym: taking it over into the
    unique `pseudonym` column needs a row lock the open import blocks, so the
    second import keeps the label in `name` only instead of waiting until the
    lock_timeout fails it."""
    factory, created = worker_like_sessions
    source_id = f"source-{uuid.uuid4()}"
    alias = f"Alias {uuid.uuid4().hex[:12]}"
    shared = [(source_id, f"{source_id}@source.example")]

    outcomes, titles = _run_overlapping_imports(
        factory, created, shared, pseudonyms=(None, alias)
    )

    for name in ("first", "second"):
        assert isinstance(outcomes.get(name), dict), f"{name} import: {outcomes.get(name)!r}"
    with factory() as db:
        placeholder = (
            db.query(User).filter(User.email == f"{source_id}@imported.invalid").one()
        )
        created["users"].add(placeholder.id)
        assert placeholder.name == alias
        assert placeholder.pseudonym is None


@pytest.mark.integration
def test_concurrent_imports_sharing_several_users_in_opposite_order_both_succeed(
    worker_like_sessions,
):
    """Two exports listing the same unknown authors in opposite order: no
    lock wait and no deadlock between the two imports' user phases."""
    factory, created = worker_like_sessions
    shared = []
    for _ in range(3):
        source_id = f"source-{uuid.uuid4()}"
        shared.append((source_id, f"{source_id}@source.example"))

    importer = _importer(factory, created)
    titles = [f"Concurrent import {n} {uuid.uuid4()}" for n in (1, 2)]
    created["titles"].update(titles)
    for uid, email in shared:
        created["users"].add(uid)
        created["emails"].update({email, f"{uid}@imported.invalid"})

    first_ready = threading.Event()
    second_done = threading.Event()
    outcomes = {}

    def hold_open(_result):
        first_ready.set()
        second_done.wait(_OVERLAP_WAIT_S)

    def run(name, title, users, before_commit):
        db = factory()
        try:
            outcomes[name] = run_full_project_import(
                db, io.BytesIO(_export(title, users)), importer, before_commit=before_commit
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            outcomes[name] = exc
        finally:
            db.close()

    first = threading.Thread(target=run, args=("first", titles[0], shared, hold_open))
    first.start()
    try:
        assert first_ready.wait(_OVERLAP_WAIT_S), outcomes.get("first")
        run("second", titles[1], list(reversed(shared)), None)
    finally:
        second_done.set()
        first.join(_OVERLAP_WAIT_S)

    for name in ("first", "second"):
        assert isinstance(outcomes.get(name), dict), f"{name} import: {outcomes.get(name)!r}"
    with factory() as db:
        placeholders = (
            db.query(User).filter(User.email.like("source-%@imported.invalid")).all()
        )
        mine = [u for u in placeholders if u.email.split("@")[0] in {s for s, _ in shared}]
        assert len(mine) == 3
        created["users"].update(u.id for u in mine)


@pytest.mark.integration
def test_concurrent_nested_imports_sharing_an_annotator_both_succeed(
    worker_like_sessions,
):
    """A task import (Project data page) creates a stub account for every
    annotator id this deployment lacks. Two of them naming the same unknown
    annotator ran into the same lock as the full-project imports."""
    factory, created = worker_like_sessions
    importer = _importer(factory, created)
    annotator = f"annotator-{uuid.uuid4()}"
    created["users"].add(annotator)
    project_ids = []
    with factory() as db:
        for n in (1, 2):
            title = f"Concurrent task import {n} {uuid.uuid4()}"
            created["titles"].add(title)
            project = Project(
                id=str(uuid.uuid4()),
                title=title,
                created_by=importer,
                label_config='<View><Text name="text" value="$text"/>'
                '<TextArea name="answer" toName="text"/></View>',
            )
            db.add(project)
            project_ids.append(project.id)
        db.commit()

    body = json.dumps(
        {
            "data": [
                {
                    "data": {"text": "one"},
                    "annotations": [
                        {
                            "result": [
                                {
                                    "from_name": "answer",
                                    "to_name": "text",
                                    "type": "textarea",
                                    "value": {"text": ["Ja"]},
                                }
                            ],
                            "completed_by": annotator,
                        }
                    ],
                }
            ]
        }
    ).encode("utf-8")

    first_ready = threading.Event()
    second_done = threading.Event()
    outcomes = {}

    def hold_open(_result):
        first_ready.set()
        second_done.wait(_OVERLAP_WAIT_S)

    def run(name, project_id, before_commit):
        db = factory()
        try:
            outcomes[name] = run_nested_import(
                db, project_id, io.BytesIO(body), importer, before_commit=before_commit
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            outcomes[name] = exc
        finally:
            db.close()

    first = threading.Thread(target=run, args=("first", project_ids[0], hold_open))
    first.start()
    try:
        assert first_ready.wait(_OVERLAP_WAIT_S), outcomes.get("first")
        run("second", project_ids[1], None)
    finally:
        second_done.set()
        first.join(_OVERLAP_WAIT_S)

    for name in ("first", "second"):
        assert isinstance(outcomes.get(name), dict), f"{name} import: {outcomes.get(name)!r}"
    with factory() as db:
        authors = {
            a.completed_by
            for a in db.query(Annotation).filter(Annotation.project_id.in_(project_ids))
        }
        assert authors == {annotator}
        assert db.get(User, annotator) is not None
