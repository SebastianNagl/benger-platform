"""
Coverage boost tests for project members and assignments endpoints.

Targets specific branches in:
- routers/projects/members.py
- routers/projects/assignments.py
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _setup_project(db, users):
    """Create a project with org and memberships."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Member Org",
        slug=f"member-org-{uuid.uuid4().hex[:8]}",
        display_name="Member Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Member Project",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="manual",
    )
    db.add(p)
    db.commit()

    # Add org memberships
    for i, user in enumerate(users[:4]):
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i in [0, 3] else ("CONTRIBUTOR" if i == 1 else "ANNOTATOR"),
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    return p, org


class TestListProjectMembers:
    """Test list_project_members endpoint."""

    def test_list_members_from_org(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/members",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1

    def test_list_members_with_direct_members(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        # Add direct member
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[2].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/members",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        members = resp.json()
        # Should have both direct and org members
        direct = [m for m in members if m["is_direct_member"]]
        assert len(direct) >= 1

    def test_list_members_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_list_members_no_duplicates(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        # Add user[0] as both org member and direct member
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[0].id,
            role="ADMIN",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/members",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        members = resp.json()
        user_ids = [m["user_id"] for m in members]
        assert len(user_ids) == len(set(user_ids))


class TestAddProjectMember:
    """Test add_project_member endpoint."""

    def test_add_member_success(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[2].id}",
            json={"role": "ANNOTATOR"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "ANNOTATOR"

    def test_add_member_project_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.post(
            f"/api/projects/nonexistent/members/{test_users[0].id}",
            json={"role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_add_member_user_not_found(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/members/nonexistent-user",
            json={"role": "ANNOTATOR"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404

    def test_add_duplicate_member(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            json={"role": "ANNOTATOR"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 400

    def test_reactivate_inactive_member(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=False,
        ))
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            json={"role": "CONTRIBUTOR"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert "reactivated" in resp.json()["message"]

    def test_add_member_annotator_forbidden(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            json={"role": "ANNOTATOR"},
            headers={**auth_headers["annotator"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 403


class TestRemoveProjectMember:
    """Test remove_project_member endpoint."""

    def test_remove_member_success(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_remove_project_creator_forbidden(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.delete(
            f"/api/projects/{p.id}/members/{test_users[0].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 400

    def test_remove_nonexistent_member(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.delete(
            f"/api/projects/{p.id}/members/{test_users[2].id}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404

    def test_remove_member_project_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.delete(
            f"/api/projects/nonexistent/members/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestGetProjectAnnotators:
    """Test get_project_annotators endpoint."""

    def test_annotators_empty(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/annotators",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["annotators"] == []

    def test_annotators_with_annotations(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "test"}, inner_id=1)
        test_db.add(t)
        test_db.commit()

        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=tid,
            project_id=p.id,
            completed_by=test_users[1].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["ann"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/annotators",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        annotators = resp.json()["annotators"]
        assert len(annotators) >= 1
        assert annotators[0]["count"] >= 1

    def test_annotators_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/annotators",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestAssignTasks:
    """Test assign_tasks endpoint."""

    def test_manual_assignment(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "assign"}, inner_id=1)
        test_db.add(t)
        # Add direct project member
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [tid],
                "user_ids": [test_users[1].id],
                "distribution": "manual",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 1

    def test_round_robin_assignment(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tasks = []
        for i in range(3):
            tid = str(uuid.uuid4())
            t = Task(id=tid, project_id=p.id, data={"text": f"rr-{i}"}, inner_id=i + 1)
            test_db.add(t)
            tasks.append(tid)
        # Add direct project members
        for uid in [test_users[1].id, test_users[2].id]:
            test_db.add(ProjectMember(
                id=str(uuid.uuid4()),
                project_id=p.id,
                user_id=uid,
                role="ANNOTATOR",
                assigned_by=test_users[0].id,
                is_active=True,
            ))
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": tasks,
                "user_ids": [test_users[1].id, test_users[2].id],
                "distribution": "round_robin",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 3

    def test_assign_empty_ids(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={"task_ids": [], "user_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 400

    def test_assign_nonexistent_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": ["nonexistent"],
                "user_ids": [test_users[1].id],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 400

    def test_assign_project_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.post(
            "/api/projects/nonexistent/tasks/assign",
            json={"task_ids": ["x"], "user_ids": ["y"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_assign_annotator_forbidden(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={"task_ids": ["x"], "user_ids": ["y"]},
            headers={**auth_headers["annotator"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 403

    def test_duplicate_assignment_skipped(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "dup"}, inner_id=1)
        test_db.add(t)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        # First assignment
        client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [tid],
                "user_ids": [test_users[1].id],
                "distribution": "manual",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )

        # Duplicate
        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [tid],
                "user_ids": [test_users[1].id],
                "distribution": "manual",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 0


class TestListTaskAssignments:
    """Test list_task_assignments endpoint."""

    def test_list_assignments(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "list"}, inner_id=1)
        test_db.add(t)
        test_db.add(TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=tid,
            user_id=test_users[1].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks/{tid}/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_assignments_task_not_found(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/tasks/nonexistent/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404


class TestRemoveAssignment:
    """Test remove_task_assignment endpoint."""

    def test_remove_assignment(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "remove"}, inner_id=1)
        test_db.add(t)
        aid = str(uuid.uuid4())
        test_db.add(TaskAssignment(
            id=aid,
            task_id=tid,
            user_id=test_users[1].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/tasks/{tid}/assignments/{aid}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_remove_nonexistent_assignment(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "x"}, inner_id=1)
        test_db.add(t)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/tasks/{tid}/assignments/nonexistent",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404


class TestGetMyTasks:
    """Test get_my_tasks endpoint."""

    def test_my_tasks_success(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "my"}, inner_id=1)
        test_db.add(t)
        test_db.add(TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=tid,
            user_id=test_users[0].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/my-tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_my_tasks_with_status_filter(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        tid = str(uuid.uuid4())
        t = Task(id=tid, project_id=p.id, data={"text": "status"}, inner_id=1)
        test_db.add(t)
        test_db.add(TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=tid,
            user_id=test_users[0].id,
            assigned_by=test_users[0].id,
            status="completed",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/my-tasks?status=completed",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_my_tasks_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/my-tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestProjectWorkload:
    """Test get_project_workload endpoint."""

    def test_workload_success(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        test_db.add(ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
            is_active=True,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/workload",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "annotators" in data
        assert "stats" in data

    def test_workload_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/workload",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_workload_annotator_forbidden(self, client, auth_headers, test_db, test_users):
        p, org = _setup_project(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/workload",
            headers={**auth_headers["annotator"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 403
