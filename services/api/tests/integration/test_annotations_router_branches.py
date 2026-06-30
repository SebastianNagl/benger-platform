"""Behavioral integration tests for the projects/annotations router — net-new
branches only.

Scope rationale: the create/list/update happy paths, task-not-found,
cancelled-annotation, instruction_variant/ai_assisted, mark-labeled, all_users,
the maximum_annotations 400, the was_cancelled counter toggle, and the
"can only update your own annotation" 403 are ALREADY covered by
``tests/integration/test_annotations_integration.py``,
``tests/integration/test_annotations_coverage.py``, and
``tests/unit/test_coverage_boost_annotations.py`` (all real-DB via ``client``).

This file deliberately covers ONLY the branches those three miss:
  * GET ``completed_by_username`` resolution — match AND no-match (returns []).
  * GET ``latest_only`` per-annotator deduplication.
  * GET empty-result (``cast(result) != '[]'``) exclusion from listings.
  * POST server-side TaskDraft cleanup on submit.
  * POST ``min_annotations_per_task`` labeling threshold (labels only AT min).

The GET ``list_task_annotations`` handler was migrated to the async DB lane
(``Depends(get_async_db)``), so the GET-driven tests below seed real rows via
``async_test_db`` and drive the surface through ``async_test_client`` with a
``require_user`` override (the sync ``client``/``test_db`` pair only overrides
``get_db``, so an async handler can't see uncommitted SAVEPOINT rows). The POST
``create_annotation`` handler STAYED sync (it calls sync-only extension hooks),
so ``TestCreateSideEffects`` keeps the sync ``client``/``test_db`` fixtures.

Full paths through the /api/projects router prefix:
  POST   /api/projects/tasks/{task_id}/annotations
  GET    /api/projects/tasks/{task_id}/annotations
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, Project, Task, TaskDraft


@pytest.fixture(autouse=True)
def _mute_celery():
    """Stub the report-refresh Celery dispatch in create/update_annotation.

    Without a Redis broker (isolated venv) Celery retries the connection for
    ~20s, which on the async lane outlives the 15s statement_timeout and
    cancels the in-flight transaction. The handler already swallows dispatch
    failures in prod, so stubbing it changes no behaviour under test.
    """
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(
    db,
    *,
    is_superadmin=True,
    name="Ann User",
    username=None,
    pseudonym=None,
    use_pseudonym=False,
):
    u = User(
        id=_uid(),
        username=username or f"ann-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        pseudonym=pseudonym,
        use_pseudonym=use_pseudonym,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


# ---------------------------------------------------------------------------
# Sync helpers — used ONLY by the POST (create_annotation) tests below, which
# stay on the sync client/test_db pair.
# ---------------------------------------------------------------------------


def _make_project(test_db, *, created_by, **overrides):
    project = Project(
        id=str(uuid.uuid4()),
        title="Annotations Router Branch Test",
        created_by=created_by,
        assignment_mode=overrides.pop("assignment_mode", "open"),
        maximum_annotations=overrides.pop("maximum_annotations", 0),
        min_annotations_per_task=overrides.pop("min_annotations_per_task", 1),
        **overrides,
    )
    test_db.add(project)
    test_db.flush()
    return project


def _make_task(test_db, project, *, inner_id=1, **overrides):
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "Some legal text to annotate"},
        **overrides,
    )
    test_db.add(task)
    test_db.flush()
    return task


def _payload(**overrides):
    payload = {
        "result": [{"value": {"choices": ["positive"]}, "from_name": "label"}],
        "was_cancelled": False,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Async helpers — used by the GET (list_task_annotations) tests, which run on
# the async client/db pair so the migrated async handler sees the rows.
# ---------------------------------------------------------------------------


async def _make_project_async(db, *, created_by, **overrides):
    project = Project(
        id=str(uuid.uuid4()),
        title="Annotations Router Branch Test",
        created_by=created_by,
        assignment_mode=overrides.pop("assignment_mode", "open"),
        maximum_annotations=overrides.pop("maximum_annotations", 0),
        min_annotations_per_task=overrides.pop("min_annotations_per_task", 1),
        **overrides,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_task_async(db, project, *, inner_id=1, **overrides):
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "Some legal text to annotate"},
        **overrides,
    )
    db.add(task)
    await db.flush()
    return task


async def _seed_annotation_async(
    db, task, project, completed_by, result=None, was_cancelled=False
):
    ann = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=completed_by,
        result=result if result is not None else [{"value": {"choices": ["x"]}}],
        was_cancelled=was_cancelled,
    )
    db.add(ann)
    await db.flush()
    return ann


# ---------------------------------------------------------------------------
# GET completed_by_username resolution (match + no-match) — uncovered elsewhere
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListByUsername:
    @pytest.mark.asyncio
    async def test_filter_by_username_match(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(
            async_test_db,
            is_superadmin=False,
            name="Test Contributor",
            username="contributor@test.com",
        )
        project = await _make_project_async(async_test_db, created_by=admin.id)
        task = await _make_task_async(async_test_db, project)
        await _seed_annotation_async(async_test_db, task, project, admin.id)
        theirs = await _seed_annotation_async(
            async_test_db, task, project, contributor.id
        )
        await async_test_db.commit()

        # contributor.username == "contributor@test.com"; the handler resolves
        # the display string back to a user via username/name/pseudonym.
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{task.id}/annotations",
                params={"completed_by_username": contributor.username},
            )
        assert resp.status_code == 200, resp.text
        ids = {a["id"] for a in resp.json()}
        assert ids == {theirs.id}

    @pytest.mark.asyncio
    async def test_filter_by_username_no_match_returns_empty(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project_async(async_test_db, created_by=admin.id)
        task = await _make_task_async(async_test_db, project)
        await _seed_annotation_async(async_test_db, task, project, admin.id)
        await async_test_db.commit()

        # No user resolves -> early `return []` branch.
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{task.id}/annotations",
                params={"completed_by_username": "no-such-display-name"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET latest_only dedup + empty-result exclusion — uncovered elsewhere
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListLatestAndEmpty:
    @pytest.mark.asyncio
    async def test_latest_only_dedupes_per_annotator(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project_async(async_test_db, created_by=admin.id)
        task = await _make_task_async(async_test_db, project)
        # One active + one withdrawn (cancelled) annotation from the same user.
        # Both carry a non-empty result so both appear in the list; only one
        # active row is permitted per (task, user) by the unique index, so the
        # cancelled row is the realistic source of a per-annotator duplicate.
        await _seed_annotation_async(async_test_db, task, project, admin.id)
        await _seed_annotation_async(
            async_test_db, task, project, admin.id, was_cancelled=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{task.id}/annotations",
                params={"latest_only": "true"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The two rows from one annotator collapse to a single latest row.
        assert len(body) == 1
        assert body[0]["completed_by"] == admin.id

    @pytest.mark.asyncio
    async def test_empty_result_annotations_excluded(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project_async(async_test_db, created_by=admin.id)
        task = await _make_task_async(async_test_db, project)
        real = await _seed_annotation_async(async_test_db, task, project, admin.id)
        # result == [] is filtered by the `cast(result, String) != '[]'` clause.
        # Seeded under a different user so the active-annotation unique index
        # (one per task+user) isn't violated — the exclusion is about the empty
        # result, not the annotator.
        await _seed_annotation_async(
            async_test_db, task, project, other.id, result=[]
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{task.id}/annotations",
                params={"all_users": "true"},
            )
        assert resp.status_code == 200, resp.text
        ids = {a["id"] for a in resp.json()}
        assert ids == {real.id}


# ---------------------------------------------------------------------------
# POST TaskDraft cleanup + min_annotations labeling threshold — uncovered.
# These hit create_annotation, which stayed on the sync DB lane.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateSideEffects:
    def test_create_clears_existing_server_draft(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(test_db, created_by=admin.id)
        task = _make_task(test_db, project)

        draft = TaskDraft(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            user_id=admin.id,
            draft_result=[{"value": {"choices": ["draft"]}}],
        )
        test_db.add(draft)
        test_db.flush()

        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=_payload(),
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text

        test_db.expire_all()
        remaining = (
            test_db.query(TaskDraft)
            .filter(TaskDraft.task_id == task.id, TaskDraft.user_id == admin.id)
            .count()
        )
        # Submitting the annotation deletes the user's server-side draft.
        assert remaining == 0

    def test_labels_task_only_at_min_annotations(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        other = test_users[1]
        project = _make_project(
            test_db,
            created_by=admin.id,
            maximum_annotations=0,
            min_annotations_per_task=2,
        )
        task = _make_task(test_db, project)

        # One annotator's annotation -> 1 of 2 -> below the min -> not labeled.
        # One active annotation per (task, user) means the min of 2 can only be
        # reached across DISTINCT annotators, so seed the other annotator's row.
        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            completed_by=other.id,
            result=[{"value": {"choices": ["y"]}}],
            was_cancelled=False,
        ))
        test_db.commit()
        test_db.expire_all()
        after_one = test_db.query(Task).filter(Task.id == task.id).first()
        assert after_one.is_labeled is False

        # A second, distinct annotator (admin) submits via create_annotation ->
        # 2 of 2 -> meets the min -> the new insert flips is_labeled.
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=_payload(),
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        after_two = test_db.query(Task).filter(Task.id == task.id).first()
        assert after_two.is_labeled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
