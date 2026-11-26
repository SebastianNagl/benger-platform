"""Delivery of in-app problem reports as GitHub issues (``bug_reports``).

Runs the worker's sync lane against the test database and a mock GitHub API
(``httpx.MockTransport``): the issue text and what stays out of it, labels,
retries of transient errors, permanent errors, the token never in a stored
error, the "no target" case and the sweep of stale pending reports.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import httpx
import pytest
from sqlalchemy import update

import bug_reports as reports
from models import BugReport, User
from tests.integration.test_bug_reports import _context

pytestmark = [pytest.mark.integration]

def _stored_report(db, **extra) -> BugReport:
    user_id = None
    if extra.pop("signed_in", True):
        user = User(
            id=str(uuid.uuid4()),
            username=f"brd-{uuid.uuid4().hex[:8]}",
            email=f"brd-{uuid.uuid4().hex[:8]}@example.com",
            name="Visible Name",
            is_active=True,
        )
        db.add(user)
        db.flush()
        user_id = user.id
    ctx = reports.clean_context(_context())
    ctx["server"] = {"received_at": "2026-11-26T10:00:01+00:00", "core_version": "2.89"}
    row = BugReport(
        reporter_id=user_id,
        title="Save ```button``` @someone does nothing\nsecond line",
        description="Steps: click save.\n```\nstill text\n```\n@octocat please look",
        expected="Saved.",
        context=ctx,
        screenshot_key="bug_reports/2026/11/x.png",
        status="pending",
        **extra,
    )
    db.add(row)
    db.commit()
    return row


class FakeGitHub:
    """Records issue posts and answers from a script of responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: List[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, payload = self.responses.pop(0) if self.responses else (201, None)
        if status == 201 and payload is None:
            n = len(self.requests)
            payload = {"number": n, "html_url": f"https://github.example/o/r/issues/{n}"}
        return httpx.Response(status, json=payload)

    def create_issue(self, target, title, body):
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return reports.create_github_issue(target, title, body, client=client)


@pytest.fixture
def target(monkeypatch):
    monkeypatch.setenv("BUG_REPORT_GITHUB_REPO", "example-owner/example-repo")
    monkeypatch.setenv("BUG_REPORT_GITHUB_TOKEN", "secret-token-value")
    monkeypatch.delenv("BUG_REPORT_GITHUB_LABELS", raising=False)
    monkeypatch.setenv("BUG_REPORT_GITHUB_API_URL", "https://github.example/api/")


def test_delivery_creates_the_issue_and_records_it(test_db, target):
    row = _stored_report(test_db)
    github = FakeGitHub()
    outcome = reports.deliver_report(
        test_db, row.id, final=False, frontend_url="https://app.example", create_issue=github.create_issue
    )
    assert outcome.state == "delivered" and not outcome.retry
    test_db.refresh(row)
    assert row.status == "delivered"
    assert row.issue_number == 1 and row.issue_url == "https://github.example/o/r/issues/1"
    assert row.delivery_attempts == 1 and row.delivery_error is None and row.delivered_at

    (request,) = github.requests
    assert request.url == "https://github.example/api/repos/example-owner/example-repo/issues"
    assert request.headers["authorization"] == "Bearer secret-token-value"
    payload = json.loads(request.content)
    assert payload["labels"] == ["bug", "user-report"]
    assert payload["title"] == "Save ```button``` @someone does nothing second line"
    body = payload["body"]
    # The reporter's text is fenced so no backtick run inside can close it.
    assert "````text\nSteps: click save.\n```\nstill text\n```\n@octocat please look\n````" in body
    assert f"Reporter: user {row.reporter_id}" in body
    assert "Visible Name" not in body and "@example.com" not in body
    assert "Page: /projects/0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11/tasks" in body
    assert "Viewport: 1280x800 @2x" in body
    assert "GET /api/projects/1 -> 500 request-id r-1" in body
    assert "TypeError: x is undefined" in body
    assert f"https://app.example/api/bug-reports/{row.id}/screenshot" in body
    assert f"https://app.example/admin/bug-reports?report={row.id}" in body
    assert "secret-token-value" not in body

    again = reports.deliver_report(test_db, row.id, final=False, create_issue=github.create_issue)
    assert again.state == "skipped" and len(github.requests) == 1


def test_anonymous_contact_address_stays_out_of_the_issue(test_db, target):
    row = _stored_report(test_db, signed_in=False, contact_email="someone@example.com")
    github = FakeGitHub()
    reports.deliver_report(test_db, row.id, final=False, frontend_url="https://app.example", create_issue=github.create_issue)
    body = json.loads(github.requests[0].content)["body"]
    assert "someone@example.com" not in body
    assert "Reporter: not signed in, left a contact address (see BenGER)" in body


def test_transient_errors_retry_then_fail_on_the_last_attempt(test_db, target):
    row = _stored_report(test_db)
    github = FakeGitHub((502, {"message": "Bad gateway"}), (403, {"message": "API rate limit exceeded"}), (503, {}))
    first = reports.deliver_report(test_db, row.id, final=False, create_issue=github.create_issue)
    assert first.retry and first.state == "pending"
    test_db.refresh(row)
    assert row.status == "pending" and row.delivery_attempts == 1
    assert row.delivery_error == "GitHub answered 502: Bad gateway"

    second = reports.deliver_report(test_db, row.id, final=False, create_issue=github.create_issue)
    assert second.retry  # a rate-limit 403 is worth waiting for

    last = reports.deliver_report(test_db, row.id, final=True, create_issue=github.create_issue)
    assert not last.retry and last.state == "failed"
    test_db.refresh(row)
    assert row.status == "failed" and row.delivery_attempts == 3


def test_permanent_errors_fail_at_once_without_leaking_the_token(test_db, target):
    row = _stored_report(test_db)
    github = FakeGitHub((401, {"message": "Bad credentials"}))
    outcome = reports.deliver_report(test_db, row.id, final=False, create_issue=github.create_issue)
    assert not outcome.retry and outcome.state == "failed"
    test_db.refresh(row)
    assert row.delivery_error == "GitHub answered 401: Bad credentials"
    assert "secret-token-value" not in row.delivery_error


def test_refused_labels_still_create_the_issue(test_db, target):
    row = _stored_report(test_db)
    github = FakeGitHub((422, {"message": "Validation Failed", "errors": [{"field": "labels"}]}))
    outcome = reports.deliver_report(test_db, row.id, final=False, create_issue=github.create_issue)
    assert outcome.state == "delivered"
    assert "labels" in json.loads(github.requests[0].content)
    assert "labels" not in json.loads(github.requests[1].content)


def test_network_errors_are_transient(test_db, target):
    row = _stored_report(test_db)

    def unreachable(request):
        raise httpx.ConnectError("refused")

    def create_issue(target, title, body):
        client = httpx.Client(transport=httpx.MockTransport(unreachable))
        return reports.create_github_issue(target, title, body, client=client)

    outcome = reports.deliver_report(test_db, row.id, final=False, create_issue=create_issue)
    assert outcome.retry
    test_db.refresh(row)
    assert row.delivery_error == "GitHub unreachable (ConnectError)"


def test_without_a_target_the_report_is_only_stored(test_db, monkeypatch):
    monkeypatch.delenv("BUG_REPORT_GITHUB_REPO", raising=False)
    monkeypatch.setenv("BUG_REPORT_GITHUB_TOKEN", "t")
    row = _stored_report(test_db)

    def never(*args, **kwargs):
        raise AssertionError("no delivery without a target")

    outcome = reports.deliver_report(test_db, row.id, final=False, create_issue=never)
    assert outcome.state == "stored"
    test_db.refresh(row)
    assert row.status == "stored" and row.delivery_attempts == 0


def test_delivery_target_from_env(monkeypatch):
    monkeypatch.setenv("BUG_REPORT_GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("BUG_REPORT_GITHUB_TOKEN", "t")
    monkeypatch.setenv("BUG_REPORT_GITHUB_LABELS", " user-report, ,triage,user-report")
    monkeypatch.delenv("BUG_REPORT_GITHUB_API_URL", raising=False)
    target = reports.delivery_target()
    assert target.labels == ("user-report", "triage")
    assert target.api_url == "https://api.github.com"
    monkeypatch.setenv("BUG_REPORT_GITHUB_TOKEN", "very-secret")
    assert "very-secret" not in repr(reports.delivery_target())
    monkeypatch.setenv("BUG_REPORT_GITHUB_REPO", "not a repo")
    assert reports.delivery_target() is None
    monkeypatch.setenv("BUG_REPORT_GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("BUG_REPORT_GITHUB_TOKEN", " ")
    assert reports.delivery_target() is None


def test_sweep_requeues_only_stale_pending_reports(test_db):
    stale = _stored_report(test_db)
    fresh = _stored_report(test_db)
    done = _stored_report(test_db)
    done.status = "delivered"
    test_db.commit()
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    test_db.execute(
        update(BugReport).where(BugReport.id.in_([stale.id, done.id])).values(updated_at=long_ago)
    )
    test_db.commit()
    sent: List[str] = []
    queued_ids = reports.requeue_stale(test_db, sent.append)
    assert stale.id in queued_ids and fresh.id not in queued_ids and done.id not in queued_ids
    assert sent == queued_ids


def test_clean_context_helpers():
    assert reports.clean_path("https://h/x/activate/abc?x=1") == "/x/activate/[redacted]"
    assert reports.clean_path("/projects/0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11") == (
        "/projects/0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11"
    )
    assert reports.clean_path("/shares/" + "q" * 30) == "/shares/[redacted]"
    assert reports.clean_context("nope") == {}
    assert reports.clean_context({"viewport": {"width": "1"}, "device_pixel_ratio": float("nan")}) == {}
    assert reports.sniff_screenshot_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert reports.sniff_screenshot_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert reports.sniff_screenshot_type(b"GIF89a") is None
    assert [reports.retry_countdown(n) for n in range(8)] == [60, 120, 240, 480, 960, 1920, 3600, 3600]
