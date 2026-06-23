"""
Unit tests for routers/projects/crud.py targeting uncovered lines.

Covers: list_projects happy path, create_project org/private paths,
get_project success, update_project with field updates, delete_project success,
update_project_visibility, recalculate, completion stats.

The CRUD handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``), so the old
``get_db``-Mock / query-chain pattern no longer reaches the handlers. These
tests seed real ORM rows via ``async_test_db`` and drive the surface through
``async_test_client``; ``require_user`` is overridden per-test via ``_as_user``
to an auth User matching the seeded owner. The admin-only
``recalculate-stats`` endpoint resolves the caller via ``get_current_user``
(returns a DB ``User``), so those tests additionally override that dependency
with the seeded DB user.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization


# ---------------------------------------------------------------------------
# Helpers (mirror tests/unit/test_projects_router.py — the converted reference)
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override require_user with an AuthUser matching the seeded DB user."""
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


@contextmanager
def _as_current_user(db_user: User):
    """Override get_current_user (used by recalculate-stats) with the seeded
    DB ``User`` row — that endpoint reads ``current_user.is_superadmin`` off a
    real ``User``, not an ``AuthUser``."""
    app.dependency_overrides[get_current_user] = lambda: db_user
    try:
        yield db_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"cru-{_uid()[:8]}",
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


async def _make_org(db, *, name="Test Org"):
    org = Organization(
        id=_uid(), name=name, display_name=name, slug=f"org-{_uid()[:8]}"
    )
    db.add(org)
    await db.flush()
    return org


