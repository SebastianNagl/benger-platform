"""The ``before_annotation_write`` hook (core 2.46, audit finding S3).

An overlay (the extended exam timer) refuses a client annotation write by
raising ``extensions.AnnotationWriteRejected`` from this hook. The platform
calls it in ``create_annotation`` and ``update_annotation`` after their own
gates and before anything is written, and answers a refusal with the status
and detail the exception carries.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import extension_activation as activation
import extensions
from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Annotation, Project, ProjectOrganization, Task

KEY = "before_annotation_write"
REJECTION = {"code": "exam_timer_expired", "message": "time is up"}
RESULT = [
    {"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}
]


class _FakePackage:
    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _install(monkeypatch, *packages):
    """Make ``packages`` the loaded overlays, in hook order."""
    names = ["benger_extended", "benger_other", "benger_third"]
    monkeypatch.setattr(
        extensions, "_packages", lambda: list(zip(names, packages, strict=False))
    )


def _recorder(calls, tag="ext"):
    def hook(db, task_id, user_id, project_id, **kwargs):
        calls.append((tag, task_id, user_id, project_id, kwargs))

    return hook


def _rejecting(status_code=None):
    def hook(db, task_id, user_id, project_id, **kwargs):
        if status_code is None:
            raise extensions.AnnotationWriteRejected(REJECTION)
        raise extensions.AnnotationWriteRejected(REJECTION, status_code=status_code)

    return hook


@pytest.fixture(autouse=True)
def _mute_celery():
    """The handlers dispatch a report refresh to Celery; keep it offline."""
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
class TestContract:
    def test_spec_and_gating(self):
        assert extensions.HOOK_SPECS[KEY] == extensions.CALL_ALL
        assert extensions.HOOK_GATING[KEY] == activation.ALWAYS
        assert KEY not in extensions.PENDING_HOOK_KEYS
        extensions._validate_hook_gating()

    def test_rejection_defaults_to_409(self):
        exc = extensions.AnnotationWriteRejected("closed")
        assert exc.status_code == 409
        assert exc.detail == "closed"
        coded = extensions.AnnotationWriteRejected(REJECTION, status_code=403)
        assert coded.status_code == 403
        assert coded.detail == REJECTION


# --------------------------------------------------------------------------- #
# Wrapper
# --------------------------------------------------------------------------- #
class TestWrapper:
    def test_noop_without_package(self, monkeypatch):
        monkeypatch.setattr(extensions, "_packages", lambda: [])
        assert extensions.before_annotation_write(None, "t", "u", "p") is None

    def test_runs_every_implementation_in_order(self, monkeypatch):
        calls = []
        _install(
            monkeypatch,
            _FakePackage({KEY: _recorder(calls, "ext")}),
            _FakePackage({}),
            _FakePackage({KEY: _recorder(calls, "other")}),
        )
        extensions.before_annotation_write(
            "db", "t", "u", "p", annotation_id="a", is_update=True
        )
        kwargs = {"annotation_id": "a", "is_update": True}
        assert calls == [
            ("ext", "t", "u", "p", kwargs),
            ("other", "t", "u", "p", kwargs),
        ]

    def test_defaults_reach_the_hook(self, monkeypatch):
        calls = []
        _install(monkeypatch, _FakePackage({KEY: _recorder(calls)}))
        extensions.before_annotation_write("db", "t", "u", "p")
        assert calls == [
            ("ext", "t", "u", "p", {"annotation_id": None, "is_update": False})
        ]

    def test_rejection_propagates_and_stops_later_packages(self, monkeypatch):
        calls = []
        _install(
            monkeypatch,
            _FakePackage({KEY: _rejecting()}),
            _FakePackage({KEY: _recorder(calls)}),
        )
        with pytest.raises(extensions.AnnotationWriteRejected) as info:
            extensions.before_annotation_write("db", "t", "u", "p")
        assert info.value.detail == REJECTION
        assert calls == []

    def test_other_exceptions_propagate(self, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("timer lookup failed")

        _install(monkeypatch, _FakePackage({KEY: broken}))
        with pytest.raises(RuntimeError, match="timer lookup failed"):
            extensions.before_annotation_write("db", "t", "u", "p")


# --------------------------------------------------------------------------- #
# Router call sites
# --------------------------------------------------------------------------- #
def _uid():
    return str(uuid.uuid4())


def _seed_project_sync(db, user_id):
    project = Project(
        id=_uid(),
        title="Write Hook Project",
        created_by=user_id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=3,
        min_annotations_per_task=1,
        assignment_mode="open",
    )
    db.add(project)
    org = Organization(
        id=_uid(),
        name="Hook Org",
        slug=f"hook-org-{uuid.uuid4().hex[:8]}",
        display_name="Hook Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.commit()
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user_id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=user_id
        )
    )
    task = Task(id=_uid(), project_id=project.id, data={"text": "t"}, inner_id=1)
    db.add(task)
    db.commit()
    return project, task


class TestCreateCallsHook:
    def test_rejection_maps_status_and_writes_nothing(
        self, monkeypatch, client, auth_headers, test_db, test_users
    ):
        project, task = _seed_project_sync(test_db, test_users[0].id)
        _install(monkeypatch, _FakePackage({KEY: _rejecting()}))
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": RESULT},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == REJECTION
        test_db.expire_all()
        assert test_db.query(Annotation).filter(Annotation.task_id == task.id).count() == 0
        assert test_db.query(Task).filter(Task.id == task.id).one().total_annotations == 0

    def test_custom_status_is_kept(
        self, monkeypatch, client, auth_headers, test_db, test_users
    ):
        project, task = _seed_project_sync(test_db, test_users[0].id)
        _install(monkeypatch, _FakePackage({KEY: _rejecting(status_code=423)}))
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": RESULT},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 423
        assert resp.json()["detail"] == REJECTION

    def test_accepting_hook_sees_create_arguments(
        self, monkeypatch, client, auth_headers, test_db, test_users
    ):
        project, task = _seed_project_sync(test_db, test_users[0].id)
        calls = []
        _install(monkeypatch, _FakePackage({KEY: _recorder(calls)}))
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": RESULT},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert calls == [
            (
                "ext",
                task.id,
                test_users[0].id,
                project.id,
                {"annotation_id": None, "is_update": False},
            )
        ]

    def test_hook_runs_after_the_platform_gates(
        self, monkeypatch, client, auth_headers
    ):
        calls = []
        _install(monkeypatch, _FakePackage({KEY: _recorder(calls)}))
        resp = client.post(
            "/api/projects/tasks/no-such-task/annotations",
            json={"result": RESULT},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert calls == []

    def test_no_implementation_writes_normally(
        self, monkeypatch, client, auth_headers, test_db, test_users
    ):
        project, task = _seed_project_sync(test_db, test_users[0].id)
        monkeypatch.setattr(extensions, "_packages", lambda: [])
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": RESULT},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


@contextmanager
def _as_user(db_user):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_annotation_async(db):
    user = User(
        id=_uid(),
        username=f"h-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Hook User",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    project = Project(
        id=_uid(),
        title="Write Hook Project",
        created_by=user.id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=3,
        min_annotations_per_task=1,
        assignment_mode="open",
    )
    db.add(project)
    task = Task(id=_uid(), project_id=project.id, data={"text": "t"}, inner_id=1)
    db.add(task)
    await db.flush()
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=[{"from_name": "text", "type": "textarea", "value": {"text": ["old"]}}],
    )
    db.add(annotation)
    await db.commit()
    return user, project, task, annotation


@pytest.mark.asyncio
class TestUpdateCallsHook:
    async def test_rejection_maps_status_and_leaves_row_unchanged(
        self, monkeypatch, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed_annotation_async(async_test_db)
        _install(monkeypatch, _FakePackage({KEY: _rejecting()}))
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{annotation.id}",
                json={"result": RESULT, "was_cancelled": True},
            )
        assert resp.status_code == 409
        assert resp.json()["detail"] == REJECTION
        # Read the id before expiring: an expired attribute would lazy-load
        # outside the async context and raise MissingGreenlet.
        annotation_id = annotation.id
        async_test_db.expire_all()
        row = (
            await async_test_db.execute(
                select(Annotation).where(Annotation.id == annotation_id)
            )
        ).scalar_one()
        assert row.result[0]["value"]["text"] == ["old"]
        assert row.was_cancelled is False

    async def test_accepting_hook_sees_update_arguments(
        self, monkeypatch, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed_annotation_async(async_test_db)
        calls = []
        _install(monkeypatch, _FakePackage({KEY: _recorder(calls)}))
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{annotation.id}",
                json={"result": RESULT},
            )
        assert resp.status_code == 200
        assert calls == [
            (
                "ext",
                task.id,
                user.id,
                project.id,
                {"annotation_id": annotation.id, "is_update": True},
            )
        ]

    async def test_hook_runs_after_the_platform_gates(
        self, monkeypatch, async_test_client, async_test_db
    ):
        user, project, task, annotation = await _seed_annotation_async(async_test_db)
        calls = []
        _install(monkeypatch, _FakePackage({KEY: _recorder(calls)}))
        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{_uid()}",
                json={"result": RESULT},
            )
        assert resp.status_code == 404
        assert calls == []
