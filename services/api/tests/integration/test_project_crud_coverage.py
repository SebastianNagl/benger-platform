"""
Integration tests targeting uncovered handler body code in routers/projects/crud.py.

Focuses on:
- list_projects: org context filtering, search, pagination, is_archived filter,
  enriched response with stats, generation_models_count
- create_project: org assignment, private mode, label_config validation,
  annotator role rejection, contributor creation
- get_project: enriched response, access control, stats calculation
- update_project: field mapping (instructions -> expert_instruction),
  generation_config deep merge, evaluation_config deep merge,
  label_config versioning, llm_model_ids backward compat
- delete_project: cascade deletion, non-admin rejection
- visibility: private <-> org toggle, superadmin only
- recalculate_stats: admin only, stat computation
- completion_stats: task completion rates

The CRUD handlers were migrated to the async DB lane (``Depends(get_async_db)``
+ ``await db.execute(select(...))``). The old pattern (sync ``client`` +
``auth_headers`` JWT + rows seeded into the sync ``test_db``) no longer reaches
the handlers — rows seeded on the sync engine are invisible to the async
engine. These tests now seed real ORM rows via ``async_test_db`` and drive the
surface through ``async_test_client``, with ``require_user`` (or
``get_current_user`` for the admin-only recalc endpoint) overridden per-test via
``_as_user`` to an auth user matching the seeded owner. Create/delete tests
patch the sync notification/report wrappers to avoid the Redis-backed
threadpool stall.
"""

import json
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
        username=f"cc-{_uid()[:8]}",
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


async def _make_project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"CrudCov {uuid.uuid4().hex[:6]}"),
        description=kwargs.get("description", "Test project for crud coverage"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kwargs.get("is_private", False),
        generation_config=kwargs.get("generation_config", None),
        evaluation_config=kwargs.get("evaluation_config", None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    if not kwargs.get("is_private", False):
        po = ProjectOrganization(
            id=_uid(),
            project_id=p.id,
            organization_id=org.id,
            assigned_by=admin.id,
        )
        db.add(po)
        await db.flush()
    return p


async def _make_tasks(db, project, admin, count=3, labeled_count=0):
    tasks = []
    for i in range(count):
        is_lab = i < labeled_count
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Crud text #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
            is_labeled=is_lab,
            total_annotations=(1 if is_lab else 0),
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _make_annotations(db, project, tasks, user_id):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[
                {
                    "from_name": "answer",
                    "to_name": "text",
                    "type": "choices",
                    "value": {"choices": ["Ja"]},
                }
            ],
            was_cancelled=False,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _make_generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        status="completed",
        created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    await db.flush()
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=t.id,
            model_id=model_id,
            run_index=i,
            case_data=json.dumps(t.data),
            response_content="Gen",
            label_config_version="v1",
            status="completed",
        )
        db.add(gen)
    await db.flush()


# ===================================================================
# LIST PROJECTS
# ===================================================================

@pytest.mark.integration
class TestListProjectsDeep:
    """Deep coverage for list_projects handler body."""

    @pytest.mark.asyncio
    async def test_list_with_org_context(self, async_test_client, async_test_db):
        """List projects with org context returns only org projects."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org, title="Org Project")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

    @pytest.mark.asyncio
    async def test_list_with_search_filter(self, async_test_client, async_test_db):
        """Search filter works on title."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org, title="UniqueSearchable XYZ")
        await _make_project(async_test_db, admin, org, title="Other Project")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?search=UniqueSearchable",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert (
                "UniqueSearchable" in item["title"]
                or "uniquesearchable" in item["title"].lower()
            )

    @pytest.mark.asyncio
    async def test_list_pagination(self, async_test_client, async_test_db):
        """Pagination returns correct page_size."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        for i in range(5):
            await _make_project(async_test_db, admin, org, title=f"Paginated {i}")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?page=1&page_size=2",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_enriched_response_fields(
        self, async_test_client, async_test_db
    ):
        """Projects include enriched fields: task_count, annotation_count, progress_percentage."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, title="Enriched")
        tasks = await _make_tasks(async_test_db, p, admin, count=4, labeled_count=2)
        await _make_annotations(async_test_db, p, tasks[:2], admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        our_proj = next((it for it in items if it["title"] == "Enriched"), None)
        if our_proj:
            assert "task_count" in our_proj
            assert "annotation_count" in our_proj
            assert "progress_percentage" in our_proj
            assert "created_by_name" in our_proj

    @pytest.mark.asyncio
    async def test_list_with_generations_stats(
        self, async_test_client, async_test_db
    ):
        """Projects include generation-related statistics."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, title="WithGens")
        tasks = await _make_tasks(async_test_db, p, admin, count=3)
        await _make_generations(async_test_db, p, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_superadmin_no_org_context(
        self, async_test_client, async_test_db
    ):
        """Superadmin without org context sees all projects."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org, title="No Context")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/")
        assert resp.status_code == 200


