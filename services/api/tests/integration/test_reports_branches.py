"""
Integration tests for the project-reports router (routers/reports.py).

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
these tests seed real rows via ``async_test_db`` and drive the HTTP surface
through ``async_test_client``. ``require_user`` is overridden per-test via the
``_as_user`` context manager to return an auth User matching a seeded DB user
(the sync auth dependency can't see the async test transaction).

Targets the CRUD / metadata / list / get / delete report-record branches that
hit only Postgres:
  - GET    /api/projects/{project_id}/report          (get + superadmin auto-create)
  - POST   /api/projects/{project_id}/report          (update content)
  - PUT    /api/projects/{project_id}/report/publish
  - PUT    /api/projects/{project_id}/report/unpublish
  - GET    /api/reports                               (list published)
  - GET    /api/reports/{report_id}/data              (report data)

These deliberately avoid the object-storage (MinIO) byte-streaming
export/import endpoints, which live in other routers and require a live
storage backend. Every endpoint exercised here reads/writes only Postgres.

The report-aggregation helpers (``can_publish_report``,
``create_or_update_report_from_existing_data``, the statistics/charts bundle)
are sync-only in /shared; the handlers bridge them onto a sync ``Session``
bound to the async connection via ``await db.run_sync(...)``, so they run
inside the same (test) transaction and see the seeded rows directly — no
mocking of the bridge is needed.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task
from report_models import ProjectReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


async def _make_user(db, *, is_superadmin=False, username_prefix="rpt") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Report User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Org") -> Organization:
    org = Organization(
        id=_uid(),
        name=name,
        display_name=name,
        slug=f"{name.lower().replace(' ', '-')}-{_uid()[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _add_membership(db, user: User, org: Organization, *, role="CONTRIBUTOR"):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


def _make_content() -> dict:
    """A minimal-but-valid report content blob matching the ReportContent
    Pydantic model (requires `sections` + `metadata` dicts)."""
    return {
        "sections": {
            "project_info": {
                "title": "Test Report",
                "description": "A report under test",
                "status": "completed",
                "editable": True,
                "visible": True,
            }
        },
        "metadata": {"sections_completed": ["project_info"], "can_publish": False},
    }


async def _create_project(
    db,
    creator: User,
    *,
    title: str = "Report Project",
    org: Organization = None,
    assigned_by: User = None,
    with_task: bool = False,
) -> Project:
    """Create a project, optionally linked to an org and seeded with one task."""
    project_id = _uid()
    project = Project(
        id=project_id,
        title=title,
        description="Integration test project for reports",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()

    if org is not None:
        po = ProjectOrganization(
            id=_uid(),
            project_id=project_id,
            organization_id=org.id,
            assigned_by=(assigned_by or creator).id,
        )
        db.add(po)
        await db.flush()

    if with_task:
        task = Task(
            id=_uid(),
            project_id=project_id,
            data={"text": "sample"},
            created_by=creator.id,
            inner_id=1,
        )
        db.add(task)
        await db.flush()

    return project


async def _create_report(
    db,
    project: Project,
    creator: User,
    *,
    is_published: bool = False,
    published_by: User = None,
    content: dict = None,
) -> ProjectReport:
    """Insert a ProjectReport row directly."""
    report = ProjectReport(
        id=_uid(),
        project_id=project.id,
        content=content or _make_content(),
        is_published=is_published,
        published_at=datetime.utcnow() if is_published else None,
        published_by=(published_by.id if (is_published and published_by) else None),
        created_by=creator.id,
    )
    db.add(report)
    await db.flush()
    return report


# ===========================================================================
# GET /api/projects/{project_id}/report
# ===========================================================================

@pytest.mark.asyncio
async def test_get_report_project_not_found(async_test_client, async_test_db):
    """GET report for a non-existent project -> 404 (project branch)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/projects/does-not-exist/report")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_report_missing_for_non_superadmin_404(async_test_client, async_test_db):
    """Project exists but no report; a non-superadmin cannot auto-create ->
    404 'Report not found' (the non-superadmin branch)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)
    project = await _create_project(async_test_db, admin, org=org)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/projects/{project.id}/report")
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()

    # No report row was created.
    from sqlalchemy import select

    row = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project.id)
        )
    ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_get_report_superadmin_autocreates(async_test_client, async_test_db):
    """Project exists, no report; superadmin GET auto-creates one and persists
    it (the create_or_update_report_from_existing_data branch).

    The sync autocreate + can_publish bridges run via ``db.run_sync`` on a sync
    Session bound to this async session's connection, so they execute inside the
    test transaction and see the seeded project — no mocking needed.
    """
    from sqlalchemy import select

    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org, with_task=True)
    await async_test_db.commit()

    # The target project has no report → autocreate branch.
    existing = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project.id)
        )
    ).scalar_one_or_none()
    assert existing is None

    with _as_user(admin):
        resp = await async_test_client.get(f"/api/projects/{project.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project.id
    assert body["project_title"] == project.title
    assert body["is_published"] is False
    assert "can_publish" in body
    assert "can_publish_reason" in body

    # A report row now exists in the DB (created by the run_sync bridge inside
    # this transaction).
    created = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project.id)
        )
    ).scalar_one_or_none()
    assert created is not None
    assert created.created_by == admin.id
    assert created.is_published is False


@pytest.mark.asyncio
async def test_get_report_unpublished_forbidden_for_non_superadmin(
    async_test_client, async_test_db
):
    """An existing unpublished report cannot be viewed by a non-superadmin ->
    403 'not published yet'."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)
    project = await _create_project(async_test_db, admin, org=org)
    await _create_report(async_test_db, project, admin, is_published=False)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/projects/{project.id}/report")
    assert resp.status_code == 403
    assert "not published" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_report_published_org_member_allowed(async_test_client, async_test_db):
    """A published report is viewable by a member of an org that owns the
    project (the published + org-access branch)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)
    project = await _create_project(async_test_db, admin, org=org)
    report = await _create_report(
        async_test_db, project, admin, is_published=True, published_by=admin
    )
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/projects/{project.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == report.id
    assert body["is_published"] is True


@pytest.mark.asyncio
async def test_get_report_published_no_org_overlap_forbidden(async_test_client, async_test_db):
    """A published report whose project belongs to NO org the user is in ->
    403 via check_report_access (no overlapping organizations)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)

    # Org A owns the project; contributor is in org B only.
    org_a = await _make_org(async_test_db, name="Org A")
    org_b = await _make_org(async_test_db, name="Org B")
    await _add_membership(async_test_db, contributor, org_b)

    project = await _create_project(async_test_db, admin, org=org_a)
    await _create_report(async_test_db, project, admin, is_published=True, published_by=admin)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/projects/{project.id}/report")
    assert resp.status_code == 403
    assert "permission" in resp.json()["detail"].lower()


