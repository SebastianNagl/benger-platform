"""
Integration tests targeting uncovered handler body code in routers/projects/crud.py.

Covers lines: 100-197 (list_projects), 217-348 (create_project),
366-398 (get_project), 410-542 (update_project), 553-614 (delete_project),
630-711 (update_project_visibility), 727-746 (recalculate_stats), 772-792 (completion_stats)

The CRUD handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). Rows seeded
into the sync ``test_db`` are on a separate connection invisible to the async
engine, so these tests now seed real ORM rows via ``async_test_db`` and drive
the surface through ``async_test_client``. ``require_user`` (or
``get_current_user`` for the admin-only recalc endpoint) is overridden per-test
via ``_as_user`` / ``_as_current_user`` to an auth user matching the seeded
owner. Create/delete tests patch the sync notification/report wrappers to avoid
the Redis-backed threadpool stall.
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
from models import (
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


# ============= helpers =============


def _uid():
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
        username=f"cd-{_uid()[:8]}",
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


async def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Crud {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kwargs.get("is_private", False),
        description=kwargs.get("description", "Test project"),
        created_at=datetime.now(timezone.utc),
        **{
            k: v
            for k, v in kwargs.items()
            if k not in ("title", "label_config", "is_private", "description")
        },
    )
    db.add(p)
    await db.flush()
    if org is not None:
        po = ProjectOrganization(
            id=_uid(),
            project_id=p.id,
            organization_id=org.id,
            assigned_by=admin.id,
        )
        db.add(po)
        await db.flush()
    return p


async def _tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _annotations(db, project, tasks, user_id, lead_time=10.0):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=False,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _seed_admin_org(db):
    """Seed a superadmin who is a member of a fresh org, mirroring the
    original ``test_users[0]`` (admin) + ``test_org`` fixtures."""
    admin = await _make_user(db, is_superadmin=True, name="Admin")
    org = await _make_org(db)
    await _make_membership(db, admin.id, org.id, "ORG_ADMIN")
    return admin, org


# ===================================================================
# LIST PROJECTS (lines 100-197)
# ===================================================================

@pytest.mark.integration
class TestListProjects:
    """Cover list_projects handler body."""

    @pytest.mark.asyncio
    async def test_list_projects_with_org_context(self, async_test_client, async_test_db):
        """List projects with organization context header."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org, title="List Test 1")
        await _tasks(async_test_db, p, admin, count=5)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_projects_with_search(self, async_test_client, async_test_db):
        """List projects with search filter."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org, title="UniqueSearchableTitle99")
        await _tasks(async_test_db, p, admin, count=2)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?search=UniqueSearchableTitle99",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_projects_pagination(self, async_test_client, async_test_db):
        """List projects with pagination params."""
        admin, org = await _seed_admin_org(async_test_db)
        for i in range(3):
            p = await _project(async_test_db, admin, org, title=f"Page Test {i}")
            await _tasks(async_test_db, p, admin, count=1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?page=1&page_size=2",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_projects_empty_org(self, async_test_client, async_test_db):
        """List projects with archived filter."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?is_archived=false",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_projects_private_context(self, async_test_client, async_test_db):
        """List private projects."""
        admin, _ = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 200


# ===================================================================
# CREATE PROJECT (lines 217-348)
# ===================================================================

