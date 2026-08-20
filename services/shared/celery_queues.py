"""Single source of truth for Celery task -> queue routing.

Imported by BOTH the worker app (``services/workers/worker_celery.py``) and the
API dispatch client (``services/api/celery_client.py``); ``/shared`` is on
``sys.path`` in both containers, same as ``models`` and ``metric_filters``.

Why this exists
---------------
There used to be one worker Deployment consuming every queue with 4 execution
slots total (2 replicas x concurrency 2). A single bulk evaluation fans out a
chord of up to ~6940 cell sub-tasks and a generation run enqueues
tasks x models x structures x runs_per_task trials, so long work held every slot
for hours and user-blocking work (immediate evaluation, invitation mail, report
refresh) queued behind it.

Celery message priority does NOT fix that, so don't reach for it:

* Celery never preempts a running task, so a high-priority message still waits
  for a slot occupied by a minutes-long LLM call.
* Prefetch reserves messages before priority is consulted
  (``concurrency * worker_prefetch_multiplier``).
* Redis "priority" is emulated by sharding each queue into extra Redis lists
  (``generation``, ``generation\\x06\\x163``, ...), which breaks LLEN monitoring
  and ``celery purge`` and still only orders within an already-starved queue.

The fix is execution-slot isolation: disjoint queues served by separate worker
pools (``infra/helm/benger/values.yaml`` -> ``workers.queues`` +
``workerPools``). This module is the contract between the two halves.

Queue names are a DEPLOYMENT contract: every name in :data:`QUEUES` must appear
in exactly one pool's ``-Q`` list, or its messages strand with no consumer.
Enforced by ``services/workers/tests/test_celery_queues.py``, which parses
values.yaml directly.

Ownership note: this table lives in platform, and deliberately includes the
extended task names as plain string keys. Per the split rule in CLAUDE.md, queue
names are an extension-point contract, and a string-keyed lookup that runs no
proprietary logic stays in platform "even if some of the strings are
extended-feature names".
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# --- Queue names ------------------------------------------------------------
# Served by the `fast` pool: user-blocking, seconds, no local ML models.
INTERACTIVE = "interactive"
# Served by the `aux` pool. Kept off `interactive` on purpose: a rate-limited
# task takes the limit_task branch (celery/worker/strategy.py) WITHOUT a
# qos.increment_eventually(), so it holds its prefetch slot while waiting for a
# token. A 200-address bulk invite at 30/m would otherwise pin the interactive
# pool for ~7 minutes.
EMAILS = "emails"
# Also `aux`: short periodic housekeeping + beat sweeps. Notably
# sweep_missing_immediate_evals, which is the recovery path for immediate
# evaluation -- behind a generation run it would never get to run at all.
MAINTENANCE = "maintenance"
# Served by the `workers` (bulk) pool: minutes-to-hours, memory-hungry.
GENERATION = "generation"
EVALUATION = "evaluation"
BULK = "bulk"

QUEUES = (INTERACTIVE, EMAILS, MAINTENANCE, GENERATION, EVALUATION, BULK)

# Retired queue names kept as consumers only while their Redis lists drain.
# The pool-split names ("celery", "default") were dropped 2026-07-30 after
# `LLEN` reached 0 in both namespaces (issue #286). Repopulate this tuple when
# the next queue retirement needs a drain window — the pool checker and tests
# handle it generically.
LEGACY_QUEUES: tuple[str, ...] = ()

# Where a task with no declared queue lands. Deliberately `maintenance` and NOT
# `interactive`: an unrouted task should be slow-and-visible, never a black hole
# (an unconsumed queue) and never a thief of student-facing slots.
DEFAULT_QUEUE = MAINTENANCE

# --- The table --------------------------------------------------------------
TASK_QUEUES: dict[str, str] = {
    # --- interactive: a human is waiting on the result right now ---
    "tasks.run_single_sample_evaluation": INTERACTIVE,
    "tasks.grade_and_schedule_card": INTERACTIVE,  # extended
    "tasks.auto_submit_expired_timer": INTERACTIVE,  # extended; ETA, see note below
    "tasks.update_report_annotations_async": INTERACTIVE,
    "tasks.lti_push_grade": INTERACTIVE,  # extended
    # --- emails: rate-limited, own pool ---
    "emails.send_invitation": EMAILS,
    "emails.send_bulk_invitations": EMAILS,
    "emails.send_notification_batch": EMAILS,
    "emails.send_account_activation": EMAILS,
    # --- maintenance: periodic housekeeping, nobody is blocked ---
    "tasks.recompute_aggregates": MAINTENANCE,
    "tasks.sweep_missing_immediate_evals": MAINTENANCE,
    "tasks.reconcile_grading_usage": MAINTENANCE,  # extended
    "tasks.lti_grade_sync_sweep": MAINTENANCE,  # extended
    "tasks.cleanup_project_data": MAINTENANCE,
    "tasks.get_supported_metrics": MAINTENANCE,
    # --- generation: one LLM call per task, minutes each ---
    "tasks.generate_response": GENERATION,
    "tasks.generate_llm_responses": GENERATION,
    "tasks.generate_synthetic_data": GENERATION,
    "tasks.generate_bewertungsbogen": GENERATION,  # extended; per-task rubric
    # extended; Skript -> synthetic Klausur / Karteikarten deck. One LLM call
    # per job over a whole lecture script (up to 400k chars in, 32k tokens out),
    # so it belongs with the other minutes-long generation work, NOT on
    # `interactive` — the student polls for it and is not holding a slot.
    "tasks.generate_synthetic_project": GENERATION,  # extended
    # --- evaluation: orchestrator + the big chord fan-out ---
    "tasks.run_evaluation": EVALUATION,
    "tasks.run_multi_field_evaluation": EVALUATION,  # back-compat alias of the above
    "tasks.evaluate_generation_cell": EVALUATION,
    "tasks.evaluate_annotation_cell": EVALUATION,
    "tasks.finalize_evaluation_run": EVALUATION,
    # --- bulk: long single jobs. NOT on `aux` -- two concurrent exports would
    # block invitation mail, which is the same starvation just relocated.
    "tasks.export_project": BULK,
    "tasks.import_project": BULK,
}

# Extended task names, tracked separately so the platform-side test can assert
# they are still routed even though `benger_extended` is not installed there.
# A platform-side deletion would otherwise silently strand them on DEFAULT_QUEUE.
EXTENDED_TASK_NAMES = frozenset(
    {
        "tasks.grade_and_schedule_card",
        "tasks.auto_submit_expired_timer",
        "tasks.lti_push_grade",
        "tasks.reconcile_grading_usage",
        "tasks.lti_grade_sync_sweep",
        "tasks.generate_bewertungsbogen",
        "tasks.generate_synthetic_project",
    }
)

# --- Time limits, per queue class -------------------------------------------
# There were no time limits at all before this, so a wedged provider call could
# hold an execution slot forever. (soft, hard) seconds.
#
# `interactive` is 180/240 to sit inside the frontend's 300_000 ms poll ceiling
# (services/frontend/src/lib/api/evaluations.ts, pollImmediateEvaluation) with
# ~60s of slack for the 2s poller to observe the terminal state. Note this only
# improves UX because run_single_sample_evaluation catches SoftTimeLimitExceeded
# and marks the EvaluationRun failed -- without that handler the hard kill would
# leave the row `running` and the UI would spin the full 5 minutes anyway.
QUEUE_TIME_LIMITS: dict[str, tuple[int, int]] = {
    INTERACTIVE: (180, 240),
    EMAILS: (60, 90),
    MAINTENANCE: (600, 660),
    GENERATION: (1800, 2100),
    # 3600 hard: a cell is one target x ALL judge-runs of its config — a
    # 12-call multi-judge repeat cell (3 passes x 4 judges, 30-100s/call
    # plus provider retries) legitimately runs 20-40 min. The old 1200s
    # hard limit SIGKILLed such cells without a trace (no rows, no retry,
    # chord never fires -> run stuck 'running'). Stays below the broker
    # visibility_timeout (7200) so acks_late redelivery semantics hold.
    EVALUATION: (3300, 3600),
    BULK: (5100, 5400),
}

# The orchestrator enumerates up to ~6940 cells before dispatching the chord and
# is not itself a cell, so it gets its own budget rather than the cell number.
TASK_TIME_LIMIT_OVERRIDES: dict[str, tuple[int, int]] = {
    "tasks.run_evaluation": (600, 900),
    "tasks.run_multi_field_evaluation": (600, 900),
}


def register_task_queue(task_name: str, queue: str) -> None:
    """Claim a queue for a task name at import time.

    Extension hook for out-of-tree packages. The queue must already be one of
    :data:`QUEUES`; a genuinely new queue name needs a worker pool to consume it,
    which is a Helm/values decision and cannot be made from Python.
    """
    if queue not in QUEUES:
        raise ValueError(f"{queue!r} is not a declared queue; expected one of {QUEUES}")
    TASK_QUEUES[task_name] = queue


def queue_for(task_name: str) -> str:
    """Return the queue for ``task_name``.

    Total function: never raises, so a missing entry can never 500 a request
    path. An unknown name logs a warning and lands on :data:`DEFAULT_QUEUE`.
    """
    queue = TASK_QUEUES.get(task_name)
    if queue is None:
        logger.warning(
            "celery_queues: no queue declared for task %r; falling back to %r. "
            "Add it to TASK_QUEUES in services/shared/celery_queues.py.",
            task_name,
            DEFAULT_QUEUE,
        )
        return DEFAULT_QUEUE
    return queue


def time_limits_for(task_name: str) -> tuple[int, int]:
    """Return ``(soft_time_limit, time_limit)`` seconds for ``task_name``."""
    override = TASK_TIME_LIMIT_OVERRIDES.get(task_name)
    if override is not None:
        return override
    return QUEUE_TIME_LIMITS[queue_for(task_name)]


def route_task(name, args=None, kwargs=None, options=None, task=None, **kw):
    """Celery ``task_routes`` callable.

    Used by both ``Celery.send_task`` (via ``app.amqp.router``) and worker-side
    ``apply_async``. Because it routes on the *name*, it also covers task names
    the sending process has not imported -- which is how the API can correctly
    route extended tasks it never registers.

    An explicit ``queue=`` at a call site still wins: celery/app/routes.py does
    ``lpmerge(expand_destination(route), options)`` and lpmerge writes the
    right-hand mapping (the per-send options) over the left. That is deliberate
    here -- it makes this table's rollout a no-op until call sites drop their
    ``queue=`` kwargs, and it keeps an older extended release working against a
    newer platform during the cross-repo deploy window.
    """
    return {"queue": queue_for(name)}


def task_annotations() -> dict[str, dict]:
    """Per-task ``task_annotations``: time limits, plus the email rate limits.

    Built from the table so limits cannot drift away from queue membership.
    """
    annotations: dict[str, dict] = {}
    for task_name in TASK_QUEUES:
        soft, hard = time_limits_for(task_name)
        annotations[task_name] = {"soft_time_limit": soft, "time_limit": hard}

    # Rate limits are per-worker-process token buckets, so the `aux` pool runs a
    # single replica to keep the configured rate honest. With the old 2-replica
    # shared pool the effective invitation rate was double the number below.
    annotations["emails.send_invitation"]["rate_limit"] = "30/m"
    annotations["emails.send_bulk_invitations"]["rate_limit"] = "5/m"
    return annotations


def celery_queue_defs():
    """kombu ``Queue`` objects for ``task_queues``.

    Declaring these makes the contract visible to ``celery inspect`` and to
    monitoring. Legacy names are included so they keep a declared home for the
    duration of the drain window.

    Leave ``task_create_missing_queues`` at its default ``True``: celery's
    ``Queues.__missing__`` then auto-creates an undeclared name instead of
    raising ``QueueNotFound``, so a stray or legacy ``queue=`` can never blow up
    a request path.
    """
    from kombu import Queue

    return tuple(Queue(name) for name in QUEUES + LEGACY_QUEUES)
