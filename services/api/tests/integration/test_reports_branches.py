"""
Integration tests for the project-reports router (routers/reports.py).

Targets the uncovered CRUD / metadata / list / get / delete report-record
branches that hit only Postgres:
  - GET    /api/projects/{project_id}/report          (get + superadmin auto-create)
  - POST   /api/projects/{project_id}/report          (update content)
  - PUT    /api/projects/{project_id}/report/publish
  - PUT    /api/projects/{project_id}/report/unpublish
  - GET    /api/reports                               (list published)
  - GET    /api/reports/{report_id}/data              (report data)

These deliberately avoid the object-storage (MinIO) byte-streaming
export/import endpoints, which live in other routers and require a live
storage backend. Every endpoint exercised here reads/writes only Postgres.

Each test runs against the real test PostgreSQL via the shared `test_db`
fixture (per-test SAVEPOINT rollback isolation). Assertions check both the
HTTP response and the persisted DB state.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task
from report_models import ProjectReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


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


def _create_project(
    test_db: Session,
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
    test_db.add(project)
    test_db.flush()

    if org is not None:
        po = ProjectOrganization(
            id=_uid(),
            project_id=project_id,
            organization_id=org.id,
            assigned_by=(assigned_by or creator).id,
        )
        test_db.add(po)
        test_db.flush()

    if with_task:
        task = Task(
            id=_uid(),
            project_id=project_id,
            data={"text": "sample"},
            created_by=creator.id,
            inner_id=1,
        )
        test_db.add(task)
        test_db.flush()

    test_db.commit()
    return project


def _create_report(
    test_db: Session,
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
    test_db.add(report)
    test_db.commit()
    test_db.refresh(report)
    return report


# ===========================================================================
# GET /api/projects/{project_id}/report
# ===========================================================================

def test_get_report_project_not_found(client, test_users, auth_headers):
    """GET report for a non-existent project -> 404 (project branch)."""
    resp = client.get(
        "/api/projects/does-not-exist/report", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_report_missing_for_non_superadmin_404(
    client, test_db, test_users, auth_headers, test_org
):
    """Project exists but no report; a non-superadmin cannot auto-create ->
    404 'Report not found' (the non-superadmin branch)."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)

    resp = client.get(
        f"/api/projects/{project.id}/report", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()

    # No report row was created.
    assert (
        test_db.query(ProjectReport)
        .filter(ProjectReport.project_id == project.id)
        .first()
        is None
    )


def test_get_report_superadmin_autocreates(
    client, test_db, test_users, auth_headers, test_org
):
    """Project exists, no report; superadmin GET auto-creates one and persists
    it (the create_or_update_report_from_existing_data branch)."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org, with_task=True)

    assert (
        test_db.query(ProjectReport)
        .filter(ProjectReport.project_id == project.id)
        .first()
        is None
    )

    resp = client.get(
        f"/api/projects/{project.id}/report", headers=auth_headers["admin"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project.id
    assert body["project_title"] == project.title
    assert body["is_published"] is False
    assert "can_publish" in body
    assert "can_publish_reason" in body

    # A report row now exists in the DB.
    created = (
        test_db.query(ProjectReport)
        .filter(ProjectReport.project_id == project.id)
        .first()
    )
    assert created is not None
    assert created.created_by == admin.id
    assert created.is_published is False


def test_get_report_unpublished_forbidden_for_non_superadmin(
    client, test_db, test_users, auth_headers, test_org
):
    """An existing unpublished report cannot be viewed by a non-superadmin ->
    403 'not published yet'."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    _create_report(test_db, project, admin, is_published=False)

    resp = client.get(
        f"/api/projects/{project.id}/report", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 403
    assert "not published" in resp.json()["detail"].lower()


def test_get_report_published_org_member_allowed(
    client, test_db, test_users, auth_headers, test_org
):
    """A published report is viewable by a member of an org that owns the
    project (the published + org-access branch)."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    report = _create_report(
        test_db, project, admin, is_published=True, published_by=admin
    )

    # contributor is a member of test_org, which owns the project.
    resp = client.get(
        f"/api/projects/{project.id}/report", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == report.id
    assert body["is_published"] is True


def test_get_report_published_no_org_overlap_forbidden(
    client, test_db, test_users, auth_headers
):
    """A published report whose project belongs to NO org the user is in ->
    403 via check_report_access (no overlapping organizations)."""
    admin = test_users[0]
    contributor = test_users[1]

    # Org A owns the project; contributor is in org B only.
    org_a = Organization(
        id=_uid(),
        name="Org A",
        display_name="Org A",
        slug=f"org-a-{_uid()[:8]}",
        created_at=datetime.utcnow(),
    )
    org_b = Organization(
        id=_uid(),
        name="Org B",
        display_name="Org B",
        slug=f"org-b-{_uid()[:8]}",
        created_at=datetime.utcnow(),
    )
    test_db.add_all([org_a, org_b])
    test_db.flush()
    test_db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=contributor.id,
            organization_id=org_b.id,
            role="CONTRIBUTOR",
            is_active=True,
            joined_at=datetime.utcnow(),
        )
    )
    test_db.commit()

    project = _create_project(test_db, admin, org=org_a)
    _create_report(test_db, project, admin, is_published=True, published_by=admin)

    resp = client.get(
        f"/api/projects/{project.id}/report", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 403
    assert "permission" in resp.json()["detail"].lower()


# ===========================================================================
# POST /api/projects/{project_id}/report  (update content)
# ===========================================================================

def test_update_report_forbidden_for_non_superadmin(
    client, test_db, test_users, auth_headers, test_org
):
    """Only superadmins may edit -> 403 for a contributor."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    _create_report(test_db, project, admin)

    resp = client.post(
        f"/api/projects/{project.id}/report",
        headers=auth_headers["contributor"],
        json={"content": _make_content()},
    )
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


def test_update_report_project_not_found(client, test_users, auth_headers):
    """Superadmin updating a report for a missing project -> 404."""
    resp = client.post(
        "/api/projects/nope/report",
        headers=auth_headers["admin"],
        json={"content": _make_content()},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_update_report_report_not_found(
    client, test_db, test_users, auth_headers, test_org
):
    """Superadmin, project exists but no report row -> 404 'Report not found'."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)

    resp = client.post(
        f"/api/projects/{project.id}/report",
        headers=auth_headers["admin"],
        json={"content": _make_content()},
    )
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


def test_update_report_persists_new_content(
    client, test_db, test_users, auth_headers, test_org
):
    """Successful update writes new content to the DB row."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    report = _create_report(test_db, project, admin)

    new_content = _make_content()
    new_content["sections"]["project_info"]["title"] = "Edited Title"
    new_content["metadata"]["edited"] = True

    resp = client.post(
        f"/api/projects/{project.id}/report",
        headers=auth_headers["admin"],
        json={"content": new_content},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"]["sections"]["project_info"]["title"] == "Edited Title"

    # Persisted change is visible on a fresh read of the row.
    test_db.expire_all()
    refreshed = (
        test_db.query(ProjectReport)
        .filter(ProjectReport.id == report.id)
        .first()
    )
    assert refreshed.content["sections"]["project_info"]["title"] == "Edited Title"
    assert refreshed.content["metadata"]["edited"] is True
    assert refreshed.updated_at is not None


def test_update_report_invalid_body_422(
    client, test_db, test_users, auth_headers, test_org
):
    """Missing required `content` field -> 422 (request validation branch)."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    _create_report(test_db, project, admin)

    resp = client.post(
        f"/api/projects/{project.id}/report",
        headers=auth_headers["admin"],
        json={"not_content": {}},
    )
    assert resp.status_code == 422


# ===========================================================================
# PUT /api/projects/{project_id}/report/publish
# ===========================================================================

def test_publish_forbidden_for_non_superadmin(
    client, test_db, test_users, auth_headers, test_org
):
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    _create_report(test_db, project, admin)

    resp = client.put(
        f"/api/projects/{project.id}/report/publish",
        headers=auth_headers["contributor"],
    )
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


def test_publish_project_not_found(client, test_users, auth_headers):
    resp = client.put(
        "/api/projects/missing/report/publish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404


def test_publish_report_not_found(
    client, test_db, test_users, auth_headers, test_org
):
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)

    resp = client.put(
        f"/api/projects/{project.id}/report/publish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


def test_publish_blocked_when_requirements_unmet_400(
    client, test_db, test_users, auth_headers, test_org
):
    """Report with no tasks/generations/evaluations cannot be published ->
    400 'Cannot publish report'. The DB row stays unpublished."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org, with_task=False)
    report = _create_report(test_db, project, admin, is_published=False)

    resp = client.put(
        f"/api/projects/{project.id}/report/publish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 400
    assert "cannot publish report" in resp.json()["detail"].lower()

    # Persisted state unchanged.
    test_db.expire_all()
    refreshed = (
        test_db.query(ProjectReport).filter(ProjectReport.id == report.id).first()
    )
    assert refreshed.is_published is False
    assert refreshed.published_at is None


# ===========================================================================
# PUT /api/projects/{project_id}/report/unpublish
# ===========================================================================

def test_unpublish_forbidden_for_non_superadmin(
    client, test_db, test_users, auth_headers, test_org
):
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    _create_report(test_db, project, admin, is_published=True, published_by=admin)

    resp = client.put(
        f"/api/projects/{project.id}/report/unpublish",
        headers=auth_headers["contributor"],
    )
    assert resp.status_code == 403
    assert "superadmin" in resp.json()["detail"].lower()


def test_unpublish_project_not_found(client, test_users, auth_headers):
    resp = client.put(
        "/api/projects/missing/report/unpublish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404


def test_unpublish_report_not_found(
    client, test_db, test_users, auth_headers, test_org
):
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)

    resp = client.put(
        f"/api/projects/{project.id}/report/unpublish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404
    assert "report not found" in resp.json()["detail"].lower()


def test_unpublish_clears_publication_state(
    client, test_db, test_users, auth_headers, test_org
):
    """Unpublishing a published report flips is_published False and clears
    published_at / published_by in the persisted row."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    report = _create_report(
        test_db, project, admin, is_published=True, published_by=admin
    )
    assert report.is_published is True

    resp = client.put(
        f"/api/projects/{project.id}/report/unpublish", headers=auth_headers["admin"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is False
    assert body["published_at"] is None
    assert body["published_by"] is None

    test_db.expire_all()
    refreshed = (
        test_db.query(ProjectReport).filter(ProjectReport.id == report.id).first()
    )
    assert refreshed.is_published is False
    assert refreshed.published_at is None
    assert refreshed.published_by is None


# ===========================================================================
# GET /api/reports  (list published)
# ===========================================================================

def test_list_published_reports_superadmin_sees_all(
    client, test_db, test_users, auth_headers, test_org
):
    """Superadmin sees published reports; unpublished ones are excluded."""
    admin = test_users[0]
    pub_project = _create_project(test_db, admin, org=test_org, title="Published P")
    pub_report = _create_report(
        test_db, pub_project, admin, is_published=True, published_by=admin
    )
    draft_project = _create_project(test_db, admin, org=test_org, title="Draft P")
    _create_report(test_db, draft_project, admin, is_published=False)

    resp = client.get("/api/reports", headers=auth_headers["admin"])
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
    assert test_org.id in org_ids


def test_list_published_reports_org_member_filtered(
    client, test_db, test_users, auth_headers, test_org
):
    """A non-superadmin org member sees published reports of their org's
    projects, and not published reports of unrelated orgs."""
    admin = test_users[0]
    contributor = test_users[1]  # member of test_org

    # Published report owned by test_org (contributor is a member here).
    own_project = _create_project(test_db, admin, org=test_org, title="Own Org Report")
    own_report = _create_report(
        test_db, own_project, admin, is_published=True, published_by=admin
    )

    # Published report owned by an unrelated org the contributor is NOT in.
    other_org = Organization(
        id=_uid(),
        name="Unrelated Org",
        display_name="Unrelated Org",
        slug=f"unrelated-{_uid()[:8]}",
        created_at=datetime.utcnow(),
    )
    test_db.add(other_org)
    test_db.commit()
    other_project = _create_project(
        test_db, admin, org=other_org, title="Other Org Report", assigned_by=admin
    )
    other_report = _create_report(
        test_db, other_project, admin, is_published=True, published_by=admin
    )

    resp = client.get("/api/reports", headers=auth_headers["contributor"])
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert own_report.id in ids
    assert other_report.id not in ids


def test_list_published_reports_empty(client, test_db, test_users, auth_headers):
    """No published reports at all -> empty list (not an error)."""
    resp = client.get("/api/reports", headers=auth_headers["admin"])
    assert resp.status_code == 200
    assert resp.json() == []


# ===========================================================================
# GET /api/reports/{report_id}/data
# ===========================================================================

def test_get_report_data_not_found(client, test_users, auth_headers):
    """Unknown report id -> 404."""
    resp = client.get(
        "/api/reports/no-such-report/data", headers=auth_headers["admin"]
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_report_data_unpublished_forbidden_for_non_superadmin(
    client, test_db, test_users, auth_headers, test_org
):
    """Draft report data is forbidden to non-superadmins -> 403."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org)
    report = _create_report(test_db, project, admin, is_published=False)

    resp = client.get(
        f"/api/reports/{report.id}/data", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 403
    assert "not published" in resp.json()["detail"].lower()


def test_get_report_data_superadmin_draft_ok(
    client, test_db, test_users, auth_headers, test_org
):
    """Superadmin can fetch data for a draft report; response carries the
    statistics / participants / models / evaluation_charts envelope."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org, with_task=True)
    report = _create_report(test_db, project, admin, is_published=False)

    resp = client.get(
        f"/api/reports/{report.id}/data", headers=auth_headers["admin"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["id"] == report.id
    assert "statistics" in body
    assert body["statistics"]["task_count"] == 1
    assert "participants" in body
    assert "models" in body
    assert "evaluation_charts" in body


def test_get_report_data_published_org_member_allowed(
    client, test_db, test_users, auth_headers, test_org
):
    """A published report's data is viewable by a member of an owning org."""
    admin = test_users[0]
    project = _create_project(test_db, admin, org=test_org, with_task=True)
    report = _create_report(
        test_db, project, admin, is_published=True, published_by=admin
    )

    resp = client.get(
        f"/api/reports/{report.id}/data", headers=auth_headers["contributor"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["id"] == report.id
    assert body["report"]["is_published"] is True


# ===========================================================================
# Auth gate
# ===========================================================================

def test_reports_endpoints_require_auth(client):
    """No credentials -> 401 on a representative endpoint (require_user gate)."""
    resp = client.get("/api/reports")
    assert resp.status_code == 401
