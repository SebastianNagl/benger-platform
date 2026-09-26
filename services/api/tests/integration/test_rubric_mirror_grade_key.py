"""The grading sheets' task-data mirrors follow the exam's Notenschlüssel.

``task.data["bewertungsbogen"]`` mirrors the active sheet and ends in the key
that grades the exam (``rubric_structure.resolve_grade_scale``: the exam's
key, else the sheet's own, else the standard key). The mirror used to be
refreshed only when a sheet was activated or edited, so changing the exam's
key left every mirror of the project showing the old one.

Pinned here against Postgres:

- ``task_rubric_service.remirror_project_rubrics`` (async) and
  ``remirror_project_rubrics_sync``: one query for the whole project, only
  active sheets, only this project, only mirrors that differ;
- the eval-config PUT (sync lane, ``client`` / ``test_db``) re-mirrors on a
  key change and leaves the mirrors alone otherwise.

The pure row pass is unit-tested in ``tests/unit/test_task_rubric_remirror.py``.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select

from models import User
from project_models import Project, ProjectOrganization, Task, TaskRubric
from rubric_structure import (
    GRADE_SCALE_PRESETS,
    PERCENT_GRADE_UNIT,
    criteria_from_structure,
    effective_grade_scale,
    mirror_rubric_into_task_data,
    normalize_structure,
    render_grade_scale_text,
)
from task_rubric_service import remirror_project_rubrics, remirror_project_rubrics_sync

BASE = "/api/evaluations"

STRUCTURE = normalize_structure(
    {
        "version": 1,
        "nodes": [
            {"id": "a", "level": 0, "kind": "section", "label": "A.", "title": "Zulässigkeit"},
            {"id": "b", "level": 1, "kind": "step", "label": "I.", "title": "Rechtsweg", "max_score": 40},
            {"id": "c", "level": 1, "kind": "step", "label": "II.", "title": "Klageart", "max_score": 60},
        ],
    }
)
# A sheet's own (legacy, absolute) key.
SHEET_KEY = {
    "unit": "BE",
    "thresholds": [5 * i for i in range(1, 19)],
    "rounding": "floor",
    "pass_grade": 4,
}


def _uid():
    return str(uuid.uuid4())


def _exam_key(preset="uebungsklausur"):
    return {
        "unit": PERCENT_GRADE_UNIT,
        "preset": preset,
        "thresholds": list(GRADE_SCALE_PRESETS[preset]),
        "rounding": "floor",
        "pass_grade": 4,
    }


def _key_block(scale):
    return render_grade_scale_text(effective_grade_scale(scale, 100.0))


_next_inner_id = itertools.count(1)


def _rubric(task, project, *, status="active", grade_scale=None, metadata=None):
    return TaskRubric(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        title="Bogen",
        criteria=criteria_from_structure(STRUCTURE),
        total_points=100.0,
        structure=STRUCTURE,
        grade_scale=grade_scale,
        source="human",
        status=status,
        generation_metadata=metadata,
    )


def _mirror(task_or_data):
    data = task_or_data.data if hasattr(task_or_data, "data") else task_or_data
    return (data or {}).get("bewertungsbogen")


# ---------------------------------------------------------------------------
# sync lane: the helper and the eval-config PUT
# ---------------------------------------------------------------------------


def _seed_project(test_db, test_users, test_org, evaluation_config=None):
    project = Project(
        id=_uid(),
        title="Notenschlüssel Spiegel",
        created_by=test_users[0].id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_users[0].id,
        )
    )
    test_db.commit()
    return project


def _seed_sheet(test_db, project, *, status="active", grade_scale=None, metadata=None, mirror=None):
    """A task with one sheet. An active sheet is mirrored the way activation
    mirrors it (with the project's config at that time) unless ``mirror``
    says what the task carries."""
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"sachverhalt": "SV"},
        inner_id=next(_next_inner_id),
        created_by=project.created_by,
    )
    test_db.add(task)
    test_db.flush()
    rubric = _rubric(task, project, status=status, grade_scale=grade_scale, metadata=metadata)
    test_db.add(rubric)
    test_db.flush()
    if status == "active":
        if mirror is None:
            mirror_rubric_into_task_data(task, rubric, project.evaluation_config or {})
        else:
            task.data = {**task.data, "bewertungsbogen": mirror}
    test_db.commit()
    return task


def _reload_task(test_db, task_id):
    test_db.expire_all()
    return test_db.query(Task).filter(Task.id == task_id).first()


def _put(client, auth_headers, project_id, body):
    return client.put(
        f"{BASE}/projects/{project_id}/evaluation-config",
        json=body,
        headers=auth_headers["admin"],
    )


@pytest.mark.integration
class TestRemirrorSync:
    def test_one_query_rewrites_every_active_sheet_of_the_project(
        self, test_db, test_users, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        tasks = [_seed_sheet(test_db, project) for _ in range(6)]
        candidate_only = _seed_sheet(test_db, project, status="candidate")
        other = _seed_project(test_db, test_users, test_org, {})
        foreign = _seed_sheet(test_db, other)
        foreign_mirror = _mirror(foreign)
        project_id = project.id  # read before counting (the row is expired)

        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        conn = test_db.connection()
        event.listen(conn, "before_cursor_execute", _record)
        try:
            changed = remirror_project_rubrics_sync(
                test_db, project_id, {"grade_scale": _exam_key()}
            )
        finally:
            event.remove(conn, "before_cursor_execute", _record)
        test_db.commit()

        assert changed == 6
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        assert len(selects) == 1, selects
        for task in tasks:
            assert _mirror(_reload_task(test_db, task.id)).endswith(_key_block(_exam_key()))
        # A task without an active sheet gets no mirror, another project's
        # mirror is untouched.
        assert _mirror(_reload_task(test_db, candidate_only.id)) is None
        assert _mirror(_reload_task(test_db, foreign.id)) == foreign_mirror

    def test_a_second_pass_changes_nothing(self, test_db, test_users, test_org):
        project = _seed_project(test_db, test_users, test_org, {})
        _seed_sheet(test_db, project)
        config = {"grade_scale": _exam_key()}
        assert remirror_project_rubrics_sync(test_db, project.id, config) == 1
        test_db.commit()
        assert remirror_project_rubrics_sync(test_db, project.id, config) == 0

    def test_a_generated_sheet_reads_only_its_rendered_text(
        self, test_db, test_users, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        task = _seed_sheet(
            test_db,
            project,
            metadata={
                "rendered_text": "BEWERTUNGSBOGEN (generiert)",
                "full_document": {"schritte": ["x" * 1000] * 50},
            },
            mirror="alt",
        )
        assert remirror_project_rubrics_sync(test_db, project.id, {"grade_scale": _exam_key()}) == 1
        test_db.commit()
        assert _mirror(_reload_task(test_db, task.id)) == "BEWERTUNGSBOGEN (generiert)"


@pytest.mark.integration
class TestEvalConfigPut:
    def test_a_new_exam_key_re_mirrors_the_sheets(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        tasks = [_seed_sheet(test_db, project) for _ in range(3)]
        assert _mirror(tasks[0]).endswith(_key_block(None))

        resp = _put(client, auth_headers, project.id, {"grade_scale": _exam_key()})
        assert resp.status_code == 200, resp.text

        for task in tasks:
            assert _mirror(_reload_task(test_db, task.id)).endswith(_key_block(_exam_key()))

    def test_changing_and_clearing_the_key_follow_the_precedence(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The exam's key beats the sheet's own; cleared, the sheet's key
        shows again; a sheet without one shows the standard key."""
        project = _seed_project(test_db, test_users, test_org, {})
        with_own = _seed_sheet(test_db, project, grade_scale=SHEET_KEY)
        without = _seed_sheet(test_db, project)
        assert _mirror(with_own).endswith(_key_block(SHEET_KEY))

        assert _put(client, auth_headers, project.id, {"grade_scale": _exam_key()}).status_code == 200
        assert _mirror(_reload_task(test_db, with_own.id)).endswith(_key_block(_exam_key()))
        assert _mirror(_reload_task(test_db, without.id)).endswith(_key_block(_exam_key()))

        other = _exam_key("standard")
        assert _put(client, auth_headers, project.id, {"grade_scale": other}).status_code == 200
        assert _mirror(_reload_task(test_db, with_own.id)).endswith(_key_block(other))

        assert _put(client, auth_headers, project.id, {"grade_scale": None}).status_code == 200
        assert _mirror(_reload_task(test_db, with_own.id)).endswith(_key_block(SHEET_KEY))
        assert _mirror(_reload_task(test_db, without.id)).endswith(_key_block(None))

    def test_no_key_change_no_rewrite(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A save that leaves the key as it is never touches the mirrors: the
        sentinel below would be re-rendered by any re-mirror."""
        project = _seed_project(
            test_db, test_users, test_org, {"grade_scale": _exam_key()}
        )
        task = _seed_sheet(test_db, project, mirror="SENTINEL")

        assert _put(client, auth_headers, project.id, {"runs_per_task": 2}).status_code == 200
        assert _mirror(_reload_task(test_db, task.id)) == "SENTINEL"
        # The same key again, with a number type that differs, is no change.
        same = {**_exam_key(), "thresholds": [float(t) for t in _exam_key()["thresholds"]]}
        assert _put(client, auth_headers, project.id, {"grade_scale": same}).status_code == 200
        assert _mirror(_reload_task(test_db, task.id)) == "SENTINEL"

    def test_an_invalid_key_writes_nothing(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, {})
        task = _seed_sheet(test_db, project, mirror="SENTINEL")
        resp = _put(
            client, auth_headers, project.id, {"grade_scale": {**_exam_key(), "thresholds": [1, 2]}}
        )
        assert resp.status_code == 422
        assert _mirror(_reload_task(test_db, task.id)) == "SENTINEL"


# ---------------------------------------------------------------------------
# async lane: the helper
# ---------------------------------------------------------------------------


async def _make_user(db) -> User:
    user = User(
        id=_uid(),
        username=f"mirror-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Mirror Tester",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_exam(db, owner, evaluation_config=None) -> Project:
    project = Project(
        id=_uid(),
        title="Probeklausur",
        created_by=owner.id,
        is_private=True,
        evaluation_config=evaluation_config,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_sheet(db, project, *, grade_scale=None, mirror=None) -> Task:
    task = Task(
        id=_uid(),
        project_id=project.id,
        data={"sachverhalt": "SV"},
        inner_id=next(_next_inner_id),
    )
    db.add(task)
    await db.flush()
    rubric = _rubric(task, project, grade_scale=grade_scale)
    db.add(rubric)
    await db.flush()
    if mirror is None:
        mirror_rubric_into_task_data(task, rubric, project.evaluation_config or {})
    else:
        task.data = {**task.data, "bewertungsbogen": mirror}
    await db.flush()
    return task


async def _stored_task(db, task_id):
    db.expire_all()
    return (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()


async def _stored_config(db, project_id):
    db.expire_all()
    return (
        await db.execute(select(Project.evaluation_config).where(Project.id == project_id))
    ).scalar_one()


@pytest.mark.integration
class TestRemirrorAsync:
    @pytest.mark.asyncio
    async def test_rewrites_the_projects_mirrors_once(self, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_exam(async_test_db, owner, {})
        task_ids = [(await _make_sheet(async_test_db, project)).id for _ in range(4)]
        project_id = project.id
        await async_test_db.commit()

        config = {"grade_scale": _exam_key()}
        assert await remirror_project_rubrics(async_test_db, project_id, config) == 4
        await async_test_db.commit()
        for task_id in task_ids:
            stored = await _stored_task(async_test_db, task_id)
            assert _mirror(stored).endswith(_key_block(_exam_key()))
        assert await remirror_project_rubrics(async_test_db, project_id, config) == 0

    @pytest.mark.asyncio
    async def test_a_task_the_session_holds_is_updated_in_place(self, async_test_db):
        """The query hands back the session's own task object, so a caller
        that keeps using it (and returns it in a response) sees the new
        mirror without a reload."""
        owner = await _make_user(async_test_db)
        project = await _make_exam(async_test_db, owner, {})
        task = await _make_sheet(async_test_db, project)
        await async_test_db.commit()

        await remirror_project_rubrics(async_test_db, project.id, {"grade_scale": _exam_key()})
        assert _mirror(task).endswith(_key_block(_exam_key()))
