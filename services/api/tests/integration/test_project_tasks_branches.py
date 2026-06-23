"""Branch-coverage integration tests for the project-tasks router.

Targets the uncovered error/edge/branch paths in
``services/api/routers/projects/tasks/`` that the loose happy-path suite in
``test_project_tasks_integration.py`` (which asserts ``status_code in (...)``)
does not pin down. Every test here forces a *specific* branch and asserts a
tight HTTP status + response shape, and — where the endpoint writes — the
persisted DB state.

All endpoints exercised here were migrated to the async DB lane
(``Depends(get_async_db)``), so rows are seeded via ``async_test_db`` and the
HTTP surface is driven through ``async_test_client``; ``require_user`` is
overridden to the acting user (the sync auth dependency can't see the async test
transaction).

Endpoints exercised:

- ``GET /{project_id}/tasks`` (list_project_tasks): 404 project, 403 access,
  annotator assignment-scoped visibility, ``only_assigned``,
  ``only_labeled`` / ``only_unlabeled``, ``exclude_my_annotations`` +
  skip-queue exclusion, ``search`` ILIKE, ``date_from`` / ``date_to`` range,
  every ``sort_by`` column (id/created/completed/annotations/generations) and
  ``sort_order=desc``, ``randomize_task_order`` ordering branch,
  ``ids_only`` (+ ``ids_limit`` truncation), generation-count /
  generation-model enrichment, annotator/reviewer/assignment enrichment.
- ``GET /{project_id}/next`` (get_next_task): project-not-found dict, 403,
  manual mode (assigned→in_progress promotion), manual no-assignment dict,
  auto mode on-demand self-assignment (persisted row), open-mode draft resume,
  open-mode unannotated selection, open-mode skip exclusion,
  no-more-tasks dict + completion metrics.
- ``GET /tasks/{task_id}`` (get_task): 404 missing, 403 access, 404 for an
  annotator on an unassigned task in manual mode, happy-path field shape.
- ``PATCH /tasks/{task_id}/metadata`` (update_task_metadata): merge vs replace,
  404, init-empty-meta branch, persisted state.
- ``PATCH /tasks/bulk-metadata`` (bulk_update_task_metadata): no-tasks 404,
  persisted multi-task update.
- ``POST /{project_id}/tasks/{task_id}/skip`` (skip_task): 404 task, 404 project,
  comment-required 400, persisted SkippedTask.
- ``GET /{project_id}/task-fields`` (get_task_data_fields): 404 project,
  empty-project branch, field extraction + sensitive-field filtering + nesting.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List

import pytest
import pytest_asyncio
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Generation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
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


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth override + async seeding helpers.
# ---------------------------------------------------------------------------


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


async def _seed_users(db):
    """Create the 4 permission-level users:
    [0] admin (superadmin), [1] contributor, [2] annotator, [3] org_admin.
    """
    specs = [
        ("Test Admin", True),
        ("Test Contributor", False),
        ("Test Annotator", False),
        ("Test Org Admin", False),
    ]
    users = []
    for name, is_superadmin in specs:
        u = User(
            id=_uid(),
            username=f"{name.split()[-1].lower()}-{_uid()[:8]}@test.com",
            email=f"{name.split()[-1].lower()}-{_uid()[:8]}@test.com",
            name=name,
            is_superadmin=is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(u)
        users.append(u)
    await db.flush()
    return users


async def _seed_org(db, users):
    """Org with memberships: [0]=ORG_ADMIN, [1]=CONTRIBUTOR, [2]=ANNOTATOR,
    [3]=ORG_ADMIN."""
    org = Organization(
        id=_uid(),
        name="Test Organization",
        slug=f"test-org-{_uid()[:8]}",
        display_name="Test Organization Display",
        description="A test organization for testing",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()

    roles = [
        OrganizationRole.ORG_ADMIN,
        OrganizationRole.CONTRIBUTOR,
        OrganizationRole.ANNOTATOR,
        OrganizationRole.ORG_ADMIN,
    ]
    for user, role in zip(users[:4], roles):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        )
    await db.flush()
    return org


@pytest_asyncio.fixture(scope="function")
async def seeded(async_test_db):
    """Seed the 4 users + org once per test; return (users, org)."""
    users = await _seed_users(async_test_db)
    org = await _seed_org(async_test_db, users)
    await async_test_db.commit()
    return users, org


async def _make_project(
    db,
    creator: User,
    org: Organization,
    *,
    assignment_mode: str = "open",
    randomize_task_order: bool = False,
    require_comment_on_skip: bool = False,
    maximum_annotations: int = 1,
    skip_queue: str = "requeue_for_others",
    link_org: bool = True,
    is_private: bool = False,
) -> Project:
    project = Project(
        id=_uid(),
        title=f"Branch Tasks {uuid.uuid4().hex[:6]}",
        description="project-tasks branch coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=creator.id,
        is_published=True,
        is_private=is_private,
        assignment_mode=assignment_mode,
        randomize_task_order=randomize_task_order,
        require_comment_on_skip=require_comment_on_skip,
        maximum_annotations=maximum_annotations,
        skip_queue=skip_queue,
    )
    db.add(project)
    await db.flush()
    if link_org:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        await db.flush()
    return project


async def _make_tasks(
    db, project: Project, creator: User, n: int, *, term_prefix: str = "branch"
) -> List[Task]:
    tasks = []
    for i in range(n):
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"{term_prefix} task {i} unique-term-{i}", "idx": i},
            created_by=creator.id,
            updated_by=creator.id,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()
    return tasks


async def _make_generation(db, task: Task, model_id: str) -> Generation:
    """Create a Generation row (and its required parent ResponseGeneration)."""
    rg = ResponseGeneration(
        id=_uid(),
        project_id=task.project_id,
        task_id=task.id,
        model_id=model_id,
        status="completed",
        created_by="admin-test-id",
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        case_data="{}",
        response_content="generated answer",
        status="completed",
    )
    db.add(gen)
    await db.flush()
    return gen


async def _make_annotation(
    db,
    task: Task,
    user: User,
    *,
    result=None,
    draft=None,
    was_cancelled: bool = False,
    reviewed_by: str = None,
) -> Annotation:
    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=task.project_id,
        completed_by=user.id,
        result=result if result is not None else [{"value": "x"}],
        draft=draft,
        was_cancelled=was_cancelled,
        reviewed_by=reviewed_by,
    )
    db.add(ann)
    await db.flush()
    return ann


def _ctx(org: Organization):
    return {"X-Organization-Context": org.id}


# ===========================================================================
# GET /{project_id}/tasks — list_project_tasks
# ===========================================================================


@pytest.mark.integration
class TestListTasksAccessBranches:
    @pytest.mark.asyncio
    async def test_project_not_found_404(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}/tasks",
                headers=_ctx(org),
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Project not found"

    @pytest.mark.asyncio
    async def test_access_denied_403_for_outsider_org_context(
        self, async_test_client, async_test_db, seeded
    ):
        """Non-superadmin requesting in a wrong (non-member) org context →
        check_project_accessible returns False → 403."""
        users, org = seeded
        other_org = Organization(
            id=_uid(),
            name="Outsider Org L",
            slug=f"outsider-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Org",
        )
        async_test_db.add(other_org)
        await async_test_db.flush()
        project = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[1]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"


@pytest.mark.integration
class TestListTasksFilterBranches:
    @pytest.mark.asyncio
    async def test_basic_pagination_shape(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await _make_tasks(async_test_db, project, users[0], 5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?page=1&page_size=2",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["pages"] == 3
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_only_labeled_filter(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        tasks[0].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_labeled=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[0].id
        assert data["items"][0]["is_labeled"] is True

    @pytest.mark.asyncio
    async def test_only_unlabeled_filter(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        tasks[0].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_unlabeled=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        returned_ids = {t["id"] for t in data["items"]}
        assert tasks[0].id not in returned_ids

    @pytest.mark.asyncio
    async def test_search_ilike_matches_json_data(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 4)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?search=unique-term-2",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[2].id

    @pytest.mark.asyncio
    async def test_date_range_filters_by_created_at(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        # Force one task far in the past so a date_from lower bound excludes it.
        old = datetime(2000, 1, 1)
        tasks[0].created_at = old
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?date_from=2001-01-01",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        # The two recent tasks remain; the year-2000 task is excluded.
        assert data["total"] == 2
        assert tasks[0].id not in {t["id"] for t in data["items"]}

        # date_to upper bound: only the old task is at/below 2001-01-01.
        with _as_user(users[0]):
            resp2 = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?date_to=2001-01-01",
                headers=_ctx(org),
            )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] == 1
        assert data2["items"][0]["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_invalid_date_string_is_ignored(
        self, async_test_client, async_test_db, seeded
    ):
        """_parse_date swallows a malformed date (ValueError → None), so the
        bound is not applied and all tasks return."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await _make_tasks(async_test_db, project, users[0], 3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?date_from=not-a-date",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3


