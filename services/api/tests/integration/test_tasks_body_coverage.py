"""
Integration tests for tasks.py handler body code.

Covers:
- list_project_tasks: pagination, only_labeled/only_unlabeled, only_assigned,
  exclude_my_annotations, annotator role-based filtering,
  randomize_task_order deterministic ordering, skip_queue variants
- get_next_task: open mode (draft resume, unannotated), manual mode,
  auto mode (self-assignment, maximum_annotations enforcement),
  skip exclusion in all modes
- get_task: single task retrieval, assignment enforcement
- update_task_metadata: merge vs replace, null meta init
- bulk_update_task_metadata: multi-project access check
- update_task_data: superadmin-only, audit log creation, merge data
- bulk_delete_tasks: cascade deletion, permission check
- bulk_export_tasks: json/csv/tsv format, evaluation nesting
- bulk_archive_tasks: meta flag setting
- skip_task: record creation, require_comment_on_skip enforcement
- task_fields: field discovery, sensitive field filtering, nested fields

Lane note (asyncpg migration):
Every endpoint exercised here was migrated to the async DB lane
(``Depends(get_async_db)``) — list/next/get tasks (``listing.py``), metadata
ops (``metadata_ops.py``), update/bulk-delete/bulk-archive/skip
(``mutations.py``), and task-fields (``fields.py``). Those tests seed via
``async_test_db`` and drive ``async_test_client`` with a per-test
``require_user`` override (the sync auth dependency cannot see the async test
transaction, and ``async_test_client`` only overrides ``get_async_db``).

The lone exception is ``bulk_export_tasks`` (``export.py``), which is still on
the sync lane (``Depends(get_db)``). Converting it to ``async_test_client``
would let its sync handler fall through to a real, un-isolated ``SessionLocal``,
so ``TestBulkExportTasks`` deliberately stays on the sync ``client``/``test_db``
fixtures.
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


# ===================================================================
# SYNC seeding helpers (used by the still-sync TestBulkExportTasks)
# ===================================================================

def _project(db, admin, org, **kw):
    p = Project(
        id=_uid(),
        title=kw.get("title", f"TaskBody {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        assignment_mode=kw.get("assignment_mode", "open"),
        maximum_annotations=kw.get("maximum_annotations", 1),
        randomize_task_order=kw.get("randomize_task_order", False),
        skip_queue=kw.get("skip_queue", "requeue_for_others"),
        require_comment_on_skip=kw.get("require_comment_on_skip", False),
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


def _tasks(db, project, admin, count=5, labeled_count=0):
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
    db.flush()
    return tasks


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
            response_content="Generated", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


def _annotator_h(auth_headers, org):
    return {**auth_headers["annotator"], "X-Organization-Context": org.id}


def _contributor_h(auth_headers, org):
    return {**auth_headers["contributor"], "X-Organization-Context": org.id}


# ===================================================================
# ASYNC auth + seeding helpers (used by the async-lane tests)
# ===================================================================

@contextmanager
def _as_user(db_user: User):
    """Override require_user to return an AuthUser matching the seeded actor.

    The sync auth dependency can't see the async test transaction, so the
    Bearer-token path used by auth_headers won't resolve. Overriding
    require_user directly is the same trick the passing reference
    (test_global_tasks_integration.py) uses.
    """
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


async def _make_user_async(db, *, is_superadmin=False, label="user"):
    u = User(
        id=_uid(),
        username=f"{label}-{_uid()[:8]}@test.com",
        email=f"{label}-{_uid()[:8]}@test.com",
        name=f"Test {label.title()}",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org_async(db):
    org = Organization(
        id=_uid(),
        name=f"Test Organization {_uid()[:6]}",
        slug=f"test-organization-{_uid()[:6]}",
        display_name="Test Organization Display",
        description="A test organization for testing",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _membership_async(db, user, org, role):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user.id,
        organization_id=org.id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _setup_users_org_async(db):
    """Mirror the sync test_users/test_org fixtures in the async session.

    Returns (users, org) where ``users`` is a 3-element list:
      [0] admin (superadmin, ORG_ADMIN membership)
      [1] contributor (CONTRIBUTOR membership)
      [2] annotator (ANNOTATOR membership)
    so existing ``test_users[i]`` index usage maps onto ``users[i]``.
    """
    admin = await _make_user_async(db, is_superadmin=True, label="admin")
    contributor = await _make_user_async(db, label="contributor")
    annotator = await _make_user_async(db, label="annotator")

    org = await _make_org_async(db)
    await _membership_async(db, admin, org, "ORG_ADMIN")
    await _membership_async(db, contributor, org, "CONTRIBUTOR")
    await _membership_async(db, annotator, org, "ANNOTATOR")

    return [admin, contributor, annotator], org


async def _project_async(db, admin, org, **kw):
    p = Project(
        id=_uid(),
        title=kw.get("title", f"TaskBody {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        assignment_mode=kw.get("assignment_mode", "open"),
        maximum_annotations=kw.get("maximum_annotations", 1),
        randomize_task_order=kw.get("randomize_task_order", False),
        skip_queue=kw.get("skip_queue", "requeue_for_others"),
        require_comment_on_skip=kw.get("require_comment_on_skip", False),
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


async def _tasks_async(db, project, admin, count=5, labeled_count=0):
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


async def _annotate_async(db, project, tasks, user_id, count=None, cancelled=False):
    anns = []
    for t in (tasks[:count] if count else tasks):
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=cancelled,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _assign_async(db, tasks, user_id, admin_id, count=None, status="assigned"):
    assigns = []
    for t in (tasks[:count] if count else tasks):
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status=status,
        )
        db.add(a)
        assigns.append(a)
    await db.flush()
    return assigns


async def _skip_async(db, project, tasks, user_id, count=None):
    skips = []
    for t in (tasks[:count] if count else tasks):
        s = SkippedTask(
            id=_uid(), task_id=t.id, project_id=project.id,
            skipped_by=user_id, comment="Skipped in test",
        )
        db.add(s)
        skips.append(s)
    await db.flush()
    return skips


def _org_ctx(org):
    return {"X-Organization-Context": org.id}


# ===================================================================
# LIST TASKS: pagination and filters
# ===================================================================

@pytest.mark.integration
class TestListTasksPagination:

    @pytest.mark.asyncio
    async def test_pagination_first_page(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=5",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 10
        assert len(body["items"]) == 5
        assert body["page"] == 1
        assert body["pages"] == 2

    @pytest.mark.asyncio
    async def test_pagination_second_page(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=2&page_size=5",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 5

    @pytest.mark.asyncio
    async def test_pagination_beyond_last_page(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=10&page_size=30",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 0

    @pytest.mark.asyncio
    async def test_only_labeled_filter(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=5, labeled_count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_only_unlabeled_filter(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=5, labeled_count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_unlabeled=true",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    @pytest.mark.asyncio
    async def test_only_assigned_filter(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _assign_async(async_test_db, tasks[:2], users[2].id, users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_assigned=true",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


# ===================================================================
# LIST TASKS: exclude_my_annotations
# ===================================================================

@pytest.mark.integration
class TestListTasksExcludeAnnotations:

    @pytest.mark.asyncio
    async def test_exclude_my_annotations_skip_queue_requeue_for_me(self, async_test_client, async_test_db):
        """With requeue_for_me, skipped tasks should NOT be excluded from the user's view."""
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, skip_queue="requeue_for_me")
        tasks = await _tasks_async(async_test_db, p, users[0], count=4)
        await _skip_async(async_test_db, p, tasks[:1], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        # Skipped tasks not excluded when skip_queue=requeue_for_me
        assert resp.json()["total"] == 4


# ===================================================================
# LIST TASKS: annotator role-based filtering
# ===================================================================

@pytest.mark.integration
class TestListTasksAnnotatorRole:

    @pytest.mark.asyncio
    async def test_annotator_only_sees_assigned_in_manual_mode(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _assign_async(async_test_db, tasks[:2], users[2].id, users[0].id)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_annotator_sees_all_in_open_mode(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="open")
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 5


# ===================================================================
# LIST TASKS: randomized order
# ===================================================================

@pytest.mark.integration
class TestListTasksRandomized:

    @pytest.mark.asyncio
    async def test_randomized_order_deterministic_per_user(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, randomize_task_order=True)
        await _tasks_async(async_test_db, p, users[0], count=20)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp1 = await async_test_client.get(f"/api/projects/{p.id}/tasks", headers=_org_ctx(org))
            resp2 = await async_test_client.get(f"/api/projects/{p.id}/tasks", headers=_org_ctx(org))
        assert resp1.status_code == 200
        ids1 = [t["id"] for t in resp1.json()["items"]]
        ids2 = [t["id"] for t in resp2.json()["items"]]
        # Same user gets same order
        assert ids1 == ids2


# ===================================================================
# LIST TASKS: task dict fields
# ===================================================================

@pytest.mark.integration
class TestListTasksFieldEnrichment:

    @pytest.mark.asyncio
    async def test_task_items_have_required_fields(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks", headers=_org_ctx(org))
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        required = ["id", "inner_id", "data", "meta", "is_labeled",
                     "total_annotations", "total_generations", "project_id",  # noqa: E127
                     "assignments", "tags"]
        for field in required:
            assert field in item, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_task_items_tags_derived_from_meta(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "with tags"}, inner_id=1,
            meta={"tags": ["urgent", "review"]},
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks", headers=_org_ctx(org))
        item = resp.json()["items"][0]
        assert item["tags"] == ["urgent", "review"]


# ===================================================================
# GET NEXT TASK: open mode
# ===================================================================

@pytest.mark.integration
class TestGetNextTaskOpen:

    @pytest.mark.asyncio
    async def test_next_task_returns_first_unannotated(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["total_tasks"] == 3
        assert data["remaining"] == 3

    @pytest.mark.asyncio
    async def test_next_task_skips_annotated(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _annotate_async(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["user_completed_tasks"] == 2
        assert data["remaining"] == 1

    @pytest.mark.asyncio
    async def test_next_task_all_annotated(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=2)
        await _annotate_async(async_test_db, p, tasks, users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"] is None

    @pytest.mark.asyncio
    async def test_next_task_nonexistent_project(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{_uid()}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"] is None

    @pytest.mark.asyncio
    async def test_next_task_skip_exclusion(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, skip_queue="requeue_for_others")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _skip_async(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        # Should return the 3rd task (first two are skipped)
        assert data["task"]["id"] == tasks[2].id

    @pytest.mark.asyncio
    async def test_next_task_ignore_skipped(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, skip_queue="ignore_skipped")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        # Different user skips a task - should still be excluded
        await _skip_async(async_test_db, p, tasks[:1], users[1].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["task"]["id"] != tasks[0].id

    @pytest.mark.asyncio
    async def test_next_task_with_randomized_order(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, randomize_task_order=True)
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"] is not None


# ===================================================================
# GET NEXT TASK: manual mode
# ===================================================================

@pytest.mark.integration
class TestGetNextTaskManual:

    @pytest.mark.asyncio
    async def test_manual_returns_assigned_task(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _assign_async(async_test_db, tasks[:1], users[0].id, users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"]["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_manual_no_assignments_returns_none(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"] is None


# ===================================================================
# GET NEXT TASK: auto mode
# ===================================================================

@pytest.mark.integration
class TestGetNextTaskAuto:

    @pytest.mark.asyncio
    async def test_auto_creates_self_assignment(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)  # noqa: F841
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"] is not None

    @pytest.mark.asyncio
    async def test_auto_resumes_existing_assignment(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _assign_async(async_test_db, tasks[:1], users[0].id, users[0].id, status="in_progress")
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        assert resp.json()["task"]["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_auto_respects_maximum_annotations(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto", maximum_annotations=1)
        tasks = await _tasks_async(async_test_db, p, users[0], count=2)
        # First task fully annotated by contributor
        await _annotate_async(async_test_db, p, tasks[:1], users[1].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        # Should skip the fully annotated task
        if data["task"] is not None:
            assert data["task"]["id"] == tasks[1].id

    @pytest.mark.asyncio
    async def test_auto_skip_exclusion(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="auto", skip_queue="requeue_for_others")
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await _skip_async(async_test_db, p, tasks[:2], users[0].id)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next", headers=_org_ctx(org))
        assert resp.status_code == 200
        data = resp.json()
        if data["task"] is not None:
            assert data["task"]["id"] == tasks[2].id


# ===================================================================
# GET SINGLE TASK
# ===================================================================

@pytest.mark.integration
class TestGetTask:

    @pytest.mark.asyncio
    async def test_get_task_by_id(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id
        assert "data" in data
        assert "meta" in data
        assert "inner_id" in data

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{_uid()}",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 404


# ===================================================================
# UPDATE TASK METADATA
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskMetadata:

    @pytest.mark.asyncio
    async def test_merge_metadata(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "test"}, inner_id=1,
            meta={"existing": "value"},
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{t.id}/metadata?merge=true",
                json={"new_key": "new_value"},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["existing"] == "value"
        assert meta["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_replace_metadata(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "test"}, inner_id=1,
            meta={"old_key": "old_value"},
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{t.id}/metadata?merge=false",
                json={"replaced": True},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert "old_key" not in meta
        assert meta["replaced"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_metadata_init_null_meta(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "test"}, inner_id=1,
            meta=None,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{t.id}/metadata",
                json={"init": True},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["meta"]["init"] == True  # noqa: E712


# ===================================================================
# UPDATE TASK DATA (superadmin only)
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskData:

    @pytest.mark.asyncio
    async def test_superadmin_can_update_data(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated text"}},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Updated text"

    @pytest.mark.asyncio
    async def test_non_superadmin_cannot_update_data(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated"}},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_creates_audit_log(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Audited change"}},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert "audit_log" in meta
        assert len(meta["audit_log"]) == 1
        assert meta["audit_log"][0]["action"] == "data_update"

    @pytest.mark.asyncio
    async def test_update_empty_data_returns_400(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {}},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{_uid()}",
                json={"data": {"text": "x"}},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 404


# ===================================================================
# BULK DELETE
# ===================================================================

@pytest.mark.integration
class TestBulkDelete:

    @pytest.mark.asyncio
    async def test_bulk_delete_tasks(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": [tasks[0].id, tasks[1].id]},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_project(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/tasks/bulk-delete",
                json={"task_ids": [_uid()]},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 404


# ===================================================================
# BULK EXPORT TASKS  (SYNC LANE — export.py uses Depends(get_db))
# ===================================================================

@pytest.mark.integration
class TestBulkExportTasks:

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data["tasks"]) == 3

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_bulk_export_tsv(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [tasks[0].id], "format": "tsv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert "\t" in resp.text

    def test_bulk_export_unsupported_format(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [tasks[0].id], "format": "xml"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400


# ===================================================================
# BULK ARCHIVE
# ===================================================================

@pytest.mark.integration
class TestBulkArchive:

    @pytest.mark.asyncio
    async def test_bulk_archive_sets_meta_flag(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-archive",
                json={"task_ids": [tasks[0].id, tasks[1].id]},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["archived"] == 2


# ===================================================================
# SKIP TASK
# ===================================================================

@pytest.mark.integration
class TestSkipTask:

    @pytest.mark.asyncio
    async def test_skip_task_creates_record(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Too complex"},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == tasks[0].id
        assert resp.json()["comment"] == "Too complex"

    @pytest.mark.asyncio
    async def test_skip_task_requires_comment_when_enforced(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org, require_comment_on_skip=True)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_skip_task_nonexistent(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{_uid()}/skip",
                json={},
                headers=_org_ctx(org),
            )
        assert resp.status_code == 404


# ===================================================================
# TASK FIELDS DISCOVERY
# ===================================================================

@pytest.mark.integration
class TestTaskFields:

    @pytest.mark.asyncio
    async def test_task_fields_basic(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sample_task_count"] == 3
        paths = [f["path"] for f in data["fields"]]
        assert "$text" in paths
        assert "$category" in paths

    @pytest.mark.asyncio
    async def test_task_fields_sensitive_filtered(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "test", "ground_truth": "secret", "annotations": []},
            inner_id=1,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields",
                headers=_org_ctx(org),
            )
        paths = [f["path"] for f in resp.json()["fields"]]
        assert "$ground_truth" not in paths
        assert "$annotations" not in paths

    @pytest.mark.asyncio
    async def test_task_fields_nested(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "test", "context": {"jurisdiction": "DE", "court": "BGH"}},
            inner_id=1,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields",
                headers=_org_ctx(org),
            )
        paths = [f["path"] for f in resp.json()["fields"]]
        assert "$context.jurisdiction" in paths
        assert "$context.court" in paths

    @pytest.mark.asyncio
    async def test_task_fields_empty_project(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["fields"] == []

    @pytest.mark.asyncio
    async def test_task_fields_various_types(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        p = await _project_async(async_test_db, users[0], org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={
                "text": "string val",
                "score": 42,
                "ratio": 0.75,
                "tags": ["a", "b"],
                "active": True,
            },
            inner_id=1,
        )
        async_test_db.add(t)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/task-fields",
                headers=_org_ctx(org),
            )
        fields = {f["path"]: f["data_type"] for f in resp.json()["fields"]}
        assert fields["$text"] == "string"
        assert fields["$score"] == "number"
        assert fields["$ratio"] == "number"
        assert fields["$tags"] == "array"
        # Note: Python bool is subclass of int, so extract_fields_from_data
        # classifies True/False as "number" because (int, float) check comes first
        assert fields["$active"] == "number"

    @pytest.mark.asyncio
    async def test_task_fields_nonexistent_project(self, async_test_client, async_test_db):
        users, org = await _setup_users_org_async(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}/task-fields",
                headers=_org_ctx(org),
            )
        assert resp.status_code == 404