@pytest.mark.integration
class TestCreateProject:
    """Cover create_project handler body."""

    @pytest.mark.asyncio
    async def test_create_project_with_org_context(self, async_test_client, async_test_db):
        """Create a project assigned to an organization."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Created via API",
                    "description": "Integration test project",
                    "label_config": '<View><Text name="text" value="$text"/></View>',
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Created via API"

    @pytest.mark.asyncio
    async def test_create_private_project(self, async_test_client, async_test_db):
        """Create a private project."""
        admin, _ = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Private Project Test",
                    "is_private": True,
                },
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Private Project Test"

    @pytest.mark.asyncio
    async def test_create_project_with_all_fields(self, async_test_client, async_test_db):
        """Create project with all optional fields."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Full Fields Project",
                    "description": "A project with all fields",
                    "label_config": '<View><Text name="text" value="$text"/>'
                                   '<Choices name="answer" toName="text">'
                                   '<Choice value="A"/><Choice value="B"/></Choices></View>',
                    "expert_instruction": "Read carefully",
                    "show_instruction": True,
                    "show_skip_button": True,
                    "enable_empty_annotation": False,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expert_instruction"] == "Read carefully"

    @pytest.mark.asyncio
    async def test_create_project_invalid_label_config(self, async_test_client, async_test_db):
        """Create project with invalid label config should fail."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Bad Config Project",
                    "label_config": "<Invalid>Not valid XML",
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (422, 400)

    @pytest.mark.asyncio
    async def test_create_project_annotator_denied(self, async_test_client, async_test_db):
        """Annotator should not be able to create projects."""
        annotator = await _make_user(async_test_db, is_superadmin=False, name="Annotator")
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(annotator), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Annotator Project"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403


# ===================================================================
# GET PROJECT (lines 366-398)
# ===================================================================

@pytest.mark.integration
class TestGetProject:
    """Cover get_project handler body."""

    @pytest.mark.asyncio
    async def test_get_project_detail(self, async_test_client, async_test_db):
        """Get project detail with enriched response."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org, title="Detail Test")
        tasks = await _tasks(async_test_db, p, admin, count=5)
        await _annotations(async_test_db, p, tasks[:3], admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Detail Test"
        assert data["task_count"] == 5

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        """Get non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_with_generations(self, async_test_client, async_test_db):
        """Get project that has generation data."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        tasks = await _tasks(async_test_db, p, admin, count=2)
        rg = ResponseGeneration(
            id=_uid(), project_id=p.id, model_id="gpt-4o",
            status="completed", created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        for i, t in enumerate(tasks):
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=t.id,
                model_id="gpt-4o", run_index=i,
                case_data="{}", response_content="answer",
                label_config_version="v1", status="completed",
            )
            async_test_db.add(gen)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}", headers={"X-Organization-Context": org.id}
            )
        assert resp.status_code == 200


# ===================================================================
# UPDATE PROJECT (lines 410-542)
# ===================================================================

@pytest.mark.integration
class TestUpdateProject:
    """Cover update_project handler body."""

    @pytest.mark.asyncio
    async def test_update_project_title(self, async_test_client, async_test_db):
        """Update project title."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org, title="Old Title")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"title": "New Title"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_project_description(self, async_test_client, async_test_db):
        """Update project description."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"description": "Updated description"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_project_label_config(self, async_test_client, async_test_db):
        """Update project label config triggers versioning."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        new_config = (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="A"/><Choice value="B"/><Choice value="C"/></Choices></View>'
        )
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"label_config": new_config},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_instructions_mapping(self, async_test_client, async_test_db):
        """Update project with 'instructions' field maps to expert_instruction."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"instructions": "New instructions for annotators"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["expert_instruction"] == "New instructions for annotators"

    @pytest.mark.asyncio
    async def test_update_project_generation_config(self, async_test_client, async_test_db):
        """Update project generation_config with deep merge."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"generation_config": {"selected_configuration": {"models": ["gpt-4o"]}}},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_evaluation_config(self, async_test_client, async_test_db):
        """Update project evaluation_config with deep merge."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"evaluation_config": {"metrics": ["accuracy"]}},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, async_test_client, async_test_db):
        """Update non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{_uid()}",
                json={"title": "nope"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project_show_skip_button(self, async_test_client, async_test_db):
        """Update project skip button setting."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"show_skip_button": True, "enable_empty_annotation": True},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


# ===================================================================
# DELETE PROJECT (lines 553-614)
# ===================================================================

