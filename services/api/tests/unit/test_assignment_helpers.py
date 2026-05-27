"""Unit tests for `utils.assignment_helpers` — the primitives shared between
annotation (platform) and korrektur (extended).

Imports are deferred into the fixtures/tests (via the `_helpers()` wrapper)
so pytest collection doesn't race the conftest sys.path setup — sibling
pattern used by test_json_merge_extended.py et al.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


def _helpers():
    """Deferred import wrapper so module-level collection doesn't race the
    conftest sys.path setup. Returns the two helpers under test as a tuple."""
    from utils.assignment_helpers import (
        mark_assignment_completed,
        user_assignment_exists,
    )
    return user_assignment_exists, mark_assignment_completed


@pytest.fixture
def task_with_user(test_db):
    """One project with one task + one user. Returns (project, task, user)."""
    from models import User
    from project_models import Project, Task

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()),
        username=f"u{suffix}",
        email=f"u{suffix}@example.com",
        name=f"Test U{suffix}",
        is_superadmin=False,
    )
    test_db.add(user)
    test_db.flush()

    project = Project(
        id=str(uuid.uuid4()),
        title="assignment-helpers test",
        created_by=user.id,
        assignment_mode="manual",
        label_config="<View></View>",
    )
    test_db.add(project)
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
            target_type=None, target_id=None, assigned_by=None):
    from project_models import TaskAssignment
    a = TaskAssignment(
        id=str(uuid.uuid4()),
        task_id=task_id,
        user_id=user_id,
        # task_assignments.assigned_by is NOT NULL — default to assigning
        # the row to oneself when the test doesn't care.
        assigned_by=assigned_by or user_id,
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
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == False  # noqa: E712


def test_user_assignment_exists_true_for_active_task_level(task_with_user, test_db):
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == True  # noqa: E712


def test_user_assignment_exists_true_for_completed_task_level(task_with_user, test_db):
    """Completed rows still count — annotators can re-open their own work."""
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="completed")
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == True  # noqa: E712


def test_user_assignment_exists_false_for_skipped(task_with_user, test_db):
    """`skipped` is not in the active-or-done set; helper returns False."""
    _, task, user = task_with_user
    _assign(test_db, task_id=task.id, user_id=user.id, status="skipped")
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == False  # noqa: E712


def test_user_assignment_exists_excludes_other_users(task_with_user, test_db):
    from models import User
    _, task, user = task_with_user
    suffix = uuid.uuid4().hex[:8]
    other = User(
        id=str(uuid.uuid4()),
        username=f"other{suffix}",
        email=f"o{suffix}@example.com",
        name=f"Other {suffix}",
        is_superadmin=False,
    )
    test_db.add(other)
    test_db.commit()
    _assign(test_db, task_id=task.id, user_id=other.id, status="assigned")
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == False  # noqa: E712


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
    assert _helpers()[0](
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="annotation",
        target_id="ann-1",
    ) == True  # noqa: E712

    # A different annotation_id does NOT match
    assert _helpers()[0](
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="annotation",
        target_id="ann-2",
    ) == False  # noqa: E712

    # A different target_type with the same id does NOT match
    assert _helpers()[0](
        test_db,
        task_id=task.id,
        user_id=user.id,
        target_type="generation",
        target_id="ann-1",
    ) == False  # noqa: E712


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
    assert _helpers()[0](test_db, task_id=task.id, user_id=user.id) == False  # noqa: E712


# ---------------------------------------------------------------------------
# mark_assignment_completed
# ---------------------------------------------------------------------------


def test_mark_assignment_completed_flips_status_and_stamps_time(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    a = _assign(test_db, task_id=task.id, user_id=user.id, status="assigned")
    out = _helpers()[1](test_db, task_id=task.id, user_id=user.id)
    assert out is not None
    assert out.id == a.id
    assert out.status == "completed"
    assert out.completed_at != None  # noqa: E711
    assert (datetime.now(timezone.utc) - out.completed_at).total_seconds() < 60


def test_mark_assignment_completed_returns_none_when_unassigned(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    out = _helpers()[1](test_db, task_id=task.id, user_id=user.id)
    assert out is None


def test_mark_assignment_completed_idempotent_on_already_completed(
    task_with_user, test_db,
):
    _, task, user = task_with_user
    earlier = datetime(2025, 1, 1, tzinfo=timezone.utc)
    a = _assign(test_db, task_id=task.id, user_id=user.id, status="completed")
    a.completed_at = earlier
    test_db.commit()

    out = _helpers()[1](test_db, task_id=task.id, user_id=user.id)
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

    out = _helpers()[1](
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


# NOTE: a "same user, same task-level target, one completed + one active" row
# state is forbidden by the `uniq_task_level_assignment` constraint, so the
# helper's active-row-preference branch only matters in defensive code paths.
# Deleted what was test_mark_assignment_completed_picks_active_row_when_completed_also_exists
# — it modeled an unreachable state and only the constraint kept production
# safe. The idempotency test above already covers the realistic "already
# completed" case.
