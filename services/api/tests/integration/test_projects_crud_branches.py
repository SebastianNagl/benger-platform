"""Behavioral integration tests for uncovered branches of the project CRUD
router (``services/api/routers/projects/crud.py``, mounted at
``/api/projects``).

The happy paths and simple 404/403s for this router are already covered by
``tests/routers/projects/test_crud.py`` and several mock-heavy unit suites.
This module fills the genuinely-uncovered *behavioral* branches that need a
real DB to exercise — chiefly the public-project create/visibility paths and
the org-assignment churn that mock sessions cannot reproduce:

- ``POST /`` (create_project):
    * public-project create (``is_public=True``) → persisted with
      ``public_role`` defaulted to ANNOTATOR and NO ProjectOrganization row.
    * the both-private-and-public 400 guard.
- ``GET /`` (list_projects):
    * the ``is_archived`` SQL filter (true / false).
    * the annotator hardening: an annotator org-member never receives archived
      projects from the list, even when explicitly requesting them.
- ``PATCH /{id}/visibility`` (update_project_visibility):
    * make-public: drops org assignments, flips flags (persisted).
    * standalone ``public_role`` flip on an already-public project.
    * the public_role-flip-on-non-public 400 guard.
    * make-private: reassign owner + drop org assignments (persisted).
    * make-org-assigned with an unknown org id → 404.
- ``GET /{id}/completion-stats``:
    * happy path counts (labeled vs total) + 403 for an outsider context.

The CRUD handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). Rows seeded
into the sync ``test_db`` are on a separate connection invisible to the async
engine, so these tests seed real ORM rows via ``async_test_db`` and drive the
surface through ``async_test_client``, with ``require_user`` overridden
per-test via ``_as_user`` to an auth user matching the seeded owner. Each test
asserts the HTTP status, response JSON, and the persisted ``Project`` /
``ProjectOrganization`` rows re-queried via ``async_test_db``. The public
create test patches the sync notification/report wrappers to avoid the
Redis-backed threadpool stall.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task


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


def _no_side_effects():
    return (
        patch("routers.projects.crud._notify_project_created_sync"),
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


async def _make_org(db, *, name="CRUD Branch Org"):
    org = Organization(
        id=_uid(),
        name=name,
        slug=f"crud-branch-{uuid.uuid4().hex[:8]}",
        display_name=name,
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


async def _seed_admin_org(db):
    """Seed a superadmin who is a member of a fresh org, mirroring the original
    ``test_users[0]`` (admin) + ``test_org`` fixtures."""
    admin = await _make_user(db, is_superadmin=True, name="Admin")
    org = await _make_org(db)
    await _make_membership(db, admin.id, org.id, "ORG_ADMIN")
    return admin, org


async def _make_project(db, creator, org=None, *, is_private=False, is_public=False,
                        public_role=None, is_archived=False):
    p = Project(
        id=_uid(),
        title=f"CRUD Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=is_private,
        is_public=is_public,
        public_role=public_role,
        is_archived=is_archived,
        label_config='<View><Text name="text" value="$text"/></View>',
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()
    return p


async def _get_project(db, project_id):
    # `async_test_db` uses expire_on_commit=False and is the same session the
    # handler mutated, so a bare select() returns the cached identity-map row —
    # the visibility persistence assertions (is_public / is_private /
    # public_role) would pass even if nothing was committed. populate_existing
    # forces a real DB round-trip for THIS row (matching the sync HEAD refresh)
    # without expiring the whole session (which would break later access to
    # other ORM objects, e.g. a reassigned owner).
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _count_org_rows(db, project_id):
    result = await db.execute(
        select(func.count())
        .select_from(ProjectOrganization)
        .where(ProjectOrganization.project_id == project_id)
    )
    return result.scalar_one()


# ===========================================================================
# POST / — create_project (public + conflict branches)
# ===========================================================================


@pytest.mark.integration
class TestCreatePublicProject:
    @pytest.mark.asyncio
    async def test_create_public_defaults_role_and_no_org_link(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, r = _no_side_effects()
        with _as_user(admin), n, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Public Branch Project", "is_public": True},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        project_id = body["id"]

        project = await _get_project(async_test_db, project_id)
        assert project.is_public is True
        assert project.is_private is False
        # public_role defaults to ANNOTATOR when omitted.
        assert project.public_role == "ANNOTATOR"
        # Public projects get NO org assignment row.
        assert await _count_org_rows(async_test_db, project_id) == 0

    @pytest.mark.asyncio
    async def test_create_public_with_contributor_role(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, r = _no_side_effects()
        with _as_user(admin), n, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "Public Contributor Project",
                    "is_public": True,
                    "public_role": "CONTRIBUTOR",
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        project_id = resp.json()["id"]

        project = await _get_project(async_test_db, project_id)
        assert project.public_role == "CONTRIBUTOR"

    @pytest.mark.asyncio
    async def test_create_both_private_and_public_400(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        n, r = _no_side_effects()
        with _as_user(admin), n, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Conflict", "is_public": True, "is_private": True},
                headers={"X-Organization-Context": org.id},
            )
        # The pydantic validator rejects this combination before the handler
        # body runs, so the response is a 422 validation error; if it reaches
        # the handler guard it is a 400. Accept either, assert nothing else.
        assert resp.status_code in (400, 422)


# ===========================================================================
# GET / — list_projects is_archived virtual filter
# ===========================================================================


@pytest.mark.integration
class TestListProjectsArchivedFilter:
    @pytest.mark.asyncio
    async def test_is_archived_true_and_false(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        archived = await _make_project(async_test_db, admin, org, is_archived=True)
        active = await _make_project(async_test_db, admin, org, is_archived=False)
        await async_test_db.commit()

        # is_archived=true → only the archived project.
        with _as_user(admin):
            r_arch = await async_test_client.get(
                "/api/projects/?is_archived=true&page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r_arch.status_code == 200
        arch_ids = {p["id"] for p in r_arch.json()["items"]}
        assert archived.id in arch_ids
        assert active.id not in arch_ids

        # is_archived=false → excludes the archived one.
        with _as_user(admin):
            r_active = await async_test_client.get(
                "/api/projects/?is_archived=false&page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r_active.status_code == 200
        active_ids = {p["id"] for p in r_active.json()["items"]}
        assert active.id in active_ids
        assert archived.id not in active_ids


@pytest.mark.integration
class TestListProjectsArchivedAnnotatorHardening:
    """An annotator org-member must never receive archived projects from the
    list endpoint, even when explicitly requesting ``is_archived=true``. The
    detail endpoint already blocks them (``check_project_accessible_async``);
    the list endpoint mirrors that block so it can't leak archived rows the UI
    hides — while higher roles and the project creator keep their access."""

    @pytest.mark.asyncio
    async def test_annotator_never_sees_archived_even_when_requested(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db, is_superadmin=True, name="Owner")
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, owner.id, org.id, "ORG_ADMIN")

        annotator = await _make_user(async_test_db, name="Annotator")
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")

        archived = await _make_project(async_test_db, owner, org, is_archived=True)
        active = await _make_project(async_test_db, owner, org, is_archived=False)
        await async_test_db.commit()

        # Explicitly asking for archived returns nothing for the annotator.
        with _as_user(annotator):
            r_arch = await async_test_client.get(
                "/api/projects/?is_archived=true&page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r_arch.status_code == 200
        body = r_arch.json()
        assert body["items"] == []
        assert body["total"] == 0

        # With no archive param the annotator still sees the active project but
        # not the archived one.
        with _as_user(annotator):
            r_all = await async_test_client.get(
                "/api/projects/?page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r_all.status_code == 200
        all_ids = {p["id"] for p in r_all.json()["items"]}
        assert active.id in all_ids
        assert archived.id not in all_ids

    @pytest.mark.asyncio
    async def test_contributor_still_sees_archived(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db, is_superadmin=True, name="Owner")
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, owner.id, org.id, "ORG_ADMIN")

        contributor = await _make_user(async_test_db, name="Contributor")
        await _make_membership(async_test_db, contributor.id, org.id, "CONTRIBUTOR")

        archived = await _make_project(async_test_db, owner, org, is_archived=True)
        await async_test_db.commit()

        with _as_user(contributor):
            r = await async_test_client.get(
                "/api/projects/?is_archived=true&page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r.status_code == 200
        assert archived.id in {p["id"] for p in r.json()["items"]}

    @pytest.mark.asyncio
    async def test_annotator_creator_keeps_own_archived(
        self, async_test_client, async_test_db
    ):
        # Mirrors the creator short-circuit in check_project_accessible_async: a
        # project's creator resolves to ORG_ADMIN, so the annotator block does
        # not apply to their own archived project. The list carve-out
        # (created_by == current_user) keeps it visible.
        annotator = await _make_user(async_test_db, name="Annotator-Creator")
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, annotator.id, org.id, "ANNOTATOR")

        own_archived = await _make_project(
            async_test_db, annotator, org, is_archived=True
        )
        await async_test_db.commit()

        with _as_user(annotator):
            r = await async_test_client.get(
                "/api/projects/?is_archived=true&page_size=500",
                headers={"X-Organization-Context": org.id},
            )
        assert r.status_code == 200
        assert own_archived.id in {p["id"] for p in r.json()["items"]}


# ===========================================================================
# PATCH /{id}/visibility — update_project_visibility
# ===========================================================================


@pytest.mark.integration
class TestVisibilityTransitions:
    @pytest.mark.asyncio
    async def test_make_public_drops_orgs_and_sets_flags(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()
        assert await _count_org_rows(async_test_db, project.id) == 1

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_public": True, "public_role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 200

        refreshed = await _get_project(async_test_db, project.id)
        assert refreshed.is_public is True
        assert refreshed.is_private is False
        assert refreshed.public_role == "CONTRIBUTOR"
        # Org assignment removed.
        assert await _count_org_rows(async_test_db, project.id) == 0

    @pytest.mark.asyncio
    async def test_standalone_public_role_flip(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True, name="Admin")
        project = await _make_project(
            async_test_db, admin, is_public=True, public_role="ANNOTATOR"
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"public_role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 200

        refreshed = await _get_project(async_test_db, project.id)
        assert refreshed.public_role == "CONTRIBUTOR"
        assert refreshed.is_public is True

    @pytest.mark.asyncio
    async def test_public_role_flip_on_non_public_400(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"public_role": "CONTRIBUTOR"},
            )
        assert resp.status_code == 400
        assert "public project" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_make_private_reassigns_owner_and_drops_orgs(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        new_owner = await _make_user(async_test_db, is_superadmin=False, name="New Owner")
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True, "owner_user_id": new_owner.id},
            )
        assert resp.status_code == 200

        refreshed = await _get_project(async_test_db, project.id)
        assert refreshed.is_private is True
        assert refreshed.is_public is False
        assert str(refreshed.created_by) == new_owner.id
        assert await _count_org_rows(async_test_db, project.id) == 0

    @pytest.mark.asyncio
    async def test_make_org_assigned_unknown_org_404(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()
        unknown = _uid()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": [unknown]},
            )
        assert resp.status_code == 404
        assert unknown in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_make_org_assigned_no_org_ids_400(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )
        assert resp.status_code == 400
        assert "organization_id" in resp.json()["detail"]


# ===========================================================================
# GET /{id}/completion-stats — get_project_completion_stats
# ===========================================================================


@pytest.mark.integration
class TestCompletionStats:
    @pytest.mark.asyncio
    async def test_completion_stats_counts(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        project = await _make_project(async_test_db, admin, org)
        # 3 tasks, 1 labeled.
        for i in range(3):
            async_test_db.add(
                Task(
                    id=_uid(),
                    project_id=project.id,
                    inner_id=i + 1,
                    data={"text": f"t{i}"},
                    created_by=admin.id,
                    is_labeled=(i == 0),
                )
            )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["completed"] == 1
        assert abs(body["completion_rate"] - (1 / 3 * 100)) < 0.01

    @pytest.mark.asyncio
    async def test_completion_stats_not_found_404(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Project not found"

    @pytest.mark.asyncio
    async def test_completion_stats_outsider_403(
        self, async_test_client, async_test_db
    ):
        admin, org = await _seed_admin_org(async_test_db)
        # An outsider contributor who belongs only to a different org.
        outsider = await _make_user(async_test_db, is_superadmin=False, name="Outsider")
        other_org = await _make_org(async_test_db, name="Outsider Completion Org")
        await _make_membership(async_test_db, outsider.id, other_org.id, "CONTRIBUTOR")
        project = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"