# ===========================================================================
# POST /api/projects/{project_id}/report  (update content)
# ===========================================================================

@pytest.mark.asyncio
async def test_update_report_forbidden_for_non_superadmin(async_test_client, async_test_db):
    """Only superadmins may edit -> 403 for a contributor."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await _create_report(async_test_db, project, admin)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"content": _make_content()},
        )
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_report_project_not_found(async_test_client, async_test_db):
    """Superadmin updating a report for a missing project -> 404."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.post(
            "/api/projects/nope/report",
            json={"content": _make_content()},
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_report_report_not_found(async_test_client, async_test_db):
    """Superadmin, project exists but no report row -> 404 'Report not found'."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"content": _make_content()},
        )
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_report_persists_new_content(async_test_client, async_test_db):
    """Successful update writes new content to the DB row."""
    from sqlalchemy import select

    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    report = await _create_report(async_test_db, project, admin)
    report_id = report.id
    await async_test_db.commit()

    new_content = _make_content()
    new_content["sections"]["project_info"]["title"] = "Edited Title"
    new_content["metadata"]["edited"] = True

    with _as_user(admin):
        resp = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"content": new_content},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"]["sections"]["project_info"]["title"] == "Edited Title"

    # Persisted change is visible on a fresh read of the row.
    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.id == report_id)
        )
    ).scalar_one_or_none()
    assert refreshed.content["sections"]["project_info"]["title"] == "Edited Title"
    assert refreshed.content["metadata"]["edited"] is True
    assert refreshed.updated_at is not None


@pytest.mark.asyncio
async def test_update_report_invalid_body_422(async_test_client, async_test_db):
    """Missing required `content` field -> 422 (request validation branch)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await _create_report(async_test_db, project, admin)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"not_content": {}},
        )
    assert resp.status_code == 422


