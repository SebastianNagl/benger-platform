"""Guards for the task -> queue routing table (services/shared/celery_queues.py).

These are the assertions that keep the worker-pool split from silently rotting.
The failure mode they prevent is quiet and nasty: a task with no routing entry
lands on the fallback queue, or a queue nobody consumes swallows messages that
simply never run.

Chart-side contract (every queue has exactly one consuming pool) is checked
separately by ``services/workers/scripts/check_celery_queue_pools.py``, which
runs in the Python Lint CI job -- the workers test container only mounts
``services/workers`` and ``services/shared``, so ``infra/helm`` is not reachable
from here.
"""

import celery_queues
import pytest

# Every task WE own lives under one of these two namespaces.
OUR_NAMESPACES = ("tasks.", "emails.")

# Task names registered onto the same app by third parties, which we neither own
# nor route: celery's own bookkeeping (celery.chord, celery.backend_cleanup) and
# the fixture tasks pytest-celery's vendor worker registers when the full suite
# runs (add, ping, xsum, ...). Filtering only on `celery.` was not enough -- the
# targeted run passed and the full-suite run failed on the pytest_celery ones.
EXTERNAL_PREFIXES = ("celery.", "pytest_celery.")


def _registered_task_names():
    """Every task name the worker registers, extended included when installed."""
    import tasks  # noqa: F401  -- import registers everything onto the app

    from worker_celery import app

    return {n for n in app.tasks if n.startswith(OUR_NAMESPACES)}


def test_no_task_escapes_the_known_namespaces():
    """Guard for the filter above.

    _registered_task_names() only looks at `tasks.*` / `emails.*`, so a task
    registered under some new namespace would silently escape the completeness
    check. Fail loudly instead, rather than letting the guard quietly narrow.
    """
    import tasks  # noqa: F401

    from worker_celery import app

    unclassified = {
        n
        for n in app.tasks
        if not n.startswith(OUR_NAMESPACES) and not n.startswith(EXTERNAL_PREFIXES)
    }
    assert not unclassified, (
        "tasks registered under an unrecognised namespace -- either add the "
        f"namespace to OUR_NAMESPACES or the plugin to EXTERNAL_PREFIXES: {sorted(unclassified)}"
    )


def test_every_registered_task_has_a_declared_queue():
    """A new task without a routing entry must fail CI, not silently fall back.

    This is the single most valuable assertion in the file: without it, someone
    adds `@app.task` six months from now, it lands on DEFAULT_QUEUE, and nobody
    notices until a student's grading is stuck behind a bulk run.
    """
    missing = _registered_task_names() - set(celery_queues.TASK_QUEUES)
    assert not missing, (
        "these registered tasks have no queue in celery_queues.TASK_QUEUES: "
        f"{sorted(missing)}"
    )


def test_extended_task_names_are_still_routed():
    """Companion to the above for the platform-only CI run.

    In platform CI `benger_extended` is not installed, so the extended tasks are
    never registered and the completeness check above cannot see them. Without
    this, deleting an extended entry from the table would pass platform CI and
    only stranded in extended's suite -- or worse, in production.
    """
    missing = celery_queues.EXTENDED_TASK_NAMES - set(celery_queues.TASK_QUEUES)
    assert not missing, f"extended tasks dropped from the routing table: {sorted(missing)}"


def test_no_task_routes_to_an_undeclared_queue():
    """Every routed queue must be a real queue name in QUEUES."""
    bad = {
        name: queue
        for name, queue in celery_queues.TASK_QUEUES.items()
        if queue not in celery_queues.QUEUES
    }
    assert not bad, f"tasks routed to undeclared queues: {bad}"


def test_table_has_no_stale_entries():
    """Entries must correspond to a real task, or be a known extended name.

    Catches the reverse drift: a task gets renamed/deleted and its routing entry
    lingers, which makes the table lie about what actually exists.
    """
    registered = _registered_task_names()
    stale = set(celery_queues.TASK_QUEUES) - registered - celery_queues.EXTENDED_TASK_NAMES
    assert not stale, (
        f"routing entries for tasks that are not registered: {sorted(stale)}"
    )


def test_legacy_queues_are_not_routing_targets():
    """Legacy names exist only to drain; nothing new may be routed onto them."""
    targets = set(celery_queues.TASK_QUEUES.values())
    overlap = targets & set(celery_queues.LEGACY_QUEUES)
    assert not overlap, (
        f"tasks routed onto retired queues {sorted(overlap)}; those are drain-only"
    )


def test_beat_schedule_does_not_override_the_routing_table():
    """Beat options go through the same router and would override task_routes.

    A pinned `options: {"queue": ...}` in the schedule is how the table silently
    drifts out of sync for exactly the periodic tasks nobody watches.
    """
    import tasks  # noqa: F401

    from worker_celery import app

    offenders = {}
    for entry_name, entry in (app.conf.beat_schedule or {}).items():
        pinned = (entry.get("options") or {}).get("queue")
        if pinned is None:
            continue
        expected = celery_queues.queue_for(entry["task"])
        if pinned != expected:
            offenders[entry_name] = (pinned, expected)
    assert not offenders, (
        "beat entries pin a queue that disagrees with celery_queues "
        f"(entry: (pinned, expected)): {offenders}"
    )


