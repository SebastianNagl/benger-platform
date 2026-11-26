"""In-app problem reports (flag ``bug_reports``, migration 160).

Pinned here: the flag closes every route (404 ``feature_disabled``) and
nothing is stored; a signed-in or anonymous report is stored with its
cleaned context and screenshot and its delivery is queued; the size, type and
field checks; the per-user and per-address rate limits; and the superadmin
list, detail, screenshot and redelivery. The delivery itself is in
``test_bug_report_delivery.py``.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List

import pytest
from sqlalchemy import select

import bug_reports as reports
from models import BugReport, User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE = "/api/bug-reports"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


async def _user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"br-{uuid.uuid4().hex[:8]}",
        email=f"br-{uuid.uuid4().hex[:8]}@example.com",
        name="Reporter Person",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@contextmanager
def _session(db_user):
    """Sign in as ``db_user`` (None: no session) for every dependency the
    routes use."""
    from auth_module.dependencies import get_current_user, optional_user, require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = None
    if db_user is not None:
        auth_user = AuthUser(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            name=db_user.name,
            is_superadmin=db_user.is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=db_user.created_at,
        )
    overrides = {optional_user: lambda: auth_user, get_current_user: lambda: auth_user}
    if auth_user is not None:
        overrides[require_user] = lambda: auth_user
    app.dependency_overrides.update(overrides)
    try:
        yield auth_user
    finally:
        for dep in (optional_user, get_current_user, require_user):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture
def storage(monkeypatch):
    """An in-memory stand-in for object storage."""
    from storage.object_storage import object_storage

    objects: Dict[str, bytes] = {}

    def upload_file(data, filename, file_type="uploads", user_id=None, content_type=None, metadata=None):
        key = f"{file_type}/test/{uuid.uuid4().hex}_{filename}"
        objects[key] = data
        return {"file_key": key, "size": len(data), "content_type": content_type}

    def download_to_fileobj(key, fileobj):
        if key not in objects:
            raise FileNotFoundError(key)
        fileobj.write(objects[key])

    def delete_file(key):
        return objects.pop(key, None) is not None

    monkeypatch.setattr(object_storage, "upload_file", upload_file)
    monkeypatch.setattr(object_storage, "download_to_fileobj", download_to_fileobj)
    monkeypatch.setattr(object_storage, "delete_file", delete_file)
    return objects


@pytest.fixture
def queued(monkeypatch) -> List[str]:
    """Delivery sends, captured instead of going to a broker."""
    import celery_client

    sent: List[str] = []

    def send_task_safe(name, args=None, **kwargs):
        assert name == "tasks.deliver_bug_report"
        sent.append(args[0])

    monkeypatch.setattr(celery_client, "send_task_safe", send_task_safe)
    return sent


@pytest.fixture
def limiter(monkeypatch):
    """A fresh memory-backed limiter that counts even under TESTING."""
    import routers.bug_reports as router_module
    from services.rate_limiter import RateLimiter

    fresh = RateLimiter("redis://127.0.0.1:1")
    monkeypatch.setattr(router_module, "rate_limiter", fresh)
    monkeypatch.setenv("TESTING", "false")
    return fresh


def _context(**extra):
    ctx = {
        "page": "https://app.example/projects/0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11/tasks?status=open&token=abc#top",
        "query_keys": ["status", "token"],
        "route_params": {"projectId": "0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11"},
        "time": "2026-11-26T10:00:00.000Z",
        "timezone": "Europe/Berlin",
        "locale": "de",
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
        "viewport": {"width": 1280, "height": 800},
        "device_pixel_ratio": 2,
        "extensions": ["extended"],
        "feature_flags": ["bug_reports"],
        "errors": [{"message": "TypeError: x is undefined", "stack": "at a (b.js:1:2)"}],
        "failed_requests": [
            {"method": "get", "path": "/api/projects/1?secret=1", "status": 500, "request_id": "r-1"},
            {"method": "POST", "path": "/api/auth/reset-password/" + "a" * 40, "status": 400},
        ],
        "navigation": [{"path": "/dashboard"}, {"path": "/reset-password/" + "Zz9" * 10}],
        "cookies": "session=never-kept",
        "body": {"password": "never-kept"},
    }
    ctx.update(extra)
    return ctx


async def _submit(client, *, files=None, **fields):
    data = {"title": "Save button does nothing", "description": "I clicked save and nothing happened."}
    data.update(fields)
    return await client.post(BASE, data=data, files=files)


# --------------------------------------------------------------------------- #
# flag off
# --------------------------------------------------------------------------- #


async def test_flag_off_closes_every_route_and_stores_nothing(
    async_test_client, async_test_db, storage, queued
):
    admin = await _user(async_test_db, superadmin=True)
    await async_test_db.commit()
    with _session(admin):
        created = await _submit(async_test_client, context=json.dumps(_context()))
        listed = await async_test_client.get(BASE)
        one = await async_test_client.get(f"{BASE}/{uuid.uuid4()}")
    with _session(None):
        anonymous = await _submit(async_test_client)
    for response in (created, listed, one, anonymous):
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == {"code": "feature_disabled", "flag": "bug_reports"}
    count = (await async_test_db.execute(select(BugReport))).scalars().all()
    assert count == [] and storage == {} and queued == []


# --------------------------------------------------------------------------- #
# storing
# --------------------------------------------------------------------------- #


@pytest.mark.flags_on("bug_reports")
async def test_signed_in_report_is_stored_with_screenshot_and_queued(
    async_test_client, async_test_db, storage, queued
):
    user = await _user(async_test_db)
    await async_test_db.commit()
    with _session(user):
        r = await _submit(
            async_test_client,
            expected="The project is saved.",
            contact_email="ignored@example.com",
            context=json.dumps(_context()),
            files={"screenshot": ("shot.png", PNG, "image/png")},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert queued == [body["id"]]

    row = await async_test_db.get(BugReport, body["id"])
    assert row.reporter_id == user.id
    assert row.contact_email is None  # only kept without a session
    assert row.expected == "The project is saved."
    assert row.screenshot_content_type == "image/png" and row.screenshot_size == len(PNG)
    assert storage[row.screenshot_key] == PNG
    assert row.screenshot_key.startswith("bug_reports/")

    ctx = row.context
    assert ctx["page"] == "/projects/0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11/tasks"
    assert ctx["route_params"] == {"projectId": "0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11"}
    assert ctx["failed_requests"][0] == {
        "method": "GET",
        "path": "/api/projects/1",
        "status": 500,
        "request_id": "r-1",
    }
    assert ctx["failed_requests"][1]["path"] == "/api/auth/reset-password/[redacted]"
    assert ctx["navigation"][1]["path"] == "/reset-password/[redacted]"
    assert "cookies" not in ctx and "body" not in ctx
    assert ctx["server"]["core_version"]
    assert ctx["server"]["reporter_is_superadmin"] is False


@pytest.mark.flags_on("bug_reports")
async def test_anonymous_report_keeps_the_contact_address(
    async_test_client, async_test_db, storage, queued
):
    with _session(None):
        r = await _submit(async_test_client, contact_email=" someone@example.com ")
    assert r.status_code == 201, r.text
    row = await async_test_db.get(BugReport, r.json()["id"])
    assert row.reporter_id is None
    assert row.contact_email == "someone@example.com"
    assert row.screenshot_key is None
    assert queued == [row.id]


@pytest.mark.flags_on("bug_reports")
@pytest.mark.parametrize(
    "fields, files, status, code",
    [
        ({"title": "   "}, None, 422, "title_required"),
        ({"description": ""}, None, 422, "description_required"),
        ({"title": "x" * (reports.MAX_TITLE_CHARS + 1)}, None, 422, "too_long"),
        ({"description": "x" * (reports.MAX_DESCRIPTION_CHARS + 1)}, None, 422, "too_long"),
        ({"expected": "x" * (reports.MAX_EXPECTED_CHARS + 1)}, None, 422, "too_long"),
        ({"contact_email": "not-an-address"}, None, 422, "invalid_email"),
        ({"context": "{not json"}, None, 422, "invalid_context"),
        ({"context": json.dumps({"page": "x" * reports.MAX_CONTEXT_BYTES})}, None, 413, "context_too_large"),
        ({}, {"screenshot": ("a.png", b"<svg onload=alert(1)>", "image/png")}, 415, "screenshot_type"),
        (
            {},
            {"screenshot": ("a.png", PNG + b"\x00" * reports.MAX_SCREENSHOT_BYTES, "image/png")},
            413,
            "screenshot_too_large",
        ),
    ],
)
async def test_checks_refuse_bad_reports(
    async_test_client, async_test_db, storage, queued, fields, files, status, code
):
    with _session(None):
        r = await _submit(async_test_client, files=files, **fields)
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code
    assert (await async_test_db.execute(select(BugReport))).scalars().all() == []
    assert storage == {} and queued == []


@pytest.mark.flags_on("bug_reports")
async def test_a_storage_error_keeps_the_report_without_screenshot(
    async_test_client, async_test_db, queued, monkeypatch
):
    from storage.object_storage import object_storage

    def broken(*args, **kwargs):
        raise RuntimeError("storage down")

    monkeypatch.setattr(object_storage, "upload_file", broken)
    with _session(None):
        r = await _submit(async_test_client, files={"screenshot": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    row = await async_test_db.get(BugReport, r.json()["id"])
    assert row.screenshot_key is None
    assert row.context["server"]["screenshot_not_stored"] is True


@pytest.mark.flags_on("bug_reports")
async def test_a_broker_error_still_stores_the_report(
    async_test_client, async_test_db, storage, monkeypatch
):
    import celery_client

    def down(*args, **kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery_client, "send_task_safe", down)
    with _session(None):
        r = await _submit(async_test_client)
    assert r.status_code == 201
    row = await async_test_db.get(BugReport, r.json()["id"])
    assert row.status == "pending"


# --------------------------------------------------------------------------- #
# rate limits
# --------------------------------------------------------------------------- #


@pytest.mark.flags_on("bug_reports")
async def test_rate_limit_per_user(async_test_client, async_test_db, storage, queued, limiter):
    user, other = await _user(async_test_db), await _user(async_test_db)
    await async_test_db.commit()
    with _session(user):
        for _ in range(reports.USER_REPORTS_PER_HOUR):
            assert (await _submit(async_test_client)).status_code == 201
        refused = await _submit(async_test_client)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0
    with _session(other):
        assert (await _submit(async_test_client)).status_code == 201
    rows = (await async_test_db.execute(select(BugReport))).scalars().all()
    assert len(rows) == reports.USER_REPORTS_PER_HOUR + 1


@pytest.mark.flags_on("bug_reports")
async def test_rate_limit_without_session_is_stricter(
    async_test_client, async_test_db, storage, queued, limiter
):
    with _session(None):
        for _ in range(reports.ANONYMOUS_REPORTS_PER_HOUR):
            assert (await _submit(async_test_client)).status_code == 201
        refused = await _submit(async_test_client)
    assert refused.status_code == 429
    assert reports.ANONYMOUS_REPORTS_PER_HOUR < reports.USER_REPORTS_PER_HOUR


# --------------------------------------------------------------------------- #
# superadmin views
# --------------------------------------------------------------------------- #


@pytest.mark.flags_on("bug_reports")
async def test_superadmin_lists_reads_and_gets_the_screenshot(
    async_test_client, async_test_db, storage, queued
):
    admin, user = await _user(async_test_db, superadmin=True), await _user(async_test_db)
    await async_test_db.commit()
    with _session(user):
        first = (await _submit(async_test_client, title="First")).json()
        second = (
            await _submit(
                async_test_client,
                title="Second",
                files={"screenshot": ("a.png", PNG, "image/png")},
            )
        ).json()
        denied = await async_test_client.get(BASE)
        denied_shot = await async_test_client.get(f"{BASE}/{second['id']}/screenshot")
    assert denied.status_code == 403 and denied_shot.status_code == 403

    with _session(admin):
        listed = (await async_test_client.get(BASE)).json()
        pending = (await async_test_client.get(BASE, params={"status": "pending"})).json()
        delivered = (await async_test_client.get(BASE, params={"status": "delivered"})).json()
        bad = await async_test_client.get(BASE, params={"status": "lost"})
        detail = (await async_test_client.get(f"{BASE}/{second['id']}")).json()
        shot = await async_test_client.get(f"{BASE}/{second['id']}/screenshot")
        no_shot = await async_test_client.get(f"{BASE}/{first['id']}/screenshot")
        missing = await async_test_client.get(f"{BASE}/{uuid.uuid4()}")

    assert listed["total"] == 2
    assert {item["id"] for item in listed["items"]} == {first["id"], second["id"]}
    assert "description" not in listed["items"][0] and "context" not in listed["items"][0]
    assert pending["total"] == 2 and delivered["total"] == 0
    assert bad.status_code == 422
    assert detail["reporter_id"] == user.id and detail["has_screenshot"] is True
    assert detail["description"] and detail["context"]["server"]
    assert shot.status_code == 200 and shot.content == PNG
    assert shot.headers["content-type"] == "image/png"
    assert shot.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in shot.headers["cache-control"]
    assert no_shot.status_code == 404 and missing.status_code == 404


@pytest.mark.flags_on("bug_reports")
async def test_redeliver_queues_a_failed_report_again(
    async_test_client, async_test_db, storage, queued
):
    admin = await _user(async_test_db, superadmin=True)
    await async_test_db.commit()
    with _session(admin):
        created = (await _submit(async_test_client)).json()
    row = await async_test_db.get(BugReport, created["id"])
    row.status, row.delivery_error = "failed", "GitHub answered 401: Bad credentials"
    await async_test_db.commit()
    with _session(admin):
        again = await async_test_client.post(f"{BASE}/{created['id']}/redeliver")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "pending" and again.json()["delivery_error"] is None
    assert queued == [created["id"], created["id"]]

    await async_test_db.refresh(row)
    row.status, row.issue_url = "delivered", "https://github.example/o/r/issues/1"
    await async_test_db.commit()
    with _session(admin):
        refused = await async_test_client.post(f"{BASE}/{created['id']}/redeliver")
    assert refused.status_code == 409
