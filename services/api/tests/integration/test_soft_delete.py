"""Soft delete (migration 093): non-superadmin delete hides a project from
EVERYONE while all data survives; superadmins list/restore/purge."""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import Organization, OrganizationMembership, OrganizationRole, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    ProjectShareLink,
    ProjectShareMember,
    Task,
)

# Reuse the participant-tier fixtures' shapes.
from tests.integration.test_participant_tier import (  # noqa: F401
    EXAM_CONFIG,
    _as_user,
    _attach,
    _org,
    _project,
    _share_member,
    _user,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_soft_delete_hides_everywhere_and_preserves_data(
    async_test_client, async_test_db
):
    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner, tasks=2)
    await _share_member(db, p, owner, member)
    task_id = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().first()
    db.add(Annotation(id=str(uuid.uuid4()), task_id=task_id, project_id=p.id,
                      completed_by=member.id, result=[{"v": 1}]))
    await db.commit()

    # Creator of a private project soft-deletes.
    with _as_user(owner):
        r = await async_test_client.delete(f"/api/projects/{p.id}")
        assert r.status_code == 200, r.text
        # ...and immediately loses sight of it (owner included!).
        assert (await async_test_client.get(f"/api/projects/{p.id}")).status_code == 404
        assert p.id not in {x["id"] for x in (await async_test_client.get("/api/projects/")).json()["items"]}
        # A second delete is a 404, not an error.
        assert (await async_test_client.delete(f"/api/projects/{p.id}")).status_code == 404

    with _as_user(member):
        assert (await async_test_client.get(f"/api/projects/{p.id}")).status_code == 404
        assert (await async_test_client.get(f"/api/projects/{p.id}/tasks")).status_code == 404
        assert p.id not in {x["id"] for x in (await async_test_client.get("/api/projects/")).json()["items"]}

    # Every row survives.
    proj = (await db.execute(select(Project).where(Project.id == p.id))).scalar_one()
    assert proj.deleted_at is not None and proj.deleted_by == owner.id
    assert (await db.execute(select(Task).where(Task.project_id == p.id))).scalars().all()
    assert (await db.execute(select(Annotation).where(Annotation.project_id == p.id))).scalars().all()
    assert (await db.execute(select(ProjectShareMember).where(ProjectShareMember.project_id == p.id))).scalars().all()


async def test_share_links_of_deleted_project_dead(async_test_client, async_test_db):
    from auth_module.user_service import get_password_hash

    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner)
    link = ProjectShareLink(id=str(uuid.uuid4()), token=uuid.uuid4().hex, project_id=p.id,
                            created_by=owner.id, password_hash=get_password_hash("abcdefgh"),
                            is_listed=True)
    db.add(link)
    await db.commit()
    with _as_user(owner):
        await async_test_client.delete(f"/api/projects/{p.id}")
    with _as_user(member):
        assert (await async_test_client.get(f"/api/shares/{link.token}")).status_code == 404
        r = await async_test_client.post(
            f"/api/shares/{link.token}/join", json={"password": "abcdefgh", "gdpr_consent": True}
        )
        assert r.status_code == 404
        assert p.id not in {
            x["project_id"]
            for x in (await async_test_client.get("/api/shares/discover", params={"scope": "all"})).json()
        }


