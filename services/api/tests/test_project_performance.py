"""
Performance tests for project API endpoints

These tests verify that optimized query patterns are used to avoid N+1 problems.

``list_projects`` was migrated to the async DB lane (``Depends(get_async_db)``),
so the three HTTP-surface tests below seed via ``async_test_db`` and drive the
endpoint through ``async_test_client``; ``require_user`` is overridden to a
superadmin via ``_as_user`` (the sync auth dependency can't see the async test
transaction). The batch-stats tests call the still-sync
``calculate_project_stats_batch`` helper directly, so they keep the sync
``test_db`` fixture.
"""


import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override ``require_user`` to return an auth User matching a seeded DB row
    (the sync auth dependency can't resolve a user inside the async test txn)."""
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


async def _make_user(db, *, is_superadmin=False, username_prefix="perf") -> User:
    u = User(
        id=_uid(),
        username=f"{username_prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Perf User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


class QueryCounter:
    """Helper class to count SQL queries executed.

    Listens on the ``Engine`` *class* (``before_cursor_execute``), so it also
    counts the async engine's queries — the async engine runs cursor executions
    through its underlying ``sync_engine``, which is an ``Engine`` instance.
    """

    def __init__(self):
        self.count = 0
        self.queries = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.queries.append(statement)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_projects_query_count(async_test_client, async_test_db):
    """Verify list_projects uses optimized queries (not N+1).

    ``list_projects`` is on the async DB lane, so we seed via ``async_test_db``
    and drive it through ``async_test_client`` with a superadmin via ``_as_user``.
    ``include_all_private=true`` gives the superadmin the broad "see everything"
    surface (the default superadmin path mirrors a regular user: own private +
    public + org-scoped)."""
    admin = await _make_user(async_test_db, is_superadmin=True)

    # Create 10 test projects with varying stats
    projects = []
    for i in range(10):
        project = Project(
            id=_uid(),
            title=f"Test Project {i}",
            description=f"Project {i} description",
            created_by=admin.id,
        )
        async_test_db.add(project)
        projects.append(project)

        # Add varying number of tasks to each project
        for j in range(i + 1):
            task = Task(
                id=_uid(),
                project_id=project.id,
                inner_id=j + 1,
                data={"text": f"Task {j}"},
                is_labeled=(j % 2 == 0),  # Half completed
            )
            async_test_db.add(task)

            # Add annotation to some tasks
            if j % 3 == 0:
                async_test_db.add(
                    Annotation(
                        id=_uid(),
                        project_id=project.id,
                        task_id=task.id,
                        completed_by=admin.id,
                        result=[],
                        was_cancelled=False,
                    )
                )

    await async_test_db.commit()

    # Set up query counter (class-level — catches the async engine's queries via
    # its sync_engine).
    counter = QueryCounter()
    event.listen(Engine, "before_cursor_execute", counter)

    try:
        with _as_user(admin):
            response = await async_test_client.get(
                "/api/projects/?page=1&page_size=100&include_all_private=true"
            )
        assert response.status_code == 200, response.text

        # Verify query count
        # Expected queries:
        # 1. Count query for pagination
        # 2. Main project query with joinedloads
        # 3. Task stats batch query
        # 4. Annotation stats batch query
        # 5-6. Possible additional queries for organizations/memberships
        # 7. project_summaries batch lookup for evaluation/generation
        #    counts (added 2026-05-19 with the aggregate_summaries refactor)
        #
        # Should be <= 15 queries (not 1 + 10*3 = 31 queries). The point is "no
        # N+1," not a tight equality check; the async lane adds a couple of
        # transaction-control statements (SAVEPOINT/RELEASE) the sync lane didn't.
        assert counter.count <= 15, (
            f"Too many queries: {counter.count}. "
            f"Expected <= 15, got {counter.count}. "
            "This indicates N+1 query problem."
        )

        # Verify response contains at least our test projects
        data = response.json()
        created_ids = {p.id for p in projects}
        returned_ids = {item["id"] for item in data["items"]}
        assert created_ids.issubset(returned_ids), (
            "Missing test projects in response. "
            f"Expected {len(created_ids)} test projects, found {len(created_ids & returned_ids)}"
        )

        # Verify stats are populated correctly
        for item in data["items"]:
            assert "task_count" in item
            assert "annotation_count" in item
            assert "completed_tasks_count" in item
            assert item["task_count"] >= 0
            assert item["annotation_count"] >= 0
            assert item["completed_tasks_count"] >= 0

    finally:
        # Clean up event listener
        event.remove(Engine, "before_cursor_execute", counter)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_projects_with_zero_stats(async_test_client, async_test_db):
    """Verify projects with no tasks/annotations show 0, not NULL"""
    admin = await _make_user(async_test_db, is_superadmin=True)

    # Create project with no tasks
    async_test_db.add(
        Project(
            id=_uid(),
            title="Empty Project",
            description="Project with no tasks",
            created_by=admin.id,
        )
    )
    await async_test_db.commit()

    # Fetch project list (broad view — see all projects regardless of visibility)
    with _as_user(admin):
        response = await async_test_client.get(
            "/api/projects/?page=1&page_size=100&include_all_private=true"
        )
    assert response.status_code == 200, response.text

    data = response.json()
    empty_project = next((p for p in data["items"] if p["title"] == "Empty Project"), None)

    assert empty_project is not None
    assert empty_project["task_count"] == 0
    assert empty_project["annotation_count"] == 0
    assert empty_project["completed_tasks_count"] == 0
    assert empty_project["progress_percentage"] == 0.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_projects_progress_calculation(async_test_client, async_test_db):
    """Verify progress percentage is calculated correctly from the per-project
    stats and wired into the response.

    ``list_projects`` computes stats via ``_calculate_project_stats_batch_sync``,
    which runs ``calculate_project_stats_batch`` on a SEPARATE short-lived sync
    session (``run_in_threadpool``) — it cannot see this test's async-savepoint
    rows. The raw stat computation from tasks/annotations is covered by the
    ``test_batch_stats_*`` tests; here we pin the batch result to a known shape
    (10 tasks, 3 completed) and assert the endpoint wires it through and computes
    progress = 3/10 = 30%."""
    admin = await _make_user(async_test_db, is_superadmin=True)
    project = Project(
        id=_uid(),
        title="Progress Test Project",
        description="Testing progress calculation",
        created_by=admin.id,
    )
    async_test_db.add(project)
    await async_test_db.commit()

    stats = {
        project.id: {
            "task_count": 10,
            "completed_tasks_count": 3,
            "annotation_count": 0,
            "evaluation_count": 0,
            "evaluations_completed_count": 0,
        }
    }
    with _as_user(admin), patch(
        "routers.projects.crud._calculate_project_stats_batch_sync",
        return_value=stats,
    ):
        response = await async_test_client.get(
            "/api/projects/?page=1&page_size=100&include_all_private=true"
        )
    assert response.status_code == 200, response.text

    data = response.json()
    test_project = next((p for p in data["items"] if p["title"] == "Progress Test Project"), None)

    assert test_project is not None
    assert test_project["task_count"] == 10
    assert test_project["completed_tasks_count"] == 3
    assert test_project["progress_percentage"] == 30.0


@pytest.mark.integration
def test_batch_stats_function_directly(test_db, test_users):
    """Test the batch stats calculation function directly"""

    import uuid

    from project_models import Project, Task
    from routers.projects.helpers import calculate_project_stats_batch

    test_user = test_users[0]

    # Create 5 projects
    project_ids = []
    for i in range(5):
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            title=f"Batch Test Project {i}",
            description=f"Project {i}",
            created_by=test_user.id,
        )
        test_db.add(project)
        project_ids.append(project_id)

        # Add tasks
        for j in range(i + 1):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                inner_id=j + 1,
                data={"text": f"Task {j}"},
                is_labeled=(j == 0),  # Only first task is completed
            )
            test_db.add(task)

    test_db.commit()

    # Call batch stats function
    stats_map = calculate_project_stats_batch(test_db, project_ids)

    # Verify results
    assert len(stats_map) == 5

    for i, project_id in enumerate(project_ids):
        assert project_id in stats_map
        stats = stats_map[project_id]
        assert stats["task_count"] == i + 1
        assert stats["completed_tasks_count"] == 1  # Only first task is completed
        assert stats["annotation_count"] == 0  # No annotations


