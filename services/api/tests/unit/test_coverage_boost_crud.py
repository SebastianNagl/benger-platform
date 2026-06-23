"""
Coverage boost tests for project CRUD endpoints.

Targets specific branches in routers/projects/crud.py:
- list_projects with search, is_archived filters
- create_project with private vs org, label_config validation
- update_project with deep merge, label_config versioning
- delete_project with permission checks
- update_project_visibility
- recalculate_project_statistics
- get_project_completion_stats

The CRUD handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). The old
pattern (sync ``client`` + ``auth_headers`` JWT + rows seeded into the sync
``test_db``) no longer reaches the handlers — rows seeded on the sync engine
are invisible to the async engine. These tests now seed real ORM rows via
``async_test_db`` and drive the surface through ``async_test_client``, with
``require_user`` (or ``get_current_user`` for the admin-only recalc endpoint)
overridden per-test via ``_as_user`` to an auth user matching the seeded owner.
Create/delete tests patch the sync notification/report wrappers to avoid the
Redis-backed threadpool stall.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


# ============= helpers =============


def _uid() -> str:
    return str(uuid.uuid4())


def _auth_user(db_user: User) -> AuthUser:
    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


@contextmanager
def _as_user(db_user: User):
    """Override require_user with an AuthUser matching the seeded DB user."""
    auth_user = _auth_user(db_user)
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


@contextmanager
def _as_current_user(db_user: User):
    """Override get_current_user (the recalc endpoint's dep) with the DB user."""
    app.dependency_overrides[get_current_user] = lambda: db_user
    try:
        yield db_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# Patch the sync report/notification wrappers so create/delete never stall on
# the Redis-backed threadpool dispatch (no Redis locally).
def _no_side_effects():
    return (
        patch("routers.projects.crud._notify_project_created_sync"),
        patch("routers.projects.crud._notify_project_deleted_sync"),
        patch("routers.projects.crud._create_initial_report_draft_sync"),
    )


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"cb-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(
    db,
    user_id,
    *,
    title="Test",
    is_private=False,
    label_config="<View><Text name='text' value='$text'/></View>",
    **kwargs,
):
    p = Project(
        id=_uid(),
        title=title,
        created_by=user_id,
        is_private=is_private,
        label_config=label_config,
        created_at=datetime.now(timezone.utc),
        **kwargs,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project_id, *, is_labeled=False):
    t = Task(
        id=_uid(),
        project_id=project_id,
        data={"text": "hello"},
        inner_id=1,
        is_labeled=is_labeled,
    )
    db.add(t)
    await db.flush()
    return t


