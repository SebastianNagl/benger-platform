"""Deterministic Celery task-id scheme for the generation fan-out.

EVERY generation dispatch — the initial fan-out (``generation_task_list.py``)
AND resume/retry (``generation.py``) — fans out one ``tasks.generate_response``
Celery job per ``(generation × run_index)`` (up to 25 jobs for a single
``ResponseGeneration`` row), each with a **deterministic** id
``f"{generation_id}:{run_index}:{epoch}"`` (passed as ``task_id=`` to
``send_task``).

So stop / pause / supersede revoke the *whole* fan-out by reconstructing the ids
from the persisted ``runs_requested`` count and ``dispatch_epoch`` — no
per-generation id needs storing, and every dispatch path is covered by one
scheme. The ``generation_id`` is a fresh uuid minted per cell per trigger, so the
ids are globally unique and never collide across re-runs.

Why the ``epoch``: resume/retry RE-dispatch the same ``(generation, run_index)``
trials. If they reused the prior id, Celery's in-memory revoked set (every worker
remembers a revoked id for ~3h) would **discard** the re-dispatch — the trial
would never run and resume/retry would silently regenerate nothing. So each
re-dispatch bumps ``dispatch_epoch`` and the id carries it: the new ids were
never revoked, while stop/pause still revoke the *current* epoch. The initial
fan-out runs at ``epoch=0`` (the row's default).
"""

from __future__ import annotations

from typing import List


def generation_run_task_id(generation_id: str, run_index: int, epoch: int = 0) -> str:
    """The deterministic Celery task id for one trial of a generation.

    ``epoch`` is the parent's ``dispatch_epoch`` (0 for the initial fan-out,
    incremented on each resume/retry re-dispatch) so a re-dispatched trial gets a
    fresh, un-revoked id.
    """
    return f"{generation_id}:{run_index}:{int(epoch or 0)}"


def generation_run_task_ids(
    generation_id: str, runs_requested: int | None, epoch: int = 0
) -> List[str]:
    """All deterministic Celery task ids for a generation's fan-out at ``epoch``.

    ``runs_requested`` is the per-trigger run count stored on the parent
    ``ResponseGeneration`` row. Defaults to a single id when it is missing or
    non-positive (mirrors the dispatch loop's ``max(1, ...)`` floor).
    """
    n = runs_requested if runs_requested and runs_requested > 0 else 1
    return [generation_run_task_id(generation_id, i, epoch) for i in range(n)]


def send_generation_trial(
    celery_app,
    *,
    generation_id: str,
    project_id,
    task_id,
    model_id,
    structure_key,
    force_rerun: bool,
    organization_id,
    run_index: int,
    epoch: int = 0,
) -> None:
    """Fan out ONE ``tasks.generate_response`` trial with the deterministic,
    epoch-stamped task id.

    The single home for the dispatch contract (arg order, ``queue``, ``task_id``)
    shared by the initial fan-out (``generation_task_list.py``) and resume/retry
    (``generation.py``) — so the two paths can't drift on the positional args the
    worker unpacks.
    """
    celery_app.send_task(
        "tasks.generate_response",
        args=[
            generation_id,
            project_id,
            task_id,
            model_id,
            structure_key,
            force_rerun,
            organization_id,
            run_index,
        ],
        queue="generation",
        task_id=generation_run_task_id(generation_id, run_index, epoch),
    )