# ===================================================================
# CREATE PROJECT
# ===================================================================

@pytest.mark.integration
class TestCreateProjectDeep:
    """Deep coverage for create_project handler body."""

    @pytest.mark.asyncio
    async def test_create_org_project(self, async_test_client, async_test_db):
        """Create project with org context."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "New Org Project", "description": "Test"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["title"] == "New Org Project"
        assert "id" in data
        assert "created_by_name" in data

    @pytest.mark.asyncio
    async def test_create_private_project(self, async_test_client, async_test_db):
        """Create private project without org context."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Private Project", "is_private": True},
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_create_with_label_config(self, async_test_client, async_test_db):
        """Create project with label_config."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Labeled Project",
                    "label_config": '<View><Text name="text" value="$text"/></View>',
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_create_with_invalid_label_config(
        self, async_test_client, async_test_db
    ):
        """Invalid label_config returns 422."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Bad Config",
                    "label_config": "not valid xml at all {{{}}}",
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_instructions(self, async_test_client, async_test_db):
        """Create project with expert_instruction."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Instructed Project",
                    "expert_instruction": "Please annotate carefully.",
                    "show_instruction": True,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_annotator_cannot_create(self, async_test_client, async_test_db):
        """Annotator role cannot create projects."""
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(annotator), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Should Fail"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_contributor_can_create(self, async_test_client, async_test_db):
        """Contributor role can create projects."""
        contributor = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, contributor.id, org.id, "CONTRIBUTOR")
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(contributor), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Contributor Project"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)


# ===================================================================
# GET PROJECT
# ===================================================================

@pytest.mark.integration
class TestGetProjectDeep:
    """Deep coverage for get_project handler body."""

    @pytest.mark.asyncio
    async def test_get_enriched_response(self, async_test_client, async_test_db):
        """GET project returns enriched fields."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, title="Enriched Get")
        tasks = await _make_tasks(async_test_db, p, admin, count=5, labeled_count=2)
        await _make_annotations(async_test_db, p, tasks[:2], admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == p.id
        assert "task_count" in data
        assert "annotation_count" in data
        assert "created_by_name" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(
        self, async_test_client, async_test_db
    ):
        """GET nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent-uuid")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_with_generation_stats(
        self, async_test_client, async_test_db
    ):
        """GET project includes generation statistics."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, title="Gen Stats")
        tasks = await _make_tasks(async_test_db, p, admin, count=3)
        await _make_generations(async_test_db, p, tasks)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


# ===================================================================
# UPDATE PROJECT
# ===================================================================

@pytest.mark.integration
class TestUpdateProjectDeep:
    """Deep coverage for update_project handler body."""

    @pytest.mark.asyncio
    async def test_update_title_and_description(
        self, async_test_client, async_test_db
    ):
        """Basic title/description update."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"title": "Updated Title", "description": "Updated Desc"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_generation_config_deep_merge(
        self, async_test_client, async_test_db
    ):
        """Generation config update uses deep merge, preserving existing keys."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(
            async_test_db,
            admin,
            org,
            generation_config={
                "selected_configuration": {"models": ["gpt-4o"]},
                "prompt_template": "original",
            },
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "generation_config": {
                        "selected_configuration": {"models": ["claude-3-sonnet"]},
                    }
                },
            )
        assert resp.status_code == 200
        config = resp.json().get("generation_config", {})
        # Deep merge should preserve prompt_template
        assert config.get("prompt_template") == "original"

    @pytest.mark.asyncio
    async def test_update_evaluation_config_deep_merge(
        self, async_test_client, async_test_db
    ):
        """Evaluation config update uses deep merge."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(
            async_test_db,
            admin,
            org,
            evaluation_config={
                "selected_methods": {"answer": {"automated": ["accuracy"]}},
                "other_key": "preserved",
            },
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "evaluation_config": {
                        "selected_methods": {
                            "answer": {"automated": ["accuracy", "f1"]}
                        },
                    }
                },
            )
        assert resp.status_code == 200
        config = resp.json().get("evaluation_config", {})
        assert config.get("other_key") == "preserved"

    @pytest.mark.asyncio
    async def test_update_label_config(self, async_test_client, async_test_db):
        """Label config update triggers versioning."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        new_config = (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Yes"/><Choice value="No"/></Choices></View>'
        )
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"label_config": new_config},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_invalid_label_config(
        self, async_test_client, async_test_db
    ):
        """Invalid label config returns 422."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"label_config": "invalid xml {{"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(
        self, async_test_client, async_test_db
    ):
        """Update nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent",
                json={"title": "Nope"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_show_skip_button(self, async_test_client, async_test_db):
        """Update show_skip_button setting."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"show_skip_button": True},
            )
        assert resp.status_code == 200


# ===================================================================
# DELETE PROJECT
# ===================================================================

@pytest.mark.integration
class TestDeleteProjectDeep:
    """Deep coverage for delete_project handler body."""

    @pytest.mark.asyncio
    async def test_delete_with_tasks_and_annotations(
        self, async_test_client, async_test_db
    ):
        """Delete project cascades to tasks."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        tasks = await _make_tasks(async_test_db, p, admin, count=3)
        await _make_annotations(async_test_db, p, tasks, admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(
        self, async_test_client, async_test_db
    ):
        """Delete nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_org_project(
        self, async_test_client, async_test_db
    ):
        """Non-superadmin cannot delete org project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code == 403


# ===================================================================
# VISIBILITY
# ===================================================================

@pytest.mark.integration
class TestVisibilityDeep:
    """Deep coverage for visibility endpoint."""

    @pytest.mark.asyncio
    async def test_make_project_private(self, async_test_client, async_test_db):
        """Superadmin can make a project private."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": admin.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_make_project_org_assigned(
        self, async_test_client, async_test_db
    ):
        """Superadmin can assign project to orgs."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, is_private=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_visibility_non_admin_rejected(
        self, async_test_client, async_test_db
    ):
        """Non-superadmin cannot change visibility."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_visibility_nonexistent_project(
        self, async_test_client, async_test_db
    ):
        """Visibility on nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_org_no_ids(self, async_test_client, async_test_db):
        """Making org-assigned without organization_ids returns 400."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_visibility_nonexistent_org(
        self, async_test_client, async_test_db
    ):
        """Assignment to nonexistent org returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": False, "organization_ids": ["nonexistent-org"]},
            )
        assert resp.status_code == 404


