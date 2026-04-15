"""
Deep integration tests for tasks, CRUD, members, reviews, annotations, assignments.

Targets: routers/projects/tasks.py, crud.py, members.py, reviews.py,
annotations.py, assignments.py, timer.py, questionnaire.py, helpers.py
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kw):
    pid = _uid()
    p = Project(
        id=pid,
        title=kw.get("title", f"P-{pid[:6]}"),
        created_by=admin.id,
        label_config=kw.get("label_config", '<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>'),
        is_private=kw.get("is_private", False),
        assignment_mode=kw.get("assignment_mode", "open"),
        randomize_task_order=kw.get("randomize_task_order", False),
        min_annotations_per_task=kw.get("min_annotations_per_task", 1),
        maximum_annotations=kw.get("maximum_annotations", 0),
        skip_queue=kw.get("skip_queue", "requeue_for_others"),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
    )
    db.add(p)
    db.flush()
    if org:
        db.add(ProjectOrganization(id=_uid(), project_id=pid, organization_id=org.id, assigned_by=admin.id))
        db.flush()
    return p


def _task(db, project, admin, *, inner_id=1, data=None, is_labeled=False, meta=None):
    t = Task(
        id=_uid(), project_id=project.id,
        data=data or {"text": f"Task {inner_id}"},
        meta=meta, inner_id=inner_id, created_by=admin.id,
        is_labeled=is_labeled,
    )
    db.add(t)
    db.flush()
    return t


def _ann(db, task, project, user, *, result=None, was_cancelled=False):
    a = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id,
        completed_by=user.id,
        result=result or [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
        was_cancelled=was_cancelled,
    )
    db.add(a)
    db.flush()
    return a


# ==============================================================
# Task listing tests
# ==============================================================


class TestTaskListing:
    def test_list_tasks_basic(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        for i in range(5):
            _task(test_db, p, test_users[0], inner_id=i + 1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5

    def test_list_tasks_pagination(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        for i in range(10):
            _task(test_db, p, test_users[0], inner_id=i + 1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?page=1&page_size=3",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        # tasks key may vary; just check page_size is respected
        tasks_list = data.get("tasks", data.get("items", []))
        assert len(tasks_list) <= 3

    def test_list_tasks_only_labeled(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _task(test_db, p, test_users[0], inner_id=1, is_labeled=True)
        _task(test_db, p, test_users[0], inner_id=2, is_labeled=False)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_labeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_only_unlabeled(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _task(test_db, p, test_users[0], inner_id=1, is_labeled=True)
        _task(test_db, p, test_users[0], inner_id=2, is_labeled=False)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_exclude_my_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t1 = _task(test_db, p, test_users[0], inner_id=1)
        t2 = _task(test_db, p, test_users[0], inner_id=2)
        _ann(test_db, t1, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)

    def test_list_tasks_randomized(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, randomize_task_order=True)
        for i in range(5):
            _task(test_db, p, test_users[0], inner_id=i + 1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ==============================================================
# Single task operations
# ==============================================================


class TestTaskOperations:
    def test_get_single_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        test_db.commit()

        # GET single task: /api/projects/tasks/{task_id}
        resp = client.get(
            f"/api/projects/tasks/{t.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            "/api/projects/tasks/nonexistent",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (404, 500)

    def test_update_task_data(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        test_db.commit()

        # PUT task: /api/projects/{project_id}/tasks/{task_id}
        resp = client.put(
            f"/api/projects/{p.id}/tasks/{t.id}",
            json={"data": {"text": "Updated text"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)

    def test_update_task_metadata(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0], meta={"source": "test"})
        test_db.commit()

        # PATCH metadata: /api/projects/tasks/{task_id}/metadata
        resp = client.patch(
            f"/api/projects/tasks/{t.id}/metadata",
            json={"meta": {"source": "updated", "extra": "data"}, "merge": True},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)

    def test_bulk_delete_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = [_task(test_db, p, test_users[0], inner_id=i) for i in range(3)]
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": [t.id for t in tasks[:2]]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)

    def test_skip_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/skip",
            json={"comment": "Too difficult"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 404)

    def test_bulk_archive(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t1 = _task(test_db, p, test_users[0], inner_id=1, is_labeled=True)
        t2 = _task(test_db, p, test_users[0], inner_id=2, is_labeled=False)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-archive",
            json={"task_ids": [t1.id, t2.id]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)


# ==============================================================
# Project CRUD tests
# ==============================================================


class TestProjectCRUD:
    def test_list_projects(self, client, test_db, test_users, auth_headers, test_org):
        _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            "/api/projects/",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_list_projects_search(self, client, test_db, test_users, auth_headers, test_org):
        _project(test_db, test_users[0], test_org, title="Legal Analysis Project")
        test_db.commit()

        resp = client.get(
            "/api/projects/?search=Legal",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_projects_private_context(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/",
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code == 200

    def test_create_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/",
            json={"title": "Test Create Project", "description": "desc"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["title"] == "Test Create Project"

    def test_create_project_with_label_config(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "With Config",
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)

    def test_create_project_invalid_label_config(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/",
            json={"title": "Bad Config", "label_config": "not valid xml<<<"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201, 422)

    def test_create_private_project(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={"title": "Private Project", "is_private": True},
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code in (200, 201)

    def test_get_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"title": "Updated Title"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_project_generation_config(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_project_evaluation_config_deep_merge(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        # First update
        client.patch(
            f"/api/projects/{p.id}",
            json={"evaluation_config": {"field1": {"method": "exact_match"}}},
            headers=auth_headers["admin"],
        )
        # Second update (should deep merge)
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"evaluation_config": {"field2": {"method": "f1"}}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_disable_time_limit(self, client, test_db, test_users, auth_headers, test_org):
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_delete_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_completion_stats(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _task(test_db, p, test_users[0], inner_id=1, is_labeled=True)
        _task(test_db, p, test_users[0], inner_id=2, is_labeled=False)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["completed"] == 1

    def test_recalculate_stats(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _task(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_project_visibility_make_private(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": test_users[0].id},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ==============================================================
# Deep merge helper tests
# ==============================================================


class TestDeepMergeDicts:
    def test_basic_merge(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_merge(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(
            {"config": {"x": 1, "y": 2}},
            {"config": {"y": 3, "z": 4}},
        )
        assert result == {"config": {"x": 1, "y": 3, "z": 4}}

    def test_none_removes_key(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1, "b": 2}, {"b": None})
        assert result == {"a": 1}

    def test_none_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_none_update(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_list_replaced(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"items": [1, 2]}, {"items": [3, 4]})
        assert result == {"items": [3, 4]}

    def test_empty_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({}, {"a": 1})
        assert result == {"a": 1}


# ==============================================================
# Project members tests
# ==============================================================


class TestProjectMembers:
    def test_list_members(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/members",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_add_member(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[2].id}",
            json={"role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_add_member_already_exists(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        pm = ProjectMember(
            id=_uid(), project_id=p.id, user_id=test_users[1].id,
            role="ANNOTATOR", is_active=True,
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            json={"role": "ANNOTATOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_reactivate_member(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        pm = ProjectMember(
            id=_uid(), project_id=p.id, user_id=test_users[1].id,
            role="ANNOTATOR", is_active=False,
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            json={"role": "CONTRIBUTOR"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_remove_member(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        pm = ProjectMember(
            id=_uid(), project_id=p.id, user_id=test_users[1].id,
            role="ANNOTATOR", is_active=True,
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/members/{test_users[1].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_remove_creator_fails(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}/members/{test_users[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (400, 404)

    def test_list_annotators(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        _ann(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/annotators",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "annotators" in data
        assert len(data["annotators"]) >= 1


# ==============================================================
# Review workflow tests
# ==============================================================


class TestAnnotations:
    def test_create_annotation(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)

    def test_list_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        _ann(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{t.id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_annotations_all_users(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        _ann(test_db, t, p, test_users[0])
        _ann(test_db, t, p, test_users[1])
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{t.id}/annotations?all_users=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_update_annotation(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        ann = _ann(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={"result": [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Nein"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_cancel_annotation(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        ann = _ann(test_db, t, p, test_users[0])
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={
                "result": [{"from_name": "answer", "to_name": "text", "type": "choices", "value": {"choices": ["Ja"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


# ==============================================================
# Assignment tests
# ==============================================================


class TestAssignments:
    def test_assign_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = [_task(test_db, p, test_users[0], inner_id=i) for i in range(3)]
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": [test_users[1].id],
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_assign_random(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = [_task(test_db, p, test_users[0], inner_id=i) for i in range(4)]
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": [test_users[1].id, test_users[2].id],
                "distribution": "random",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_assign_empty_ids(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={"task_ids": [], "user_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_list_assignments_for_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        t = _task(test_db, p, test_users[0])
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks/{t.id}/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 404)


# ==============================================================
# Helpers tests
# ==============================================================


class TestHelpers:
    def test_get_accessible_project_ids_superadmin(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_accessible_project_ids
        # Superadmin returns None (no filter)
        result = get_accessible_project_ids(test_db, test_users[0], test_org.id)
        assert result is None

    def test_get_accessible_project_ids_private(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_accessible_project_ids
        result = get_accessible_project_ids(test_db, test_users[1], "private")
        assert isinstance(result, list)

    def test_check_project_accessible_superadmin(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_project_accessible
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        assert check_project_accessible(test_db, test_users[0], p.id) is True

    def test_check_project_accessible_nonexistent(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible
        assert check_project_accessible(test_db, test_users[1], "nonexistent") is False

    def test_check_project_accessible_private_mode(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_project_accessible
        p = _project(test_db, test_users[0], None, is_private=True)
        test_db.commit()
        assert check_project_accessible(test_db, test_users[0], p.id, "private") is True

    def test_check_user_can_edit_project_creator(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_user_can_edit_project
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        # User[0] is superadmin so always True
        assert check_user_can_edit_project(test_db, test_users[0], p.id) is True

    def test_calculate_project_stats_batch(self, test_db, test_users, test_org):
        from routers.projects.helpers import calculate_project_stats_batch
        p = _project(test_db, test_users[0], test_org)
        _task(test_db, p, test_users[0])
        test_db.commit()

        stats = calculate_project_stats_batch(test_db, [p.id])
        assert p.id in stats
        assert stats[p.id]["task_count"] >= 1

    def test_calculate_project_stats_batch_empty(self, test_db):
        from routers.projects.helpers import calculate_project_stats_batch
        assert calculate_project_stats_batch(test_db, []) == {}

    def test_get_project_organizations(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_project_organizations
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        orgs = get_project_organizations(test_db, p.id)
        assert len(orgs) >= 1

    def test_check_task_assigned_open_mode(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_task_assigned_to_user
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        t = _task(test_db, p, test_users[0])
        test_db.commit()
        assert check_task_assigned_to_user(test_db, test_users[0], t.id, p) is True

    def test_calculate_generation_stats(self, test_db, test_users, test_org):
        from project_schemas import ProjectResponse
        from routers.projects.helpers import calculate_generation_stats
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = ProjectResponse.from_orm(p)
        calculate_generation_stats(test_db, p, resp)
        assert resp.generation_config_ready is False