@pytest.mark.integration
class TestDeleteProject:
    """Cover delete_project handler body."""

    @pytest.mark.asyncio
    async def test_delete_project_as_admin(self, async_test_client, async_test_db):
        """Admin can delete a project."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org, title="To Delete")
        await _tasks(async_test_db, p, admin, count=2)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, async_test_client, async_test_db):
        """Delete non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/projects/{_uid()}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_non_admin_denied(self, async_test_client, async_test_db):
        """Non-admin cannot delete org project."""
        admin, org = await _seed_admin_org(async_test_db)
        annotator = await _make_user(async_test_db, is_superadmin=False, name="Annotator")
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.delete(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_project_with_annotations(self, async_test_client, async_test_db):
        """Delete project that has annotations."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        tasks = await _tasks(async_test_db, p, admin, count=2)
        await _annotations(async_test_db, p, tasks, admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


# ===================================================================
# UPDATE VISIBILITY (lines 630-711)
# ===================================================================

@pytest.mark.integration
class TestUpdateVisibility:
    """Cover update_project_visibility handler body."""

    @pytest.mark.asyncio
    async def test_make_project_private(self, async_test_client, async_test_db):
        """Make an org project private."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": admin.id},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_make_project_org_assigned(self, async_test_client, async_test_db):
        """Make a private project org-assigned."""
        admin, org = await _seed_admin_org(async_test_db)
        # Create private project first
        p = Project(
            id=_uid(), title="Private to Org", created_by=admin.id,
            is_private=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(p)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_visibility_nonexistent_project(self, async_test_client, async_test_db):
        """Update visibility for non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{_uid()}/visibility",
                json={"is_private": True},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_no_org_ids_for_public(self, async_test_client, async_test_db):
        """Making project public without org IDs should fail."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": []},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_visibility_non_admin_denied(self, async_test_client, async_test_db):
        """Non-superadmin cannot change visibility."""
        admin, org = await _seed_admin_org(async_test_db)
        contributor = await _make_user(async_test_db, is_superadmin=False, name="Contributor")
        await _make_membership(async_test_db, contributor.id, org.id, "CONTRIBUTOR")
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_visibility_invalid_owner(self, async_test_client, async_test_db):
        """Make private with non-existent owner."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": _uid()},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_invalid_org(self, async_test_client, async_test_db):
        """Make public with non-existent org."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": [_uid()]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404


# ===================================================================
# RECALCULATE STATS (lines 727-746)
# ===================================================================

@pytest.mark.integration
class TestRecalculateStats:
    """Cover recalculate_project_statistics handler."""

    @pytest.mark.asyncio
    async def test_recalculate_stats(self, async_test_client, async_test_db):
        """Recalculate stats for a project with data."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        tasks = await _tasks(async_test_db, p, admin, count=5)
        await _annotations(async_test_db, p, tasks[:3], admin.id)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 5

    @pytest.mark.asyncio
    async def test_recalculate_stats_not_found(self, async_test_client, async_test_db):
        """Recalculate stats for non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/recalculate-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_recalculate_stats_non_admin(self, async_test_client, async_test_db):
        """Non-admin cannot recalculate stats."""
        admin, org = await _seed_admin_org(async_test_db)
        annotator = await _make_user(async_test_db, is_superadmin=False, name="Annotator")
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_current_user(annotator):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403


# ===================================================================
# COMPLETION STATS (lines 772-792)
# ===================================================================

@pytest.mark.integration
class TestCompletionStats:
    """Cover get_project_completion_stats handler."""

    @pytest.mark.asyncio
    async def test_completion_stats(self, async_test_client, async_test_db):
        """Get completion stats for a project."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        tasks = await _tasks(async_test_db, p, admin, count=10)
        await _annotations(async_test_db, p, tasks[:6], admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_completion_stats_not_found(self, async_test_client, async_test_db):
        """Completion stats for non-existent project."""
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_completion_stats_empty_project(self, async_test_client, async_test_db):
        """Completion stats for project with no tasks."""
        admin, org = await _seed_admin_org(async_test_db)
        p = await _project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
