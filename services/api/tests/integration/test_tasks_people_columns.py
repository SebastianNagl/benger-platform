"""Integration tests for the people/role columns on the project data table.

Covers the serializer additions in `routers/projects/tasks.py:list_project_tasks`:
- each assignment carries `target_type` (annotator vs Korrektur grader);
- `annotators` lists distinct Annotation.completed_by users;
- `reviewers` lists distinct Annotation.reviewed_by users;
- `generation_models` lists the distinct models that generated for the task.
"""

import uuid
from typing import List

import pytest
from sqlalchemy.orm import Session

from models import Generation, ResponseGeneration, User
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


@pytest.fixture(scope="function")
def people_columns_project(test_db: Session, test_users: List[User], test_org):
    """A project with one task that has an annotation (annotator + reviewer),
    an annotator assignment, a grader assignment, and a generation."""
    owner, annotator, reviewer, grader = test_users[:4]

    project = Project(
        id=str(uuid.uuid4()),
        title="People Columns Project",
        description="Project for testing the data-table people columns",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        assignment_mode="manual",
    )
    test_db.add(project)
    test_db.flush()

    test_db.add(
        ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=owner.id,
        )
    )
    test_db.add(
        ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=owner.id,
            role="admin",
            is_active=True,
        )
    )

    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=1,
        data={"text": "Task content"},
        created_by=owner.id,
        updated_by=owner.id,
    )
    test_db.add(task)
    test_db.flush()

    # An annotation that was both authored (annotator) and reviewed (reviewer).
    annotation = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=annotator.id,
        result=[{"value": "label-a"}],
        was_cancelled=False,
        reviewed_by=reviewer.id,
        review_result="approved",
    )
    test_db.add(annotation)
    test_db.flush()

    # Annotator (whole-task) assignment + Korrektur grader (item-level) one.
    test_db.add(
        TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=task.id,
            user_id=annotator.id,
            assigned_by=owner.id,
            target_type="task",
            status="assigned",
        )
    )
    test_db.add(
        TaskAssignment(
            id=str(uuid.uuid4()),
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
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        model_id="model-x",
        created_by=owner.id,
        status="completed",
    )
    test_db.add(parent)
    test_db.flush()
    test_db.add(
        Generation(
            id=str(uuid.uuid4()),
            generation_id=parent.id,
            task_id=task.id,
            model_id="model-x",
            case_data="input",
            response_content="output",
            status="completed",
        )
    )

    test_db.commit()
    return {
        "project": project,
        "task": task,
        "annotator": annotator,
        "reviewer": reviewer,
        "grader": grader,
    }


def _fetch_task(client, auth_headers, project_id, task_id):
    resp = client.get(
        f"/api/projects/{project_id}/tasks?page=1&page_size=50",
        headers=auth_headers["admin"],
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    match = [it for it in items if it["id"] == task_id]
    assert match, f"task {task_id} not in page"
    return match[0]


class TestPeopleColumns:
    def test_assignments_carry_target_type(
        self, client, auth_headers, people_columns_project
    ):
        p = people_columns_project
        item = _fetch_task(
            client, auth_headers, p["project"].id, p["task"].id
        )
        target_types = {a["target_type"] for a in item["assignments"]}
        assert target_types == {"task", "annotation"}

    def test_annotators_from_completed_by(
        self, client, auth_headers, people_columns_project
    ):
        p = people_columns_project
        item = _fetch_task(
            client, auth_headers, p["project"].id, p["task"].id
        )
        annotator_ids = {a["id"] for a in item["annotators"]}
        assert annotator_ids == {p["annotator"].id}

    def test_reviewers_from_reviewed_by(
        self, client, auth_headers, people_columns_project
    ):
        p = people_columns_project
        item = _fetch_task(
            client, auth_headers, p["project"].id, p["task"].id
        )
        reviewer_ids = {r["id"] for r in item["reviewers"]}
        assert reviewer_ids == {p["reviewer"].id}

    def test_generation_models_and_count(
        self, client, auth_headers, people_columns_project
    ):
        p = people_columns_project
        item = _fetch_task(
            client, auth_headers, p["project"].id, p["task"].id
        )
        assert item["generation_models"] == ["model-x"]
        assert item["total_generations"] == 1
