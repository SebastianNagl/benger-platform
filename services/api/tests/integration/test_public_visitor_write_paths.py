"""Integration tests: a non-creator, non-superadmin user (the "public visitor")
acting on a public project — exercising the WRITE paths the public_role
contract is supposed to govern.

Confirms the end-to-end behaviour for:
  - POST /tasks/{task_id}/annotations  (write annotations)
  - PATCH /projects/{project_id}        (project settings — must always 403)
  - PATCH /projects/{project_id}/visibility  (must always 403 for visitor)

Note on PROJECT_EDIT cap:
  The authorization-service Permission matrix caps PROJECT_EDIT/DELETE/CREATE
  for public_role visitors at the matrix level. The actual `update_project`
  router enforces this via `check_user_can_edit_project`, which rejects
  visitors regardless of public_role (creator + superadmin only). Both these
  layers are exercised by the assertions below.

Note on TASK_CREATE / GENERATION_CREATE:
  These endpoints (`POST /projects/{id}/imports/upload-url` — the async import
  entry point that replaced the removed sync `POST /{id}/import` in #158 — and
  `POST /projects/{id}/generate`) call `check_project_write_access`, which
  enforces the documented public_role contract: public-tier ANNOTATOR
  visitors are blocked; CONTRIBUTOR visitors are allowed.

The projects/tasks/search routers these tests hit were migrated to the async DB
lane, so rows are seeded via ``async_test_db`` and the HTTP surface is driven
through ``async_test_client``. ``require_user`` is overridden per-test with the
seeded actor (the sync Bearer-token auth + sync ``test_db`` rows are invisible
to the async handler's separate connection / event loop).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Annotation, Project, Task

pytestmark = pytest.mark.asyncio


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


async def _make_creator(db):
    user = User(
        id=f"vw-creator-{uuid.uuid4()}",
        username=f"vwc-{uuid.uuid4().hex[:8]}",
        email=f"vwc-{uuid.uuid4().hex[:8]}@test.com",
        name="Public-project creator",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_visitor(db):
    """Authenticated user with no relationship to the project."""
    user = User(
        id=f"vw-visitor-{uuid.uuid4()}",
        username=f"vwv-{uuid.uuid4().hex[:8]}",
        email=f"vwv-{uuid.uuid4().hex[:8]}@test.com",
        name="Public-project visitor",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _public_project(db, creator, public_role):
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Public {public_role} Bench",
        created_by=creator.id,
        is_private=False,
        is_public=True,
        public_role=public_role,
    )
    db.add(project)
    await db.flush()
    return project


_inner_id_counter = 0


async def _task(db, project):
    global _inner_id_counter
    _inner_id_counter += 1
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "hello"},
        inner_id=_inner_id_counter,
    )
    db.add(task)
    await db.flush()
    return task


# ── Sync seed helpers ────────────────────────────────────────────────────────
# `create_annotation` is sync-lane (Depends(get_db)), so the "visitor CAN
# annotate" contract is exercised through the SYNC `client`/`test_db` fixtures
# (which the sync handler sees) rather than the async fixtures. These mirror the
# async helpers above on the sync session.
def _sync_make_user(db, prefix):
    user = User(
        id=f"vw-{prefix}-{uuid.uuid4()}",
        username=f"vw{prefix[:3]}-{uuid.uuid4().hex[:8]}",
        email=f"vw{prefix[:3]}-{uuid.uuid4().hex[:8]}@test.com",
        name=f"Public-project {prefix}",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _sync_public_project(db, creator, public_role):
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Public {public_role} Bench",
        created_by=creator.id,
        is_private=False,
        is_public=True,
        public_role=public_role,
    )
    db.add(project)
    db.flush()
    return project


def _sync_task(db, project):
    global _inner_id_counter
    _inner_id_counter += 1
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "hello"},
        inner_id=_inner_id_counter,
    )
    db.add(task)
    db.flush()
    return task


_ANNOTATION_BODY = {
    "result": [
        {
            "from_name": "answer",
            "type": "textarea",
            "to_name": "text",
            "value": {"text": ["Visitor answer"]},
        }
    ]
}


class TestPublicAnnotatorVisitorWritePaths:
    """ANNOTATOR public_role: read + annotate only."""

    async def test_visitor_can_read_project(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "ANNOTATOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_public"] == True  # noqa: E712
        assert body["public_role"] == "ANNOTATOR"

    def test_visitor_can_create_annotation(self, client, test_db):
        """An ANNOTATOR public visitor is permitted to annotate — driven through
        the REAL ``POST /tasks/{id}/annotations`` endpoint (sync-lane), which the
        sync ``client``/``test_db`` fixtures see. Open assignment_mode means no
        task assignment is required, so the visitor's write is accepted (200/201)
        and the row is persisted by the endpoint with ``completed_by`` = visitor.
        """
        creator = _sync_make_user(test_db, "creator")
        visitor = _sync_make_user(test_db, "visitor")
        project = _sync_public_project(test_db, creator, "ANNOTATOR")
        task = _sync_task(test_db, project)
        test_db.flush()

        with _as_user(visitor):
            resp = client.post(
                f"/api/projects/tasks/{task.id}/annotations",
                json=_ANNOTATION_BODY,
            )
        assert resp.status_code in (200, 201), resp.text

        # The endpoint persisted the visitor's annotation.
        ann = (
            test_db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.completed_by == visitor.id,
            )
            .first()
        )
        assert ann is not None

    async def test_visitor_cannot_edit_project_settings(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "ANNOTATOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"title": "hijacked"},
            )
        assert resp.status_code == 403, resp.text

    async def test_visitor_cannot_change_visibility(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "ANNOTATOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == 403, resp.text

    async def test_visitor_cannot_import_tasks(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "ANNOTATOR")
        await async_test_db.commit()

        # The sync POST /{id}/import was removed (#158); async import now begins
        # by requesting a presigned upload URL, gated by the same write-access
        # check. An ANNOTATOR visitor must be rejected before any storage call.
        with _as_user(visitor):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports/upload-url",
            )
        assert resp.status_code == 403, resp.text

    async def test_visitor_cannot_start_generation(self, async_test_client, async_test_db):
        """``routers/generation_task_list.py`` was migrated to the async DB lane,
        so this seeds via ``async_test_db`` and overrides ``require_user`` with the
        visitor (the sync Bearer-token auth + sync ``test_db`` rows are invisible
        to the async handler's separate connection)."""
        creator_user = await _make_creator(async_test_db)
        visitor_user = await _make_visitor(async_test_db)

        project = await _public_project(async_test_db, creator_user, "ANNOTATOR")
        project_id = project.id
        await async_test_db.commit()

        with _as_user(visitor_user):
            resp = await async_test_client.post(
                f"/api/generation-tasks/projects/{project_id}/generate",
                json={"mode": "missing"},
            )
        assert resp.status_code == 403, resp.text


class TestPublicContributorVisitorWritePaths:
    """CONTRIBUTOR public_role: extra write powers (annotate + future writes),
    but settings + visibility editing remain creator/superadmin-only."""

    async def test_visitor_can_read_project(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "CONTRIBUTOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["public_role"] == "CONTRIBUTOR"

    def test_visitor_can_create_annotation(self, client, test_db):
        """A CONTRIBUTOR public visitor is permitted to annotate — driven through
        the REAL sync-lane ``POST /tasks/{id}/annotations`` endpoint. See the
        ANNOTATOR twin for the rationale.
        """
        creator = _sync_make_user(test_db, "creator")
        visitor = _sync_make_user(test_db, "visitor")
        project = _sync_public_project(test_db, creator, "CONTRIBUTOR")
        task = _sync_task(test_db, project)
        test_db.flush()

        with _as_user(visitor):
            resp = client.post(
                f"/api/projects/tasks/{task.id}/annotations",
                json=_ANNOTATION_BODY,
            )
        assert resp.status_code in (200, 201), resp.text

        ann = (
            test_db.query(Annotation)
            .filter(
                Annotation.task_id == task.id,
                Annotation.completed_by == visitor.id,
            )
            .first()
        )
        assert ann is not None

    async def test_visitor_cannot_edit_project_settings(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "CONTRIBUTOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"title": "hijacked"},
            )
        # Public CONTRIBUTOR is the most permissive public role; settings edit
        # still belongs to the creator + superadmins (the documented cap).
        assert resp.status_code == 403, resp.text

    async def test_visitor_cannot_change_visibility(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "CONTRIBUTOR")
        await async_test_db.commit()

        with _as_user(visitor):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"public_role": "ANNOTATOR"},
            )
        assert resp.status_code == 403, resp.text

    async def test_visitor_can_import_tasks(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        project = await _public_project(async_test_db, creator, "CONTRIBUTOR")
        await async_test_db.commit()

        # The sync POST /{id}/import was removed (#158); async import now begins
        # by requesting a presigned upload URL, gated by write access. A public
        # CONTRIBUTOR must clear that gate (anything except 403).
        with _as_user(visitor):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports/upload-url",
            )
        assert resp.status_code != 403, resp.text


class TestPublicProjectVisibleAcrossOrgs:
    """A user who is a member of an unrelated org still sees the public project."""

    async def test_other_org_member_sees_public_project(self, async_test_client, async_test_db):
        creator = await _make_creator(async_test_db)
        visitor = await _make_visitor(async_test_db)
        other_org = Organization(
            id=str(uuid.uuid4()),
            name=f"OtherOrg-{uuid.uuid4().hex[:6]}",
            slug=f"otherorg-{uuid.uuid4().hex[:6]}",
            display_name="Other Org",
        )
        async_test_db.add(other_org)
        async_test_db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=visitor.id,
                organization_id=other_org.id,
                role="ANNOTATOR",
                is_active=True,
            )
        )
        project = await _public_project(async_test_db, creator, "CONTRIBUTOR")
        await async_test_db.commit()

        # Hit list with the visitor's org context — public project must appear.
        with _as_user(visitor):
            resp = await async_test_client.get(
                "/api/projects/?page=1&page_size=100",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 200, resp.text
        items = resp.json().get("items", [])
        ids = [it["id"] for it in items]
        assert project.id in ids
