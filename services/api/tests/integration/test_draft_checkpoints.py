"""Integration tests for restorable draft checkpoints.

Covers the append-only checkpoint endpoints in ``routers/projects/drafts.py``:

- POST appends a snapshot only when the project enables checkpoints and the
  payload has content; GET lists (newest first) and fetches one.
- The crucial guarantee: submitting an annotation deletes the live ``TaskDraft``
  but does NOT delete the checkpoint history (so a restore is still possible).

Real-DB via the sync ``client``/``test_db`` pair (mirrors the existing
create_annotation side-effect tests in ``test_annotations_router_branches``).
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
from project_models import Project, Task, TaskDraft, TaskDraftCheckpoint


@pytest.fixture(autouse=True)
def _mute_celery():
    """Stub the report-refresh Celery dispatch fired on annotation submit."""
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


def _make_project(test_db, *, created_by, **overrides):
    project = Project(
        id=_uid(),
        title="Checkpoint Test",
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
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "Some legal text to annotate"},
        **overrides,
    )
    test_db.add(task)
    test_db.flush()
    return task


def _loesung(markdown="A könnte sich gem. § 242 StGB strafbar gemacht haben."):
    return {
        "result": [
            {
                "from_name": "loesung",
                "to_name": "sachverhalt",
                "type": "loesung",
                "value": {"markdown": markdown},
            }
        ]
    }


def _count_checkpoints(test_db, task_id, user_id):
    return (
        test_db.query(TaskDraftCheckpoint)
        .filter(
            TaskDraftCheckpoint.task_id == task_id,
            TaskDraftCheckpoint.user_id == user_id,
        )
        .count()
    )


class TestCheckpointEndpoints:
    def test_appends_history_and_lists(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, restorable_checkpoints_enabled=True
        )
        task = _make_task(test_db, project)

        base = f"/api/projects/{project.id}/tasks/{task.id}"

        r1 = client.post(
            f"{base}/checkpoint",
            json=_loesung("Erster Stand."),
            headers=auth_headers["admin"],
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "ok"

        r2 = client.post(
            f"{base}/checkpoint",
            json=_loesung("Zweiter, längerer Stand mit mehr Text."),
            headers=auth_headers["admin"],
        )
        assert r2.status_code == 200, r2.text

        test_db.expire_all()
        assert _count_checkpoints(test_db, task.id, admin.id) == 2

        listing = client.get(f"{base}/checkpoints", headers=auth_headers["admin"])
        assert listing.status_code == 200, listing.text
        items = listing.json()["checkpoints"]
        assert len(items) == 2
        # Newest first.
        assert items[0]["created_at"] >= items[1]["created_at"]

        one = client.get(
            f"{base}/checkpoints/{items[0]['id']}", headers=auth_headers["admin"]
        )
        assert one.status_code == 200, one.text
        result = one.json()["result"]
        assert result[0]["from_name"] == "loesung"
        assert "markdown" in result[0]["value"]

    def test_disabled_project_is_noop(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, restorable_checkpoints_enabled=False
        )
        task = _make_task(test_db, project)

        resp = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/checkpoint",
            json=_loesung(),
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "disabled"
        test_db.expire_all()
        assert _count_checkpoints(test_db, task.id, admin.id) == 0

    def test_empty_payload_is_skipped(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, restorable_checkpoints_enabled=True
        )
        task = _make_task(test_db, project)

        resp = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/checkpoint",
            json={"result": [{"from_name": "loesung", "value": {"markdown": "   "}}]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "skipped_empty"
        test_db.expire_all()
        assert _count_checkpoints(test_db, task.id, admin.id) == 0

    def test_submit_does_not_delete_checkpoints(
        self, client, test_db, test_users, auth_headers
    ):
        """The core guarantee: submitting clears the live draft but KEEPS the
        checkpoint history, so a restore remains possible after submission."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, restorable_checkpoints_enabled=True
        )
        task = _make_task(test_db, project)
        base = f"/api/projects/{project.id}/tasks/{task.id}"

        # A live draft + a checkpoint both exist before submit.
        test_db.add(
            TaskDraft(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                user_id=admin.id,
                draft_result=_loesung()["result"],
            )
        )
        test_db.flush()
        cp = client.post(
            f"{base}/checkpoint", json=_loesung(), headers=auth_headers["admin"]
        )
        assert cp.status_code == 200, cp.text
        assert _count_checkpoints(test_db, task.id, admin.id) == 1

        submit = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": _loesung()["result"],
                "was_cancelled": False,
            },
            headers=auth_headers["admin"],
        )
        assert submit.status_code == 200, submit.text

        test_db.expire_all()
        # Live draft is gone...
        assert (
            test_db.query(TaskDraft)
            .filter(TaskDraft.task_id == task.id, TaskDraft.user_id == admin.id)
            .count()
            == 0
        )
        # ...but the checkpoint history survives.
        assert _count_checkpoints(test_db, task.id, admin.id) == 1