# ===========================================================================
# PUT /api/projects/{project_id}/report/publish
# ===========================================================================

@pytest.mark.asyncio
async def test_publish_forbidden_for_non_superadmin(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await _create_report(async_test_db, project, admin)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_project_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put("/api/projects/missing/report/publish")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_publish_report_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_blocked_when_requirements_unmet_400(async_test_client, async_test_db):
    """Report with no tasks/generations/evaluations cannot be published ->
    400 'Cannot publish report'. The DB row stays unpublished."""
    from sqlalchemy import select

    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org, with_task=False)
    report = await _create_report(async_test_db, project, admin, is_published=False)
    report_id = report.id
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert resp.status_code == 400
    assert "cannot publish report" in resp.json()["detail"].lower()

    # Persisted state unchanged.
    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.id == report_id)
        )
    ).scalar_one_or_none()
    assert refreshed.is_published is False
    assert refreshed.published_at is None


# ===========================================================================
# PUT /api/projects/{project_id}/report/unpublish
# ===========================================================================

@pytest.mark.asyncio
async def test_unpublish_forbidden_for_non_superadmin(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await _create_report(async_test_db, project, admin, is_published=True, published_by=admin)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/unpublish")
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unpublish_project_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.put("/api/projects/missing/report/unpublish")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unpublish_report_not_found(async_test_client, async_test_db):
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/unpublish")
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unpublish_clears_publication_state(async_test_client, async_test_db):
    """Unpublishing a published report flips is_published False and clears
    published_at / published_by in the persisted row."""
    from sqlalchemy import select

    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org)
    report = await _create_report(
        async_test_db, project, admin, is_published=True, published_by=admin
    )
    report_id = report.id
    await async_test_db.commit()
    assert report.is_published is True

    with _as_user(admin):
        resp = await async_test_client.put(f"/api/projects/{project.id}/report/unpublish")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is False
    assert body["published_at"] is None
    assert body["published_by"] is None

    async_test_db.expire_all()
    refreshed = (
        await async_test_db.execute(
            select(ProjectReport).where(ProjectReport.id == report_id)
        )
    ).scalar_one_or_none()
    assert refreshed.is_published is False
    assert refreshed.published_at is None
    assert refreshed.published_by is None


# ===========================================================================
# GET /api/reports  (list published)
# ===========================================================================

