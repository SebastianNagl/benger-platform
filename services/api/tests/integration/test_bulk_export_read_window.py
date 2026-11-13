"""The bulk exports honour the timed read window like the single export.

``POST /api/projects/{id}/exports`` refuses a non-editor (for example a
public CONTRIBUTOR visitor) while the project's window has not opened yet
(``enforce_project_read_window``). The three bulk exports dump the same task
data, so they must apply the same gate: ``/bulk-export`` and
``/bulk-export-full`` leave such a project out (they skip every project the
caller may not export), ``/{id}/tasks/bulk-export`` answers 403. Editors and
open or closed windows are unaffected.
"""

import io
import json
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project, Task

SECRET = "GEHEIME MUSTERLOESUNG"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _user(test_db) -> User:
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Person",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(u)
    test_db.flush()
    return u


def _seed(test_db, *, window):
    """A public CONTRIBUTOR project with one task. ``window`` is "upcoming",
    "open" or None. Returns (owner, visitor, project)."""
    owner, visitor = _user(test_db), _user(test_db)
    now = datetime.now(timezone.utc)
    bounds = {
        "upcoming": (now + timedelta(hours=1), now + timedelta(hours=3)),
        "open": (now - timedelta(hours=1), now + timedelta(hours=1)),
        None: (None, None),
    }[window]
    p = Project(
        id=_uid(),
        title=f"P {_uid()[:6]}",
        created_by=owner.id,
        is_private=False,
        is_public=True,
        public_role="CONTRIBUTOR",
        label_config='<View><Text name="t" value="$t"/></View>',
        window_start_at=bounds[0],
        window_end_at=bounds[1],
    )
    test_db.add(p)
    test_db.flush()
    test_db.add(
        Task(
            id=f"task-{p.id}",
            project_id=p.id,
            inner_id=1,
            data={"t": "Fall", "musterloesung": SECRET},
            created_by=owner.id,
        )
    )
    test_db.commit()
    return owner, visitor, p


def _bulk_export_ids(client, project_id):
    r = client.post(
        "/api/projects/bulk-export",
        json={"project_ids": [project_id], "format": "json"},
    )
    assert r.status_code == 200, r.text
    return [p["id"] for p in json.loads(r.content)["projects"]], r.text


@pytest.mark.integration
class TestBulkExportWindow:
    def test_visitor_skipped_before_window_opens(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window="upcoming")
        with _as_user(visitor):
            ids, text = _bulk_export_ids(client, p.id)
        assert ids == []
        assert SECRET not in text

    def test_visitor_exports_once_window_is_open(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window="open")
        with _as_user(visitor):
            ids, text = _bulk_export_ids(client, p.id)
        assert ids == [p.id]
        assert SECRET in text

    def test_creator_exports_before_window_opens(self, client, test_db):
        owner, _visitor, p = _seed(test_db, window="upcoming")
        with _as_user(owner):
            ids, _ = _bulk_export_ids(client, p.id)
        assert ids == [p.id]


@pytest.mark.integration
class TestBulkExportFullWindow:
    URL = "/api/projects/bulk-export-full"

    def test_visitor_gets_nothing_before_window_opens(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window="upcoming")
        with _as_user(visitor):
            r = client.post(self.URL, json={"project_ids": [p.id]})
        assert r.status_code == 404, r.text
        assert SECRET not in r.text

    def test_visitor_exports_without_window(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window=None)
        with _as_user(visitor):
            r = client.post(self.URL, json={"project_ids": [p.id]})
        assert r.status_code == 200, r.text
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert len(z.namelist()) == 1

    def test_creator_exports_before_window_opens(self, client, test_db):
        owner, _visitor, p = _seed(test_db, window="upcoming")
        with _as_user(owner):
            r = client.post(self.URL, json={"project_ids": [p.id]})
        assert r.status_code == 200, r.text


@pytest.mark.integration
class TestTaskBulkExportWindow:
    URL = "/api/projects/{}/tasks/bulk-export"

    def test_visitor_403_before_window_opens(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window="upcoming")
        with _as_user(visitor):
            r = client.post(
                self.URL.format(p.id), json={"format": "json", "task_ids": [f"task-{p.id}"]}
            )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "project_window_upcoming"
        assert SECRET not in r.text

    def test_visitor_exports_once_window_is_open(self, client, test_db):
        _owner, visitor, p = _seed(test_db, window="open")
        with _as_user(visitor):
            r = client.post(
                self.URL.format(p.id), json={"format": "json", "task_ids": [f"task-{p.id}"]}
            )
        assert r.status_code == 200, r.text
        assert SECRET in r.text

    def test_creator_exports_before_window_opens(self, client, test_db):
        owner, _visitor, p = _seed(test_db, window="upcoming")
        with _as_user(owner):
            r = client.post(
                self.URL.format(p.id), json={"format": "json", "task_ids": [f"task-{p.id}"]}
            )
        assert r.status_code == 200, r.text
