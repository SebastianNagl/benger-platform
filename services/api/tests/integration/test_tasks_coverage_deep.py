"""
Integration tests targeting uncovered handler body code in routers/projects/tasks.py.

Covers lines: 69-225 (list_project_tasks), 257-557 (get_next_task),
576-618 (get_task), 637-665 (update_task_metadata), 686-723 (bulk_update_metadata),
754-847 (update_task_data), 860-909 (bulk_delete_tasks), 928-1087 (bulk_export_tasks),
1117-1166 (bulk_archive), 1191-1225 (skip_task), 1254-1301 (extract_fields),
1333-1368 (get_task_data_fields)

Most handlers in routers/projects/tasks.py migrated to the async DB lane
(``Depends(get_async_db)``); their tests seed via ``async_test_db`` and drive
the surface through ``async_test_client`` with ``require_user`` overridden
per-test (the sync auth path can't see the async test transaction). The one
exception is ``bulk_export_tasks`` — still a sync ``def`` handler on
``Depends(get_db)`` — so ``TestBulkExportTasks`` stays on ``client`` /
``test_db`` with the sync seeding helpers.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Tasks {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        assignment_mode=kwargs.get("assignment_mode", "open"),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        maximum_annotations=kwargs.get("maximum_annotations", 0),
    )
    db.add(p)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    return p


def _tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, lead_time=10.0, cancelled=False):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=cancelled,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    db.flush()
    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, run_index=i,
            case_data=json.dumps(t.data),
            response_content=f"Generated answer #{i}",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# ASYNC HELPERS (for the async-migrated handler tests)
# ===================================================================

@contextmanager
def _as_user(db_user):
    auth_user = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email,
        name=db_user.name, is_superadmin=db_user.is_superadmin,
        is_active=True, email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_users(db):
    specs = [("Test Admin", True, "admin"), ("Test Contributor", False, "contributor"),
             ("Test Annotator", False, "annotator"), ("Test Org Admin", False, "orgadmin")]
    users = []
    for name, is_superadmin, tag in specs:
        u = User(id=_uid(), username=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 email=f"{tag}-{uuid.uuid4().hex[:8]}@test.com", name=name,
                 is_superadmin=is_superadmin, is_active=True, email_verified=True,
                 created_at=datetime.now(timezone.utc))
        db.add(u)
        users.append(u)
    await db.flush()
    return users


async def _make_org(db, users):
    org = Organization(id=_uid(), name="Test Organization",
                       slug=f"test-org-{uuid.uuid4().hex[:8]}",
                       display_name="Test Organization Display", created_at=datetime.utcnow())
    db.add(org)
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, u in enumerate(users[:4]):
        db.add(OrganizationMembership(id=_uid(), user_id=u.id, organization_id=org.id,
               role=roles[i], joined_at=datetime.utcnow()))
    await db.flush()
    return org


async def _project_async(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Tasks {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        assignment_mode=kwargs.get("assignment_mode", "open"),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        maximum_annotations=kwargs.get("maximum_annotations", 0),
    )
    db.add(p)
    await db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()
    return p


async def _tasks_async(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _annotations_async(db, project, tasks, user_id, lead_time=10.0, cancelled=False):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=cancelled,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _generations_async(db, project, tasks, admin, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by=admin.id,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    await db.flush()
    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, run_index=i,
            case_data=json.dumps(t.data),
            response_content=f"Generated answer #{i}",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    await db.flush()
    return gens


# ===================================================================
# LIST PROJECT TASKS (lines 69-225)
# ===================================================================

@pytest.mark.integration
class TestListProjectTasks:
    """Cover list_project_tasks handler body."""

    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, async_test_client, async_test_db):
        """List tasks for a project."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        """List tasks with pagination."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=3",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert len(data["items"]) == 3
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db):
        """List only labeled tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        tasks[0].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db):
        """List only unlabeled tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_my_annotations(self, async_test_client, async_test_db):
        """List tasks excluding ones I have annotated."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _annotations_async(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_with_generations(self, async_test_client, async_test_db):
        """List tasks that have generation counts."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _generations_async(async_test_db, p, tasks, users[0])
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert "total_generations" in item

    @pytest.mark.asyncio
    async def test_list_tasks_project_not_found(self, async_test_client, async_test_db):
        """List tasks for non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/tasks")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks_with_assignments(self, async_test_client, async_test_db):
        """List tasks that have task assignments."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        for t in tasks[:2]:
            assign = TaskAssignment(
                id=_uid(), task_id=t.id, user_id=users[1].id,
                assigned_by=users[0].id, status="assigned",
            )
            async_test_db.add(assign)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3