async def test_superadmin_deleted_view_restore_and_purge(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p = await _project(db, owner, tasks=1)
    with _as_user(owner):
        await async_test_client.delete(f"/api/projects/{p.id}")

    with _as_user(admin):
        # Normal list: hidden even for superadmins...
        assert p.id not in {x["id"] for x in (await async_test_client.get("/api/projects/")).json()["items"]}
        # ...the deleted view shows it.
        r = await async_test_client.get("/api/projects/", params={"only_deleted": "true"})
        rows = {x["id"]: x for x in r.json()["items"]}
        assert p.id in rows and rows[p.id]["deleted_at"] is not None
        # Restore brings everything back.
        assert (await async_test_client.post(f"/api/projects/{p.id}/restore")).status_code == 200
    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{p.id}")
        assert r.status_code == 200 and r.json()["deleted_at"] is None
        assert (await async_test_client.get(f"/api/projects/{p.id}/tasks")).status_code == 200

    # Purge: superadmin only, requires a prior soft delete, rows really gone.
    with _as_user(owner):
        assert (await async_test_client.delete(f"/api/projects/{p.id}/purge")).status_code == 403
        assert (await async_test_client.post(f"/api/projects/{p.id}/restore")).status_code == 403
    with _as_user(admin):
        # The project is live again after the restore — purging it directly
        # is refused (409 not_deleted) until it is soft-deleted first.
        r = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert r.status_code == 409, r.text
        assert (await async_test_client.delete(f"/api/projects/{p.id}")).status_code == 200
        assert (await async_test_client.delete(f"/api/projects/{p.id}/purge")).status_code == 200
    assert (await db.execute(select(Project).where(Project.id == p.id))).scalar_one_or_none() is None
    assert not (await db.execute(select(Task).where(Task.project_id == p.id))).scalars().all()


async def test_delete_permissions(async_test_client, async_test_db):
    db = async_test_db
    creator, admin, contrib, outsider = [await _user(db) for _ in range(4)]
    org = await _org(db, (admin, OrganizationRole.ORG_ADMIN), (contrib, OrganizationRole.CONTRIBUTOR))
    org_project = await _project(db, creator, private=False)
    await _attach(db, org_project, org, admin)

    # Org project: creator (non-admin) and contributor may NOT delete...
    for u in (creator, contrib, outsider):
        with _as_user(u):
            assert (await async_test_client.delete(f"/api/projects/{org_project.id}")).status_code == 403
    # ...an org admin may (soft).
    with _as_user(admin):
        assert (await async_test_client.delete(f"/api/projects/{org_project.id}")).status_code == 200
    proj = (await db.execute(select(Project).where(Project.id == org_project.id))).scalar_one()
    assert proj.deleted_at is not None

    # bulk-delete enforces the same rule: creator of an ORG project is denied.
    org_project2 = await _project(db, creator, private=False)
    await _attach(db, org_project2, org, admin)
    with _as_user(creator):
        r = await async_test_client.post(
            "/api/projects/bulk-delete", json={"project_ids": [org_project2.id]}
        )
        assert r.status_code == 200 and r.json()["deleted"] == 0
        assert r.json()["failed"] == 1


async def test_deleted_project_rejects_writes_and_only_deleted_is_superadmin_only(
    async_test_client, async_test_db
):
    db = async_test_db
    owner = await _user(db)
    p = await _project(db, owner)
    with _as_user(owner):
        await async_test_client.delete(f"/api/projects/{p.id}")
        # Writes bounce off a deleted project with 404 (existence-hiding).
        r = await async_test_client.patch(f"/api/projects/{p.id}", json={"title": "Zombie"})
        assert r.status_code == 404, r.text
        # only_deleted is a superadmin-only lens; others just get nothing.
        r = await async_test_client.get("/api/projects/", params={"only_deleted": "true"})
        assert r.status_code == 200
        assert p.id not in {x["id"] for x in r.json()["items"]}


async def test_bulk_soft_delete_restore_purge(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p1 = await _project(db, owner, tasks=1)
    p2 = await _project(db, owner, tasks=1)
    with _as_user(owner):
        r = await async_test_client.post("/api/projects/bulk-delete", json={"project_ids": [p1.id, p2.id]})
        assert r.status_code == 200 and r.json()["deleted"] == 2
        # Non-superadmin cannot restore/purge.
        assert (await async_test_client.post("/api/projects/bulk-restore", json={"project_ids": [p1.id]})).status_code == 403
        assert (await async_test_client.post("/api/projects/bulk-purge", json={"project_ids": [p1.id]})).status_code == 403
    for pid in (p1.id, p2.id):
        assert (await db.execute(select(Project.deleted_at).where(Project.id == pid))).scalar_one() is not None
        assert (await db.execute(select(Task).where(Task.project_id == pid))).scalars().all()
    with _as_user(admin):
        assert (await async_test_client.post("/api/projects/bulk-restore", json={"project_ids": [p1.id]})).json()["restored"] == 1
        # Bulk-purge only touches soft-deleted rows: the restored p1 is skipped.
        r = (await async_test_client.post("/api/projects/bulk-purge", json={"project_ids": [p1.id, p2.id]})).json()
        assert r["purged"] == 1
        assert [f["reason"] for f in r["failed_projects"]] == ["Not soft-deleted"]
    assert (await db.execute(select(Project.deleted_at).where(Project.id == p1.id))).scalar_one() is None
    assert (await db.execute(select(Project).where(Project.id == p2.id))).scalar_one_or_none() is None


async def test_deleted_project_out_of_score_history_and_participant_map(
    async_test_client, async_test_db
):
    from routers.projects.helpers import get_participant_project_ids_async

    db = async_test_db
    owner, member = await _user(db), await _user(db)
    p = await _project(db, owner)
    await _share_member(db, p, owner, member)
    assert p.id in await get_participant_project_ids_async(db, member.id)
    with _as_user(owner):
        await async_test_client.delete(f"/api/projects/{p.id}")
    assert p.id not in await get_participant_project_ids_async(db, member.id)
