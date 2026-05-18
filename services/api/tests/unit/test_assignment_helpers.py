"""Unit tests for `utils.assignment_helpers` — the primitives shared between
annotation (platform) and korrektur (extended).

Two flavors:
  - DB-backed integration tests using the existing pytest postgres fixtures
    (`test_db` from conftest)
  - One sanity test that confirms the import path resolves and the constants
    are what the docstrings promise

Run: `pytest services/api/tests/unit/test_assignment_helpers.py -v`
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from project_models import Project, Task, TaskAssignment, User
from utils.assignment_helpers import (
    mark_assignment_completed,
    user_assignment_exists,
)


@pytest.fixture
def task_with_user(test_db):
    """One project with one task + one user. Returns (project, task, user)."""
    project = Project(
        id=str(uuid.uuid4()),
        title="assignment-helpers test",
        assignment_mode="manual",
        label_config="<View></View>",
    )
    test_db.add(project)
    test_db.flush()

    user = User(
        id=str(uuid.uuid4()),
        username=f"u{uuid.uuid4().hex[:8]}",
        email=f"u{uuid.uuid4().hex[:8]}@example.com",
        is_superadmin=False,
    )
    test_db.add(user)
    test_db.flush()

    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "hi"},
        inner_id=1,
    )
    test_db.add(task)
    test_db.commit()
    return project, task, user


def _assign(test_db, *, task_id, user_id, status="assigned",
            target_type=None, target_id=None):
    a = TaskAssignment(
        id=str(uuid.uuid4()),
        task_id=task_id,
        user_id=user_id,
        status=status,
        target_type=target_type,
        target_id=target_id,
    )
    test_db.add(a)
    test_db.commit()
    return a


# ---------------------------------------------------------------------------
# user_assignment_exists
# ---------------------------------------------------------------------------


def test_user_assignment_exists_false_when_no_row(task_with_user, test_db):
    _, task, user = task_with_user
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is False


def test_user_assignment_exists_true_for_active_task_level(task_with_user, test_db):
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is True


def test_user_assignment_exists_true_for_completed_task_level(task_with_user, test_db):
    """Completed rows still count — annotators can re-open their own work."""
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="completed")
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is True


def test_user_assignment_exists_false_for_skipped(task_with_user, test_db):
    """`skipped` is not in the active-or-done set; helper returns False."""
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="skipped")
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is False


def test_user_assignment_exists_excludes_other_users(task_with_user, test_db):
    _, task, user = task_with_user
    other = User(
        id=str(uuid.uuid4()),
        username=f"other{uuid.uuid4().hex[:8]}",
        email=f"o{uuid.uuid4().hex[:8]}@example.com",
        is_superadmin=False,
    )
    test_db.add(other)
    test_db.commit()
    _assign(test_db, task_id=task.id, user_id=other.id, status="assigned")
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is False


def test_user_assignment_exists_per_target_matches_only_exact(task_with_user, test_db):
    """Per-target queries (korrektur) must not match a task-level row, and
    must not match a different target_id."""
    _, task, user = task_with_user
    # Task-level row + per-target row for two different annotations
    _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    _assign(
        test_db,
        task_id=task.id,
        user_id=user.id,
        status="assigned",
        target_type="annotation",
        target_id="ann-1",
    )

    # The (annotation, ann-1) target matches
    assert user_assignment_exists(
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="annotation",
        target_id="ann-1",
    ) is True

    # A different annotation_id does NOT match
    assert user_assignment_exists(
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="annotation",
        target_id="ann-2",
    ) is False

    # A different target_type with the same id does NOT match
    assert user_assignment_exists(
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="generation",
        target_id="ann-1",
    ) is False


def test_user_assignment_exists_task_level_ignores_per_target_rows(task_with_user, test_db):
    """A korrektur per-target assignment must not satisfy an annotation
    task-level check — otherwise the annotation submit gate would silently
    accept a user who only had a korrektur claim."""
    _, task, user = task_with_user
    _assign(
        test_db,
        task_id=task.id,
        user_id=user.id,
        status="assigned",
        target_type="annotation",
        target_id="ann-1",
    )
    assert user_assignment_exists(test_db, task_id=task.id, user_id=user.id) is False


# ---------------------------------------------------------------------------
# mark_assignment_completed
# ---------------------------------------------------------------------------


def test_mark_assignment_completed_flips_status_and_stamps_time(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    a = _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    out = mark_assignment_completed(test_db, task_id=task.id, user_id=user.id)
    assert out is not None
    assert out.id == a.id
    assert out.status == "completed"
    assert out.completed_at is not None
    assert (datetime.now(timezone.utc) - out.completed_at).total_seconds() < 60


def test_mark_assignment_completed_returns_none_when_unassigned(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    out = mark_assignment_completed(test_db, task_id=task.id, user_id=user.id)
    assert out is None


def test_mark_assignment_completed_idempotent_on_already_completed(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    earlier = datetime(2025, 1, 1, tzinfo=timezone.utc)
    a = _assign(test_db, task_id=task.id, user_id=user.id, status="completed")
    a.completed_at = earlier
    test_db.commit()

    out = mark_assignment_completed(test_db, task_id=task.id, user_id=user.id)
    # Returned the existing row, did NOT re-stamp completed_at
    assert out is not None
    assert out.id == a.id
    assert out.completed_at == earlier


def test_mark_assignment_completed_per_target_targets_exact_row(
    task_with_user, test_db,
):
    """A per-target call must only flip the matching (target_type, target_id)
    row — not the user's task-level row on the same task."""
    _, task, user = task_with_user
    task_level = _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    per_target = _assign(
        test_db,
        task_id=task.id,
        user_id=user.id,
        status="assigned",
        target_type="annotation",
        target_id="ann-1",
    )

    out = mark_assignment_completed(
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="annotation",
        target_id="ann-1",
    )
    assert out is not None
    assert out.id == per_target.id
    assert out.status == "completed"

    test_db.refresh(task_level)
    assert task_level.status == "assigned"  # Untouched


def test_mark_assignment_completed_picks_active_row_when_completed_also_exists(
    task_with_user, test_db,
):
    """Edge case: same user has both an old completed and a new assigned row
    for the same task (re-claim flow). The helper must pick the active one
    to flip, not the already-completed one."""
    _, task, user = task_with_user
    completed = _assign(
        test_db, task_id=task.id, user_id=user.id, status="completed",
    )
    completed.completed_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    active = _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    test_db.commit()

    out = mark_assignment_completed(test_db, task_id=task.id, user_id=user.id)
    assert out is not None
    assert out.id == active.id
    assert out.status == "completed"