# ===================================================================
# GET NEXT TASK (lines 257-557)
# ===================================================================

@pytest.mark.integration
class TestGetNextTask:
    """Cover get_next_task handler body for different assignment modes."""

    @pytest.mark.asyncio
    async def test_next_task_open_mode(self, async_test_client, async_test_db):
        """Get next task in open mode."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="open")
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["total_tasks"] == 5

    @pytest.mark.asyncio
    async def test_next_task_all_annotated(self, async_test_client, async_test_db):
        """Get next task when all tasks are annotated by current user."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="open")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _annotations_async(async_test_db, p, tasks, users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    @pytest.mark.asyncio
    async def test_next_task_project_not_found(self, async_test_client, async_test_db):
        """Get next task for non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    @pytest.mark.asyncio
    async def test_next_task_manual_mode_no_assignments(self, async_test_client, async_test_db):
        """Get next task in manual mode with no assignments."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    @pytest.mark.asyncio
    async def test_next_task_manual_mode_with_assignment(self, async_test_client, async_test_db):
        """Get next task in manual mode with a task assigned."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        assign = TaskAssignment(
            id=_uid(), task_id=tasks[0].id, user_id=users[0].id,
            assigned_by=users[0].id, status="assigned",
        )
        async_test_db.add(assign)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    @pytest.mark.asyncio
    async def test_next_task_auto_mode(self, async_test_client, async_test_db):
        """Get next task in auto mode creates assignment on the fly."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto")
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    @pytest.mark.asyncio
    async def test_next_task_auto_mode_resume_existing(self, async_test_client, async_test_db):
        """Get next task in auto mode resumes existing assignment."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        assign = TaskAssignment(
            id=_uid(), task_id=tasks[1].id, user_id=users[0].id,
            assigned_by=users[0].id, status="in_progress",
        )
        async_test_db.add(assign)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    @pytest.mark.asyncio
    async def test_next_task_randomized_order(self, async_test_client, async_test_db):
        """Get next task with randomized order."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, randomize_task_order=True)
        await _tasks_async(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        assert resp.json()["task"] is not None

    @pytest.mark.asyncio
    async def test_next_task_with_metrics(self, async_test_client, async_test_db):
        """Get next task returns user-specific completion metrics."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _annotations_async(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_completed_tasks" in data
        assert data["total_tasks"] == 5

    @pytest.mark.asyncio
    async def test_next_task_auto_mode_max_annotations(self, async_test_client, async_test_db):
        """Auto mode respects maximum_annotations setting."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto", maximum_annotations=1)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        # Annotate all by another user
        await _annotations_async(async_test_db, p, tasks, users[1].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200
        # All tasks at max, so should be None
        data = resp.json()
        assert data["task"] is None


# ===================================================================
# GET TASK (lines 576-618)
# ===================================================================

@pytest.mark.integration
class TestGetTask:
    """Cover get_task handler body."""

    @pytest.mark.asyncio
    async def test_get_task_detail(self, async_test_client, async_test_db):
        """Get task detail."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{tasks[0].id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id
        assert "data" in data
        assert "meta" in data

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, async_test_client, async_test_db):
        """Get non-existent task."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{_uid()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_with_generation_count(self, async_test_client, async_test_db):
        """Get task that has generations."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await _generations_async(async_test_db, p, tasks, users[0])
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{tasks[0].id}")
        assert resp.status_code == 200
        assert resp.json()["total_generations"] >= 1


# ===================================================================
# UPDATE TASK METADATA (lines 637-665)
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskMetadata:
    """Cover update_task_metadata handler body."""

    @pytest.mark.asyncio
    async def test_update_metadata_merge(self, async_test_client, async_test_db):
        """Update task metadata with merge mode."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        tasks[0].meta = {"existing": "value"}
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tasks[0].id}/metadata?merge=true",
                json={"new_key": "new_value"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["existing"] == "value"
        assert data["meta"]["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_update_metadata_replace(self, async_test_client, async_test_db):
        """Update task metadata with replace mode."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        tasks[0].meta = {"old_key": "old_value"}
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tasks[0].id}/metadata?merge=false",
                json={"replaced": "data"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "old_key" not in data["meta"]
        assert data["meta"]["replaced"] == "data"

    @pytest.mark.asyncio
    async def test_update_metadata_null_meta(self, async_test_client, async_test_db):
        """Update metadata when task has null meta."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        tasks[0].meta = None
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tasks[0].id}/metadata?merge=true",
                json={"key": "value"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_metadata_not_found(self, async_test_client, async_test_db):
        """Update metadata for non-existent task."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{_uid()}/metadata",
                json={"key": "value"},
            )
        assert resp.status_code == 404


# ===================================================================
# BULK UPDATE TASK METADATA (lines 686-723)
# ===================================================================

@pytest.mark.integration
class TestBulkUpdateTaskMetadata:
    """Cover bulk_update_task_metadata handler body."""

    @pytest.mark.asyncio
    async def test_bulk_metadata_merge(self, async_test_client, async_test_db):
        """Bulk update metadata for multiple tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=true",
                json={
                    "task_ids": [t.id for t in tasks],
                    "metadata": {"tag": "important"},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 3

    @pytest.mark.asyncio
    async def test_bulk_metadata_replace(self, async_test_client, async_test_db):
        """Bulk replace metadata."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=false",
                json={
                    "task_ids": [t.id for t in tasks],
                    "metadata": {"replaced": True},
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_metadata_not_found(self, async_test_client, async_test_db):
        """Bulk update with non-existent task IDs."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata",
                json={
                    "task_ids": [_uid()],
                    "metadata": {"key": "val"},
                },
            )
        assert resp.status_code == 404


# ===================================================================
# UPDATE TASK DATA (lines 754-847)
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskData:
    """Cover update_task_data handler body."""

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db):
        """Update task data as admin."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated text"}},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["text"] == "Updated text"

    @pytest.mark.asyncio
    async def test_update_task_data_non_admin(self, async_test_client, async_test_db):
        """Non-admin cannot update task data."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[1]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated"}},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_task_data_not_found(self, async_test_client, async_test_db):
        """Update non-existent task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{_uid()}",
                json={"data": {"text": "test"}},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_data_no_data_field(self, async_test_client, async_test_db):
        """Update task with no data field should fail."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {}},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_task_data_creates_audit_log(self, async_test_client, async_test_db):
        """Update task data creates audit log entry."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Audited update"}},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "audit_log" in data["meta"]

    @pytest.mark.asyncio
    async def test_update_task_project_not_found(self, async_test_client, async_test_db):
        """Update task in non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{_uid()}/tasks/{_uid()}",
                json={"data": {"text": "test"}},
            )
        assert resp.status_code == 404


