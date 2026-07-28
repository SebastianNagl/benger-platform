"""The API must publish to the same queues the workers consume.

The API has its own Celery app (``celery_client._create_celery_app``) that is
dispatch-only -- it never registers a task. Before the worker-pool split it also
had no ``task_routes`` at all, so where a message landed was decided by whatever
``queue=`` each call site happened to pass. That is how
``tasks.grade_and_schedule_card`` ended up on Celery's default ``celery`` queue:
its call site simply passes no queue.
"""

import celery_queues
import pytest
from celery_client import _create_celery_app


@pytest.fixture(scope="module")
def router():
    return _create_celery_app().amqp.router


@pytest.mark.parametrize(
    "task_name,expected",
    [
        # The task this whole change exists for.
        ("tasks.run_single_sample_evaluation", celery_queues.INTERACTIVE),
        # Extended task the API never registers -- routing is by NAME, so the
        # API can still place it correctly. This is the flashcards bug.
        ("tasks.grade_and_schedule_card", celery_queues.INTERACTIVE),
        ("tasks.update_report_annotations_async", celery_queues.INTERACTIVE),
        ("emails.send_invitation", celery_queues.EMAILS),
        ("emails.send_notification_batch", celery_queues.EMAILS),
        ("emails.send_account_activation", celery_queues.EMAILS),
        ("tasks.generate_response", celery_queues.GENERATION),
        ("tasks.run_evaluation", celery_queues.EVALUATION),
        # Moved off `default` so a long export cannot block interactive work.
        ("tasks.export_project", celery_queues.BULK),
        ("tasks.import_project", celery_queues.BULK),
    ],
)
def test_api_routes_task_to_expected_queue(router, task_name, expected):
    assert router.route({}, task_name)["queue"].name == expected


def test_unregistered_task_name_still_routes(router):
    """send_task() resolves on the name, so an unknown task cannot 500.

    It lands on the fallback queue -- which is a queue a pool actually consumes.
    """
    assert (
        router.route({}, "tasks.some_future_task")["queue"].name
        == celery_queues.DEFAULT_QUEUE
    )


def test_explicit_queue_kwarg_still_wins(router):
    """Pinning the override semantics on purpose -- do not "clean this up".

    celery/app/routes.py does ``lpmerge(expand_destination(route), options)`` and
    lpmerge writes the right-hand mapping (the per-send options) over the left.
    Two things depend on it:

      1. The routing table could be introduced with every ``queue=`` call site
         still in place, making that commit a provable no-op.
      2. During the cross-repo deploy window, prod runs NEW platform against OLD
         extended, which still passes ``queue="celery"`` explicitly. That has to
         keep working, and it does, because `celery` stays in the fast pool's -Q
         list for the drain window.
    """
    assert router.route({"queue": "celery"}, "tasks.run_single_sample_evaluation")[
        "queue"
    ].name == "celery"


def test_no_task_routes_to_a_retired_queue(router):
    """Nothing the API sends may target a drain-only queue by default."""
    for task_name in celery_queues.TASK_QUEUES:
        assert (
            router.route({}, task_name)["queue"].name
            not in celery_queues.LEGACY_QUEUES
        )
