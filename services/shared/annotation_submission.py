"""Storing a submission: the part every writer shares (API and workers).

``persist_submission`` is the persistence core that
``routers.projects.annotations.persist_annotation_submission`` (the API's
submit and the extended on-behalf upload) and server-side writers (the
extended handwriting OCR worker) run, so the one-active-annotation rule, the
task counters and the draft cleanup exist once:

- a transaction-scoped advisory lock per (task, user) serializes concurrent
  submits; an existing active annotation is updated in place (latest content
  wins), backed by the partial unique index ``uq_annotations_active_task_user``
  (an IntegrityError adopts the row that won the race);
- the project's ``maximum_annotations`` limit (new rows only);
- atomic task counters and ``is_labeled``;
- the writer's ``TaskDraft`` is deleted.

What happens AFTER the commit differs per process and stays with the caller:
the API runs the ``on_annotation_created`` hook, assignment completion and the
report refresh; a worker runs its own follow-ups
(:func:`complete_assignment` is shared too).

:func:`withdraw_submission` is the one writer of a withdrawal (the author
takes a submission back, or a project editor returns it): the row and its
data stay, ``was_cancelled`` and the ``withdrawn_*`` record are set and the
task counters follow.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import String, cast, text, update
from sqlalchemy.exc import IntegrityError

#: Fields a submission copies onto its annotation row.
SUBMISSION_FIELDS = (
    "result",
    "draft",
    "lead_time",
    "active_duration_ms",
    "focused_duration_ms",
    "tab_switches",
    "instruction_variant",
    "ai_assisted",
)


class MaximumAnnotationsReached(Exception):
    """The task already holds ``project.maximum_annotations`` submissions."""

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(
            f"Maximum annotations limit reached ({limit}). "
            "Cannot add more annotations to this task."
        )


def _has_result(result: Any) -> bool:
    return bool(result) and len(result) > 0


def persist_submission(
    db,
    *,
    task,
    project,
    user_id: str,
    fields: Dict[str, Any],
    was_cancelled: bool = False,
    auto_submitted: Optional[bool] = None,
):
    """Store ``fields`` as ``user_id``'s submission for ``task``; commits.

    ``fields`` holds :data:`SUBMISSION_FIELDS` (missing keys are None).
    ``auto_submitted`` None keeps the historic behaviour (copied from
    ``fields`` on an update only); True/False sets it on new and updated rows.
    Returns the stored row (new, or the existing active one updated in place).
    Raises :class:`MaximumAnnotationsReached`.
    """
    from project_models import Annotation, Task, TaskDraft

    task_id = task.id
    values = {key: fields.get(key) for key in SUBMISSION_FIELDS}
    result = values["result"]

    existing = None
    if not was_cancelled:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"annsubmit:{task_id}:{user_id}"},
        )
        existing = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.completed_by == user_id,
                Annotation.was_cancelled == False,  # noqa: E712
            )
            .order_by(Annotation.created_at.desc())
            .first()
        )

    def _apply(target) -> None:
        target.result = values["result"]
        target.draft = values["draft"]
        target.lead_time = values["lead_time"]
        target.active_duration_ms = values["active_duration_ms"]
        target.focused_duration_ms = values["focused_duration_ms"]
        target.tab_switches = values["tab_switches"] or 0
        target.instruction_variant = values["instruction_variant"]
        target.ai_assisted = bool(values["ai_assisted"])
        target.auto_submitted = (
            bool(auto_submitted)
            if auto_submitted is not None
            else bool(fields.get("auto_submitted") or False)
        )

    if existing is not None:
        row = existing
        _apply(row)
    else:
        row = Annotation(
            id=str(uuid.uuid4()),
            task_id=task_id,
            project_id=task.project_id,
            completed_by=user_id,
            result=values["result"],
            draft=values["draft"],
            was_cancelled=was_cancelled,
            lead_time=values["lead_time"],
            active_duration_ms=values["active_duration_ms"],
            focused_duration_ms=values["focused_duration_ms"],
            tab_switches=values["tab_switches"] or 0,
            instruction_variant=values["instruction_variant"],
            ai_assisted=bool(values["ai_assisted"]),
        )
        if auto_submitted is not None:
            row.auto_submitted = bool(auto_submitted)

    if existing is None and not was_cancelled and _has_result(result):
        count = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.was_cancelled == False,  # noqa: E712
                Annotation.result != None,  # noqa: E711
                cast(Annotation.result, String) != "[]",
            )
            .count()
        )
        limit = getattr(project, "maximum_annotations", 0) or 0
        if limit > 0 and count >= limit:
            raise MaximumAnnotationsReached(limit)

    if existing is None and _has_result(result):
        # Atomic in-SQL increments (see the API docstring): concurrent
        # submitters of one task must not lose updates; the UPDATE holds the
        # task row lock until commit, serializing the is_labeled check.
        db.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                total_annotations=Task.total_annotations + 1,
                cancelled_annotations=Task.cancelled_annotations + (1 if was_cancelled else 0),
            )
            .execution_options(synchronize_session="fetch")
        )
        if not was_cancelled:
            labeled = (
                db.query(Annotation)
                .filter(
                    Annotation.task_id == task_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                    Annotation.result != None,  # noqa: E711
                    cast(Annotation.result, String) != "[]",
                )
                .count()
            ) + 1
            if project is not None and labeled >= project.min_annotations_per_task:
                db.execute(
                    update(Task)
                    .where(Task.id == task_id)
                    .values(is_labeled=True)
                    .execution_options(synchronize_session="fetch")
                )

    if existing is None:
        db.add(row)

    def _drop_draft() -> None:
        db.query(TaskDraft).filter(
            TaskDraft.task_id == task_id, TaskDraft.user_id == user_id
        ).delete()

    _drop_draft()
    try:
        db.commit()
    except IntegrityError:
        # A concurrent writer won the INSERT race on the partial unique
        # index: adopt its row and fold this submission in. The winner
        # already moved the counters, so they are not applied again.
        db.rollback()
        survivor = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.completed_by == user_id,
                Annotation.was_cancelled == False,  # noqa: E712
            )
            .order_by(Annotation.created_at.desc())
            .first()
        )
        if survivor is None:
            raise
        row = survivor
        _apply(row)
        _drop_draft()
        db.commit()

    db.refresh(row)
    return row


def complete_assignment(db, project, task_id: str, user_id: str, annotation) -> None:
    """Mark the writer's task assignment completed (manual/auto modes)."""
    if (
        project is not None
        and project.assignment_mode in ("manual", "auto")
        and not annotation.was_cancelled
        and annotation.result
    ):
        from utils.assignment_helpers import mark_assignment_completed

        mark_assignment_completed(db, task_id=task_id, user_id=user_id)


