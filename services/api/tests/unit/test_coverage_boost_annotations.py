"""
Coverage boost tests for annotation endpoints.

Targets specific branches in routers/projects/annotations.py:
- create_annotation with various conditions (still on the SYNC DB lane —
  it calls the sync-only on_annotation_created hook + mark_assignment_completed,
  so it stays on ``get_db``/``test_db`` and the sync ``client``).
- list_task_annotations / update_annotation were migrated to the ASYNC DB lane
  (``Depends(get_async_db)``); those tests seed real rows via ``async_test_db``
  and drive the surface through ``async_test_client`` with ``require_user``
  overridden per-test.
- Maximum annotations limit.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


@pytest.fixture(autouse=True)
def _mute_celery():
    """Stub the report-refresh Celery dispatch in create/update_annotation.

    The handlers call ``get_celery_app().send_task(...)`` for the async report
    update. With no Redis broker (as in the isolated venv) Celery retries the
    connection for ~20s, which on the async lane outlives the 15s
    statement_timeout and cancels the in-flight transaction. Stubbing the
    dispatch keeps the request fast and deterministic; the handler already
    swallows dispatch failures in prod, so behaviour under test is unchanged.
    """
    with patch("celery_client.get_celery_app", return_value=MagicMock()):
        yield


def _setup_project_with_task(db, user_id, **project_kwargs):
    """Create a project with one task (sync — for the create_annotation suite)."""
    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Test Annotation Project",
        created_by=user_id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=3,
        min_annotations_per_task=1,
        assignment_mode="open",
        **project_kwargs,
    )
    db.add(p)
    db.commit()

    # Create org and assignment so the project is accessible
    org = Organization(
        id=str(uuid.uuid4()),
        name="Ann Org",
        slug=f"ann-org-{uuid.uuid4().hex[:8]}",
        display_name="Ann Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    db.add(OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org.id,
        role="ORG_ADMIN",
        joined_at=datetime.utcnow(),
    ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=user_id,
    ))
    db.commit()

    tid = str(uuid.uuid4())
    t = Task(
        id=tid, project_id=pid, data={"text": "test data"}, inner_id=1
    )
    db.add(t)
    db.commit()

    return p, t, org


# ---- async helpers for the migrated list/update handlers -------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
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


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"a-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Ann User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _setup_project_with_task_async(db, user_id, **project_kwargs):
    """Async twin of _setup_project_with_task (open-mode → accessible)."""
    p = Project(
        id=_uid(),
        title="Test Annotation Project",
        created_by=user_id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=3,
        min_annotations_per_task=1,
        assignment_mode="open",
        **project_kwargs,
    )
    db.add(p)
    org = Organization(
        id=_uid(),
        name="Ann Org",
        slug=f"ann-org-{uuid.uuid4().hex[:8]}",
        display_name="Ann Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    await db.flush()
    db.add(OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org.id,
        role="ORG_ADMIN",
        joined_at=datetime.utcnow(),
    ))
    db.add(ProjectOrganization(
        id=_uid(),
        project_id=p.id,
        organization_id=org.id,
        assigned_by=user_id,
    ))
    t = Task(id=_uid(), project_id=p.id, data={"text": "test data"}, inner_id=1)
    db.add(t)
    await db.flush()
    return p, t, org


class TestCreateAnnotation:
    """Test create_annotation endpoint (sync DB lane)."""

    def test_create_annotation_basic(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["hello"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == t.id
        assert data["was_cancelled"] == False  # noqa: E712

    def test_create_cancelled_annotation(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] == True  # noqa: E712

    def test_create_annotation_task_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/projects/tasks/nonexistent/annotations",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_create_annotation_with_timing_data(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["y"]}}],
                "lead_time": 45.5,
                "active_duration_ms": 40000,
                "focused_duration_ms": 35000,
                "tab_switches": 2,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_duration_ms"] == 40000
        assert data["tab_switches"] == 2

    def test_create_annotation_with_instruction_variant(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(
            test_db,
            test_users[0].id,
            conditional_instructions=[
                {"id": "variant-1", "content": "Normal instructions", "weight": 50, "ai_allowed": False},
                {"id": "variant-2", "content": "AI instructions", "weight": 50, "ai_allowed": True},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["z"]}}],
                "instruction_variant": "variant-2",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_assisted"] == True  # noqa: E712

    def test_create_annotation_non_ai_variant(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(
            test_db,
            test_users[0].id,
            conditional_instructions=[
                {"id": "variant-1", "content": "Normal", "weight": 100, "ai_allowed": False},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["w"]}}],
                "instruction_variant": "variant-1",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["ai_assisted"] == False  # noqa: E712

    def test_create_annotation_empty_result(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestListAnnotations:
    """Test list_task_annotations endpoint (async DB lane)."""

    async def test_list_annotations_own_only(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, user.id)
        async_test_db.add(Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=user.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["own"]}}],
        ))
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{t.id}/annotations",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_list_annotations_all_users(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, owner.id)
        async_test_db.add(OrganizationMembership(
            id=_uid(),
            user_id=other.id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
        for uid in [owner.id, other.id]:
            async_test_db.add(Annotation(
                id=_uid(),
                task_id=t.id,
                project_id=p.id,
                completed_by=uid,
                result=[{"from_name": "text", "type": "textarea", "value": {"text": [f"by-{uid}"]}}],
            ))
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{t.id}/annotations?all_users=true",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_list_annotations_task_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/projects/tasks/nonexistent/annotations")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUpdateAnnotation:
    """Test update_annotation endpoint (async DB lane)."""

    async def test_update_annotation_result(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, user.id)
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=user.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["old"]}}],
        )
        async_test_db.add(ann)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={"result": [{"from_name": "text", "type": "textarea", "value": {"text": ["new"]}}]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    async def test_update_annotation_cancel(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, user.id)
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=user.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
            was_cancelled=False,
        )
        async_test_db.add(ann)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
                    "was_cancelled": True,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] == True  # noqa: E712

    async def test_update_annotation_uncancel(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, user.id)
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=user.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["uncancel"]}}],
            was_cancelled=True,
        )
        async_test_db.add(ann)
        t.cancelled_annotations = 1
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["uncancel"]}}],
                    "was_cancelled": False,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] == False  # noqa: E712

    async def test_update_annotation_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.patch(
                "/api/projects/annotations/nonexistent",
                json={"result": []},
            )
        assert resp.status_code == 404

    async def test_update_annotation_not_owner(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        p, t, org = await _setup_project_with_task_async(async_test_db, owner.id)
        async_test_db.add(OrganizationMembership(
            id=_uid(),
            user_id=contributor.id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=owner.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["owned"]}}],
        )
        async_test_db.add(ann)
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={"result": [{"from_name": "text", "type": "textarea", "value": {"text": ["stolen"]}}]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403

    async def test_update_annotation_lead_time(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        p, t, org = await _setup_project_with_task_async(async_test_db, user.id)
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=user.id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["time"]}}],
            lead_time=10.0,
        )
        async_test_db.add(ann)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["time"]}}],
                    "lead_time": 25.5,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
