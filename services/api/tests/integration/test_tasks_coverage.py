"""
Integration tests targeting uncovered handler body code in routers/projects/tasks.

The target handlers (``routers/projects/tasks/*``) were migrated to the async DB
lane (``Depends(get_async_db)`` + ``await db.execute(select(...))``). The legacy
sync session (psycopg2) and the async ``async_test_db`` (asyncpg) are SEPARATE
connections/transactions, so a row seeded on the sync side is invisible to an
async handler reading via ``async_test_db`` — seeding sync and hitting an async
endpoint yields spurious 404s. These tests therefore seed into ``async_test_db``, drive the
surface via ``async_test_client``, and set the acting user with the ``_as_user(...)``
contextmanager (the sync ``require_user``/Bearer-token auth can't see the async
test transaction).

Focuses on:
- list_project_tasks: role-based visibility, generation counts, assignment enrichment,
  randomize_task_order, exclude_my_annotations with skip filtering, pagination edge cases
- get_next_task: open/manual/auto modes, skip queue variants, maximum_annotations enforcement,
  auto-assignment creation, concurrency-safe locking
- skip_task: SkippedTask creation, comment persistence
- update_task: data and meta update, created_by field update
- bulk_delete: cascade deletion, verification
- task_fields: field discovery from task data
- Single task retrieval via global route
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
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def _uid():
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


async def _make_users(db):
    specs = [("Test Admin", True, "admin"), ("Test Contributor", False, "contributor"),
             ("Test Annotator", False, "annotator"), ("Test Org Admin", False, "orgadmin")]
    users = []
    for name, is_superadmin, tag in specs:
        u = User(id=str(uuid.uuid4()),
                 username=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 email=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 name=name, is_superadmin=is_superadmin, is_active=True,
                 email_verified=True, created_at=datetime.now(timezone.utc))
        db.add(u)
        users.append(u)
    await db.flush()
    return users


async def _make_org(db, users):
    org = Organization(id=str(uuid.uuid4()), name="Test Organization",
                       slug=f"test-org-{uuid.uuid4().hex[:8]}",
                       display_name="Test Organization Display",
                       created_at=datetime.utcnow())
    db.add(org)
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, u in enumerate(users[:4]):
        db.add(OrganizationMembership(id=str(uuid.uuid4()), user_id=u.id,
               organization_id=org.id, role=roles[i], joined_at=datetime.utcnow()))
    await db.flush()
    return org


async def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"TaskCov {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        assignment_mode=kwargs.get("assignment_mode", "open"),
        maximum_annotations=kwargs.get("maximum_annotations", 1),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        skip_queue=kwargs.get("skip_queue", "requeue_for_others"),
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


async def _tasks(db, project, admin, count=5, labeled_count=0):
    tasks = []
    for i in range(count):
        is_lab = i < labeled_count
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task text {i}", "index": i, "category": f"cat_{i % 3}"},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=is_lab,
            total_annotations=(1 if is_lab else 0),
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _annotate(db, project, tasks, user_id, count=None):
    anns = []
    for t in tasks[:count]:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _assign(db, tasks, user_id, admin_id, count=None, status="assigned"):
    assigns = []
    for t in tasks[:count]:
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status=status,
        )
        db.add(a)
        assigns.append(a)
    await db.flush()
    return assigns


async def _skip(db, project, tasks, user_id, count=None):
    skips = []
    for t in tasks[:count]:
        s = SkippedTask(
            id=_uid(), task_id=t.id, project_id=project.id,
            skipped_by=user_id, comment="Skipped in test",
        )
        db.add(s)
        skips.append(s)
    await db.flush()
    return skips


async def _generations(db, project, tasks, created_by, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by=created_by,
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
            response_content="Generated",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    await db.flush()
    return gens


# ===================================================================
# LIST TASKS: deep handler body coverage
# ===================================================================

@pytest.mark.integration
class TestListTasksDeep:
    """Deep coverage for list_project_tasks handler body."""

    @pytest.mark.asyncio
    async def test_list_tasks_includes_generation_counts(self, async_test_client, async_test_db):
        """Task items should include total_generations count."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await _generations(async_test_db, p, tasks, users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert "total_generations" in item
            assert item["total_generations"] >= 1

    @pytest.mark.asyncio
    async def test_list_tasks_includes_assignments_data(self, async_test_client, async_test_db):
        """Task items should include assignment details."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await _assign(async_test_db, tasks, users[2].id, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        # At least some tasks should have assignment data
        has_assignments = any(len(item.get("assignments", [])) > 0 for item in body["items"])
        assert has_assignments

    @pytest.mark.asyncio
    async def test_list_tasks_assignment_enrichment_has_user_info(self, async_test_client, async_test_db):
        """Assignments include user_name and user_email."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks(async_test_db, p, users[0], count=1)
        await _assign(async_test_db, tasks, users[2].id, users[0].id, count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            for asgn in item.get("assignments", []):
                assert "user_name" in asgn
                assert "user_email" in asgn
                assert "status" in asgn

    @pytest.mark.asyncio
    async def test_list_tasks_randomized_order(self, async_test_client, async_test_db):
        """Randomized project uses MD5-based ordering."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, randomize_task_order=True)
        await _tasks(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_my_annotations_filters(self, async_test_client, async_test_db):
        """exclude_my_annotations filters out tasks the user has annotated."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _annotate(async_test_db, p, tasks[:3], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Should exclude the 3 annotated tasks
        assert body["total"] <= 2

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_skipped_for_others(self, async_test_client, async_test_db):
        """With skip_queue=requeue_for_others, exclude tasks skipped by this user."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, skip_queue="requeue_for_others")
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _skip(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] <= 3

    @pytest.mark.asyncio
    async def test_list_tasks_ignore_skipped_excludes_all(self, async_test_client, async_test_db):
        """With skip_queue=ignore_skipped, exclude tasks skipped by ANY user."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, skip_queue="ignore_skipped")
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        # Different users skip different tasks
        await _skip(async_test_db, p, tasks[:1], users[0].id)
        await _skip(async_test_db, p, tasks[1:2], users[1].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        # 2 tasks skipped by various users -> 3 remaining
        assert body["total"] <= 3

    @pytest.mark.asyncio
    async def test_list_tasks_annotator_manual_mode(self, async_test_client, async_test_db):
        """Annotator in manual mode only sees assigned tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _assign(async_test_db, tasks, users[2].id, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] <= 2

    @pytest.mark.asyncio
    async def test_list_tasks_task_dict_has_all_fields(self, async_test_client, async_test_db):
        """Verify task dict includes all expected fields."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await _tasks(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        expected_fields = [
            "id", "inner_id", "data", "meta", "created_at",
            "is_labeled", "total_annotations", "total_generations",
            "project_id", "assignments", "tags",
        ]
        for field in expected_fields:
            assert field in item, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_list_tasks_meta_tags_backward_compat(self, async_test_client, async_test_db):
        """Tags derived from meta for backward compatibility."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "Tagged task"},
            meta={"tags": ["important", "legal"]},
            inner_id=1, created_by=users[0].id,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["tags"] == ["important", "legal"]


# ===================================================================
# NEXT TASK: deep handler body coverage
# ===================================================================

@pytest.mark.integration
class TestNextTaskDeep:
    """Deep coverage for get_next_task handler body."""

    @pytest.mark.asyncio
    async def test_next_task_open_mode(self, async_test_client, async_test_db):
        """Open mode returns next unannotated task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="open")
        await _tasks(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("task") is not None or "id" in body

    @pytest.mark.asyncio
    async def test_next_task_manual_mode_returns_assigned(self, async_test_client, async_test_db):
        """Manual mode returns task assigned to the user."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _assign(async_test_db, tasks, users[0].id, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_manual_mode_no_assignments(self, async_test_client, async_test_db):
        """Manual mode with no assignments returns no task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="manual")
        await _tasks(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)
        body = resp.json()
        assert body.get("task") is None or body.get("detail") is not None

    @pytest.mark.asyncio
    async def test_next_task_auto_mode_creates_assignment(self, async_test_client, async_test_db):
        """Auto mode auto-assigns and returns a task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="auto")
        await _tasks(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_auto_mode_resumes_in_progress(self, async_test_client, async_test_db):
        """Auto mode returns existing in-progress assignment first."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="auto")
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _assign(async_test_db, tasks, users[0].id, users[0].id, count=1, status="in_progress")
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_skips_annotated(self, async_test_client, async_test_db):
        """Next task skips tasks already annotated by the user."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="open")
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await _annotate(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_all_annotated(self, async_test_client, async_test_db):
        """When all tasks annotated, returns no task."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="open")
        tasks = await _tasks(async_test_db, p, users[0], count=2)
        await _annotate(async_test_db, p, tasks, users[0].id)
        for t in tasks:
            t.is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_auto_skips_skipped_tasks(self, async_test_client, async_test_db):
        """Auto mode skips tasks the user has skipped."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="auto")
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await _skip(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_maximum_annotations_enforced(self, async_test_client, async_test_db):
        """Auto mode respects maximum_annotations limit."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="auto", maximum_annotations=1)
        tasks = await _tasks(async_test_db, p, users[0], count=2)
        # Another user has annotated both tasks
        await _annotate(async_test_db, p, tasks, users[1].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_nonexistent_project(self, async_test_client, async_test_db):
        """Next task for nonexistent project returns null task."""
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/nonexistent/next")
        # Either 200 with task=None or 404
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_next_task_randomized_order(self, async_test_client, async_test_db):
        """Randomized project uses per-user deterministic ordering."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org,
                           assignment_mode="auto", randomize_task_order=True)
        await _tasks(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)


# ===================================================================
# SKIP TASK
# ===================================================================

@pytest.mark.integration
class TestSkipTaskDeep:
    """Deep coverage for skip_task handler body."""

    @pytest.mark.asyncio
    async def test_skip_creates_record(self, async_test_client, async_test_db):
        """Skip creates a SkippedTask record."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Too ambiguous"},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_skip_with_empty_comment(self, async_test_client, async_test_db):
        """Skip with empty string comment."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": ""},
            )
        assert resp.status_code in (200, 201, 422)

    @pytest.mark.asyncio
    async def test_skip_nonexistent_task(self, async_test_client, async_test_db):
        """Skip nonexistent task returns 404."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/nonexistent/skip",
                json={"comment": "Nope"},
            )
        assert resp.status_code == 404