class SubmissionAlreadyWithdrawn(Exception):
    """The annotation is already withdrawn (or was cancelled from the start)."""


def withdraw_submission(db, annotation, *, actor_id: str, reason: str):
    """Withdraw ``annotation``: keep the row, mark it withdrawn; no commit.

    Sets ``was_cancelled`` (every reader that skips cancelled rows skips it,
    and the partial unique index lets the author hand in again) and records
    ``withdrawn_at``, ``withdrawn_by`` (``actor_id``: the author, or the
    editor who returned it) and ``withdrawal_reason``. The task's
    ``cancelled_annotations`` grows by one and ``is_labeled`` is cleared when
    fewer active answers than the project's ``min_annotations_per_task``
    remain. The caller checks permission, runs the overlay hooks in the same
    transaction and commits.

    Locks the row first, so two concurrent withdrawals cannot both pass.
    Raises :class:`SubmissionAlreadyWithdrawn` for a cancelled row.
    """
    from project_models import Annotation, Project, Task

    locked = (
        db.query(Annotation)
        .filter(Annotation.id == annotation.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if locked.was_cancelled:
        raise SubmissionAlreadyWithdrawn(locked.id)

    now = datetime.now(timezone.utc)
    locked.was_cancelled = True
    locked.withdrawn_at = now
    locked.withdrawn_by = str(actor_id)
    locked.withdrawal_reason = reason
    locked.updated_at = now

    db.execute(
        update(Task)
        .where(Task.id == locked.task_id)
        .values(cancelled_annotations=Task.cancelled_annotations + 1)
        .execution_options(synchronize_session="fetch")
    )
    db.flush()
    remaining = (
        db.query(Annotation)
        .filter(
            Annotation.task_id == locked.task_id,
            Annotation.was_cancelled == False,  # noqa: E712
            Annotation.result != None,  # noqa: E711
            cast(Annotation.result, String) != "[]",
        )
        .count()
    )
    project = db.query(Project).filter(Project.id == locked.project_id).first()
    minimum = getattr(project, "min_annotations_per_task", None) or 1
    if remaining < minimum:
        db.execute(
            update(Task)
            .where(Task.id == locked.task_id, Task.is_labeled == True)  # noqa: E712
            .values(is_labeled=False)
            .execution_options(synchronize_session="fetch")
        )
    return locked