async def _make_membership(db, *, user_id, organization_id, role="CONTRIBUTOR", is_active=True):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        is_active=is_active,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _make_project(
    db,
    *,
    created_by: str,
    title="Test Project",
    description="Test project description",
    is_private=True,
    is_public=False,
    label_config="<View></View>",
    generation_config=None,
    evaluation_config=None,
):
    p = Project(
        id=_uid(),
        title=title,
        description=description,
        created_by=created_by,
        label_config=label_config,
        is_private=is_private,
        is_public=is_public,
        generation_config=generation_config or {},
        evaluation_config=evaluation_config or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


async def _make_project_org(db, *, project_id, organization_id, assigned_by):
    po = ProjectOrganization(
        id=_uid(),
        project_id=project_id,
        organization_id=organization_id,
        assigned_by=assigned_by,
    )
    db.add(po)
    await db.flush()
    return po


# ---------------------------------------------------------------------------
# list_projects: happy path
# ---------------------------------------------------------------------------

class TestListProjectsHappyPath:
    @pytest.mark.asyncio
    async def test_list_projects_with_results(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id, title="Listed Project")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", headers={"X-Organization-Context": "private"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert any(p["title"] == "Listed Project" for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_projects_with_is_archived_filter(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", params={"is_archived": False}
            )

        assert resp.status_code == 200
        assert resp.json()["total"] >= 0

    @pytest.mark.asyncio
    async def test_list_projects_unexpected_exception(self, async_test_client, async_test_db):
        """An unexpected error in the accessible-id resolution surfaces as 500."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud.get_accessible_project_ids_async",
            side_effect=RuntimeError("Boom"),
        ):
            resp = await async_test_client.get("/api/projects/")

        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_list_projects_with_search(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await _make_project(async_test_db, created_by=admin.id, title="Searchable Topic")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/", params={"search": "no-such-title-xyz"}
            )

        assert resp.status_code == 200
        data = resp.json()
        titles = [p["title"] for p in data["items"]]
        assert "Searchable Topic" not in titles


# ---------------------------------------------------------------------------
# create_project: org mode paths
# ---------------------------------------------------------------------------

class TestCreateProjectOrgMode:
    @pytest.mark.asyncio
    async def test_create_project_private_mode(self, async_test_client, async_test_db):
        """Private (default) path: org context header 'private' => private project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_created_sync"
        ), patch("routers.projects.crud._create_initial_report_draft_sync"):
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Private", "is_private": True},
                headers={"X-Organization-Context": "private"},
            )

        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body["is_private"] is True
        row = (
            await async_test_db.execute(select(Project).where(Project.id == body["id"]))
        ).scalar_one_or_none()
        assert row is not None
        assert row.is_private is True
        assert row.created_by == admin.id

    @pytest.mark.asyncio
    async def test_create_project_org_mode_no_membership(self, async_test_client, async_test_db):
        """Org context but the (non-superadmin) user has no membership => 400."""
        user = await _make_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Org Project"},
                headers={"X-Organization-Context": "org-123"},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_project_org_mode_no_active_membership(self, async_test_client, async_test_db):
        """User has only an inactive membership => 400."""
        user = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(
            async_test_db,
            user_id=user.id,
            organization_id=org.id,
            role="ANNOTATOR",
            is_active=False,
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Org Project"},
                headers={"X-Organization-Context": org.id},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_project_org_mode_annotator_denied(self, async_test_client, async_test_db):
        """Active ANNOTATOR membership cannot create projects => 403."""
        user = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(
            async_test_db,
            user_id=user.id,
            organization_id=org.id,
            role="ANNOTATOR",
            is_active=True,
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Org Project"},
                headers={"X-Organization-Context": org.id},
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_project_invalid_label_config(self, async_test_client, async_test_db):
        """Invalid label_config XML => 422."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_created_sync"
        ), patch("routers.projects.crud._create_initial_report_draft_sync"):
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Bad Config", "label_config": "<<<bad>>>"},
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# get_project: success path
# ---------------------------------------------------------------------------

class TestGetProjectSuccess:
    @pytest.mark.asyncio
    async def test_get_project_accessible(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id, title="Accessible")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{project.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == project.id
        assert body["title"] == "Accessible"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/projects/missing")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_access_denied(self, async_test_client, async_test_db):
        """A non-owner of a private project is denied (403)."""
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=owner.id, is_private=True)
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.get(f"/api/projects/{project.id}")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# update_project: happy paths
# ---------------------------------------------------------------------------

class TestUpdateProjectHappyPath:
    @pytest.mark.asyncio
    async def test_update_instructions_mapping(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"instructions": "New instructions"},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        # 'instructions' maps to expert_instruction on the row.
        await async_test_db.refresh(project)
        assert project.expert_instruction == "New instructions"

    @pytest.mark.asyncio
    async def test_update_llm_model_ids_migration(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db, created_by=admin.id, generation_config={}
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"llm_model_ids": ["gpt-4o"]},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        # llm_model_ids migrates into generation_config.selected_configuration.models
        await async_test_db.refresh(project)
        assert (
            project.generation_config["selected_configuration"]["models"] == ["gpt-4o"]
        )

    @pytest.mark.asyncio
    async def test_update_label_config_with_versioning(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        new_config = (
            "<View><Text name='text' value='$text'/>"
            "<Choices name='c' toName='text'><Choice value='A'/></Choices></View>"
        )
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"label_config": new_config},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id

    @pytest.mark.asyncio
    async def test_update_label_config_invalid(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"label_config": "<<<bad>>>"},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_generation_config_deep_merge(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            created_by=admin.id,
            generation_config={"existing": "value"},
            evaluation_config={},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"generation_config": {"new_key": "val"}},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        # Deep merge preserves the existing key.
        await async_test_db.refresh(project)
        assert project.generation_config["existing"] == "value"
        assert project.generation_config["new_key"] == "val"

    @pytest.mark.asyncio
    async def test_update_evaluation_config_deep_merge(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            created_by=admin.id,
            evaluation_config={"temperature": 0.2},
            generation_config={},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={"evaluation_config": {"metric": "bleu"}},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        await async_test_db.refresh(project)
        assert project.evaluation_config["temperature"] == 0.2
        assert project.evaluation_config["metric"] == "bleu"

    @pytest.mark.asyncio
    async def test_update_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/missing", json={"title": "New"}
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_permission_denied(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, created_by=owner.id)
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}", json={"title": "New"}
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# delete_project: success path
# ---------------------------------------------------------------------------

class TestDeleteProjectSuccess:
    @pytest.mark.asyncio
    async def test_delete_superadmin(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin), patch("routers.projects.crud._notify_project_deleted_sync"):
            resp = await async_test_client.delete(f"/api/projects/{project_id}")

        assert resp.status_code in (200, 204)
        assert resp.json()["message"] == "Project deleted successfully"
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_delete_private_by_creator(self, async_test_client, async_test_db):
        creator = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(
            async_test_db, created_by=creator.id, is_private=True
        )
        project_id = project.id
        await async_test_db.commit()

        with _as_user(creator), patch("routers.projects.crud._notify_project_deleted_sync"):
            resp = await async_test_client.delete(f"/api/projects/{project_id}")

        assert resp.status_code in (200, 204)
        assert resp.json()["message"] == "Project deleted successfully"
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_delete_notification_failure(self, async_test_client, async_test_db):
        """A failing notification must not fail the deletion."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync",
            side_effect=RuntimeError("Notify fail"),
        ):
            resp = await async_test_client.delete(f"/api/projects/{project_id}")

        assert resp.status_code in (200, 204)
        assert resp.json()["message"] == "Project deleted successfully"
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin), patch("routers.projects.crud._notify_project_deleted_sync"):
            resp = await async_test_client.delete("/api/projects/missing")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_permission_denied(self, async_test_client, async_test_db):
        """Non-superadmin, non-private (org) project => 403."""
        owner = await _make_user(async_test_db)
        regular = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=False
        )
        await async_test_db.commit()

        with _as_user(regular):
            resp = await async_test_client.delete(f"/api/projects/{project.id}")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# update_project_visibility: happy paths
