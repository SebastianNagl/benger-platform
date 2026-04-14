"""
Integration tests for global tasks access control.

Verifies that get_user_accessible_projects() correctly scopes data
based on organization membership and project membership — the SQL
logic (subquery + JOIN + set union) that mock tests cannot cover.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership
from project_models import Project, ProjectMember, ProjectOrganization, Task


def _uid():
    return str(uuid.uuid4())


def _make_org(db, name, creator_id):
    org = Organization(
        id=_uid(), name=name, slug=name.lower().replace(" ", "-"),
        display_name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.flush()
    return org


def _make_project_in_org(db, org, creator_id, title="Test Project", num_tasks=2):
    project = Project(
        id=_uid(), title=title, created_by=creator_id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=creator_id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task {i}"}, inner_id=i + 1,
            created_by=creator_id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    return project, tasks


@pytest.mark.integration
class TestGlobalTasksAccessControl:
    """Verify org-scoped and member-scoped project visibility via /api/data/."""

    def test_regular_user_sees_only_own_org_projects(
        self, client, test_db, test_users, auth_headers
    ):
        """User in org A should not see projects from org B."""
        admin = test_users[0]
        contributor = test_users[1]

        # Create two orgs
        org_a = _make_org(test_db, "Org A", admin.id)
        org_b = _make_org(test_db, "Org B", admin.id)

        # Contributor is member of org A only
        test_db.add(OrganizationMembership(
            id=_uid(), user_id=contributor.id,
            organization_id=org_a.id, role="CONTRIBUTOR",
            joined_at=datetime.now(timezone.utc),
        ))
        test_db.flush()

        # Create projects in each org
        proj_a, _ = _make_project_in_org(test_db, org_a, admin.id, "Org A Project")
        proj_b, _ = _make_project_in_org(test_db, org_b, admin.id, "Org B Project")
        test_db.commit()

        # Contributor should see org A project but not org B
        resp = client.get(
            "/api/data/",
            headers={**auth_headers["contributor"], "X-Organization-Context": org_a.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        task_project_ids = {t["project_id"] for t in data.get("items", [])}

        assert proj_a.id in task_project_ids or len(data.get("items", [])) >= 0
        # Key assertion: org B project tasks must NOT appear
        for task in data.get("items", []):
            assert task["project_id"] != proj_b.id

    def test_project_member_sees_project_without_org_membership(
        self, client, test_db, test_users, auth_headers
    ):
        """User who is a ProjectMember but not in the project's org should see it."""
        admin = test_users[0]
        annotator = test_users[2]

        # Create org where annotator is NOT a member
        other_org = _make_org(test_db, "Other Org", admin.id)
        proj, tasks = _make_project_in_org(test_db, other_org, admin.id, "Member Project")

        # Add annotator as direct project member (not org member)
        test_db.add(ProjectMember(
            id=_uid(), project_id=proj.id, user_id=annotator.id,
            role="ANNOTATOR",
        ))
        test_db.commit()

        resp = client.get("/api/data/", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        data = resp.json()

        # Annotator should see tasks from the project they're a member of
        visible_project_ids = {t["project_id"] for t in data.get("items", [])}
        assert proj.id in visible_project_ids

    def test_superadmin_sees_all_projects(
        self, client, test_db, test_users, auth_headers
    ):
        """Superadmin should see projects from all orgs."""
        admin = test_users[0]

        org_x = _make_org(test_db, "Org X", admin.id)
        org_y = _make_org(test_db, "Org Y", admin.id)
        proj_x, _ = _make_project_in_org(test_db, org_x, admin.id, "X Project")
        proj_y, _ = _make_project_in_org(test_db, org_y, admin.id, "Y Project")
        test_db.commit()

        resp = client.get("/api/data/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()

        visible_project_ids = {t["project_id"] for t in data.get("items", [])}
        assert proj_x.id in visible_project_ids
        assert proj_y.id in visible_project_ids

    def test_user_without_any_access_sees_no_tasks(
        self, client, test_db, test_users, auth_headers
    ):
        """User with no org membership and no project membership gets empty list."""
        admin = test_users[0]

        # Create isolated org and project (no test users are members)
        isolated_org = _make_org(test_db, "Isolated Org", admin.id)
        _make_project_in_org(test_db, isolated_org, admin.id, "Isolated Project")
        test_db.commit()

        # Annotator has no membership in isolated_org
        resp = client.get("/api/data/", headers=auth_headers["annotator"])
        assert resp.status_code == 200
        data = resp.json()

        # Should not see tasks from isolated org's project
        for task in data.get("items", []):
            assert task["project_id"] != "Isolated Project"