# ===================================================================
# BULK DELETE TASKS (lines 860-909)
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteTasks:
    """Cover bulk_delete_tasks handler body."""

    @pytest.mark.asyncio
    async def test_bulk_delete(self, async_test_client, async_test_db):
        """Bulk delete tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": [tasks[0].id, tasks[1].id]},
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_tasks(self, async_test_client, async_test_db):
        """Bulk delete with non-existent task IDs."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": [_uid(), _uid()]},
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_project_not_found(self, async_test_client, async_test_db):
        """Bulk delete in non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/tasks/bulk-delete",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 404


# ===================================================================
# BULK EXPORT TASKS (lines 928-1087)
# ===================================================================
# NOTE: bulk_export_tasks is still a sync `def` handler on Depends(get_db),
# so this class STAYS SYNC — client / test_db / auth_headers / test_org / _h
# and the sync seeding helpers (_project, _tasks, _annotations, _generations).

@pytest.mark.integration
class TestBulkExportTasks:
    """Cover bulk_export_tasks handler body."""

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks as JSON."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks as CSV."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_with_generations_and_evals(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks with full data graph."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = EvaluationRun(
            id=_uid(), project_id=p.id, model_id="gpt-4o",
            evaluation_type_ids=["accuracy"], metrics={"accuracy": 0.9},
            status="completed", samples_evaluated=3,
            created_by=test_users[0].id,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(er)
        test_db.flush()
        # Migration 043 made TaskEvaluation.judge_run_id NOT NULL; use the
        # catch-all judge-run shape that orphan backfill uses.
        judge_run = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        test_db.add(judge_run)
        test_db.flush()
        for i, t in enumerate(tasks):
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id,
                judge_run_id=judge_run.id,
                task_id=t.id,
                generation_id=gens[i].id, field_name="answer",
                answer_type="choices", ground_truth={"value": "Ja"},
                prediction={"value": "Ja"}, metrics={"accuracy": 1.0}, passed=True,
            )
            test_db.add(te)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_tsv_format(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks in TSV format."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "tsv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export in non-existent project."""
        resp = client.post(
            f"/api/projects/{_uid()}/tasks/bulk-export",
            json={"task_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK ARCHIVE TASKS (lines 1117-1166)
# ===================================================================

@pytest.mark.integration
class TestBulkArchiveTasks:
    """Cover bulk_archive_tasks handler body."""

    @pytest.mark.asyncio
    async def test_bulk_archive(self, async_test_client, async_test_db):
        """Bulk archive tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-archive",
                json={"task_ids": [tasks[0].id, tasks[1].id]},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_archive_project_not_found(self, async_test_client, async_test_db):
        """Bulk archive in non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/tasks/bulk-archive",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 404


# ===================================================================
# SKIP TASK (lines 1191-1225)
# ===================================================================

@pytest.mark.integration
class TestSkipTask:
    """Cover skip_task handler body."""

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db):
        """Skip a task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Too difficult"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_task_no_comment(self, async_test_client, async_test_db):
        """Skip a task without comment."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_task_not_found(self, async_test_client, async_test_db):
        """Skip non-existent task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{_uid()}/skip",
                json={},
            )
        assert resp.status_code == 404


# ===================================================================
# TASK FIELDS (lines 1254-1368)
# ===================================================================

@pytest.mark.integration
class TestTaskDataFields:
    """Cover get_task_data_fields handler body."""

    @pytest.mark.asyncio
    async def test_get_task_fields(self, async_test_client, async_test_db):
        """Get task data fields for a project."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code == 200
        data = resp.json()
        assert "fields" in data

    @pytest.mark.asyncio
    async def test_get_task_fields_nested_data(self, async_test_client, async_test_db):
        """Get task fields with nested data structures."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "hello", "metadata": {"source": "corpus", "year": 2024}},
            inner_id=1, created_by=users[0].id,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_task_fields_empty_project(self, async_test_client, async_test_db):
        """Get task fields for a project with no tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_task_fields_not_found(self, async_test_client, async_test_db):
        """Get task fields for non-existent project."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/task-fields")
        assert resp.status_code == 404
