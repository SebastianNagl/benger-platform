"""Integration tests: a non-creator, non-superadmin user (the "public visitor")
acting on a public project — exercising the WRITE paths the public_role
contract is supposed to govern.

Confirms the end-to-end behaviour for:
  - POST /tasks/{task_id}/annotations  (write annotations)
  - PATCH /projects/{project_id}        (project settings — must always 403)
  - PATCH /projects/{project_id}/visibility  (must always 403 for visitor)

Note on PROJECT_EDIT cap:
  The authorization-service Permission matrix caps PROJECT_EDIT/DELETE/CREATE
  for public_role visitors at the matrix level. The actual `update_project`
  router enforces this via `check_user_can_edit_project`, which rejects
  visitors regardless of public_role (creator + superadmin only). Both these
  layers are exercised by the assertions below.

Note on TASK_CREATE / GENERATION_CREATE:
  These endpoints (`POST /projects/{id}/import` and
  `POST /projects/{id}/generate`) call `check_project_write_access`, which
  enforces the documented public_role contract: public-tier ANNOTATOR
  visitors are blocked; CONTRIBUTOR visitors are allowed.
"""

import uuid
from datetime import datetime, timezone

import pytest

from models import Organization, OrganizationMembership, User
from project_models import Annotation, Project, Task


@pytest.fixture
def creator(test_db):
    user = User(
        id=f"vw-creator-{uuid.uuid4()}",
        username=f"vwc-{uuid.uuid4().hex[:8]}",
        email=f"vwc-{uuid.uuid4().hex[:8]}@test.com",
        name="Public-project creator",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.flush()
    return user


@pytest.fixture
def visitor(test_db):
    """Authenticated user with no relationship to the project."""
    user = User(
        id=f"vw-visitor-{uuid.uuid4()}",
        username=f"vwv-{uuid.uuid4().hex[:8]}",
        email=f"vwv-{uuid.uuid4().hex[:8]}@test.com",
        name="Public-project visitor",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.flush()
    return user


def _public_project(test_db, creator, public_role):
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Public {public_role} Bench",
        created_by=creator.id,
        is_private=False,
        is_public=True,
        public_role=public_role,
    )
    test_db.add(project)
    test_db.flush()
    return project


_inner_id_counter = 0


def _task(test_db, project):
    global _inner_id_counter
    _inner_id_counter += 1
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"text": "hello"},
        inner_id=_inner_id_counter,
    )
    test_db.add(task)
    test_db.flush()
    return task


def _bearer(user) -> dict:
    """Mint a bearer-token header for a user without going through /login."""
    from auth_module import create_access_token

    token = create_access_token(data={"user_id": user.id, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


class TestPublicAnnotatorVisitorWritePaths:
    """ANNOTATOR public_role: read + annotate only."""

    def test_visitor_can_read_project(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        test_db.commit()

        resp = client.get(f"/api/projects/{project.id}", headers=_bearer(visitor))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_public"] is True
        assert body["public_role"] == "ANNOTATOR"

    def test_visitor_can_create_annotation(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        task = _task(test_db, project)
        test_db.commit()

        payload = {"result": []}
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json=payload,
            headers=_bearer(visitor),
        )
        assert resp.status_code in (200, 201), resp.text
        body = resp.json()
        assert body.get("task_id") in (task.id, str(task.id))

        # The annotation row exists.
        ann = (
            test_db.query(Annotation)
            .filter(Annotation.task_id == task.id, Annotation.completed_by == visitor.id)
            .first()
        )
        assert ann is not None

    def test_visitor_cannot_edit_project_settings(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}",
            json={"title": "hijacked"},
            headers=_bearer(visitor),
        )
        assert resp.status_code == 403, resp.text

    def test_visitor_cannot_change_visibility(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": True},
            headers=_bearer(visitor),
        )
        assert resp.status_code == 403, resp.text

    def test_visitor_cannot_import_tasks(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/import",
            json={"data": [{"text": "new task"}]},
            headers=_bearer(visitor),
        )
        assert resp.status_code == 403, resp.text

    def test_visitor_cannot_start_generation(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "ANNOTATOR")
        test_db.commit()

        resp = client.post(
            f"/api/generation-tasks/projects/{project.id}/generate",
            json={"mode": "missing"},
            headers=_bearer(visitor),
        )
        assert resp.status_code == 403, resp.text


class TestPublicContributorVisitorWritePaths:
    """CONTRIBUTOR public_role: extra write powers (annotate + future writes),
    but settings + visibility editing remain creator/superadmin-only."""

    def test_visitor_can_read_project(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        test_db.commit()
        resp = client.get(f"/api/projects/{project.id}", headers=_bearer(visitor))
        assert resp.status_code == 200, resp.text
        assert resp.json()["public_role"] == "CONTRIBUTOR"

    def test_visitor_can_create_annotation(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        task = _task(test_db, project)
        test_db.commit()

        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": []},
            headers=_bearer(visitor),
        )
        assert resp.status_code in (200, 201), resp.text

    def test_visitor_cannot_edit_project_settings(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        test_db.commit()
        resp = client.patch(
            f"/api/projects/{project.id}",
            json={"title": "hijacked"},
            headers=_bearer(visitor),
        )
        # Public CONTRIBUTOR is the most permissive public role; settings edit
        # still belongs to the creator + superadmins (the documented cap).
        assert resp.status_code == 403, resp.text

    def test_visitor_cannot_change_visibility(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        test_db.commit()
        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"public_role": "ANNOTATOR"},
            headers=_bearer(visitor),
        )
        assert resp.status_code == 403, resp.text

    def test_visitor_can_import_tasks(self, client, test_db, creator, visitor):
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/import",
            json={"data": [{"text": "contributed task"}]},
            headers=_bearer(visitor),
        )
        # Either accepted (200/201) or fails on validation later — anything
        # except 403 means the public_role gate let the contributor through.
        assert resp.status_code != 403, resp.text


class TestPublicProjectVisibleAcrossOrgs:
    """A user who is a member of an unrelated org still sees the public project."""

    def test_other_org_member_sees_public_project(self, client, test_db, creator, visitor):
        other_org = Organization(
            id=str(uuid.uuid4()),
            name=f"OtherOrg-{uuid.uuid4().hex[:6]}",
            slug=f"otherorg-{uuid.uuid4().hex[:6]}",
            display_name="Other Org",
        )
        test_db.add(other_org)
        test_db.add(
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=visitor.id,
                organization_id=other_org.id,
                role="ANNOTATOR",
                is_active=True,
            )
        )
        project = _public_project(test_db, creator, "CONTRIBUTOR")
        test_db.commit()

        # Hit list with the visitor's org context — public project must appear.
        resp = client.get(
            "/api/projects/?page=1&page_size=100",
            headers={
                **_bearer(visitor),
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 200, resp.text
        items = resp.json().get("items", [])
        ids = [it["id"] for it in items]
        assert project.id in ids