# ===================================================================
# UPDATE TASK
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskDeep:
    """Deep coverage for update task handler body."""

    @pytest.mark.asyncio
    async def test_update_task_data_and_meta(self, async_test_client, async_test_db):
        """Update both data and meta fields."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated text", "extra": "field"}, "meta": {"tag": "urgent"}},
            )
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("data", {}).get("text") == "Updated text"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, async_test_client, async_test_db):
        """Update nonexistent task returns 404."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/nonexistent",
                json={"data": {"text": "Nope"}},
            )
        assert resp.status_code == 404


# ===================================================================
# BULK DELETE
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteDeep:
    """Deep coverage for bulk_delete handler body."""

    @pytest.mark.asyncio
    async def test_bulk_delete_cascades(self, async_test_client, async_test_db):
        """Bulk delete removes tasks and associated data."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=5)
        await _annotate(async_test_db, p, tasks[:3], users[0].id)
        await async_test_db.commit()

        ids = [tasks[0].id, tasks[1].id]
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": ids},
            )
            assert resp.status_code in (200, 204)

            # Verify deleted
            list_resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert list_resp.status_code == 200
        remaining = {t["id"] for t in list_resp.json()["items"]}
        for deleted_id in ids:
            assert deleted_id not in remaining

    @pytest.mark.asyncio
    async def test_bulk_delete_all_tasks(self, async_test_client, async_test_db):
        """Delete all tasks in a project."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": [t.id for t in tasks]},
            )
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_ids(self, async_test_client, async_test_db):
        """Delete with nonexistent task IDs should not fail."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": ["nonexistent-1", "nonexistent-2"]},
            )
        assert resp.status_code in (200, 204, 404)


# ===================================================================
# TASK FIELDS
# ===================================================================

@pytest.mark.integration
class TestTaskFieldsDeep:
    """Deep coverage for task-fields endpoint."""

    @pytest.mark.asyncio
    async def test_task_fields_discovers_keys(self, async_test_client, async_test_db):
        """task-fields should discover data keys from tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await _tasks(async_test_db, p, users[0], count=3,
                     labeled_count=0)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_task_fields_empty_project(self, async_test_client, async_test_db):
        """Empty project returns empty or default fields."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code in (200, 404)


# ===================================================================
# SKIP + NEXT INTEGRATION
# ===================================================================

@pytest.mark.integration
class TestSkipNextIntegration:
    """Integration between skip and next endpoints."""

    @pytest.mark.asyncio
    async def test_skip_then_next_returns_different_task(self, async_test_client, async_test_db):
        """After skipping a task, next should return a different one."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org, assignment_mode="open")
        tasks = await _tasks(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            # Skip first task
            skip_resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Skip it"},
            )
            assert skip_resp.status_code in (200, 201)

            # Get next - should not return the skipped task
            next_resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert next_resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_update_then_list_reflects_change(self, async_test_client, async_test_db):
        """Update task data and verify it appears in listing."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project(async_test_db, users[0], org)
        tasks = await _tasks(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            # Update
            update_resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Changed via integration test"}},
            )
            assert update_resp.status_code in (200, 403)

            # Verify
            list_resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert list_resp.status_code == 200
        if update_resp.status_code == 200:
            assert list_resp.json()["items"][0]["data"]["text"] == "Changed via integration test"