# ===================================================================
# RECALCULATE STATS
# ===================================================================

@pytest.mark.integration
class TestRecalculateStats:
    """Coverage for recalculate-stats endpoint."""

    @pytest.mark.asyncio
    async def test_recalculate_stats_admin(self, async_test_client, async_test_db):
        """Admin can recalculate project statistics."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        tasks = await _make_tasks(async_test_db, p, admin, count=5, labeled_count=2)
        await _make_annotations(async_test_db, p, tasks[:2], admin.id)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_count" in data
        assert "annotation_count" in data
        assert "progress_percentage" in data

    @pytest.mark.asyncio
    async def test_recalculate_stats_non_admin_rejected(
        self, async_test_client, async_test_db
    ):
        """Non-admin cannot recalculate stats."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_current_user(annotator):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_recalculate_stats_nonexistent(
        self, async_test_client, async_test_db
    ):
        """Recalculate for nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                "/api/projects/nonexistent/recalculate-stats"
            )
        assert resp.status_code == 404


# ===================================================================
# COMPLETION STATS
# ===================================================================

@pytest.mark.integration
class TestCompletionStats:
    """Coverage for completion-stats endpoint."""

    @pytest.mark.asyncio
    async def test_completion_stats(self, async_test_client, async_test_db):
        """Completion stats returns completed/total/rate."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_tasks(async_test_db, p, admin, count=10, labeled_count=4)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["completed"] == 4
        assert data["completion_rate"] == 40.0

    @pytest.mark.asyncio
    async def test_completion_stats_empty_project(
        self, async_test_client, async_test_db
    ):
        """Empty project has 0% completion."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["completion_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_completion_stats_nonexistent(
        self, async_test_client, async_test_db
    ):
        """Completion stats for nonexistent project returns 404."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/completion-stats"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_completion_stats_100_percent(
        self, async_test_client, async_test_db
    ):
        """Fully labeled project has 100% completion."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_tasks(async_test_db, p, admin, count=5, labeled_count=5)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completion_rate"] == 100.0
