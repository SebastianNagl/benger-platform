"""Shared task-assignment helpers used by both annotation (platform) and
korrektur (extended) routers.

Both surfaces touch the same `task_assignments` table with the same
status-transition + existence-check shape, so the primitives live here.
Higher-level role-bypass logic (e.g. `check_task_assigned_to_user` in
`routers/projects/helpers.py`, `_check_korrektur_permission` in
`benger_extended/api/routers/korrektur.py`) stays local to each surface —
those policies differ (annotator-vs-corrector role names, blind semantics,
etc.) and shouldn't be force-merged.

Per-target rows (`target_type` + `target_id` set) were added in migration
033 for the korrektur queue; annotation never sets them, so the task-level
queries always filter `target_type IS NULL OR target_type = 'task'`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from project_models import TaskAssignment


# Statuses that count as "the user owns this row" — assigned/in_progress are
# active work, completed grants read access (see callsite invariants in
# helpers.py:check_task_assigned_to_user and korrektur.py).
_ACTIVE_OR_DONE = ("assigned", "in_progress", "completed")


def user_assignment_exists(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> bool:
    """Pure existence check: does a `task_assignments` row tie this user to
    this (task, optional target) in any active or completed state?

    No role bypass, no project-mode reading — callers layer that on top.

    Task-level (annotation) callsite: pass `target_type=None`. The query
    matches rows where `target_type` is NULL or `'task'` (legacy rows had
    no value before migration 033 added the column with a `'task'` default).

    Per-target (korrektur) callsite: pass both `target_type` and `target_id`.
    """
    q = db.query(TaskAssignment.id).filter(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == str(user_id),
        TaskAssignment.status.in_(_ACTIVE_OR_DONE),
    )
    if target_type is None:
        q = q.filter(
            or_(
                TaskAssignment.target_type.is_(None),
                TaskAssignment.target_type == "task",
            ),
        )
    else:
        q = q.filter(
            TaskAssignment.target_type == target_type,
            TaskAssignment.target_id == target_id,
        )
    return q.first() is not None


def mark_assignment_completed(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> Optional[TaskAssignment]:
    """Flip the matching `task_assignments` row to `completed` + stamp
    `completed_at = now(UTC)`. Idempotent — returning early if already
    completed, returning the row either way.

    Looks up the row with the same `(task, user, target?)` shape as
    `user_assignment_exists`. Only `assigned` / `in_progress` rows are
    transitioned (an already-`completed` row is returned untouched, a
    `skipped` row is left alone — re-claiming a skipped item is not this
    function's job).

    Returns `None` if no matching assignment exists (open-mode projects,
    or unassigned grading paths where the caller already decided to allow
    the action).
    """
    q = db.query(TaskAssignment).filter(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == str(user_id),
    )
    if target_type is None:
        q = q.filter(
            or_(
                TaskAssignment.target_type.is_(None),
                TaskAssignment.target_type == "task",
            ),
        )
    else:
        q = q.filter(
            TaskAssignment.target_type == target_type,
            TaskAssignment.target_id == target_id,
        )
    # Prefer an active row when present, but fall through to a completed one so
    # the caller still gets the row reference (useful for callers that want to
    # log/return the assignment id).
    assignment = (
        q.filter(TaskAssignment.status.in_(("assigned", "in_progress")))
        .first()
        or q.filter(TaskAssignment.status == "completed").first()
    )
    if assignment is None:
        return None
    if assignment.status != "completed":
        assignment.status = "completed"
        assignment.completed_at = datetime.now(timezone.utc)
        db.commit()
    return assignment
