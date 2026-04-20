"""
Coverage push tests for CRUD, task, member, assignment, annotation, review,
timer, questionnaire, and serializer branches.

Targets uncovered branches across multiple routers.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def create_project_fixture(db, users, questionnaire_enabled=False,
                          num_tasks=3, is_private=False,
                          assignment_mode="open"):
    """Create a complete project with org, membership, and tasks."""
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"Project Org {uuid.uuid4().hex[:4]}",
        slug=f"proj-org-{uuid.uuid4().hex[:8]}",
        display_name="Project Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title=f"Test Project {uuid.uuid4().hex[:6]}",
        description="Test project for coverage",
        created_by=users[0].id,
        is_private=is_private,
        label_config="<View><Text name='text' value='$text'/><TextArea name='answer' toName='text'/></View>",
        assignment_mode=assignment_mode,
        questionnaire_enabled=questionnaire_enabled,
        min_annotations_per_task=1,
        maximum_annotations=2,
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        role = "ORG_ADMIN" if i == 0 else ("CONTRIBUTOR" if i < 3 else "ANNOTATOR")
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    tasks = []
    for i in range(num_tasks):
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            project_id=pid,
            data={"text": f"Task text {i}"},
            meta={"index": i},
            inner_id=i + 1,
        )
        db.add(task)
        tasks.append(task)
    db.commit()

    return {"project": p, "tasks": tasks, "org": org}


def _setup_full_project(db, users, **kwargs):
    """Wrapper around create_project_fixture for backward compatibility."""
    return create_project_fixture(db, users, **kwargs)


# =================== CRUD Tests ===================

class TestProjectCrud:
    """Test project CRUD operations."""

    def test_list_projects(self, client, test_users, test_db, auth_headers):
        _setup_full_project(test_db, test_users)
        resp = client.get("/api/projects/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    def test_list_projects_with_search(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        title = data["project"].title
        resp = client.get(f"/api/projects/?search={title[:10]}", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_list_projects_with_pagination(self, client, test_users, test_db, auth_headers):
        _setup_full_project(test_db, test_users)
        resp = client.get("/api/projects/?page=1&page_size=1", headers=auth_headers["admin"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1

    def test_get_project(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        resp = client.get(f"/api/projects/{pid}", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_get_project_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get("/api/projects/nonexistent-id", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_create_project(self, client, test_users, test_db, auth_headers):
        org = Organization(
            id=str(uuid.uuid4()),
            name="Create Project Org",
            slug=f"create-org-{uuid.uuid4().hex[:8]}",
            display_name="Create Project Org",
            created_at=datetime.utcnow(),
        )
        test_db.add(org)
        test_db.commit()

        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[0].id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        with patch("routers.projects.crud.notify_project_created"):
            resp = client.post(
                "/api/projects/",
                json={
                    "title": f"New Project {uuid.uuid4().hex[:8]}",
                    "description": "A new test project",
                    "label_config": "<View><Text name='text' value='$text'/></View>",
                },
                headers={**auth_headers["admin"], "X-Organization-Context": org.id},
            )
        assert resp.status_code in [200, 201]

    def test_update_project(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.patch(
            f"/api/projects/{pid}",
            json={"description": "Updated description"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_project_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.patch(
            "/api/projects/nonexistent",
            json={"description": "test"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_delete_project(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        with patch("routers.projects.crud.notify_project_deleted"):
            resp = client.delete(
                f"/api/projects/{pid}",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 200

    def test_delete_project_not_found(self, client, test_users, test_db, auth_headers):
        with patch("routers.projects.crud.notify_project_deleted"):
            resp = client.delete(
                "/api/projects/nonexistent",
                headers=auth_headers["admin"],
            )
        assert resp.status_code == 404


class TestDeepMergeDicts:
    """Test deep_merge_dicts utility."""

    def test_basic_merge(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_merge_dicts(base, update)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"config": {"a": 1, "b": 2}}
        update = {"config": {"b": 3, "c": 4}}
        result = deep_merge_dicts(base, update)
        assert result == {"config": {"a": 1, "b": 3, "c": 4}}

    def test_none_removal(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": None}
        result = deep_merge_dicts(base, update)
        assert result == {"a": 1}

    def test_base_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_update_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_list_replacement(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"items": [1, 2]}
        update = {"items": [3, 4, 5]}
        result = deep_merge_dicts(base, update)
        assert result == {"items": [3, 4, 5]}

    def test_empty_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({}, {"a": 1})
        assert result == {"a": 1}


# =================== Task Tests ===================

class TestTaskEndpoints:
    """Test task listing and management."""

    def test_list_tasks(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    def test_list_tasks_pagination(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/tasks?page=1&page_size=2",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

    def test_list_tasks_only_labeled(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        data["tasks"][0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{pid}/tasks?only_labeled=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_tasks_only_unlabeled(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/tasks?only_unlabeled=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_tasks_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_task_detail(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        tid = data["tasks"][0].id

        resp = client.get(
            f"/api/projects/tasks/{tid}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_get_next_task(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/next",
            headers=auth_headers["admin"],
        )
        # 200 if task found, 404 if no tasks available
        assert resp.status_code in [200, 404]

    def test_bulk_delete_tasks(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"][:2]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/bulk-delete",
            json={"task_ids": task_ids},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_skip_task(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        tid = data["tasks"][0].id

        resp = client.post(
            f"/api/projects/{pid}/tasks/{tid}/skip",
            json={"comment": "Too complex"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Member Tests ===================

class TestMemberEndpoints:
    """Test project member management."""

    def test_list_members(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        members = resp.json()
        assert isinstance(members, list)
        assert len(members) >= 1

    def test_list_members_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/members",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# =================== Assignment Tests ===================

class TestAssignmentEndpoints:
    """Test task assignment endpoints."""

    def test_assign_tasks_manual(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"][:2]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[2].id],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_assign_tasks_round_robin(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[1].id, test_users[2].id],
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_assign_tasks_random(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[1].id],
                "distribution": "random",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_assignments(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        tid = data["tasks"][0].id

        # Create an assignment first
        test_db.add(TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=tid,
            user_id=test_users[2].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{pid}/tasks/{tid}/assignments",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_unassign_task(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        tid = data["tasks"][0].id

        # Create assignment
        assignment_id = str(uuid.uuid4())
        test_db.add(TaskAssignment(
            id=assignment_id,
            task_id=tid,
            user_id=test_users[2].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{pid}/tasks/{tid}/assignments/{assignment_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Annotation Tests ===================

class TestAnnotationEndpoints:
    """Test annotation creation and management."""

    def test_create_annotation(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        tid = data["tasks"][0].id

        resp = client.post(
            f"/api/projects/tasks/{tid}/annotations",
            json={
                "result": [{"from_name": "answer", "type": "textarea", "to_name": "text",
                            "value": {"text": ["My answer"]}}],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_annotation_with_lead_time(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        tid = data["tasks"][1].id

        resp = client.post(
            f"/api/projects/tasks/{tid}/annotations",
            json={
                "result": [{"from_name": "answer", "type": "textarea", "to_name": "text",
                            "value": {"text": ["Another answer"]}}],
                "lead_time": 45.5,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_annotation_task_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/tasks/nonexistent/annotations",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_list_annotations(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        tid = data["tasks"][0].id

        # Create an annotation
        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=tid,
            project_id=pid,
            result=[{"from_name": "answer", "type": "textarea", "value": {"text": ["test"]}}],
            completed_by=test_users[0].id,
            was_cancelled=False,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tid}/annotations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_annotation(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        pid = data["project"].id
        tid = data["tasks"][0].id

        ann_id = str(uuid.uuid4())
        test_db.add(Annotation(
            id=ann_id,
            task_id=tid,
            project_id=pid,
            result=[{"from_name": "answer", "type": "textarea", "value": {"text": ["old"]}}],
            completed_by=test_users[0].id,
            was_cancelled=False,
        ))
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann_id}",
            json={
                "result": [{"from_name": "answer", "type": "textarea", "value": {"text": ["updated"]}}],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Review Tests ===================

class TestQuestionnaireEndpoints:
    """Test questionnaire endpoints."""

    def test_list_questionnaire_responses(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, questionnaire_enabled=True)
        pid = data["project"].id

        resp = client.get(
            f"/api/projects/{pid}/questionnaire-responses",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_questionnaire_responses_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/questionnaire-responses",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# =================== Serializer Tests ===================

class TestSerializers:
    """Test export serializer functions."""

    def test_serialize_task_data_mode(self):
        from routers.projects.serializers import serialize_task

        class FakeTask:
            id = "t1"
            inner_id = 1
            data = {"text": "hello"}
            meta = {"tags": ["a"]}
            is_labeled = True
            created_at = datetime(2024, 1, 1)
            updated_at = None

        result = serialize_task(FakeTask(), mode="data")
        assert result["id"] == "t1"
        assert "project_id" not in result

    def test_serialize_task_full_mode(self):
        from routers.projects.serializers import serialize_task

        class FakeTask:
            id = "t1"
            inner_id = 1
            data = {"text": "hello"}
            meta = None
            is_labeled = False
            created_at = datetime(2024, 1, 1)
            updated_at = datetime(2024, 1, 2)
            project_id = "p1"
            created_by = "u1"
            updated_by = None
            total_annotations = 2
            cancelled_annotations = 0
            comment_count = 1
            unresolved_comment_count = 0
            last_comment_updated_at = None
            comment_authors = None
            file_upload_id = None

        result = serialize_task(FakeTask(), mode="full", total_generations=5)
        assert result["project_id"] == "p1"
        assert result["total_generations"] == 5

    def test_serialize_annotation_data_mode(self):
        from routers.projects.serializers import serialize_annotation

        class FakeAnn:
            id = "a1"
            result = [{"type": "textarea"}]
            completed_by = "u1"
            created_at = datetime(2024, 1, 1)
            updated_at = None
            was_cancelled = False
            ground_truth = False
            lead_time = 30.5
            active_duration_ms = 25000
            focused_duration_ms = 20000
            tab_switches = 2

        result = serialize_annotation(FakeAnn(), mode="data")
        assert "questionnaire_response" in result
        assert result["questionnaire_response"] is None

    def test_serialize_annotation_full_mode(self):
        from routers.projects.serializers import serialize_annotation

        class FakeAnn:
            id = "a1"
            result = []
            completed_by = "u1"
            created_at = None
            updated_at = None
            was_cancelled = False
            ground_truth = True
            lead_time = None
            active_duration_ms = None
            focused_duration_ms = None
            tab_switches = None
            task_id = "t1"
            project_id = "p1"
            draft = {"partial": True}
            prediction_scores = None

        result = serialize_annotation(FakeAnn(), mode="full")
        assert result["task_id"] == "t1"
        assert result["draft"] == {"partial": True}

    def test_serialize_generation_data_mode(self):
        from routers.projects.serializers import serialize_generation

        class FakeGen:
            id = "g1"
            model_id = "gpt-4o"
            response_content = "Generated text"
            case_data = '{"text": "input"}'
            created_at = datetime(2024, 1, 1)
            response_metadata = {"temperature": 0.5}

        result = serialize_generation(FakeGen(), mode="data", evaluations=[{"id": "e1"}])
        assert result["evaluations"] == [{"id": "e1"}]

    def test_serialize_generation_full_mode(self):
        from routers.projects.serializers import serialize_generation

        class FakeGen:
            id = "g1"
            model_id = "gpt-4o"
            response_content = "text"
            case_data = "{}"
            created_at = None
            response_metadata = None
            generation_id = "rg1"
            task_id = "t1"
            usage_stats = {"tokens": 100}
            status = "completed"
            error_message = None

        result = serialize_generation(FakeGen(), mode="full")
        assert result["generation_id"] == "rg1"
        assert result["usage_stats"] == {"tokens": 100}

    def test_serialize_task_evaluation_data_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        class FakeTE:
            id = "te1"
            annotation_id = None
            field_name = "config1:answer"
            answer_type = "text"
            ground_truth = {"value": "gt"}
            prediction = {"value": "pred"}
            metrics = {"bleu": 0.7}
            passed = True
            confidence_score = 0.9
            error_message = None
            processing_time_ms = 100
            created_at = datetime(2024, 1, 1)
            evaluation_id = "er1"

        class FakeER:
            model_id = "gpt-4o"

        result = serialize_task_evaluation(
            FakeTE(), mode="data",
            eval_run=FakeER(),
            judge_model_lookup={("er1", "config1"): "gpt-4o-judge"},
        )
        assert result["evaluated_model"] == "gpt-4o"
        assert result["judge_model"] == "gpt-4o-judge"
        assert result["evaluation_run_id"] == "er1"

    def test_serialize_task_evaluation_full_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        class FakeTE:
            id = "te1"
            annotation_id = "a1"
            field_name = "answer"
            answer_type = "text"
            ground_truth = {"value": "gt"}
            prediction = {"value": "pred"}
            metrics = {"exact": 1.0}
            passed = True
            confidence_score = 0.95
            error_message = None
            processing_time_ms = 50
            created_at = None
            evaluation_id = "er1"
            task_id = "t1"
            generation_id = "g1"

        result = serialize_task_evaluation(FakeTE(), mode="full")
        assert result["evaluation_id"] == "er1"
        assert result["task_id"] == "t1"
        assert result["generation_id"] == "g1"

    def test_serialize_evaluation_run_data_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        class FakeER:
            id = "er1"
            model_id = "gpt-4o"
            evaluation_type_ids = ["test"]
            metrics = {"acc": 0.9}
            status = "completed"
            samples_evaluated = 10
            created_at = datetime(2024, 1, 1)
            completed_at = datetime(2024, 1, 1)
            eval_metadata = {"type": "automated"}
            error_message = None
            has_sample_results = True
            created_by = "u1"

        result = serialize_evaluation_run(FakeER(), mode="data")
        assert result["eval_metadata"] == {"type": "automated"}
        assert result["has_sample_results"] is True

    def test_serialize_evaluation_run_full_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        class FakeER:
            id = "er1"
            model_id = "gpt-4o"
            evaluation_type_ids = ["test"]
            metrics = {"acc": 0.9}
            status = "completed"
            samples_evaluated = 10
            created_at = None
            completed_at = None
            eval_metadata = None
            error_message = "test error"
            has_sample_results = False
            created_by = "u1"
            project_id = "p1"
            task_id = "t1"

        result = serialize_evaluation_run(FakeER(), mode="full")
        assert result["project_id"] == "p1"
        assert result["task_id"] == "t1"

    def test_build_judge_model_lookup_new_format(self):
        from routers.projects.serializers import build_judge_model_lookup

        class FakeER:
            id = "er1"
            eval_metadata = {
                "judge_models": {"config1": "gpt-4o-judge", "config2": "claude-3-judge"},
            }

        result = build_judge_model_lookup([FakeER()])
        assert result[("er1", "config1")] == "gpt-4o-judge"
        assert result[("er1", "config2")] == "claude-3-judge"

    def test_build_judge_model_lookup_old_format(self):
        from routers.projects.serializers import build_judge_model_lookup

        class FakeER:
            id = "er1"
            eval_metadata = {
                "evaluation_configs": [
                    {"id": "config1", "metric_parameters": {"judge_model": "gpt-4o-old"}},
                ],
            }

        result = build_judge_model_lookup([FakeER()])
        assert result[("er1", "config1")] == "gpt-4o-old"

    def test_build_evaluation_indexes(self):
        from routers.projects.serializers import build_evaluation_indexes

        class FakeTE:
            def __init__(self, task_id, gen_id):
                self.task_id = task_id
                self.generation_id = gen_id

        tes = [FakeTE("t1", "g1"), FakeTE("t1", None), FakeTE("t2", "g2")]
        by_task, by_gen = build_evaluation_indexes(tes)
        assert len(by_task["t1"]) == 2
        assert len(by_task["t2"]) == 1
        assert len(by_gen["g1"]) == 1
        assert "g2" in by_gen
        assert None not in by_gen
