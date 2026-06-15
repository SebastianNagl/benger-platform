"""Integration coverage for the project bulk-operations router.

Targets the uncovered arms of ``services/api/routers/projects/bulk.py``:

  * ``POST /api/projects/bulk-delete``    — creator/superadmin gate, not-found
    skip, permission-denied skip, the successful delete (project + members +
    orgs + tasks removed, notification fired), and per-project error isolation.
  * ``POST /api/projects/bulk-archive``   — edit-permission gate (creator /
    org-admin / contributor allowed, annotator / non-member skipped), the
    ``is_archived`` flip persisted, not-found skip, notification fired.
  * ``POST /api/projects/bulk-unarchive`` — the inverse flip + permission gate.

All three handlers use the SYNC DB lane (``Depends(get_db)``), so these tests
drive them through the ``client`` fixture and assert persisted state via
``test_db``. ``notify_project_*`` create real Notification rows; we assert those
where relevant and never mock them. The sibling ``tests/routers/projects/
test_bulk.py`` only checks the routes exist — this file is the behavioral
complement.

The bulk-EXPORT endpoints (``/bulk-export``, ``/bulk-export-full``) live in the
import_export router, not here — they are covered in
``test_projects_import_export_coverage.py``.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from models import Notification, NotificationType
from project_models import Project, ProjectMember, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(
    test_db: Session,
    *,
    created_by: str,
    org_id: str = None,
    title: str = "Bulk Project",
    is_archived: bool = False,
) -> Project:
    project = Project(
        id=_uid(),
        title=title,
        description="bulk-ops fixture",
        created_by=created_by,
        is_archived=is_archived,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    test_db.add(project)
    test_db.flush()
    if org_id is not None:
        test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org_id,
                assigned_by=created_by,
            )
        )
    test_db.commit()
    return project


def _add_task(test_db: Session, project: Project, *, inner_id: int = 1) -> Task:
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": "hello"},
        is_labeled=False,
    )
    test_db.add(task)
    test_db.commit()
    return task


# ---------------------------------------------------------------------------
# bulk-delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkDelete:
    def test_creator_deletes_project_and_children(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A superadmin (admin fixture) deletes their own project: the project,
        its members, its org links and its tasks are all removed and the count
        reflects exactly one deletion."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id
        )
        _add_task(test_db, project, inner_id=1)
        _add_task(test_db, project, inner_id=2)
        test_db.add(
            ProjectMember(
                id=_uid(),
                project_id=project.id,
                user_id=admin.id,
                role="ORG_ADMIN",
            )
        )
        test_db.commit()
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 1
        assert body["failed"] == 0
        assert body["failed_projects"] == []

        # Project + all child rows gone.
        assert test_db.query(Project).filter(Project.id == pid).first() is None
        assert (
            test_db.query(Task).filter(Task.project_id == pid).count() == 0
        )
        assert (
            test_db.query(ProjectMember)
            .filter(ProjectMember.project_id == pid)
            .count()
            == 0
        )
        assert (
            test_db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == pid)
            .count()
            == 0
        )

    def test_missing_project_reported_as_failed(
        self, client, test_db, test_users, auth_headers
    ):
        """An unknown project id lands in failed_projects with a not-found
        reason and nothing is deleted."""
        ghost = _uid()
        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": [ghost]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 0
        assert body["failed"] == 1
        assert body["failed_projects"][0]["id"] == ghost
        assert "not found" in body["failed_projects"][0]["reason"].lower()

    def test_non_creator_non_superadmin_permission_denied(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A contributor who is neither the creator nor a superadmin cannot
        delete the admin's project — it survives and is reported as a permission
        failure."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": [pid]},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 0
        assert body["failed"] == 1
        assert body["failed_projects"][0]["id"] == pid
        assert "permission" in body["failed_projects"][0]["reason"].lower()
        # Project untouched.
        assert test_db.query(Project).filter(Project.id == pid).first() is not None

    def test_mixed_batch_deletes_owned_skips_others(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A batch of [own, foreign, missing] for a non-superadmin creator:
        only the owned project is deleted, the other two are failures."""
        contributor, annotator = test_users[1], test_users[2]
        own = _make_project(
            test_db, created_by=contributor.id, org_id=test_org.id, title="Own"
        )
        foreign = _make_project(
            test_db, created_by=annotator.id, org_id=test_org.id, title="Foreign"
        )
        missing = _uid()

        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": [own.id, foreign.id, missing]},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] == 1
        assert body["failed"] == 2

        assert test_db.query(Project).filter(Project.id == own.id).first() is None
        assert (
            test_db.query(Project).filter(Project.id == foreign.id).first()
            is not None
        )

    def test_empty_project_ids_is_noop(self, client, auth_headers):
        """No ids → nothing deleted, nothing failed, still 200."""
        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"deleted": 0, "failed": 0, "failed_projects": []}

    def test_delete_notifies_org_members(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Deleting an org-bound project fires PROJECT_DELETED notifications to
        the OTHER org members (not the deleter). The contributor/annotator/
        org_admin are recipients; the deleting admin is not."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id, title="Notify Me"
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-delete",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] == 1

        notes = (
            test_db.query(Notification)
            .filter(Notification.type == NotificationType.PROJECT_DELETED)
            .all()
        )
        # At least one recipient (an org member other than the deleter) got it.
        assert notes
        recipient_ids = {n.user_id for n in notes}
        assert admin.id not in recipient_ids
        for n in notes:
            assert n.data.get("project_id") == pid


# ---------------------------------------------------------------------------
# bulk-archive
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkArchive:
    def test_creator_archives_and_persists_flag(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-archive",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1

        test_db.expire_all()
        assert (
            test_db.query(Project).filter(Project.id == pid).first().is_archived
            is True
        )

    def test_contributor_can_archive_org_project(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A CONTRIBUTOR org member passes check_user_can_edit_project and may
        archive a project owned by someone else in the org."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-archive",
            json={"project_ids": [pid]},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1
        test_db.expire_all()
        assert (
            test_db.query(Project).filter(Project.id == pid).first().is_archived
            is True
        )

    def test_annotator_cannot_archive_is_skipped(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """An ANNOTATOR fails the edit gate; the project stays unarchived and the
        count is zero (the loop ``continue``s past it)."""
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-archive",
            json={"project_ids": [pid]},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 0
        test_db.expire_all()
        assert (
            test_db.query(Project).filter(Project.id == pid).first().is_archived
            is False
        )

    def test_missing_project_skipped(self, client, auth_headers):
        resp = client.post(
            "/api/projects/bulk-archive",
            json={"project_ids": [_uid()]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 0

    def test_archive_notifies_org_members(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id, title="Arch Notify"
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-archive",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] == 1

        notes = (
            test_db.query(Notification)
            .filter(Notification.type == NotificationType.PROJECT_ARCHIVED)
            .all()
        )
        assert notes
        assert admin.id not in {n.user_id for n in notes}


# ---------------------------------------------------------------------------
# bulk-unarchive
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkUnarchive:
    def test_creator_unarchives_and_persists_flag(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id, is_archived=True
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-unarchive",
            json={"project_ids": [pid]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 1

        test_db.expire_all()
        assert (
            test_db.query(Project).filter(Project.id == pid).first().is_archived
            is False
        )

    def test_annotator_cannot_unarchive_is_skipped(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        project = _make_project(
            test_db, created_by=admin.id, org_id=test_org.id, is_archived=True
        )
        pid = project.id

        resp = client.post(
            "/api/projects/bulk-unarchive",
            json={"project_ids": [pid]},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 0
        test_db.expire_all()
        assert (
            test_db.query(Project).filter(Project.id == pid).first().is_archived
            is True
        )

    def test_missing_project_skipped(self, client, auth_headers):
        resp = client.post(
            "/api/projects/bulk-unarchive",
            json={"project_ids": [_uid()]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["unarchived"] == 0
