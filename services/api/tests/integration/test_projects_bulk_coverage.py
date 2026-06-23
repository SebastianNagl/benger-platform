"""Integration coverage for the project bulk-operations router.

Targets the uncovered arms of ``services/api/routers/projects/bulk.py``:

  * ``POST /api/projects/bulk-delete``    — creator/superadmin gate, not-found
    skip, permission-denied skip, the successful delete (project + members +
    orgs + tasks removed, notification fired), and per-project error isolation.
  * ``POST /api/projects/bulk-archive``   — edit-permission gate (creator /
    org-admin / contributor allowed, annotator / non-member skipped), the
    ``is_archived`` flip persisted, not-found skip, notification fired.
  * ``POST /api/projects/bulk-unarchive`` — the inverse flip + permission gate.

All three handlers were migrated to the ASYNC DB lane (``Depends(get_async_db)``
+ ``await db.execute(select(...))``), so these tests seed real ORM rows via
``async_test_db`` and drive the surface through ``async_test_client`` with
``require_user`` overridden per-test (``_as_user``). Persisted state is
re-queried via ``async_test_db`` (rows gone / ``is_archived`` flipped).

The notification side-effect dispatches to a sync ``SessionLocal()`` off the
event loop (``_notify_project_deleted_sync`` / ``_notify_project_archived_sync``);
with no Redis that path would stall, and the rows it writes land on a separate
connection invisible to the test transaction. We therefore patch those module
wrappers and assert the dispatch (recipient/org/project args) instead of
re-querying Notification rows — the same meaning, harness-safe.

The bulk-EXPORT endpoints (``/bulk-export``, ``/bulk-export-full``) live in the
import_export router, not here — they are covered in
``test_projects_import_export_coverage.py``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectMember, ProjectOrganization, Task


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


async def _make_user(db, *, is_superadmin=False, name="Bulk User"):
    u = User(
        id=_uid(),
        username=f"bk-{_uid()[:8]}",
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


async def _make_org(db, *, name="Bulk Org"):
    org = Organization(
        id=_uid(),
        name=name,
        slug=f"org-{_uid()[:8]}",
        display_name=name,
    )
    db.add(org)
    await db.flush()
    return org


async def _make_membership(db, *, user_id, org_id, role="ORG_ADMIN"):
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


async def _make_project(
    db,
    *,
    created_by,
    title="Bulk Project",
    is_archived=False,
    label_config='<View><Text name="text" value="$text"/></View>',
):
    p = Project(
        id=_uid(),
        title=title,
        description="bulk-ops fixture",
        created_by=created_by,
        is_archived=is_archived,
        label_config=label_config,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


async def _make_project_org(db, *, project_id, org_id, assigned_by):
    po = ProjectOrganization(
        id=_uid(),
        project_id=project_id,
        organization_id=org_id,
        assigned_by=assigned_by,
    )
    db.add(po)
    await db.flush()
    return po


async def _add_task(db, project, *, inner_id=1):
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "hello"},
        is_labeled=False,
    )
    db.add(task)
    await db.flush()
    return task


async def _get_project(db, pid):
    return (
        await db.execute(select(Project).where(Project.id == pid))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# bulk-delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkDelete:
    @pytest.mark.asyncio
    async def test_creator_deletes_project_and_children(
        self, async_test_client, async_test_db
    ):
        """A superadmin deletes their own project: the project, its members, its
        org links and its tasks are all removed and the count reflects exactly
        one deletion."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, created_by=admin.id)
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        await _add_task(async_test_db, project, inner_id=1)
        await _add_task(async_test_db, project, inner_id=2)
        async_test_db.add(
            ProjectMember(
                id=_uid(),
                project_id=project.id,
                user_id=admin.id,
                role="ORG_ADMIN",
            )
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 1
        assert body["failed"] == 0
        assert body["failed_projects"] == []

        # Project + all child rows gone.
        assert await _get_project(async_test_db, pid) is None
        assert (
            await async_test_db.execute(
                select(Task).where(Task.project_id == pid)
            )
        ).scalars().all() == []
        assert (
            await async_test_db.execute(
                select(ProjectMember).where(ProjectMember.project_id == pid)
            )
        ).scalars().all() == []
        assert (
            await async_test_db.execute(
                select(ProjectOrganization).where(
                    ProjectOrganization.project_id == pid
                )
            )
        ).scalars().all() == []

    @pytest.mark.asyncio
    async def test_missing_project_reported_as_failed(
        self, async_test_client, async_test_db
    ):
        """An unknown project id lands in failed_projects with a not-found
        reason and nothing is deleted."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        ghost = _uid()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": [ghost]}
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 0
        assert body["failed"] == 1
        assert body["failed_projects"][0]["id"] == ghost
        assert "not found" in body["failed_projects"][0]["reason"].lower()

    @pytest.mark.asyncio
    async def test_non_creator_non_superadmin_permission_denied(
        self, async_test_client, async_test_db
    ):
        """A user who is neither the creator nor a superadmin cannot delete
        another's project — it survives and is reported as a permission
        failure."""
        owner = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, created_by=owner.id)
        pid = project.id
        await async_test_db.commit()

        with _as_user(other), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 0
        assert body["failed"] == 1
        assert body["failed_projects"][0]["id"] == pid
        assert "permission" in body["failed_projects"][0]["reason"].lower()
        # Project untouched.
        assert await _get_project(async_test_db, pid) is not None

    @pytest.mark.asyncio
    async def test_mixed_batch_deletes_owned_skips_others(
        self, async_test_client, async_test_db
    ):
        """A batch of [own, foreign, missing] for a non-superadmin creator:
        only the owned project is deleted, the other two are failures."""
        contributor = await _make_user(async_test_db, is_superadmin=False)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        own = await _make_project(
            async_test_db, created_by=contributor.id, title="Own"
        )
        foreign = await _make_project(
            async_test_db, created_by=annotator.id, title="Foreign"
        )
        missing = _uid()
        await async_test_db.commit()

        with _as_user(contributor), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-delete",
                json={"project_ids": [own.id, foreign.id, missing]},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 1
        assert body["failed"] == 2

        assert await _get_project(async_test_db, own.id) is None
        assert await _get_project(async_test_db, foreign.id) is not None

    @pytest.mark.asyncio
    async def test_empty_project_ids_is_noop(
        self, async_test_client, async_test_db
    ):
        """No ids → nothing deleted, nothing failed, still 200."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": []}
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"deleted": 0, "failed": 0, "failed_projects": []}

    @pytest.mark.asyncio
    async def test_delete_notifies_org_members(
        self, async_test_client, async_test_db
    ):
        """Deleting an org-bound project fires the PROJECT_DELETED notification
        dispatch with the project's id, title, the deleting user, and the
        resolved org id. (The dispatch runs on a fresh sync session off-loop;
        we assert the call args rather than re-querying the cross-connection
        Notification rows.)"""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(
            async_test_db, created_by=admin.id, title="Notify Me"
        )
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_deleted_sync"
        ) as mock_notify:
            resp = await async_test_client.post(
                "/api/projects/bulk-delete", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] == 1

        # The deletion fired exactly one notification dispatch for this project,
        # attributed to the deleting admin, scoped to the bound org.
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["project_id"] == pid
        assert kwargs["project_title"] == "Notify Me"
        assert kwargs["deleted_by_user_id"] == admin.id
        assert kwargs["organization_id"] == org.id


