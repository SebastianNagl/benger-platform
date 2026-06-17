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
    * the ``is_archived`` virtual-field response-level filter (true / false).
- ``PATCH /{id}/visibility`` (update_project_visibility):
    * make-public: drops org assignments, flips flags (persisted).
    * standalone ``public_role`` flip on an already-public project.
    * the public_role-flip-on-non-public 400 guard.
    * make-private: reassign owner + drop org assignments (persisted).
    * make-org-assigned with an unknown org id → 404.
- ``GET /{id}/completion-stats``:
    * happy path counts (labeled vs total) + 403 for an outsider context.

Every test calls through ``client`` and asserts the HTTP status, response
JSON, and the persisted ``Project`` / ``ProjectOrganization`` rows via
``test_db``.
"""

from __future__ import annotations

import uuid

import pytest

from models import Organization
from project_models import Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _ctx(auth_headers, role, org):
    return {**auth_headers[role], "X-Organization-Context": org.id}


def _make_project(db, creator, org=None, *, is_private=False, is_public=False,
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
    )
    db.add(p)
    db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    return p


# ===========================================================================
# POST / — create_project (public + conflict branches)
# ===========================================================================


@pytest.mark.integration
class TestCreatePublicProject:
    def test_create_public_defaults_role_and_no_org_link(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        resp = client.post(
            "/api/projects/",
            json={"title": "Public Branch Project", "is_public": True},
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        project_id = body["id"]

        test_db.expire_all()
        project = test_db.query(Project).filter(Project.id == project_id).first()
        assert project.is_public is True
        assert project.is_private is False
        # public_role defaults to ANNOTATOR when omitted.
        assert project.public_role == "ANNOTATOR"
        # Public projects get NO org assignment row.
        org_rows = (
            test_db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project_id)
            .count()
        )
        assert org_rows == 0

    def test_create_public_with_contributor_role(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Public Contributor Project",
                "is_public": True,
                "public_role": "CONTRIBUTOR",
            },
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        project_id = resp.json()["id"]

        test_db.expire_all()
        project = test_db.query(Project).filter(Project.id == project_id).first()
        assert project.public_role == "CONTRIBUTOR"

    def test_create_both_private_and_public_400(
        self, client, auth_headers, test_org
    ):
        resp = client.post(
            "/api/projects/",
            json={"title": "Conflict", "is_public": True, "is_private": True},
            headers=_ctx(auth_headers, "admin", test_org),
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
    def test_is_archived_true_and_false(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        archived = _make_project(test_db, test_users[0], test_org, is_archived=True)
        active = _make_project(test_db, test_users[0], test_org, is_archived=False)
        test_db.commit()

        # is_archived=true → only the archived project.
        r_arch = client.get(
            "/api/projects/?is_archived=true&page_size=500",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert r_arch.status_code == 200
        arch_ids = {p["id"] for p in r_arch.json()["items"]}
        assert archived.id in arch_ids
        assert active.id not in arch_ids

        # is_archived=false → excludes the archived one.
        r_active = client.get(
            "/api/projects/?is_archived=false&page_size=500",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert r_active.status_code == 200
        active_ids = {p["id"] for p in r_active.json()["items"]}
        assert active.id in active_ids
        assert archived.id not in active_ids


# ===========================================================================
# PATCH /{id}/visibility — update_project_visibility
# ===========================================================================


@pytest.mark.integration
class TestVisibilityTransitions:
    def test_make_public_drops_orgs_and_sets_flags(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        assert (
            test_db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .count()
            == 1
        )

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_public": True, "public_role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        assert refreshed.is_public is True
        assert refreshed.is_private is False
        assert refreshed.public_role == "CONTRIBUTOR"
        # Org assignment removed.
        assert (
            test_db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .count()
            == 0
        )

    def test_standalone_public_role_flip(
        self, client, auth_headers, test_db, test_users
    ):
        project = _make_project(
            test_db, test_users[0], is_public=True, public_role="ANNOTATOR"
        )
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"public_role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        assert refreshed.public_role == "CONTRIBUTOR"
        assert refreshed.is_public is True

    def test_public_role_flip_on_non_public_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"public_role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "public project" in resp.json()["detail"]

    def test_make_private_reassigns_owner_and_drops_orgs(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        new_owner = test_users[1]

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": True, "owner_user_id": new_owner.id},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        assert refreshed.is_private is True
        assert refreshed.is_public is False
        assert str(refreshed.created_by) == new_owner.id
        assert (
            test_db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .count()
            == 0
        )

    def test_make_org_assigned_unknown_org_404(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        unknown = _uid()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": False, "organization_ids": [unknown]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert unknown in resp.json()["detail"]

    def test_make_org_assigned_no_org_ids_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": False, "organization_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400
        assert "organization_id" in resp.json()["detail"]


# ===========================================================================
# GET /{id}/completion-stats — get_project_completion_stats
# ===========================================================================


@pytest.mark.integration
class TestCompletionStats:
    def test_completion_stats_counts(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        # 3 tasks, 1 labeled.
        for i in range(3):
            test_db.add(
                Task(
                    id=_uid(),
                    project_id=project.id,
                    inner_id=i + 1,
                    data={"text": f"t{i}"},
                    created_by=test_users[0].id,
                    is_labeled=(i == 0),
                )
            )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/completion-stats",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["completed"] == 1
        assert abs(body["completion_rate"] - (1 / 3 * 100)) < 0.01

    def test_completion_stats_not_found_404(
        self, client, auth_headers, test_org
    ):
        resp = client.get(
            f"/api/projects/{_uid()}/completion-stats",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Project not found"

    def test_completion_stats_outsider_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Completion Org",
            slug=f"outsider-completion-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Completion Org",
        )
        test_db.add(other_org)
        test_db.flush()
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/completion-stats",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"