# ---------------------------------------------------------------------------

class TestVisibilityHappyPaths:
    @pytest.mark.asyncio
    async def test_make_private_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        owner = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=admin.id, is_private=False
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True, "owner_user_id": owner.id},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        await async_test_db.refresh(project)
        assert project.is_private is True
        assert project.created_by == owner.id

    @pytest.mark.asyncio
    async def test_make_org_assigned_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(
            async_test_db, created_by=admin.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == project.id
        await async_test_db.refresh(project)
        assert project.is_private is False
        po = (
            await async_test_db.execute(
                select(ProjectOrganization).where(
                    ProjectOrganization.project_id == project.id
                )
            )
        ).scalars().all()
        assert any(p.organization_id == org.id for p in po)

    @pytest.mark.asyncio
    async def test_make_org_assigned_org_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": ["missing-org"]},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_not_superadmin(self, async_test_client, async_test_db):
        """Non-superadmin non-creator => 403."""
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, created_by=owner.id)
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True},
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_visibility_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/missing/visibility",
                json={"is_private": True},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_visibility_no_org_ids(self, async_test_client, async_test_db):
        """Making a project org-assigned with no org ids => 400."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# recalculate_project_statistics — admin-only (uses get_current_user)
# ---------------------------------------------------------------------------

class TestRecalculateSuccess:
    @pytest.mark.asyncio
    async def test_recalculate_stats_success(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/recalculate-stats"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert "task_count" in body
        assert body["task_count"] == 0

    @pytest.mark.asyncio
    async def test_recalculate_not_superadmin(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()

        with _as_current_user(user):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/recalculate-stats"
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_recalculate_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                "/api/projects/missing/recalculate-stats"
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_project_completion_stats
# ---------------------------------------------------------------------------

class TestCompletionStatsSuccess:
    @pytest.mark.asyncio
    async def test_completion_stats_with_tasks(self, async_test_client, async_test_db):
        from project_models import Task

        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        # 10 tasks, 4 labeled.
        for i in range(10):
            async_test_db.add(
                Task(
                    id=_uid(),
                    project_id=project.id,
                    data={"text": f"t{i}"},
                    is_labeled=(i < 4),
                    inner_id=i + 1,
                    created_at=datetime.now(timezone.utc),
                )
            )
        await async_test_db.flush()
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 10
        assert body["completed"] == 4
        assert body["completion_rate"] == 40.0

    @pytest.mark.asyncio
    async def test_completion_stats_no_tasks(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["completion_rate"] == 0.0
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_completion_stats_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get(
                "/api/projects/missing/completion-stats"
            )

        assert resp.status_code == 404