# ---------------------------------------------------------------------------
# bulk-archive
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkArchive:
    @pytest.mark.asyncio
    async def test_creator_archives_and_persists_flag(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(async_test_db, created_by=admin.id)
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_archived_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-archive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1

        row = await _get_project(async_test_db, pid)
        await async_test_db.refresh(row)
        assert row.is_archived is True

    @pytest.mark.asyncio
    async def test_contributor_can_archive_org_project(
        self, async_test_client, async_test_db
    ):
        """A CONTRIBUTOR org member passes check_user_can_edit_project_async and
        may archive a project owned by someone else in the org."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(
            async_test_db, user_id=contributor.id, org_id=org.id, role="CONTRIBUTOR"
        )
        project = await _make_project(async_test_db, created_by=admin.id)
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(contributor), patch(
            "routers.projects.bulk._notify_project_archived_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-archive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1
        row = await _get_project(async_test_db, pid)
        await async_test_db.refresh(row)
        assert row.is_archived is True

    @pytest.mark.asyncio
    async def test_annotator_cannot_archive_is_skipped(
        self, async_test_client, async_test_db
    ):
        """An ANNOTATOR fails the edit gate; the project stays unarchived and the
        count is zero (the loop ``continue``s past it)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(
            async_test_db, user_id=annotator.id, org_id=org.id, role="ANNOTATOR"
        )
        project = await _make_project(async_test_db, created_by=admin.id)
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(annotator), patch(
            "routers.projects.bulk._notify_project_archived_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-archive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 0
        row = await _get_project(async_test_db, pid)
        await async_test_db.refresh(row)
        assert row.is_archived is False

    @pytest.mark.asyncio
    async def test_missing_project_skipped(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_archived_sync"
        ):
            resp = await async_test_client.post(
                "/api/projects/bulk-archive", json={"project_ids": [_uid()]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 0

    @pytest.mark.asyncio
    async def test_archive_notifies_org_members(
        self, async_test_client, async_test_db
    ):
        """Archiving an org-bound project fires the PROJECT_ARCHIVED dispatch
        with the archiving user + resolved org id (assert the call args; the
        cross-connection Notification rows aren't visible to the test txn)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(
            async_test_db, created_by=admin.id, title="Arch Notify"
        )
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.bulk._notify_project_archived_sync"
        ) as mock_notify:
            resp = await async_test_client.post(
                "/api/projects/bulk-archive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1

        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["project_id"] == pid
        assert kwargs["archived_by_user_id"] == admin.id
        assert kwargs["organization_id"] == org.id


# ---------------------------------------------------------------------------
# bulk-unarchive
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkUnarchive:
    @pytest.mark.asyncio
    async def test_creator_unarchives_and_persists_flag(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project = await _make_project(
            async_test_db, created_by=admin.id, is_archived=True
        )
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/projects/bulk-unarchive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 1

        row = await _get_project(async_test_db, pid)
        await async_test_db.refresh(row)
        assert row.is_archived is False

    @pytest.mark.asyncio
    async def test_annotator_cannot_unarchive_is_skipped(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(
            async_test_db, user_id=annotator.id, org_id=org.id, role="ANNOTATOR"
        )
        project = await _make_project(
            async_test_db, created_by=admin.id, is_archived=True
        )
        await _make_project_org(
            async_test_db, project_id=project.id, org_id=org.id, assigned_by=admin.id
        )
        pid = project.id
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.post(
                "/api/projects/bulk-unarchive", json={"project_ids": [pid]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 0
        row = await _get_project(async_test_db, pid)
        await async_test_db.refresh(row)
        assert row.is_archived is True

    @pytest.mark.asyncio
    async def test_missing_project_skipped(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/projects/bulk-unarchive", json={"project_ids": [_uid()]}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 0