async def _make_org(db):
    org = Organization(
        id=_uid(),
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        display_name="Test Org Display",
        description="test",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_membership(db, user_id, org_id, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _assign_project_to_org(db, project_id, org_id, user_id):
    po = ProjectOrganization(
        id=_uid(),
        project_id=project_id,
        organization_id=org_id,
        assigned_by=user_id,
    )
    db.add(po)
    await db.flush()
    return po


class TestListProjects:
    """Test list_projects with various filters."""

    @pytest.mark.asyncio
    async def test_list_projects_no_projects(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_list_projects_with_search(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, admin.id, title="Unique Alpha Search")
        await _make_project(async_test_db, admin.id, title="Unique Beta Search")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/?search=Alpha")
        assert resp.status_code == 200
        data = resp.json()
        titles = [p["title"] for p in data["items"]]
        assert any("Alpha" in t for t in titles)

    @pytest.mark.asyncio
    async def test_list_projects_with_is_archived_false(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, admin.id, title="Archived Test")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/?is_archived=false")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_projects_with_pagination(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        for i in range(5):
            await _make_project(async_test_db, admin.id, title=f"Page Test {i}")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_projects_with_org_context(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin.id, title="Org Project")
        await _assign_project_to_org(async_test_db, p.id, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", headers={"X-Organization-Context": org.id}
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_projects_private_context(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(
            async_test_db, admin.id, title="Private P", is_private=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", headers={"X-Organization-Context": "private"}
            )
        assert resp.status_code == 200


class TestCreateProject:
    """Test create_project with different input variations."""

    @pytest.mark.asyncio
    async def test_create_private_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Private Project",
                    "description": "A private test project",
                    "is_private": True,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Private Project"
        assert data["is_private"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_create_project_no_org_header_makes_private(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/", json={"title": "No Header Project"}
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project_with_org_context(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id, "ORG_ADMIN")
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Org Project Create"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project_with_label_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "With Label Config",
                    "label_config": "<View><Text name='text' value='$text'/></View>",
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project_invalid_label_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Bad Config",
                    "label_config": "not valid xml at all <<<",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_with_instructions(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "With Instructions",
                    "expert_instruction": "Annotate carefully",
                    "show_instruction": True,
                    "show_skip_button": False,
                    "enable_empty_annotation": False,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["show_skip_button"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_create_project_annotator_forbidden_in_org(
        self, async_test_client, async_test_db
    ):
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(annotator), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Annotator Try"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403


class TestGetProject:
    """Test get_project with various access scenarios."""

    @pytest.mark.asyncio
    async def test_get_project_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Get Me")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Me"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_with_tasks(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="With Tasks")
        await _make_task(async_test_db, p.id, is_labeled=False)
        await _make_task(async_test_db, p.id, is_labeled=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{p.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 2
        assert data["completed_tasks_count"] == 1


class TestUpdateProject:
    """Test update_project with various field updates."""

    @pytest.mark.asyncio
    async def test_update_title(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Old Title")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}", json={"title": "New Title"}
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent", json={"title": "X"}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_generation_config_deep_merge(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(
            async_test_db,
            admin.id,
            title="Deep Merge",
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "generation_config": {
                        "selected_configuration": {"parameters": {"temperature": 0.5}}
                    }
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        gc = data.get("generation_config", {})
        sc = gc.get("selected_configuration", {})
        assert "gpt-4o" in sc.get("models", [])
        assert sc.get("parameters", {}).get("temperature") == 0.5

    @pytest.mark.asyncio
    async def test_update_evaluation_config_deep_merge(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(
            async_test_db,
            admin.id,
            title="Eval Merge",
            evaluation_config={"default_temperature": 0.2},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"evaluation_config": {"new_field": "value"}},
            )
        assert resp.status_code == 200
        data = resp.json()
        ec = data.get("evaluation_config", {})
        assert ec.get("default_temperature") == 0.2
        assert ec.get("new_field") == "value"

    @pytest.mark.asyncio
    async def test_update_instructions_alias(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Instr Update")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}", json={"instructions": "New instructions"}
            )
        assert resp.status_code == 200
        assert resp.json()["expert_instruction"] == "New instructions"

    @pytest.mark.asyncio
    async def test_update_label_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Label Update")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "label_config": "<View><Text name='text' value='$text'/><Choices name='c' toName='text'><Choice value='A'/></Choices></View>"
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_invalid_label_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Bad Update")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}", json={"label_config": "<<<not valid>>>"}
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_questionnaire_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Questionnaire")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "questionnaire_enabled": True,
                    "questionnaire_config": "<View><Rating name='r' toName='text'/></View>",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["questionnaire_enabled"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_update_skip_queue(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Skip Queue")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}", json={"skip_queue": "requeue_for_me"}
            )
        assert resp.status_code == 200


class TestDeleteProject:
    """Test delete_project with various permission scenarios."""

    @pytest.mark.asyncio
    async def test_delete_project_superadmin(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Delete Me")
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_private_project_by_creator(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=False)
        p = await _make_project(
            async_test_db, creator.id, title="Private Delete", is_private=True
        )
        await async_test_db.commit()

        with _as_user(creator), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_project_non_creator_non_superadmin_forbidden(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=False)
        # Non-private (org) project; non-creator non-superadmin -> 403.
        p = await _make_project(async_test_db, owner.id, title="No Delete")
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_project_with_tasks_and_members(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        member = await _make_user(async_test_db, is_superadmin=False)
        p = await _make_project(async_test_db, admin.id, title="Full Delete")
        await _make_task(async_test_db, p.id)
        pm = ProjectMember(
            id=_uid(),
            project_id=p.id,
            user_id=member.id,
            role="ANNOTATOR",
            assigned_by=admin.id,
        )
        async_test_db.add(pm)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code == 200


class TestUpdateProjectVisibility:
    """Test update_project_visibility endpoint."""

    @pytest.mark.asyncio
    async def test_make_project_private(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin.id, title="Vis Test")
        await _assign_project_to_org(async_test_db, p.id, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": admin.id},
            )
        assert resp.status_code == 200
        assert resp.json()["is_private"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_make_project_org_assigned(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(
            async_test_db, admin.id, title="Org Assign", is_private=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert resp.status_code == 200
        assert resp.json()["is_private"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_visibility_change_not_superadmin(
        self, async_test_client, async_test_db
    ):
        # Non-superadmin who is also not the creator cannot change visibility.
        owner = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=False)
        p = await _make_project(async_test_db, owner.id, title="No Vis")
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility", json={"is_private": True}
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_visibility_project_not_found(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent/visibility", json={"is_private": True}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_no_orgs_provided(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="No Orgs")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_visibility_invalid_org_id(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Invalid Org")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": ["nonexistent-org"]},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_invalid_owner(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Invalid Owner")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": "nonexistent-user"},
            )
        assert resp.status_code == 404


class TestRecalculateStats:
    """Test recalculate_project_statistics endpoint."""

    @pytest.mark.asyncio
    async def test_recalculate_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Recalc")
        await _make_task(async_test_db, p.id, is_labeled=True)
        await _make_task(async_test_db, p.id, is_labeled=False)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 2
        assert data["completed_tasks_count"] == 1

    @pytest.mark.asyncio
    async def test_recalculate_not_superadmin(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db, is_superadmin=True)
        regular = await _make_user(async_test_db, is_superadmin=False)
        p = await _make_project(async_test_db, owner.id, title="Recalc NoAdmin")
        await async_test_db.commit()

        with _as_current_user(regular):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_recalculate_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                "/api/projects/nonexistent/recalculate-stats"
            )
        assert resp.status_code == 404


class TestCompletionStats:
    """Test get_project_completion_stats endpoint."""

    @pytest.mark.asyncio
    async def test_completion_stats_no_tasks(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Empty")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["completed"] == 0
        assert data["completion_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_completion_stats_partial(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="Partial")
        await _make_task(async_test_db, p.id, is_labeled=True)
        await _make_task(async_test_db, p.id, is_labeled=False)
        await _make_task(async_test_db, p.id, is_labeled=False)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["completed"] == 1
        assert abs(data["completion_rate"] - 33.33) < 1

    @pytest.mark.asyncio
    async def test_completion_stats_all_complete(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        p = await _make_project(async_test_db, admin.id, title="All Done")
        await _make_task(async_test_db, p.id, is_labeled=True)
        await _make_task(async_test_db, p.id, is_labeled=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completion_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_completion_stats_not_found(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/completion-stats"
            )
        assert resp.status_code == 404