@pytest.mark.asyncio
async def test_list_published_reports_superadmin_sees_all(async_test_client, async_test_db):
    """Superadmin sees published reports; unpublished ones are excluded."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    pub_project = await _create_project(async_test_db, admin, org=org, title="Published P")
    pub_report = await _create_report(
        async_test_db, pub_project, admin, is_published=True, published_by=admin
    )
    draft_project = await _create_project(async_test_db, admin, org=org, title="Draft P")
    await _create_report(async_test_db, draft_project, admin, is_published=False)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get("/api/reports")
    assert resp.status_code == 200
    items = resp.json()
    ids = {item["id"] for item in items}
    assert pub_report.id in ids
    # The draft report's project must not appear.
    draft_project_ids = {item["project_id"] for item in items}
    assert draft_project.id not in draft_project_ids

    # Returned item carries the org membership of the published project.
    pub_item = next(i for i in items if i["id"] == pub_report.id)
    assert pub_item["project_title"] == "Published P"
    org_ids = {o["id"] for o in pub_item["organizations"]}
    assert org.id in org_ids


@pytest.mark.asyncio
async def test_list_published_reports_org_member_filtered(async_test_client, async_test_db):
    """A non-superadmin org member sees published reports of their org's
    projects, and not published reports of unrelated orgs."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)

    # Published report owned by org (contributor is a member here).
    own_project = await _create_project(async_test_db, admin, org=org, title="Own Org Report")
    own_report = await _create_report(
        async_test_db, own_project, admin, is_published=True, published_by=admin
    )

    # Published report owned by an unrelated org the contributor is NOT in.
    other_org = await _make_org(async_test_db, name="Unrelated Org")
    other_project = await _create_project(
        async_test_db, admin, org=other_org, title="Other Org Report", assigned_by=admin
    )
    other_report = await _create_report(
        async_test_db, other_project, admin, is_published=True, published_by=admin
    )
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get("/api/reports")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert own_report.id in ids
    assert other_report.id not in ids


@pytest.mark.asyncio
async def test_list_published_reports_empty(async_test_client, async_test_db):
    """No published reports at all -> empty list (not an error)."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/reports")
    assert resp.status_code == 200
    assert resp.json() == []


# ===========================================================================
# GET /api/reports/{report_id}/data
# ===========================================================================

@pytest.mark.asyncio
async def test_get_report_data_not_found(async_test_client, async_test_db):
    """Unknown report id -> 404."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    await async_test_db.commit()
    with _as_user(admin):
        resp = await async_test_client.get("/api/reports/no-such-report/data")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_report_data_unpublished_forbidden_for_non_superadmin(
    async_test_client, async_test_db
):
    """Draft report data is forbidden to non-superadmins -> 403."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)
    project = await _create_project(async_test_db, admin, org=org)
    report = await _create_report(async_test_db, project, admin, is_published=False)
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/reports/{report.id}/data")
    assert resp.status_code == 403
    assert "not published" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_report_data_superadmin_draft_ok(async_test_client, async_test_db):
    """Superadmin can fetch data for a draft report; response carries the
    statistics / participants / models / evaluation_charts envelope."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    org = await _make_org(async_test_db)
    project = await _create_project(async_test_db, admin, org=org, with_task=True)
    report = await _create_report(async_test_db, project, admin, is_published=False)
    await async_test_db.commit()

    with _as_user(admin):
        resp = await async_test_client.get(f"/api/reports/{report.id}/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["id"] == report.id
    assert "statistics" in body
    assert body["statistics"]["task_count"] == 1
    assert "participants" in body
    assert "models" in body
    assert "evaluation_charts" in body


@pytest.mark.asyncio
async def test_get_report_data_published_org_member_allowed(async_test_client, async_test_db):
    """A published report's data is viewable by a member of an owning org."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    contributor = await _make_user(async_test_db)
    org = await _make_org(async_test_db)
    await _add_membership(async_test_db, contributor, org)
    project = await _create_project(async_test_db, admin, org=org, with_task=True)
    report = await _create_report(
        async_test_db, project, admin, is_published=True, published_by=admin
    )
    await async_test_db.commit()

    with _as_user(contributor):
        resp = await async_test_client.get(f"/api/reports/{report.id}/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["id"] == report.id
    assert body["report"]["is_published"] is True


# ===========================================================================
# Auth gate
# ===========================================================================

@pytest.mark.asyncio
async def test_reports_endpoints_require_auth(async_test_client):
    """No credentials -> 401 on a representative endpoint (require_user gate)."""
    resp = await async_test_client.get("/api/reports")
    assert resp.status_code == 401
