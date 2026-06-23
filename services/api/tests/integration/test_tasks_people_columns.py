"""Integration tests for the people/role columns on the project data table.

Covers the serializer additions in `routers/projects/tasks.py:list_project_tasks`:
- each assignment carries `target_type` (annotator vs Korrektur grader);
- `annotators` lists distinct Annotation.completed_by users;
- `reviewers` lists distinct Annotation.reviewed_by users;
- `generation_models` lists the distinct models that generated for the task.

`list_project_tasks` was migrated to the async DB lane
(``Depends(get_async_db)``), so these tests seed rows via ``async_test_db`` and
drive the endpoint through ``async_test_client``. ``require_user`` is overridden
to the seeded superadmin owner (the sync auth dependency can't see the async
test transaction).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation, Organization, ResponseGeneration, User
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid() -> str:
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


async def _make_user(db, *, name: str, is_superadmin: bool = False) -> User:
    u = User(
        id=_uid(),
        username=f"{name}-{_uid()[:8]}@test.com",
        email=f"{name}-{_uid()[:8]}@test.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture(scope="function")
async def people_columns_project(async_test_db):
    """A project with one task that has an annotation (annotator + reviewer),
    an annotator assignment, a grader assignment, and a generation."""
    db = async_test_db
    owner = await _make_user(db, name="Owner", is_superadmin=True)
    annotator = await _make_user(db, name="Annotator")
    reviewer = await _make_user(db, name="Reviewer")
    grader = await _make_user(db, name="Grader")

    # Seed a real Organization so the ProjectOrganization FK resolves (a bare
    # random org_id violated project_organizations_organization_id_fkey).
    org = Organization(
        id=_uid(),
        name="People Columns Org",
        slug=f"people-cols-{uuid.uuid4().hex[:8]}",
        display_name="People Columns Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()

    project = Project(
        id=_uid(),
        title="People Columns Project",
        description="Project for testing the data-table people columns",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        assignment_mode="manual",
    )
    db.add(project)
    await db.flush()

    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=owner.id,
        )
    )
    db.add(
        ProjectMember(
            id=_uid(),
            project_id=project.id,
            user_id=owner.id,
            role="admin",
            is_active=True,
        )
    )

    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=1,
        data={"text": "Task content"},
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(task)
    await db.flush()

    # An annotation that was both authored (annotator) and reviewed (reviewer).
    annotation = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=annotator.id,
        result=[{"value": "label-a"}],
        was_cancelled=False,
        reviewed_by=reviewer.id,
        review_result="approved",
    )
    db.add(annotation)
    await db.flush()

    # Annotator (whole-task) assignment + Korrektur grader (item-level) one.
    db.add(
        TaskAssignment(
            id=_uid(),
            task_id=task.id,
            user_id=annotator.id,
            assigned_by=owner.id,
            target_type="task",
            status="assigned",
        )
    )
    db.add(
        TaskAssignment(
            id=_uid(),
            task_id=task.id,
            user_id=grader.id,
            assigned_by=owner.id,
            target_type="annotation",
            target_id=annotation.id,
            status="assigned",
        )
    )

    # One generation (parent job + child run) for one model.
    parent = ResponseGeneration(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        model_id="model-x",
        created_by=owner.id,
        status="completed",
    )
    db.add(parent)
    await db.flush()
    db.add(
        Generation(
            id=_uid(),
            generation_id=parent.id,
            task_id=task.id,
            model_id="model-x",
            case_data="input",
            response_content="output",
            status="completed",
        )
    )

    await db.commit()
    return {
        "project": project,
        "task": task,
        "owner": owner,
        "annotator": annotator,
        "reviewer": reviewer,
        "grader": grader,
    }


async def _fetch_task(async_test_client, owner, project_id, task_id):
    with _as_user(owner):
        resp = await async_test_client.get(
            f"/api/projects/{project_id}/tasks?page=1&page_size=50",
        )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    match = [it for it in items if it["id"] == task_id]
    assert match, f"task {task_id} not in page"
    return match[0]


@pytest.mark.integration
class TestPeopleColumns:
    @pytest.mark.asyncio
    async def test_assignments_carry_target_type(
        self, async_test_client, people_columns_project
    ):
        p = people_columns_project
        item = await _fetch_task(
            async_test_client, p["owner"], p["project"].id, p["task"].id
        )
        target_types = {a["target_type"] for a in item["assignments"]}
        assert target_types == {"task", "annotation"}

    @pytest.mark.asyncio
    async def test_annotators_from_completed_by(
        self, async_test_client, people_columns_project
    ):
        p = people_columns_project
        item = await _fetch_task(
            async_test_client, p["owner"], p["project"].id, p["task"].id
        )
        annotator_ids = {a["id"] for a in item["annotators"]}
        assert annotator_ids == {p["annotator"].id}

    @pytest.mark.asyncio
    async def test_reviewers_from_reviewed_by(
        self, async_test_client, people_columns_project
    ):
        p = people_columns_project
        item = await _fetch_task(
            async_test_client, p["owner"], p["project"].id, p["task"].id
        )
        reviewer_ids = {r["id"] for r in item["reviewers"]}
        assert reviewer_ids == {p["reviewer"].id}

    @pytest.mark.asyncio
    async def test_generation_models_and_count(
        self, async_test_client, people_columns_project
    ):
        p = people_columns_project
        item = await _fetch_task(
            async_test_client, p["owner"], p["project"].id, p["task"].id
        )
        assert item["generation_models"] == ["model-x"]
        assert item["total_generations"] == 1
