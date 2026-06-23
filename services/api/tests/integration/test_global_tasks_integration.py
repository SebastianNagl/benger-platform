"""
Integration tests for global tasks access control.

Verifies that get_user_accessible_projects() correctly scopes data
based on organization membership and project membership — the SQL
logic (subquery + JOIN + set union) that mock tests cannot cover.

The global tasks router (/api/data) was migrated to the async DB lane, so
these tests seed rows via ``async_test_db`` and drive the HTTP surface through
``async_test_client``. ``require_user`` is overridden per-test to return an
auth User matching the seeded actor (the sync auth dependency can't see the
async test transaction).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectMember, ProjectOrganization, Task


def _uid():
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


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"gt-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Global Tasks User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, name, creator_id):
    org = Organization(
        id=_uid(),
        name=f"{name}-{_uid()[:6]}",
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:6]}",
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_project_in_org(db, org, creator_id, title="Test Project", num_tasks=2):
    project = Project(
        id=_uid(),
        title=title,
        created_by=creator_id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()

    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=creator_id,
    )
    db.add(po)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task {i}"},
            inner_id=i + 1,
            created_by=creator_id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    return project, tasks


@pytest.mark.integration
class TestGlobalTasksAccessControl:
    """Verify org-scoped and member-scoped project visibility via /api/data/."""

    @pytest.mark.asyncio
    async def test_regular_user_sees_only_own_org_projects(
        self, async_test_client, async_test_db
    ):
        """User in org A should not see projects from org B."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)

        org_a = await _make_org(async_test_db, "Org A", admin.id)
        org_b = await _make_org(async_test_db, "Org B", admin.id)

        # Contributor is member of org A only.
        async_test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=contributor.id,
                organization_id=org_a.id,
                role="CONTRIBUTOR",
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        )
        await async_test_db.flush()

        proj_a, _ = await _make_project_in_org(async_test_db, org_a, admin.id, "Org A Project")
        proj_b, _ = await _make_project_in_org(async_test_db, org_b, admin.id, "Org B Project")
        await async_test_db.commit()

        with _as_user(contributor):
            resp = await async_test_client.get(
                "/api/data/",
                headers={"X-Organization-Context": org_a.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        task_project_ids = {t["project_id"] for t in data.get("items", [])}

        assert proj_a.id in task_project_ids
        # Key assertion: org B project tasks must NOT appear.
        for task in data.get("items", []):
            assert task["project_id"] != proj_b.id

    @pytest.mark.asyncio
    async def test_project_member_sees_project_without_org_membership(
        self, async_test_client, async_test_db
    ):
        """User who is a ProjectMember but not in the project's org should see it."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)

        other_org = await _make_org(async_test_db, "Other Org", admin.id)
        proj, tasks = await _make_project_in_org(
            async_test_db, other_org, admin.id, "Member Project"
        )

        async_test_db.add(
            ProjectMember(
                id=_uid(),
                project_id=proj.id,
                user_id=annotator.id,
                role="ANNOTATOR",
            )
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get("/api/data/")
        assert resp.status_code == 200
        data = resp.json()

        visible_project_ids = {t["project_id"] for t in data.get("items", [])}
        assert proj.id in visible_project_ids

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_projects(
        self, async_test_client, async_test_db
    ):
        """Superadmin should see projects from all orgs."""
        admin = await _make_user(async_test_db, is_superadmin=True)

        org_x = await _make_org(async_test_db, "Org X", admin.id)
        org_y = await _make_org(async_test_db, "Org Y", admin.id)
        proj_x, _ = await _make_project_in_org(async_test_db, org_x, admin.id, "X Project")
        proj_y, _ = await _make_project_in_org(async_test_db, org_y, admin.id, "Y Project")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/data/")
        assert resp.status_code == 200
        data = resp.json()

        visible_project_ids = {t["project_id"] for t in data.get("items", [])}
        assert proj_x.id in visible_project_ids
        assert proj_y.id in visible_project_ids

    @pytest.mark.asyncio
    async def test_user_without_any_access_sees_no_tasks(
        self, async_test_client, async_test_db
    ):
        """User with no org membership and no project membership gets empty list."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        outsider = await _make_user(async_test_db, is_superadmin=False)

        isolated_org = await _make_org(async_test_db, "Isolated Org", admin.id)
        proj, _ = await _make_project_in_org(
            async_test_db, isolated_org, admin.id, "Isolated Project"
        )
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get("/api/data/")
        assert resp.status_code == 200
        data = resp.json()

        # Should not see tasks from isolated org's project.
        for task in data.get("items", []):
            assert task["project_id"] != proj.id

    @pytest.mark.asyncio
    async def test_deactivated_membership_loses_org_visibility(
        self, async_test_client, async_test_db
    ):
        """A deactivated org membership must not grant continued data access."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)

        org = await _make_org(async_test_db, "Deactivation Org", admin.id)

        membership = OrganizationMembership(
            id=_uid(),
            user_id=contributor.id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
        async_test_db.add(membership)
        proj, _ = await _make_project_in_org(
            async_test_db, org, admin.id, "Deactivation Project"
        )
        await async_test_db.commit()

        # While active: the org's project tasks are visible.
        with _as_user(contributor):
            resp_active = await async_test_client.get(
                "/api/data/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp_active.status_code == 200
        active_ids = {t["project_id"] for t in resp_active.json().get("items", [])}
        assert proj.id in active_ids

        # Deactivate the membership.
        membership.is_active = False
        await async_test_db.commit()

        # After deactivation: the org's project tasks must disappear.
        with _as_user(contributor):
            resp_inactive = await async_test_client.get(
                "/api/data/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp_inactive.status_code == 200
        inactive_ids = {t["project_id"] for t in resp_inactive.json().get("items", [])}
        assert proj.id not in inactive_ids