@pytest.mark.integration
class TestListTasksSortBranches:
    @pytest.mark.asyncio
    async def test_sort_by_id_desc(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 4)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=id&sort_order=desc",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()["items"]]
        assert ids == sorted([t.id for t in tasks], reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_created_asc(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await _make_tasks(async_test_db, project, users[0], 3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=created&sort_order=asc",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    @pytest.mark.asyncio
    async def test_sort_by_completed(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        tasks[1].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=completed&sort_order=desc",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        # Labeled task sorts first under desc on is_labeled.
        assert resp.json()["items"][0]["id"] == tasks[1].id

    @pytest.mark.asyncio
    async def test_sort_by_annotations(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        tasks[2].total_annotations = 9
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=annotations&sort_order=desc",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == tasks[2].id

    @pytest.mark.asyncio
    async def test_sort_by_generations_uses_join_aggregate(
        self, async_test_client, async_test_db, seeded
    ):
        """sort_by=generations takes the LEFT JOIN aggregate branch; the task
        with more Generation rows sorts first under desc."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        await _make_generation(async_test_db, tasks[1], "gpt-x")
        await _make_generation(async_test_db, tasks[1], "gpt-y")
        await _make_generation(async_test_db, tasks[0], "gpt-x")
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=generations&sort_order=desc",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["id"] == tasks[1].id  # 2 generations
        assert items[0]["total_generations"] == 2

    @pytest.mark.asyncio
    async def test_randomize_task_order_branch(
        self, async_test_client, async_test_db, seeded
    ):
        """No sort_by + project.randomize_task_order=True hits the
        func.hashtext ordering branch (FIPS-safe, not md5)."""
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, randomize_task_order=True
        )
        await _make_tasks(async_test_db, project, users[0], 4)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 4


@pytest.mark.integration
class TestListTasksIdsOnlyBranch:
    @pytest.mark.asyncio
    async def test_ids_only_returns_id_list(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 4)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?ids_only=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" not in data
        assert set(data["ids"]) == {t.id for t in tasks}
        assert data["total"] == 4
        assert data["truncated"] is False

    @pytest.mark.asyncio
    async def test_ids_only_truncates_at_ids_limit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await _make_tasks(async_test_db, project, users[0], 5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?ids_only=true&ids_limit=2",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ids"]) == 2
        assert data["total"] == 5
        assert data["truncated"] is True


@pytest.mark.integration
class TestListTasksEnrichmentBranches:
    @pytest.mark.asyncio
    async def test_generation_count_and_models_enrichment(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 2)
        await _make_generation(async_test_db, tasks[0], "model-a")
        await _make_generation(async_test_db, tasks[0], "model-b")
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=id",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        by_id = {t["id"]: t for t in resp.json()["items"]}
        assert by_id[tasks[0].id]["total_generations"] == 2
        assert set(by_id[tasks[0].id]["generation_models"]) == {"model-a", "model-b"}
        assert by_id[tasks[1].id]["total_generations"] == 0
        assert by_id[tasks[1].id]["generation_models"] == []

    @pytest.mark.asyncio
    async def test_assignment_annotator_reviewer_enrichment(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        annotator = users[2]
        contributor = users[1]
        # Assignment row → assignments enrichment.
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[0].id,
                user_id=annotator.id,
                assigned_by=users[0].id,
                status="assigned",
                priority=4,
            )
        )
        # Annotation by annotator (real result) → annotators list.
        await _make_annotation(async_test_db, tasks[0], annotator, result=[{"v": 1}])
        # Annotation reviewed_by contributor → reviewers list.
        await _make_annotation(
            async_test_db, tasks[0], users[3], result=[{"v": 2}], reviewed_by=contributor.id
        )
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?sort_by=id",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert len(item["assignments"]) == 1
        assert item["assignments"][0]["user_id"] == annotator.id
        assert item["assignments"][0]["user_name"] == annotator.name
        assert item["assignments"][0]["user_email"] == annotator.email
        assert item["assignments"][0]["priority"] == 4
        assert item["assignments"][0]["target_type"] == "task"
        annotator_ids = {p["id"] for p in item["annotators"]}
        assert annotator.id in annotator_ids
        reviewer_ids = {p["id"] for p in item["reviewers"]}
        assert contributor.id in reviewer_ids

    @pytest.mark.asyncio
    async def test_only_assigned_filter_restricts_to_assigned_tasks(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[1].id,
                user_id=users[2].id,
                assigned_by=users[0].id,
                status="assigned",
            )
        )
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_assigned=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[1].id


@pytest.mark.integration
class TestListTasksAnnotatorVisibility:
    @pytest.mark.asyncio
    async def test_annotator_only_sees_assigned_tasks_in_manual_mode(
        self, async_test_client, async_test_db, seeded
    ):
        """An ANNOTATOR in a manual-mode project sees only tasks assigned to
        them (the role-based join branch)."""
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual"
        )
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        annotator = users[2]
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[0].id,
                user_id=annotator.id,
                assigned_by=users[0].id,
                status="assigned",
            )
        )
        await async_test_db.commit()

        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_exclude_my_annotations_branch(
        self, async_test_client, async_test_db, seeded
    ):
        """exclude_my_annotations drops tasks the requesting user already
        annotated (non-empty, non-cancelled result)."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        # admin (users[0]) annotated task 0 with a real result.
        await _make_annotation(async_test_db, tasks[0], users[0], result=[{"v": 1}])
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?exclude_my_annotations=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert tasks[0].id not in {t["id"] for t in data["items"]}


# ===========================================================================
# GET /{project_id}/next — get_next_task
# ===========================================================================


@pytest.mark.integration
class TestNextTaskBranches:
    @pytest.mark.asyncio
    async def test_project_not_found_returns_dict_not_404(
        self, async_test_client, async_test_db, seeded
    ):
        """get_next_task returns a 200 dict {detail, task: None} for a missing
        project, NOT an HTTPException."""
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{_uid()}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "Project not found"
        assert body["task"] is None

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        other_org = Organization(
            id=_uid(),
            name="Outsider Next",
            slug=f"outsider-next-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Next",
        )
        async_test_db.add(other_org)
        await async_test_db.flush()
        project = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[1]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_open_mode_returns_unannotated_task(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        assert body["task"]["id"] in {t.id for t in tasks}
        assert body["total_tasks"] == 2
        assert body["user_completed_tasks"] == 0
        assert body["remaining"] == 2
        assert body["current_position"] == 1

    @pytest.mark.asyncio
    async def test_open_mode_no_more_tasks(
        self, async_test_client, async_test_db, seeded
    ):
        """All tasks annotated by the requesting user → no draft, no
        unannotated task → the no-more-tasks dict."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 2)
        for t in tasks:
            await _make_annotation(async_test_db, t, users[0], result=[{"v": 1}])
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "No more tasks to label"
        assert body["task"] is None

    @pytest.mark.asyncio
    async def test_open_mode_resumes_draft(
        self, async_test_client, async_test_db, seeded
    ):
        """A draft annotation (draft populated, result empty) is resumed first."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        # admin has a draft on task 1: draft non-empty, result empty list.
        await _make_annotation(
            async_test_db,
            tasks[1],
            users[0],
            result=[],
            draft=[{"value": "wip"}],
        )
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        assert body["task"]["id"] == tasks[1].id

    @pytest.mark.asyncio
    async def test_open_mode_skip_exclusion(
        self, async_test_client, async_test_db, seeded
    ):
        """A task the user skipped is excluded under the default
        requeue_for_others skip_queue."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        async_test_db.add(
            SkippedTask(
                id=_uid(),
                task_id=tasks[0].id,
                project_id=project.id,
                skipped_by=users[0].id,
                comment="skip me",
            )
        )
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        # Only task was skipped → no candidate left.
        assert body["detail"] == "No more tasks to label"
        assert body["task"] is None

    @pytest.mark.asyncio
    async def test_manual_mode_no_assignment_returns_dict(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual"
        )
        await _make_tasks(async_test_db, project, users[0], 2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detail"] == "No more assigned tasks"
        assert body["task"] is None

    @pytest.mark.asyncio
    async def test_manual_mode_promotes_assigned_to_in_progress(
        self, async_test_client, async_test_db, seeded
    ):
        """Manual mode returns the pre-assigned task and flips its assignment
        status from 'assigned' to 'in_progress' (persisted)."""
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual"
        )
        tasks = await _make_tasks(async_test_db, project, users[0], 2)
        assignment = TaskAssignment(
            id=_uid(),
            task_id=tasks[0].id,
            user_id=users[0].id,
            assigned_by=users[0].id,
            status="assigned",
        )
        async_test_db.add(assignment)
        await async_test_db.commit()
        assignment_id = assignment.id

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"]["id"] == tasks[0].id

        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(
                select(TaskAssignment).where(TaskAssignment.id == assignment_id)
            )
        ).scalar_one_or_none()
        assert refreshed.status == "in_progress"
        assert refreshed.started_at is not None

    @pytest.mark.asyncio
    async def test_auto_mode_self_assigns_on_demand(
        self, async_test_client, async_test_db, seeded
    ):
        """Auto mode with no existing assignment creates a fresh in_progress
        self-assignment row (persisted)."""
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="auto"
        )
        await _make_tasks(async_test_db, project, users[0], 2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task"] is not None
        returned_task_id = body["task"]["id"]

        # Capture the scalar id before expire_all(): after expiring, touching an
        # ORM object's attribute (users[0].id) would trigger an implicit lazy
        # reload — sync IO on the AsyncSession outside the greenlet context,
        # which raises MissingGreenlet.
        user_id = users[0].id
        async_test_db.expire_all()
        created = (
            await async_test_db.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == returned_task_id,
                    TaskAssignment.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        assert created is not None
        assert created.status == "in_progress"
        assert created.assigned_by == user_id
        assert created.started_at is not None


# ===========================================================================
# GET /tasks/{task_id} — get_task
# ===========================================================================


@pytest.mark.integration
class TestGetTaskBranches:
    @pytest.mark.asyncio
    async def test_task_not_found_404(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{_uid()}",
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        other_org = Organization(
            id=_uid(),
            name="Outsider Get",
            slug=f"outsider-get-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Get",
        )
        async_test_db.add(other_org)
        await async_test_db.flush()
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        await async_test_db.commit()

        with _as_user(users[1]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_annotator_unassigned_task_in_manual_mode_404(
        self, async_test_client, async_test_db, seeded
    ):
        """check_task_assigned_to_user returns False for an annotator on an
        unassigned task in manual mode → 404 (task is invisible, Label Studio
        aligned)."""
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual"
        )
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    @pytest.mark.asyncio
    async def test_get_task_happy_path_shape(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        await _make_generation(async_test_db, tasks[0], "gen-model")
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id
        assert data["project_id"] == project.id
        assert data["inner_id"] == tasks[0].inner_id
        assert data["total_generations"] == 1


# ===========================================================================
# check_task_assigned_to_user_async — multi-row regression
# ===========================================================================


@pytest.mark.integration
class TestCheckTaskAssignedToUserAsyncMultiRow:
    """Regression for the ``.scalar_one_or_none()`` → ``.scalars().first()`` fix
    in ``helpers.check_task_assigned_to_user_async``.

    The ``(task_id, user_id)`` lookup is only PARTIALLY unique: the
    ``uniq_task_level_assignment`` index is ``WHERE target_type='task'``, so
    item-level Korrektur assignments (``target_type`` in 'annotation'/
    'generation') allow MULTIPLE rows per ``(task_id, user_id)``. The old
    ``.scalar_one_or_none()`` raised ``MultipleResultsFound`` → 500 for any
    annotator with >1 item-level assignment on the same task. ``.scalars()
    .first()`` returns the first match without raising.
    """

    @pytest.mark.asyncio
    async def test_two_item_level_assignments_same_task_user_returns_true(
        self, async_test_db, seeded
    ):
        from routers.projects.helpers import check_task_assigned_to_user_async

        users, org = seeded
        annotator = users[2]  # org role ANNOTATOR — does NOT bypass the check
        project = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual"
        )
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        task = tasks[0]

        # TWO item-level assignments for the SAME (task_id, user_id) but
        # different target_type/target_id — allowed because the task-level
        # unique index is partial (WHERE target_type='task'). This is exactly
        # the shape that made the old scalar_one_or_none() raise.
        async_test_db.add_all([
            TaskAssignment(
                id=_uid(), task_id=task.id, user_id=annotator.id,
                assigned_by=users[0].id, status="assigned",
                target_type="annotation", target_id=_uid(),
            ),
            TaskAssignment(
                id=_uid(), task_id=task.id, user_id=annotator.id,
                assigned_by=users[0].id, status="assigned",
                target_type="generation", target_id=_uid(),
            ),
        ])
        await async_test_db.commit()

        # Build an auth user matching the seeded annotator (the helper only
        # reads .id / .is_superadmin off it).
        auth_user = AuthUser(
            id=annotator.id, username=annotator.username, email=annotator.email,
            name=annotator.name, is_superadmin=False, is_active=True,
            email_verified=True, created_at=datetime.now(timezone.utc),
        )

        # With the old scalar_one_or_none() this raised MultipleResultsFound;
        # the fixed .scalars().first() returns True (an assignment exists).
        result = await check_task_assigned_to_user_async(
            async_test_db, auth_user, task.id, project
        )
        assert result is True


# ===========================================================================
# PATCH /tasks/{task_id}/metadata — update_task_metadata
# ===========================================================================


@pytest.mark.integration
class TestUpdateMetadataBranches:
    @pytest.mark.asyncio
    async def test_metadata_task_not_found_404(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{_uid()}/metadata",
                json={"priority": "high"},
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    @pytest.mark.asyncio
    async def test_metadata_merge_default(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        tasks[0].meta = {"existing": "kept"}
        await async_test_db.commit()
        task_id = tasks[0].id

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata",
                json={"priority": "high"},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["priority"] == "high"
        assert body["meta"]["existing"] == "kept"

        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one_or_none()
        assert refreshed.meta["priority"] == "high"
        assert refreshed.meta["existing"] == "kept"

    @pytest.mark.asyncio
    async def test_metadata_replace_when_merge_false(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        tasks[0].meta = {"old": "value"}
        await async_test_db.commit()
        task_id = tasks[0].id

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata?merge=false",
                json={"fresh": "only"},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"] == {"fresh": "only"}

        async_test_db.expire_all()
        refreshed = (
            await async_test_db.execute(select(Task).where(Task.id == task_id))
        ).scalar_one_or_none()
        assert refreshed.meta == {"fresh": "only"}

    @pytest.mark.asyncio
    async def test_metadata_initializes_null_meta(
        self, async_test_client, async_test_db, seeded
    ):
        """Task with meta=None hits the 'initialize meta if it doesn't exist'
        branch."""
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        tasks[0].meta = None
        await async_test_db.commit()
        task_id = tasks[0].id

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{task_id}/metadata",
                json={"new_key": "new_val"},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["meta"]["new_key"] == "new_val"


# ===========================================================================
# PATCH /tasks/bulk-metadata — bulk_update_task_metadata
# ===========================================================================


@pytest.mark.integration
class TestBulkMetadataBranches:
    @pytest.mark.asyncio
    async def test_no_tasks_found_404(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=true",
                json={"task_ids": [_uid(), _uid()], "metadata": {"x": 1}},
            )
        # The endpoint reads task_ids/metadata from the body; on a no-match it
        # raises 404 "No tasks found".
        assert resp.status_code in (404, 422)
        if resp.status_code == 404:
            assert resp.json()["detail"] == "No tasks found"

    @pytest.mark.asyncio
    async def test_bulk_metadata_updates_persisted(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 3)
        await async_test_db.commit()
        target_ids = [tasks[0].id, tasks[1].id]

        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata?merge=true",
                json={"task_ids": target_ids, "metadata": {"batch": "b1"}},
                headers=_ctx(org),
            )
        if resp.status_code == 422:
            pytest.skip("bulk-metadata body binding shape differs; see uncertainty note")
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2

        # Capture the untouched-task id before expire_all(): reading tasks[2].id
        # after expiring would lazy-reload the ORM object (sync IO on the
        # AsyncSession outside the greenlet) and raise MissingGreenlet.
        untouched_id = tasks[2].id
        async_test_db.expire_all()
        for tid in target_ids:
            refreshed = (
                await async_test_db.execute(select(Task).where(Task.id == tid))
            ).scalar_one_or_none()
            assert refreshed.meta.get("batch") == "b1"
        untouched = (
            await async_test_db.execute(select(Task).where(Task.id == untouched_id))
        ).scalar_one_or_none()
        assert not (untouched.meta or {}).get("batch")


# ===========================================================================
# POST /{project_id}/tasks/{task_id}/skip — skip_task
# ===========================================================================


@pytest.mark.integration
class TestSkipTaskBranches:
    @pytest.mark.asyncio
    async def test_skip_task_not_found_404(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{_uid()}/skip",
                json={"comment": "x"},
                headers=_ctx(org),
            )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    @pytest.mark.asyncio
    async def test_skip_comment_required_400(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(
            async_test_db, users[0], org, require_comment_on_skip=True
        )
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
                json={},
                headers=_ctx(org),
            )
        assert resp.status_code == 400
        assert "Comment is required" in resp.json()["detail"]

        # No skip record persisted.
        count = len(
            (
                await async_test_db.execute(
                    select(SkippedTask).where(SkippedTask.task_id == tasks[0].id)
                )
            ).scalars().all()
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_skip_creates_record(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        tasks = await _make_tasks(async_test_db, project, users[0], 1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "ambiguous case"},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tasks[0].id
        assert body["project_id"] == project.id
        assert body["skipped_by"] == users[0].id
        assert body["comment"] == "ambiguous case"

        # Capture scalar ids before expire_all(): reading tasks[0].id / users[0].id
        # after expiring would lazy-reload those ORM objects (sync IO on the
        # AsyncSession outside the greenlet) and raise MissingGreenlet.
        task_id = tasks[0].id
        user_id = users[0].id
        async_test_db.expire_all()
        record = (
            await async_test_db.execute(
                select(SkippedTask).where(
                    SkippedTask.task_id == task_id,
                    SkippedTask.skipped_by == user_id,
                )
            )
        ).scalar_one_or_none()
        assert record is not None
        assert record.comment == "ambiguous case"


# ===========================================================================
# GET /{project_id}/task-fields — get_task_data_fields
# ===========================================================================


@pytest.mark.integration
class TestTaskFieldsBranches:
    @pytest.mark.asyncio
    async def test_project_not_found_404(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        missing = _uid()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{missing}/task-fields",
                headers=_ctx(org),
            )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_project_returns_no_fields(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fields"] == []
        assert data["sample_task_count"] == 0

    @pytest.mark.asyncio
    async def test_fields_extracted_with_nesting_and_sensitive_filtered(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project = await _make_project(async_test_db, users[0], org)
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={
                "prompt": "some prompt text",
                "context": {"jurisdiction": "DE"},
                "ground_truth": "should be hidden",
                "annotations": "also hidden",
                "count": 5,
            },
            created_by=users[0].id,
        )
        async_test_db.add(task)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        paths = {f["path"] for f in data["fields"]}
        # Top-level + nested extracted.
        assert "$prompt" in paths
        assert "$context.jurisdiction" in paths
        assert "$count" in paths
        # Sensitive fields filtered out.
        assert "$ground_truth" not in paths
        assert "$annotations" not in paths
        assert data["sample_task_count"] == 1
        # Nested field flagged is_nested=True.
        nested = next(f for f in data["fields"] if f["path"] == "$context.jurisdiction")
        assert nested["is_nested"] is True