@pytest.mark.integration
def test_batch_stats_empty_list(test_db):
    """Test batch stats with empty project list"""

    from routers.projects.helpers import calculate_project_stats_batch

    stats_map = calculate_project_stats_batch(test_db, [])
    assert stats_map == {}


@pytest.mark.integration
def test_batch_stats_with_annotations(test_db, test_users):
    """Test batch stats includes annotation counts"""

    import uuid

    from project_models import Annotation, Project, Task
    from routers.projects.helpers import calculate_project_stats_batch

    test_user = test_users[0]

    # Create project
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title="Annotation Test Project",
        description="Testing annotation stats",
        created_by=test_user.id,
    )
    test_db.add(project)

    # Add tasks with annotations
    for i in range(5):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project_id,
            inner_id=i + 1,
            data={"text": f"Task {i}"},
            is_labeled=True,
        )
        test_db.add(task)

        # Add 2 annotations per task, 1 cancelled
        for j in range(2):
            annotation = Annotation(
                id=str(uuid.uuid4()),
                project_id=project_id,
                task_id=task.id,
                completed_by=test_user.id,
                result=[{"from_name": "label", "to_name": "text", "type": "choices", "value": {"choices": ["positive"]}}],
                was_cancelled=(j == 1),  # Second annotation is cancelled
            )
            test_db.add(annotation)

    test_db.commit()

    # Call batch stats function
    stats_map = calculate_project_stats_batch(test_db, [project_id])

    # Verify results
    assert project_id in stats_map
    stats = stats_map[project_id]
    assert stats["task_count"] == 5
    assert stats["completed_tasks_count"] == 5
    assert stats["annotation_count"] == 5  # Only non-cancelled annotations