def test_beat_tasks_are_routed():
    """Every scheduled task must itself have a routing entry."""
    import tasks  # noqa: F401

    from worker_celery import app

    missing = {
        entry["task"]
        for entry in (app.conf.beat_schedule or {}).values()
        if entry["task"] not in celery_queues.TASK_QUEUES
    }
    assert not missing, f"scheduled tasks with no queue: {sorted(missing)}"


def test_interactive_queue_holds_the_user_blocking_tasks():
    """Pin the tasks this whole change exists to protect.

    If a refactor moves immediate evaluation back onto a bulk queue, that is the
    regression -- and it would otherwise be invisible until students complained.
    """
    for name in (
        "tasks.run_single_sample_evaluation",
        "tasks.update_report_annotations_async",
        "tasks.auto_submit_expired_timer",
        "tasks.grade_and_schedule_card",
        "tasks.lti_push_grade",
    ):
        assert celery_queues.queue_for(name) == celery_queues.INTERACTIVE, (
            f"{name} must stay on the interactive queue"
        )


def test_long_running_tasks_stay_off_the_interactive_queue():
    """The inverse guard: nothing slow may share the interactive pool."""
    for name in (
        "tasks.generate_response",
        "tasks.run_evaluation",
        "tasks.evaluate_generation_cell",
        "tasks.evaluate_annotation_cell",
        "tasks.export_project",
        "tasks.import_project",
    ):
        assert celery_queues.queue_for(name) != celery_queues.INTERACTIVE, (
            f"{name} is long-running and must not share the interactive pool"
        )


def test_unknown_task_falls_back_without_raising():
    """queue_for must be total: a missing entry cannot 500 a request path."""
    assert celery_queues.queue_for("tasks.does_not_exist") == celery_queues.DEFAULT_QUEUE


def test_default_queue_is_actually_consumed():
    """The fallback must be a real queue, never a black hole."""
    assert celery_queues.DEFAULT_QUEUE in celery_queues.QUEUES
    # And deliberately not the interactive queue: an unrouted task should be
    # slow-and-visible, not a thief of student-facing slots.
    assert celery_queues.DEFAULT_QUEUE != celery_queues.INTERACTIVE


def test_route_task_returns_the_declared_queue():
    """The celery task_routes callable resolves on name alone."""
    assert celery_queues.route_task("tasks.run_single_sample_evaluation") == {
        "queue": celery_queues.INTERACTIVE
    }
    assert celery_queues.route_task("emails.send_invitation") == {
        "queue": celery_queues.EMAILS
    }


def test_worker_app_uses_the_shared_routing_table():
    """Regression guard: the old 'tasks.*' -> default glob must not come back."""
    import tasks  # noqa: F401

    from worker_celery import app

    assert celery_queues.route_task in tuple(app.conf.task_routes), (
        "worker app must route through celery_queues.route_task"
    )
    assert app.conf.worker_prefetch_multiplier == 1


def test_time_limits_are_ordered_and_present_for_every_task():
    """Soft must be strictly below hard, or the soft handler never runs.

    For interactive work the hard limit also has to stay under the frontend's
    300s poll ceiling, otherwise the UI times out before the worker gives up and
    the user sees a spinner rather than an error.
    """
    for name in celery_queues.TASK_QUEUES:
        soft, hard = celery_queues.time_limits_for(name)
        assert 0 < soft < hard, f"{name}: bad time limits ({soft}, {hard})"

    _, hard = celery_queues.time_limits_for("tasks.run_single_sample_evaluation")
    assert hard < 300, (
        "immediate eval hard limit must stay under the frontend's 300s poll "
        f"timeout (pollImmediateEvaluation); got {hard}"
    )


def test_annotations_cover_every_task_and_keep_the_email_rate_limits():
    annotations = celery_queues.task_annotations()
    assert set(annotations) == set(celery_queues.TASK_QUEUES)
    assert annotations["emails.send_invitation"]["rate_limit"] == "30/m"
    assert annotations["emails.send_bulk_invitations"]["rate_limit"] == "5/m"


def test_declared_queues_include_legacy_for_the_drain_window():
    """Legacy names must stay declared until the cleanup PR removes them."""
    declared = {q.name for q in celery_queues.celery_queue_defs()}
    assert set(celery_queues.QUEUES) <= declared
    assert set(celery_queues.LEGACY_QUEUES) <= declared


def test_register_task_queue_rejects_undeclared_queues():
    with pytest.raises(ValueError):
        celery_queues.register_task_queue("tasks.whatever", "not-a-queue")
