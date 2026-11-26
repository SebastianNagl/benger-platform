"""The problem-report worker tasks: delivery attempts, retries and the sweep.

The delivery logic itself (issue text, GitHub answers, statuses) is covered
against a real database in the API suite
(``tests/integration/test_bug_report_delivery.py``); here the Celery wiring:
which attempt counts as the last, the back-off of a retry, the session
handling and the sweep's sends.
"""

import pytest
from celery.exceptions import Retry

import bug_reports
import celery_queues
import tasks


class _Session:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _run_delivery(monkeypatch, outcome, *, retries=0):
    session = _Session()
    calls = []

    def deliver_report(db, report_id, *, final):
        calls.append((db, report_id, final))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    retried = []

    def retry(countdown=None, **kwargs):
        retried.append(countdown)
        return Retry("retry", countdown)

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(bug_reports, "deliver_report", deliver_report)
    task = tasks.deliver_bug_report
    monkeypatch.setattr(task, "retry", retry)
    task.push_request(retries=retries)
    try:
        result = task.run("report-1")
    except Retry:
        result = "retry"
    finally:
        task.pop_request()
    return session, calls, retried, result


def test_a_delivered_report_returns_its_state(monkeypatch):
    session, calls, retried, result = _run_delivery(
        monkeypatch, bug_reports.DeliveryOutcome("delivered")
    )
    assert result == {"report_id": "report-1", "status": "delivered", "error": None}
    assert calls == [(session, "report-1", False)]
    assert retried == [] and session.closed


def test_a_transient_error_retries_with_back_off(monkeypatch):
    outcome = bug_reports.DeliveryOutcome("pending", retry=True, error="GitHub answered 502")
    session, calls, retried, result = _run_delivery(monkeypatch, outcome, retries=2)
    assert result == "retry"
    assert retried == [bug_reports.retry_countdown(2)] == [240]
    assert calls[0][2] is False and session.closed


def test_the_last_retry_is_final(monkeypatch):
    outcome = bug_reports.DeliveryOutcome("failed", error="GitHub answered 502")
    _session, calls, retried, result = _run_delivery(
        monkeypatch, outcome, retries=bug_reports.MAX_DELIVERY_RETRIES
    )
    assert calls[0][2] is True
    assert retried == [] and result["status"] == "failed"


def test_an_unexpected_error_rolls_back_and_closes(monkeypatch):
    with pytest.raises(RuntimeError):
        _run_delivery(monkeypatch, RuntimeError("db down"))
    session = tasks.SessionLocal()  # the patched factory hands out the same session
    assert session.rolled_back and session.closed


def test_the_sweep_sends_every_stale_report(monkeypatch):
    session = _Session()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(bug_reports, "stale_pending_ids", lambda db, **kw: ["a", "b"])
    sent = []
    monkeypatch.setattr(
        tasks.app, "send_task", lambda name, args=None, **kw: sent.append((name, args))
    )
    result = tasks.sweep_pending_bug_reports.run()
    assert result == {"queued": ["a", "b"]}
    assert sent == [("tasks.deliver_bug_report", ["a"]), ("tasks.deliver_bug_report", ["b"])]
    assert session.closed


def test_both_tasks_run_on_the_maintenance_queue():
    assert celery_queues.TASK_QUEUES["tasks.deliver_bug_report"] == celery_queues.MAINTENANCE
    assert celery_queues.TASK_QUEUES["tasks.sweep_pending_bug_reports"] == celery_queues.MAINTENANCE


def test_the_sweep_is_scheduled_hourly():
    from worker_celery import app

    entry = app.conf.beat_schedule["sweep-pending-bug-reports"]
    assert entry["task"] == "tasks.sweep_pending_bug_reports"
    assert "options" not in entry
    assert entry["schedule"].minute == {40}
